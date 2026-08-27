import duckdb

from ingest.loader import load_all


def _counts(db):
    con = duckdb.connect(db, read_only=True)
    try:
        landed = con.execute(
            "select sum(landed_rows), sum(quarantined_rows), sum(source_rows)"
            " from raw.run_audit").fetchone()
        statuses = [r[0] for r in con.execute("select distinct status from raw.run_audit").fetchall()]
        return landed, statuses
    finally:
        con.close()


def test_load_reconciles_and_quarantines(tmp_path):
    db = str(tmp_path / "t.duckdb")
    summaries = load_all(database=db)
    assert summaries, "no batches loaded — did make samples run?"
    (landed, quarantined, source_rows), statuses = _counts(db)
    assert statuses == ["RECONCILED"]
    assert landed + quarantined == source_rows          # the core guarantee
    assert quarantined >= 5                             # chem_scada's dirty rows
    con = duckdb.connect(db, read_only=True)
    reasons = {r[0] for r in con.execute("select distinct reason from raw.quarantine").fetchall()}
    con.close()
    assert "unparseable timestamp" in reasons
    assert "non-numeric energy value" in reasons


def test_reload_is_idempotent(tmp_path):
    db = str(tmp_path / "t.duckdb")
    load_all(database=db)
    (landed1, _, _), _ = _counts(db)
    second = load_all(database=db)                      # same files again
    assert all(s["status"].startswith("SKIPPED") for s in second)
    (landed2, _, _), _ = _counts(db)
    assert landed1 == landed2                           # nothing duplicated
