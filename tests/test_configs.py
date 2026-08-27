import pytest

from ingest.config import ConfigError, _validate_source, load_contract, load_metrics, load_source_configs


def test_all_source_templates_are_valid():
    configs = load_source_configs()
    assert len(configs) >= 3
    assert len({c["source_name"] for c in configs}) == len(configs)


def test_field_map_must_cover_canonical_fields():
    cfg = {"source_name": "x", "industry": "i", "format": "csv", "path_glob": "g",
           "energy_unit": "kWh", "field_map": {"a": "reading_ts", "b": "facility_id"}}
    with pytest.raises(ConfigError, match="field_map"):
        _validate_source(cfg, "inline")


def test_unknown_unit_rejected():
    cfg = {"source_name": "x", "industry": "i", "format": "csv", "path_glob": "g",
           "energy_unit": "BTU",
           "field_map": {"a": "reading_ts", "b": "facility_id", "c": "energy_value"}}
    with pytest.raises(ConfigError, match="energy_unit"):
        _validate_source(cfg, "inline")


def test_contract_and_metrics_load():
    contract = load_contract()
    assert contract["evolution"] == "additive_only"
    assert {c["name"] for c in contract["columns"]} >= {"reading_id", "energy_kwh", "pipeline_run_id"}
    metrics = load_metrics()
    assert metrics["model"] == "facility_daily_v1"
    assert len(metrics["metrics"]) >= 3
