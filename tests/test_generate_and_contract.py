import duckdb

from ingest.config import load_source_configs
from ingest.contract import check_contract
from ingest.generate import _mart_daily_sql, _staging_sql
from ingest.config import load_metrics


def test_unit_normalization_rendered_into_staging_sql():
    by_name = {c["source_name"]: c for c in load_source_configs()}
    assert "energy_value * 1000.0 as energy_kwh" in _staging_sql(by_name["textile_looms"])
    assert "energy_value * 1.0 as energy_kwh" in _staging_sql(by_name["steel_meters"])
    assert "energy_value * 0.2777778 as energy_kwh" in _staging_sql(by_name["chem_scada"])


def test_metric_registry_rendered_into_mart():
    sql = _mart_daily_sql(load_metrics())
    for expr in ("sum(energy_kwh) as daily_energy_kwh", "count(*) as reading_count"):
        assert expr in sql


def _build_conforming_table(db, extra_col=False, drop_col=None, retype=None):
    con = duckdb.connect(db)
    cols = [("reading_id", "varchar"), ("facility_id", "varchar"), ("industry", "varchar"),
            ("source_name", "varchar"), ("reading_ts", "timestamp"), ("energy_kwh", "double"),
            ("pipeline_run_id", "varchar"), ("loaded_at", "timestamp")]
    if drop_col:
        cols = [c for c in cols if c[0] != drop_col]
    if retype:
        cols = [(n, retype[1]) if n == retype[0] else (n, t) for n, t in cols]
    if extra_col:
        cols.append(("quality_flag", "varchar"))
    con.execute("create table energy_readings_v1 (" +
                ", ".join(f"{n} {t}" for n, t in cols) + ")")
    con.close()


def test_contract_passes_on_conforming_model(tmp_path):
    db = str(tmp_path / "c.duckdb")
    _build_conforming_table(db)
    ok, _ = check_contract(database=db)
    assert ok


def test_contract_allows_additive_columns(tmp_path):
    db = str(tmp_path / "c.duckdb")
    _build_conforming_table(db, extra_col=True)
    ok, messages = check_contract(database=db)
    assert ok
    assert any("extra column" in m for m in messages)


def test_contract_fails_on_removed_column(tmp_path):
    db = str(tmp_path / "c.duckdb")
    _build_conforming_table(db, drop_col="energy_kwh")
    ok, messages = check_contract(database=db)
    assert not ok
    assert any("missing: energy_kwh" in m for m in messages)


def test_contract_fails_on_type_change(tmp_path):
    db = str(tmp_path / "c.duckdb")
    _build_conforming_table(db, retype=("energy_kwh", "varchar"))
    ok, messages = check_contract(database=db)
    assert not ok
    assert any("type changed" in m for m in messages)
