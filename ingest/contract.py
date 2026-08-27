"""Enforce the versioned model contract against what was actually built.

additive_only means: every column the contract names must exist with the
declared type; new columns are allowed (with a warning); removing or retyping
a contracted column fails the check — and therefore CI — before any analyst's
query breaks.
"""
from __future__ import annotations

import duckdb

from .config import load_contract
from .loader import db_path

# DuckDB information_schema type spellings → contract spellings
TYPE_ALIASES = {
    "VARCHAR": "VARCHAR",
    "DOUBLE": "DOUBLE",
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
    "BIGINT": "BIGINT",
    "DATE": "DATE",
}


def check_contract(contract_path: str = "configs/contracts/energy_readings_v1.yml",
                   database: str | None = None) -> tuple[bool, list[str]]:
    contract = load_contract(contract_path)
    model = contract["model"]
    con = duckdb.connect(database or db_path(), read_only=True)
    try:
        rows = con.execute(
            "select column_name, upper(data_type) from information_schema.columns "
            "where lower(table_name) = lower(?)",
            [model],
        ).fetchall()
    finally:
        con.close()

    messages = []
    if not rows:
        return False, [f"FAIL: model {model} was not built — nothing to check"]

    built = {name: TYPE_ALIASES.get(dtype, dtype) for name, dtype in rows}
    ok = True
    for col in contract["columns"]:
        name, want = col["name"], col["type"].upper()
        if name not in built:
            ok = False
            messages.append(f"FAIL: contracted column missing: {name} ({want})")
        elif built[name] != want:
            ok = False
            messages.append(f"FAIL: column {name} type changed: contract {want}, built {built[name]}")
        else:
            messages.append(f"ok:   {name} {want}")
    extras = set(built) - {c["name"] for c in contract["columns"]}
    for name in sorted(extras):
        messages.append(f"note: extra column not yet in contract v{contract['version']}: {name} "
                        f"(allowed — evolution is {contract['evolution']})")
    return ok, messages
