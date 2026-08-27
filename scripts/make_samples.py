"""Generate deterministic synthetic sample data for the three demo sources.

All data in this repository is synthetic (fixed seed). Facility codes and
values are invented; the point is the heterogeneity of the feeds — different
formats, field names, and units — not the numbers.
"""
from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta

random.seed(7)
START = datetime(2024, 3, 1)
DAYS = 7


def hourly(day0: datetime, days: int):
    for h in range(days * 24):
        yield day0 + timedelta(hours=h)


def daily_shape(ts: datetime) -> float:
    """Factories draw more power in working hours."""
    return 0.6 + 0.4 * math.sin((ts.hour - 6) / 24 * 2 * math.pi) ** 2


def write(path: str, lines: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path} ({len(lines) - (1 if path.endswith('.csv') else 0)} data rows)")


def steel() -> None:
    """CSV, kWh, two weekly export files (two batches → shows multi-batch audit)."""
    plants = ["STL-001", "STL-002", "STL-003", "STL-004"]
    for week, day0 in enumerate([START, START + timedelta(days=DAYS)], start=1):
        rows = ["meter_ts,plant_code,kwh"]
        for ts in hourly(day0, DAYS):
            for p in plants:
                kwh = round(1200 * daily_shape(ts) * random.uniform(0.9, 1.1), 1)
                rows.append(f"{ts:%Y-%m-%d %H:%M:%S},{p},{kwh}")
        write(f"data/samples/steel_meters/steel_meters_w{week}.csv", rows)


def textile() -> None:
    """JSON lines, MWh, different field names entirely."""
    sites = ["TX-A", "TX-B", "TX-C"]
    rows = []
    for ts in hourly(START, DAYS):
        for s in sites:
            mwh = round(0.65 * daily_shape(ts) * random.uniform(0.85, 1.15), 4)
            rows.append(json.dumps({"ts": f"{ts:%Y-%m-%dT%H:%M:%S}", "site": s,
                                    "energy_mwh": mwh, "gateway": "gw-7"}))
    write("data/samples/textile_looms/textile_looms_2024-03.jsonl", rows)


def chem() -> None:
    """CSV, MJ, deliberately dirty: the quarantine demo."""
    units = ["CHM-1", "CHM-2", "CHM-3"]
    rows = ["timestamp,unit_id,energy_mj,sensor_flag"]
    for ts in hourly(START, DAYS):
        for u in units:
            mj = round(3600 * daily_shape(ts) * random.uniform(0.8, 1.2), 1)
            rows.append(f"{ts:%Y-%m-%d %H:%M:%S},{u},{mj},OK")
    # malformed rows a real SCADA export produces — these must quarantine, not crash
    rows.insert(50, "2024-03-01 12:00:00,CHM-2,-40.0,FAULT")          # negative energy
    rows.insert(120, "2024-03-02 03:00:00,,3100.5,OK")                # missing unit id
    rows.insert(200, "2024-03-03 09:00:00,CHM-1,ERR,FAULT")           # non-numeric energy
    rows.insert(300, "not-a-timestamp,CHM-3,2900.0,OK")               # bad timestamp
    rows.insert(400, "2024-03-05 18:00:00,CHM-2,9999999,OK")          # above plausible max
    write("data/samples/chem_scada/chem_scada_export.csv", rows)


if __name__ == "__main__":
    steel()
    textile()
    chem()
