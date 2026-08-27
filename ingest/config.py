"""Load and validate source templates, the contract, and the metric registry."""
from __future__ import annotations

import glob
import os

import yaml

CANONICAL_FIELDS = {"reading_ts", "facility_id", "energy_value"}
UNIT_TO_KWH = {"kWh": 1.0, "MWh": 1000.0, "MJ": 0.2777778}
FORMATS = {"csv", "jsonl"}
REQUIRED_KEYS = {"source_name", "industry", "format", "path_glob", "energy_unit", "field_map"}


class ConfigError(Exception):
    pass


def _validate_source(cfg: dict, where: str) -> dict:
    missing = REQUIRED_KEYS - set(cfg)
    if missing:
        raise ConfigError(f"{where}: missing keys {sorted(missing)}")
    if cfg["format"] not in FORMATS:
        raise ConfigError(f"{where}: format must be one of {sorted(FORMATS)}")
    if cfg["energy_unit"] not in UNIT_TO_KWH:
        raise ConfigError(f"{where}: energy_unit must be one of {sorted(UNIT_TO_KWH)}")
    mapped = set(cfg["field_map"].values())
    if mapped != CANONICAL_FIELDS:
        raise ConfigError(
            f"{where}: field_map must map onto exactly {sorted(CANONICAL_FIELDS)}, got {sorted(mapped)}"
        )
    if not str(cfg["source_name"]).replace("_", "").isalnum():
        raise ConfigError(f"{where}: source_name must be alphanumeric/underscore")
    cfg.setdefault("validation", {})
    cfg["validation"].setdefault("required", sorted(CANONICAL_FIELDS))
    return cfg


def load_source_configs(config_dir: str = "configs/sources") -> list[dict]:
    paths = sorted(glob.glob(os.path.join(config_dir, "*.yml")))
    if not paths:
        raise ConfigError(f"no source templates found in {config_dir}")
    out = []
    for p in paths:
        with open(p) as f:
            cfg = yaml.safe_load(f)
        out.append(_validate_source(cfg, p))
    names = [c["source_name"] for c in out]
    if len(names) != len(set(names)):
        raise ConfigError(f"duplicate source_name among {names}")
    return out


def load_contract(path: str = "configs/contracts/energy_readings_v1.yml") -> dict:
    with open(path) as f:
        c = yaml.safe_load(f)
    for key in ("model", "version", "evolution", "columns"):
        if key not in c:
            raise ConfigError(f"{path}: missing key {key}")
    return c


def load_metrics(path: str = "configs/metrics.yml") -> dict:
    with open(path) as f:
        m = yaml.safe_load(f)
    for key in ("model", "grain", "metrics"):
        if key not in m:
            raise ConfigError(f"{path}: missing key {key}")
    return m
