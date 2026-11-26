"""Export the versioned public contract for downstream consumers.

Writes energy_readings_v1.jsonl (one JSON object per row, only the columns the
contract names, in contract order) and prints a `total_kwh <figure>` line the
consumer must reproduce independently.

The export runs the contract check first and refuses to write anything if the
built model has drifted from the contract, so a schema change upstream stops
the chain here instead of arriving downstream as a wrong number.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime

import duckdb

from .config import load_contract
from .contract import check_contract
from .loader import db_path

DEFAULT_CONTRACT = "configs/contracts/energy_readings_v1.yml"


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def export_contract(out_path: str | None = None,
                    contract_path: str = DEFAULT_CONTRACT,
                    database: str | None = None) -> dict:
    """Write the contract rows to JSONL. Raises RuntimeError if the contract check fails."""
    ok, messages = check_contract(contract_path, database)
    if not ok:
        raise RuntimeError("contract check failed; refusing to export:\n" + "\n".join(messages))

    contract = load_contract(contract_path)
    model = contract["model"]
    columns = [c["name"] for c in contract["columns"]]
    out_path = out_path or f"{model}.jsonl"

    con = duckdb.connect(database or db_path(), read_only=True)
    try:
        schema = con.execute(
            "select table_schema from information_schema.tables "
            "where lower(table_name) = lower(?) limit 1", [model]).fetchone()[0]
        rows = con.execute(
            f'select {", ".join(chr(34) + c + chr(34) for c in columns)} '
            f'from "{schema}"."{model}" order by reading_id').fetchall()
    finally:
        con.close()

    with open(out_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({c: _jsonable(v) for c, v in zip(columns, row)}) + "\n")

    total = math.fsum(float(r[columns.index("energy_kwh")]) for r in rows)
    return {"model": model, "version": contract["version"], "path": out_path,
            "rows": len(rows), "total_kwh": total}
