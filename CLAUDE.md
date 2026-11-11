# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Finova dbt capstone (`FNV-CAP-DBT v1.5`), assignment `CAP-MG` (brokers, org units, account care). A Data Vault pipeline on PostgreSQL: kit `inbound/` files → Python loader → `landing` + `ctrl` → dbt `staging` → raw vault (`atomic`) → business vault → `asof` views → Gold (`mart`). Docs, comments and identifiers are mostly Vietnamese. The assignment spec (`.docx`/kit zip) lives outside this repo, next to it in the parent folder; set `CAP_MG_KIT_DIR` if the kit is not adjacent.

Spec IDs appear throughout code and docs (`DEC-*`, `KT-*`, `RV-*`, `AB-*`, `GD-*`, `PT-*`, `GT-*`, `TC-*`). The `docs/ky_thuat_*.md` ledgers explain each; business decisions are in `docs/decisions.md`. Check them before changing behaviour.

## Setup and commands

Python 3.12, managed with `uv`. Everything that touches the DB must run via `uv run --env-file .env` (the loader does not read `.env` itself). Copy `.env.example` → `.env` (set `FINOVA_PG_PASSWORD`, `CAP_DBNAME`, `CAP_PGPORT`; default port 5436) and `finova-dbt/profiles.example.yml` → `finova-dbt/profiles.yml` (both gitignored). See README.md for the full Windows setup notes (Python from python.org, short repo path, dbt.exe blocked → `uv run python -c "from dbt.cli.main import cli; cli()" <args>`).

```powershell
$dbt = @("--project-dir", "finova-dbt", "--profiles-dir", "finova-dbt")
uv sync
uv run --env-file .env python -m runner.init_db                 # create DB, schemas, roles, ctrl tables (idempotent; runs setup/*.sql)
uv run --env-file .env python -m runner.run                     # full schedule 2026-04-17 → 2026-05-15, one trading day at a time
uv run --env-file .env python -m runner.run --from D --to D     # a range
uv run --env-file .env python -m runner.run --full-refresh --skip-load --to D   # rebuild raw vault in one window, then BV+Gold per day
uv run --env-file .env python -m loader.load [--as-of-date D]   # landing only
uv run --env-file .env dbt build --selector cap_mg_staging @dbt # one layer (selectors in finova-dbt/selectors.yml)
uv run --env-file .env python -m runner.probes                  # SQL in evidence/probes/ → evidence/probes.csv
uv run --env-file .env python -m runner.evidence                # ~10 min; rebuilds <CAP_DBNAME>_evidence DB, 3 runs, compares counts/md5
uv run --env-file .env python -m runner.guard list|accept       # handle T-GUARD-blocked batches
```

Tests (pytest, DB-backed, dirs `tests/{loader,staging,raw,asof,gold,e2e}`):

```powershell
uv run --env-file .env pytest -q                      # loader + staging (needs staging built)
uv run --env-file .env pytest -q tests/asof           # read-only on CAP_DBNAME
uv run --env-file .env pytest -q tests/gold           # read-only; RLS via role finova_app
uv run --env-file .env pytest -q tests/gold/<file>.py::<test_name>   # single test
$env:RUN_PT_FULL = "1"; uv run --env-file .env pytest -q tests       # full suite incl. PT-FULL/PT-IDEMP/T-GUARD on a fresh <CAP_DBNAME>_ptfull DB
uv run --env-file .env dbt test --select "test_type:unit" @dbt --vars '{lo_ts: "-infinity", hi_ts: "2026-05-15T23:59:59+07:00"}'   # dbt unit tests; need raw tables to exist
```

Single dbt model/test: `dbt build --select <model> @dbt --vars '{lo_ts: ..., hi_ts: ..., as_of_date: ...}'`. Raw-vault models require `lo_ts`/`hi_ts` vars (enforced by `dv_window()` at execute time, not parse time). Selector `cap_mg_all` builds every layer for one day but excludes unit tests.

## Architecture

