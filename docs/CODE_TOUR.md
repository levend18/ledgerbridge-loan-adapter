# Code Tour: Follow One Synchronization

1. **`frontend/src/features/sync/SyncView.tsx`** sends the user's sync request.
   `frontend/src/api.ts` attaches the session JWT.
2. **`api/config/urls.py` → `api/views.py::Sync.post`** resolves identity from
   JWT membership, rejects a conflicting tenant, creates a PENDING run and
   enqueues its UUID. A concurrent active run produces 409.
3. **`workers/tasks.py::sync` → `workers/runtime.py::execute`** reads the run,
   creates temporary storage and composes adapters through `services`. Duration,
   GC duration and process peak RSS are recorded here. Each Celery child handles
   one task, allowing comparable memory measurements.
4. **`adapter/ingestion/application/__init__.py::SyncDatasetUseCase.execute`**
   owns orchestration. It acquires the unit lock and skips an unchanged non-force
   request before downloading or processing anything.
5. **`adapter/ingestion/infrastructure/bank.py::HttpBankGateway`** reads metadata
   and streams credit/plan NDJSON to files. SHA-256, row counts and a second
   metadata read detect changed or mixed source snapshots.
6. **`adapter/quality/infrastructure/processor.py::RustProcessor`** passes schema
   contracts and DB code mappings to the native extension. **`pipeline.rs`**
   samples bounded input, validates rows and writes COPY output. **`domain.rs`**
   implements pure decimal/date/code normalization; **`profile.rs`** accumulates
   bounded summaries. Raw/canonical evidence is retained for the first 1,000 issues.
7. **`adapter/warehouse/infrastructure/postgres.py::PostgresWarehouse.load`**
   adds tenant/batch metadata and streams bounded COPY blocks with socket
   backpressure. A restricted maintenance function refreshes partition statistics.
   `validate` performs duplicate, orphan and plan-count checks in PostgreSQL.
8. **`adapter/quality` exports `SeverityPolicy`**. Rejection deletes only the
   new batch; the published pointer remains unchanged. `PostgresRuns.save`
   persists state, counters and detailed evidence.
9. **`adapter/profiling/infrastructure/postgres.py::PostgresProfiles.prepare`**
   completes exact categorical summaries for columns whose Rust map exceeded
   1,000 values. SQL groups the unpublished tenant/batch and returns only ten
   rows per column; this occurs before the publication transaction.
   **`PostgresWarehouse.publish`** and
   **`adapter/profiling/infrastructure/postgres.py::PostgresProfiles.save`**
   share one publish transaction. `collect_garbage` removes obsolete unit rows;
   only then does the run become SUCCEEDED.
10. **`api/views.py::Data` → `adapter/warehouse/infrastructure/queries.py::ReaderQueries`**
    reads with app_reader, transaction-local tenant configuration and READ ONLY
    REPEATABLE READ. Cursors are tied to the snapshot identity.
11. **`api/views.py::Profiling` → `adapter/profiling/infrastructure/queries.py`**
    exposes only current profiles. UI profile cards/charts and issue tables use
    the same published state and retained validation evidence.
12. The scheduled path starts at **`workers/tasks.py::poll`** and
    **`CheckForUpdatesUseCase.execute`**. `Scheduler.enqueue` creates work only
    for changed source versions, then reuses the same synchronization use case.

## Suggested reading order

Start with `adapter/shared` and ingestion domain values, then the application
use case and its Protocol ports. Read SQL under warehouse infrastructure and
`api/storage/migrations/` before inspecting role-dependent queries.

`tests/integration/test_sync_pipeline.py` proves replacement/rejection/PATCH;
`test_api.py` covers authentication, isolation and concurrent publication;
`test_profiles.py` compares columns to SQL; `test_poll.py` uses the real scheduler.
`tests/verification/` maps these to V-IDs. `tools/verify.sh` separates execution
phases, and `tools/verification_report.py` turns JUnit evidence into the report.
