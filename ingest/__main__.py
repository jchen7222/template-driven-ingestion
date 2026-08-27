"""CLI: python -m ingest {generate|load|check|audit}"""
from __future__ import annotations

import sys

import duckdb


def _cmd_generate() -> int:
    from .generate import generate_all
    for path in generate_all():
        print(f"generated {path}")
    return 0


def _cmd_load() -> int:
    from .loader import load_all
    failures = 0
    for s in load_all():
        if "rows" in s:
            print(f"{s['source']:<15} {s['file']:<32} rows={s['rows']:>6} "
                  f"landed={s['landed']:>6} quarantined={s['quarantined']:>4}  {s['status']}")
        else:
            print(f"{s['source']:<15} {s['file']:<32} {s['status']}")
        if s["status"] == "MISMATCH":
            failures += 1
    if failures:
        print(f"\n{failures} batch(es) failed reconciliation", file=sys.stderr)
        return 1
    return 0


def _cmd_check() -> int:
    from .contract import check_contract
    ok, messages = check_contract()
    for m in messages:
        print(m)
    print("\ncontract:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _cmd_audit() -> int:
    from .loader import db_path
    con = duckdb.connect(db_path(), read_only=True)
    print(con.execute(
        "select pipeline_run_id, source_name, file_name, source_rows, landed_rows,"
        " quarantined_rows, status, loaded_at from raw.run_audit order by loaded_at, source_name"
    ).df().to_string(index=False))
    n = con.execute("select count(*) from raw.quarantine").fetchone()[0]
    if n:
        print(f"\nquarantined rows: {n} (reasons below)")
        print(con.execute(
            "select source_name, reason, count(*) as rows from raw.quarantine"
            " group by 1, 2 order by 1, 3 desc").df().to_string(index=False))
    con.close()
    return 0


def main() -> int:
    commands = {"generate": _cmd_generate, "load": _cmd_load,
                "check": _cmd_check, "audit": _cmd_audit}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(f"usage: python -m ingest {{{'|'.join(commands)}}}", file=sys.stderr)
        return 2
    return commands[sys.argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main())