**Orchestration is Python, not dbt alone.** `runner/run.py` simulates the daily schedule. For each trading day D (from `seeds/ref_calendar.csv`):
1. Loader loads every un-loaded batch with `available_ts <= cutoff(D)` (cutoff = 00:00 of D+1, Vietnam time).
2. Window `(lo_ts, hi_ts]` and `max_log_id` come from `ctrl.batch_run` / `ctrl.batch_log`; a RUNNING row is written.
3. **T-GUARD**: a newly loaded batch whose `ingested_ts <= lo_ts` would never fall in any future window, so the run stops as `BLOCKED_BY_GUARD`. Resolve with a full refresh (default) or `runner.guard accept`.
4. dbt: `cap_mg_staging` (rejected-row counts written to `ctrl.reject_count`), then `cap_mg_raw` with the window vars, then BV, then Gold for D. `asof` views are only (re)built on full refresh or when missing.
5. SUCCESS / FAILED recorded in `ctrl.batch_run`; the next window starts from the last SUCCESS `hi_ts`. All errors/warnings from loader, runner and dbt go to `ctrl.error_log` (no log files; query it first when debugging).

**Layers (`finova-dbt/models/`)**
- `staging/`: views, one per source (`stg_flex__{broker,nav,reaflnk,regrp}`, `stg_manual__kpi`, `stg_finova_app__events`) plus a `__rejected` view each. Logic lives in macros under `macros/staging/` (models are thin) and is driven by source contracts in `contracts/*.yml`.
- `atomic/raw/`: Data Vault hubs/links/sats/effectivity-sats (`esat_*`)/status-tracking (`sts_*`)/non-historized link (`nhl_*`), all incremental, built by the templates in `macros/raw/dv_load.sql`. They read staging only through `dv_window()` and `{{ this }}`, so rerunning an old window adds no rows (idempotent, PT-IDEMP). Deliberate deviation from the spec's sample SQL: first row in a window is compared with the vault version immediately *before* its `ingested_ts`, not the latest.
- `atomic/bv/`: business vault — PIT and bridge tables (`pit_*_daily`, `bridge_*`), one build per trading day.
- `asof/`: views that read `finova.asof_date` / `finova.asof_cutoff` session GUCs (error if unset); this is how "what was known at cutoff(D)" is answered, including back-dated corrections.
- `gold/`: `mart` tables (`dim_*`, `met_broker_daily`, `dq_mg_daily`, `sec_visibility_daily`) per `as_of_date`. Row-level security: role `finova_app` sees only rows in the viewer's scope from `seed ref_org_roles`, set via `set_config('finova.viewer_id', ...)`; no viewer set → zero rows.

`macros/finova_macros.sql` overrides `generate_schema_name` (custom schema used verbatim, no target-schema prefix). Selectors are layered with tag excludes so each step does not run tests for layers not yet built (tags `staging`, `dv_raw`, `dv_bv`, `gold`). Custom generic tests are in `tests/generic/dv_tests.sql`; singular tests in `finova-dbt/tests/<layer>/`; `tests/khung` holds known-answer hash tests.

**Business thresholds** are only in `customers/ctcka/thresholds.yaml` (single source, INV-M6) — don't hardcode them in SQL.

**Evidence** (`evidence/`) is committed output of `runner.run --evidence-dir`, `runner.probes` and `runner.evidence` (graded deliverable, D-BANGCHUNG); regenerate rather than hand-edit.

## Gotchas

- Staging is views (always idempotent); raw/BV/Gold are tables, and a raw full refresh cascades-drops dependent `asof` views.
- Loader dedup: same `batch_id` → `SKIPPED_DUP/ALREADY_LOADED`; identical content to the table's latest LOADED batch → `DUP_CONTENT`; `REJECTED_BATCH` is not auto-retried.
- Timestamps are written to `ctrl` as ISO-8601 UTC strings; `-infinity` must stay literal (psycopg2 converts it to `datetime.min`).
- Expected baseline on kit data: 63 LOADED batches, 41 SKIPPED_DUP, 19 successful daily runs, `RUN_PT_FULL=1 pytest -q tests` → 61 passed; known WARNs are DQ-MOCOI (staging) and GT-HUB-NOMASTER (raw).
