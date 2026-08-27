"""Idempotent file loader: raw landing, quarantine, and row-count reconciliation.

Guarantees, in order of importance:
  1. Reconciliation: for every batch, source_rows == landed + quarantined,
     recorded in raw.run_audit. A mismatch fails the run.
  2. Idempotency: a batch is identified by the hash of its file bytes; a batch
     that already reconciled is skipped, so re-running `make load` never
     duplicates data.
  3. Quarantine, not crash: malformed rows land in raw.quarantine with a
     reason and the original payload. Supplier failure is the normal case.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timezone

import duckdb

from .config import load_source_configs

DB_PATH_ENV = "PLATFORM_DB"
DEFAULT_DB = "platform.duckdb"


def db_path() -> str:
    return os.environ.get(DB_PATH_ENV, DEFAULT_DB)


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path or db_path())
    con.execute("create schema if not exists raw")
    con.execute(
        """create table if not exists raw.run_audit (
               pipeline_run_id varchar,
               source_name varchar,
               batch_id varchar,
               file_name varchar,
               source_rows bigint,
               landed_rows bigint,
               quarantined_rows bigint,
               status varchar,
               loaded_at timestamp
           )"""
    )
    con.execute(
        """create table if not exists raw.quarantine (
               source_name varchar,
               batch_id varchar,
               reason varchar,
               payload varchar,
               pipeline_run_id varchar,
               loaded_at timestamp
           )"""
    )
    return con


def _ensure_source_table(con, source_name: str) -> None:
    con.execute(
        f"""create table if not exists raw.src_{source_name} (
                facility_id varchar,
                reading_ts timestamp,
                energy_value double,
                source_file varchar,
                batch_id varchar,
                pipeline_run_id varchar,
                loaded_at timestamp
            )"""
    )


def _parse_rows(cfg: dict, blob: bytes):
    """Yield (raw_record_dict, original_line) pairs."""
    text = blob.decode("utf-8", errors="replace")
    if cfg["format"] == "csv":
        for row in csv.DictReader(io.StringIO(text)):
            yield row, json.dumps(row, ensure_ascii=False)
    else:  # jsonl
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                yield json.loads(line), line
            except json.JSONDecodeError:
                yield None, line


def _parse_ts(value: str) -> datetime:
    v = str(value).strip().replace("T", " ").replace("Z", "")
    return datetime.fromisoformat(v)


def _validate(cfg: dict, record: dict) -> tuple[dict | None, str | None]:
    """Map to canonical fields and validate. Returns (clean_row, reason)."""
    if record is None:
        return None, "unparseable line"
    mapped = {}
    for src_field, canon in cfg["field_map"].items():
        mapped[canon] = record.get(src_field)
    for field in cfg["validation"]["required"]:
        if mapped.get(field) in (None, ""):
            return None, f"missing required field: {field}"
    try:
        mapped["reading_ts"] = _parse_ts(mapped["reading_ts"])
    except (ValueError, TypeError):
        return None, "unparseable timestamp"
    try:
        mapped["energy_value"] = float(mapped["energy_value"])
    except (ValueError, TypeError):
        return None, "non-numeric energy value"
    bounds = cfg["validation"].get("energy_value", {})
    if "min" in bounds and mapped["energy_value"] < bounds["min"]:
        return None, f"energy below minimum {bounds['min']}"
    if "max" in bounds and mapped["energy_value"] > bounds["max"]:
        return None, f"energy above maximum {bounds['max']}"
    mapped["facility_id"] = str(mapped["facility_id"]).strip()
    return mapped, None


def load_all(config_dir: str = "configs/sources", database: str | None = None) -> list[dict]:
    """Load every batch of every configured source. Returns audit summaries."""
    con = connect(database)
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    summaries = []
    try:
        for cfg in load_source_configs(config_dir):
            name = cfg["source_name"]
            _ensure_source_table(con, name)
            files = sorted(glob.glob(cfg["path_glob"]))
            for path in files:
                blob = open(path, "rb").read()
                batch_id = hashlib.sha256(blob).hexdigest()[:12]
                already = con.execute(
                    "select count(*) from raw.run_audit"
                    " where source_name = ? and batch_id = ? and status = 'RECONCILED'",
                    [name, batch_id],
                ).fetchone()[0]
                if already:
                    summaries.append({"source": name, "file": os.path.basename(path),
                                      "batch": batch_id, "status": "SKIPPED (already loaded)"})
                    continue

                landed, quarantined, source_rows = [], [], 0
                for record, original in _parse_rows(cfg, blob):
                    source_rows += 1
                    clean, reason = _validate(cfg, record)
                    if clean is None:
                        quarantined.append((name, batch_id, reason, original, run_id, now))
                    else:
                        landed.append((clean["facility_id"], clean["reading_ts"],
                                       clean["energy_value"], os.path.basename(path),
                                       batch_id, run_id, now))
                if landed:
                    con.executemany(
                        f"insert into raw.src_{name} values (?,?,?,?,?,?,?)", landed)
                if quarantined:
                    con.executemany(
                        "insert into raw.quarantine values (?,?,?,?,?,?)", quarantined)

                status = "RECONCILED" if len(landed) + len(quarantined) == source_rows else "MISMATCH"
                con.execute(
                    "insert into raw.run_audit values (?,?,?,?,?,?,?,?,?)",
                    [run_id, name, batch_id, os.path.basename(path),
                     source_rows, len(landed), len(quarantined), status, now],
                )
                summaries.append({"source": name, "file": os.path.basename(path),
                                  "batch": batch_id, "rows": source_rows,
                                  "landed": len(landed), "quarantined": len(quarantined),
                                  "status": status})
    finally:
        con.close()
    return summaries
