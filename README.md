# template-driven-ingestion

**Onboard a new data source by writing a YAML template, not a pipeline.**

![ci](https://github.com/jchen7222/template-driven-ingestion/actions/workflows/ci.yml/badge.svg)

A configuration-over-code ingestion framework with a governed, versioned analytics layer.
Every data source is described by one small YAML template; the framework generates the dbt
staging model, normalizes units, enforces a public model contract, and guarantees that every
load reconciles — `source_rows == landed + quarantined`, recorded batch by batch.

Runs end-to-end on DuckDB with zero setup (`make all`). The dbt models use only portable SQL,
so the included Snowflake profile stub runs the same project unchanged.

## Why this exists

I built the production version of this pattern at a government information center: energy
telemetry from 1,000+ industrial facilities across 24 industries, where every industry's
feed had different formats, field names, and units. Writing custom pipeline code per source
made onboarding a two-day task; moving the differences into templates made it a 30-minute
task, and gave analysts one stable, versioned schema to query. That code is proprietary,
so this repository is a from-scratch reimplementation of the architecture on synthetic data
(three deliberately heterogeneous demo sources — CSV in kWh, JSON lines in MWh, and a dirty
SCADA export in MJ).

## Architecture

```
configs/sources/*.yml           configs/metrics.yml        configs/contracts/*.yml
   (one per source)             (metrics defined once)     (public schema, versioned)
        │                              │                           │
        ▼  make generate               ▼                           │
┌──────────────────────────────────────────────────┐               │
│ generated dbt models                             │               │
│   staging/stg_<source>.sql   (map, cast, → kWh)  │               │
│   marts/energy_readings_v1   (union, public)     │               │
│   marts/facility_daily_v1    (metric registry)   │               │
└──────────────────────────────────────────────────┘               │
        ▲                                                          │
        │  make load                    make build                 ▼  make check
data/ ──┴─► raw.src_<source>  ────────► dbt build ────────► contract enforcement
            raw.quarantine   (bad rows + reason)            (additive-only, fails CI
            raw.run_audit    (batch reconciliation)          on removal or retype)
```

## Quickstart

```bash
pip install -r requirements.txt
make all        # samples → generate → load → dbt build → contract check → pytest
make audit      # per-batch reconciliation report + quarantine reasons
```

`make all` output ends with dbt `PASS=25`, `contract: PASS`, and a green pytest run.
The loader prints one reconciliation line per batch:

```
chem_scada      chem_scada_export.csv        rows=  509 landed=  504 quarantined=   5  RECONCILED
steel_meters    steel_meters_w1.csv          rows=  672 landed=  672 quarantined=   0  RECONCILED
```

## Onboarding a new source (the whole point)

Three steps, no Python:

**1. Copy a template** into `configs/sources/`, e.g. `paper_mills.yml`:

```yaml
source_name: paper_mills
industry: paper
format: csv
path_glob: data/samples/paper_mills/*.csv
energy_unit: MWh               # normalized to kWh in the generated model
field_map:                     # source column -> canonical field
  time_of_reading: reading_ts
  mill: facility_id
  consumption: energy_value
validation:
  required: [reading_ts, facility_id, energy_value]
  energy_value: {min: 0, max: 500}
```

**2. `make generate`** — the framework writes `stg_paper_mills.sql` (with unit conversion
and schema tests) and adds the source to the public union model.

**3. `make load build check`** — data lands, models build, and the new source is part of
`energy_readings_v1` without any change to downstream queries.

## Guarantees

**Reconciliation, always.** Every batch's audit row asserts
`source_rows == landed + quarantined`. A mismatch fails the run. Nothing is silently dropped.

**Quarantine, not crashes.** Supplier failure is the normal case: rows with missing ids,
negative or non-numeric energy, or unparseable timestamps land in `raw.quarantine` with a
reason and the original payload. The demo chem feed ships with five such rows on purpose.

**Idempotent loads.** A batch is identified by the hash of its file bytes. Re-running
`make load` skips reconciled batches — loading twice never duplicates a row.

**A versioned public contract.** `energy_readings_v1` is governed by
`configs/contracts/energy_readings_v1.yml` with `evolution: additive_only`: new columns are
fine; removing or retyping a contracted column fails `make check` (and CI) before any
analyst's query breaks. Tests prove both directions.

**Lineage on every row.** Each row carries `pipeline_run_id`; `raw.run_audit` maps any
figure in any mart back to the file, batch, and load that produced it.

**Metrics defined once.** `configs/metrics.yml` is a small calculated-metric registry:
each metric (name, description, expression) is rendered into `facility_daily_v1` by the
generator, so "daily energy" has exactly one definition.

## Snowflake

Local and CI runs use DuckDB (free, in-process). The generated SQL sticks to portable
functions (`md5`, `concat_ws`, `date_trunc`), so pointing the commented `snowflake` target
in `warehouse/profiles.yml` at a real account runs the identical project — which mirrors
the original platform, where the warehouse was Snowflake.

## Layout

```
configs/
  sources/*.yml        source templates — the only thing you edit to onboard a source
  contracts/*.yml      versioned public schema, additive-only
  metrics.yml          calculated-metric registry
ingest/                loader (reconcile/quarantine/idempotency), generator, contract check
warehouse/             dbt project; models/ are generated, committed for browsability
scripts/make_samples.py  deterministic synthetic demo data (seed=7)
tests/                 pytest: configs, loader guarantees, generator output, contract logic
.github/workflows/ci.yml  the same make targets, on every push
```

All sample data is synthetic. MIT license.
