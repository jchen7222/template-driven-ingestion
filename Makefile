# Run everything from the repository root.
.PHONY: all samples generate load build check audit test clean

all: samples generate load build check test

samples:
	python3 scripts/make_samples.py

generate:
	python3 -m ingest generate

load:
	python3 -m ingest load

build:
	cd warehouse && dbt build --profiles-dir . --no-version-check

check:
	python3 -m ingest check

audit:
	python3 -m ingest audit

test:
	python3 -m pytest -q

clean:
	rm -f platform.duckdb
	rm -rf warehouse/target warehouse/logs logs
