# LedgerBridge — Technical Design

This document defines architecture, contracts, decisions and acceptance scope.
Implementation changes must keep this design and `VERIFICATION.md` consistent.
ADR revisions record the reason for changes; passing tests must not be obtained
by weakening the contracts. Section numbers remain stable for existing links.

## 0. Scope and priorities

**MUST:** bank simulator; three isolated tenants; separate retail/commercial
credit schemas; field and cross-file validation; normalization; atomic full
replacement; 200 MB memory measurement; profiling dashboard; JWT; Docker-only
setup; documentation and CI. Complete MUST before optional work.

**SHOULD:** API key authentication, concurrent-request 409 handling, crashed-worker
reaper, fault-injection manifest, automated Playwright smoke tests, rate limits.
409 protection is implemented; this does not imply the whole SHOULD scope passes.

**COULD:** internal analyst access with audit log, archived snapshots, approximate
percentiles and webhooks. Do not add speculative abstractions or features.

## 1. Problem and synchronization unit

Read large, dirty loan portfolios from a simulated external bank, validate and
normalize them, atomically replace the published warehouse data, and expose the
result through authenticated REST endpoints and a web portal.

The synchronization unit is `(tenant_id, loan_type)`. Its `credit` and
`payment_plan` datasets are validated and published together. Required core
technologies are Django, Python, Rust and PostgreSQL.

## 2. Requirement traceability

| ID | Requirement | Design | Evidence |
|---|---|---|---|
| R1 | Bank upload, update, JSON endpoints, storage | §8, ADR-07 | V-20, V-21 |
| R2 | Three tenants and isolation | §9, ADR-03 | V-03–V-05 |
| R3 | Separate retail and commercial portfolios | §7, §13 | V-06 |
| R4 | Field and cross-file validation | §11 | V-09, V-10 |
| R5 | Dates, rates, categories, dirty values | §12 | V-11 |
| R6 | Atomic replacement; rejected data preserves old snapshot | §14 | V-07, V-08, V-15 |
| R7 | Memory-efficient 200 MB processing | §15 | V-17 |
| R8 | Upload, sync, data, profiles, issues UI | §19 | V-22 |
| R9 | Authentication and tenant authorization | §18 | V-01, V-02, V-04 |
| R10 | Profiling and dashboard | §16 | V-18 |
| R11 | Sync, data and profiling API | §17 | V-06, V-18 |
| R12 | Periodic source-version checks | §10 | V-12–V-14 |
| R13 | README and architecture documentation | §23 | V-23 |

The original assignment was reviewed on 22 October 2026. Its eleven numbered
requirements map to R1–R11; periodic synchronization and documentation map to
R12–R13. JWT satisfies the requested JWT-or-API-key choice. A crashed-worker
reaper, rate limiting and an automated Playwright suite are our optional scope,
not missing requirements from that assignment. The source document and contact
information remain outside the repository.

The audit identified one functional gap: exact categorical statistics were
unavailable above 1,000 values. The profiling revision in §16 closes that gap;
V-18 now covers overflowed categories for both loan types and payment plans.
Authentication excludes only bootstrap token issuance and explicitly public
health/schema/documentation routes; all portfolio and operation routes require
identity. The bank simulator has its own tenant-bound key.

## 3. Supplied data and design implications

The supplied source analysis describes 25,430 retail credits (27 columns),
269,442 retail plan rows (14 columns), 4,440 commercial credits (32 columns),
and 25,070 commercial plan rows (14 columns). The files are UTF-8, semicolon
separated, with headers. They remain read-only under ignored `data/`; tests and
screenshots use generated data. Source inspection is limited to `head`.

Mixed date formats require real normalization. Retail nominal interest is in
percent; commercial default probability is fractional. Zero values must not
bias rate-unit detection. Commercial interest period is an open business question.
The source analysis reports 127 retail interest values of 100.00; they are
warnings, not automatically corrected. Installment-count inconsistencies and
outstanding balances exceeding original amounts are common enough to warrant
WARNING rather than whole-portfolio rejection. Closing dates are nullable.
The input has no tenant column; deterministic seeding assigns one.

## 4. Deployment

React/Vite connects to Django/DRF with JWT and to the separate FastAPI bank
simulator with a demo bank key. Django enqueues work in Redis. Celery worker and
beat perform source checks and synchronization. Rust is a native Python
extension. PostgreSQL contains `ref`, `ops` and `dwh`; the bank uses SQLite WAL.

Host ports bind to loopback: frontend 5173, API 8000, bank 8001. Database and Redis
remain on the compose network. Postgres, Redis, bank, API and frontend have
health checks; worker behavior is verified with live acceptance tests. Builds
run inside multi-stage Docker images on arm64 and amd64. Host prerequisites are
Docker/Compose and make. See `Architecture.md` for diagrams.

## 5. Code architecture (ADR-10)

The code is a modular monolith with ingestion, quality, warehouse, profiling and
shared modules. Presentation lives in `api/` and `workers/`.

| Layer | Responsibility | Boundary |
|---|---|---|
| Presentation | HTTP identity, serialization, task entry points | No domain policy |
| Application | Use-case orchestration and unit-of-work boundary | No framework or I/O library imports |
| Domain | Values, state machine, severity policy, Protocol ports | No I/O |
| Infrastructure | HTTP, Rust, PostgreSQL adapters | Implements domain ports |

Dependency direction is presentation → application → domain ← infrastructure.
`workers/runtime.py::services` is the worker composition root. The API creates
reader query services and performs narrowly scoped run-enqueue bookkeeping.
The application owns the publish transaction boundary. Read queries bypass
entity reconstruction and use optimized tenant-scoped SQL.

`shared` owns pure DTOs such as Issue, ValidationReport and ProcessReport.
`ingestion` owns orchestration and runs; `quality` owns normalization and policy;
`warehouse` owns facts, cross-file checks and snapshots; `profiling` owns stored
column summaries. Quality, warehouse and profiling do not import one another.
Module exports define the application-facing ports. Django ORM is used for
identity; DWH operations use psycopg. Django migrations are the single migration
mechanism, including module-owned SQL via RunSQL.

`.importlinter` enforces layer order, framework-free `adapter/`, I/O-free domains
and module independence. External package checking is enabled. Contracts must
not be relaxed to make CI pass. Strict mypy covers `adapter/`.

Rust lives in `adapter/quality/engine/src/`: `domain.rs`, `schema.rs`,
`pipeline.rs`, `profile.rs` and the PyO3 entry point in `lib.rs`. Only the quality
infrastructure adapter imports the extension. Pure normalizers have property tests.

## 6. Architecture decisions

### ADR-01 — PyO3 and maturin

A native extension avoids an extra network hop and service authentication. Rust
handles parsing, normalization, validation and profiling; Python handles I/O and
transactions. A separate Rust service is unnecessary deployment complexity;
a CLI would require an additional process-output protocol. A DataFrame-sized
in-memory representation is unsuitable for the memory target.

**M3 revision:** default_probability belongs to commercial credit. Schemas retain
all original column names. **M7 revision:** money and rates are quantized to DWH
precision before COPY and profiling, avoiding statistics for values that storage
would round differently. Midpoint rounding is away from zero. Integer and
NUMERIC overflow become field errors, not uncontrolled COPY failures.

### ADR-02 — PostgreSQL warehouse

Multi-table transactions and RLS satisfy the two critical guarantees: atomic
replacement and isolation. A column store would introduce another component
without improving the current workload's correctness. Larger future analytical
workloads could replicate the DWH through ELT; this is not implemented.

### ADR-03 — Shared schema, static partitions and RLS

Database-per-tenant offers stronger operational separation but multiplies
provisioning. Schema-per-tenant multiplies migrations. Shared tables with tenant
partitions and reader RLS provide a small operational footprint and fail-closed
reads. Reader access to child partitions is forbidden. Security-invoker views
preserve caller policies. Reader identity is never a table owner or BYPASSRLS role.

**M1/M6 revisions:** paired reads use READ ONLY REPEATABLE READ and transaction-local
tenant configuration. Independent HTTP requests may observe different committed
snapshots. Cursors contain their snapshot identity and reject stale continuation.
Django receives only narrow tenant-filtered run creation/failure permissions.

### ADR-04 — Snapshot pointer publication

COPY and validation produce an invisible batch. A short transaction changes the
unit's pointer, stores profiles and records PUBLISHING. GC removes old rows;
SUCCEEDED is recorded only after GC, so terminal physical counts are meaningful.
If GC fails after publication, the published batch is not deleted. A subsequent
sync can retry idempotent cleanup.

DELETE/INSERT holds heavy work in the publication transaction. TRUNCATE cannot
isolate a single tenant and takes broad locks. Partition attach/detach introduces
DDL and parent-table lock coordination. Pointer publication avoids these costs;
DELETE bloat remains a deliberate trade-off handled by autovacuum.

**M9 revision:** large batches need fresh statistics before SQL validation.
PostgreSQL 16 requires table-owner privileges for ANALYZE. Instead of granting
ownership to the worker, `ops.analyze_partition` is SECURITY DEFINER, has a fixed
`pg_catalog` search path and permits only nine static CASE branches. Only
app_writer may execute it; unknown inputs and reader/Django calls are rejected.
No user-provided SQL identifiers are interpolated.

### ADR-05 — Metadata polling

The source contract provides version and SHA-256. Beat checks six units instead
of repeatedly downloading unchanged data. Webhooks are optional future work.
Rejected versions differ from the current published version and may be retried
by later polls; a rejected-version suppression policy is not implemented.

### ADR-06 — Celery and Redis

POST sync returns 202. Celery provides scheduling and retry/backoff. A session
advisory lock and an active-run unique constraint prevent duplicate publication.
Network/integrity failures retry up to five times. Each retry creates a new run
and preserves the previous FAILED attempt. Validation rejection is not a task retry.
A fresh child per task makes peak RSS measurements comparable.

### ADR-07 — Separate bank simulator

FastAPI and SQLite form a distinct process, database and authentication boundary.
The adapter knows only its HTTP contract. The bank preserves raw strings, including
dirty values. SQLite rows have a surrogate ID and a nonunique business key so
PUT duplicates survive to the adapter's validation stage. PATCH replaces matching
keys. Hashes and streams use stable ID ordering and compact UTF-8 NDJSON.

### ADR-08 — React, Vite and TypeScript

TanStack Query manages server state and polling; TanStack Table supplies table
models with windowed rendering; ECharts supplies category charts. Feature folders
match authentication, bank portal, synchronization, data, profiling and issues.

### ADR-09 — Three severity levels

ERROR means the value cannot safely be used. WARNING means suspicious but usable.
CORRECTED preserves raw and canonical evidence. The default ERROR_TOLERANCE is
zero; schema mismatch always rejects. Common business inconsistencies are not
silently repaired or promoted to errors without business approval.

### ADR-10 — Enforced modular monolith

A single team and multi-table transactions do not justify microservices.
Protocols allow fake adapters in unit tests; composition stays at the boundary.
The initial import-linter configuration was corrected to `root_package` and
external-package scanning; constraints were not weakened.

### ADR-11 — Decimal business values, floating-point statistics

Python Decimal, rust_decimal and NUMERIC represent amounts and rates. Welford
mean/stddev use f64 and are labeled as statistics. Do not use float for financial
normalization or storage. SQL equivalence tests use relative tolerance 1e-9 for
statistics and exact comparisons for other results.

### ADR-12 — Exact profiles with bounded worker memory

**Requirement-audit revision (22 October 2026):** the supplied task requires exact
categorical distinct counts and modes without a cardinality exception. Keep the
Rust map bounded at 1,000 entries, then complete overflowed columns through SQL
before publication. This preserves bounded worker memory and the short atomic
pointer/profile transaction; aggregation failure leaves the old snapshot intact.

## 7. Dataset contract

Both loan types have `credit` keyed by loan_account_number and `payment_plan`
keyed by (loan_account_number, installment_number). Retail and commercial credit
schemas differ; plan schemas match. YAML contracts under `adapter/quality/schemas`
are authoritative for columns, types, required fields, ranges, patterns and rules.
Loan IDs use six digits; benchmark generation must retain that pattern.

| Type | Processing | Storage |
|---|---|---|
| string/code | String | TEXT |
| int | checked integer | INTEGER |
| money | Decimal | NUMERIC(18,2) |
| rate | Decimal fraction | NUMERIC(12,8) |
| probability | Decimal fraction | schema-defined NUMERIC |
| date | NaiveDate | DATE |
| bool_code | bool | BOOLEAN |

Rules are registered functions, not a generic expression engine. DDL is explicit;
tests compare schema columns with database columns rather than generating DDL.

## 8. Bank HTTP contract

Base: `/v1/tenants/{tenant}/loans/{loan_type}`.

| Method | Suffix | Behavior |
|---|---|---|
| PUT | `/{dataset}` | Stream CSV to disk, replace dataset, increment unit version |
| PATCH | `/{dataset}` | Upsert business keys, increment version |
| GET | `/meta` | Version, update timestamp, per-dataset digest and row count |
| GET | `/{dataset}/records` | Chunked application/x-ndjson, raw strings |
| GET | `/{dataset}/records?format=json&cursor=&limit=` | Keyset JSON pages |
| GET | `/health` outside the base | Health |

X-Bank-Key resolves tenant; a different path tenant returns 403. Malformed CSV
returns 400 and rolls back; semantically dirty fields remain accepted. Upload
limit is 250 MB. SQLite inserts are batched at 10,000. Read streams retain a
SQLite transaction; sequential iterator advancement may occur on different ASGI
thread-pool threads, so connection lifetime and thread policy are explicit.
Credit and plan uploads are separate transactions, not an atomic source manifest.

## 9. Tenant isolation and seeding

JWT membership is authoritative; a requested tenant is only compared with it.
Query services require tenant identity. RLS filters both tenant and current batch.
Each reader transaction calls `set_config('app.tenant_id', value, true)`; missing
identity yields no rows. Three static LIST partitions exist for each fact parent.

- app_migrator owns schema and performs DDL.
- app_writer is non-superuser with BYPASSRLS, private to worker/tools.
- app_reader is SELECT-only on approved parents/views, without child access.
- app_django handles identity and narrow tenant-scoped run enqueue bookkeeping.

`tools/seed.py` computes SHA-256(customer_id UTF-8), interprets the first eight
bytes as a big-endian integer and takes mod 3. A temporary SQLite mapping attaches
plans to their credit's tenant. Source CSVs remain read-only. Small update parts
are written to ignored artifacts. Without local source files, synthetic input is
generated. Internal cross-tenant analyst access and audit logging remain COULD.

## 10. Sync lifecycle

PENDING → FETCHING → PROCESSING → VALIDATING → PUBLISHING → SUCCEEDED.
Unchanged/manual non-force work is SKIPPED; validation is REJECTED; technical
errors are FAILED. Invalid domain transitions raise. Metadata, counts, units,
issues, duration, peak RSS, GC duration, source version and batch identity persist.

A session advisory lock spans the run. Downloaded digests, row counts and a second
metadata read must match. Temporary files are scoped to the run and removed on
normal exit. Crashed-worker reaping remains SHOULD; process loss must not expose
unpublished rows. Beat defaults to 30 seconds; tests use five seconds.

## 11. Validation

Schema errors reject missing/extra headers, including empty-file headers. Fields
check required values, types, patterns, ranges and known codes. Row rules check
maturity/start order, installment sums, outstanding/original amounts and dates.
SQL detects duplicate credits, duplicate plan keys, orphan plans, missing plans
and plan-count mismatch. Duplicates and orphans are ERROR; missing/count mismatches
are WARNING. Facts intentionally lack unique business-key constraints so COPY
can retain invalid rows long enough to report all relevant source positions.

The first 1,000 issue details are retained; all rows contribute to rule/severity
counters. Evidence includes dataset, row, key, column, rule, severity, raw and
normalized values. Cross-file joins occur in PostgreSQL, not Python memory.

## 12. Normalization

Dates accept YYYYMMDD, YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, YYYY/MM/DD and ISO
strings with discarded time. Dates outside 1900–2100 or invalid calendar dates
are errors. Ambiguous slash dates use day-first conventions and warning evidence
when the sample cannot disambiguate them.

Explicit `%` and `bps` win: 18.5% and 1850 bps become 0.185. Otherwise a bounded
first-10,000-row nonzero sample determines fraction/percent/bps. Conflicts with
schema units or isolated magnitude inconsistencies produce warnings. Decisions
are persisted; no independent per-row guessing is allowed. Range violations are
errors; implausible but allowed rates produce RATE_IMPLAUSIBLE warnings.

Codes are trimmed, Turkish-aware case-folded and accent-normalized before lookup.
For example K/Kapalı/Paid/Closed map to CLOSED, E/Evet/yes to true. T/V customer
types remain codes until their business meaning is confirmed. Unknown codes are
errors. The mapping is loaded from ref.code_mapping at run start.

Numbers accept localized grouping/decimal separators, spaces and supported
currency affixes. Ambiguous single separators use column evidence or produce a
warning. Negative amounts are errors. Closed installments have remaining amounts
corrected to zero; absent actual-payment dates warn. Future payment dates error.
Component totals use a 0.01 tolerance and warn on mismatch.

## 13. Warehouse model

`dwh.fact_loan_retail`, `fact_loan_commercial` and `fact_installment` have tenant,
batch and source-row metadata. Plans also contain loan_type. Nonunique indexes
start with tenant/batch/business key. `current_snapshot` is keyed by tenant and
loan type and stores batch, source version, publish time and row counts.
`v_loan_common` is security-invoker. Ops stores sync_run, validation_issue,
validation_issue_summary and column_profile. Ref stores tenant and code_mapping.
Cursor ordering is loan ID and, for plans, installment number.

## 14. Publication and cleanup guarantees

Load and validate a new batch without changing the published pointer. Reject by
deleting only the new batch. Publish pointer, profiles and PUBLISHING metadata in
one short transaction. Delete old unit batches and then mark SUCCEEDED. Reader
MVCC sees a complete committed snapshot; paired queries use one repeatable-read
transaction. Ten alternating 1,000/2,000 publications test consistency and report
read p99. GC is idempotent. DELETE bloat and future concurrent partition cleanup
are documented trade-offs, not hidden costs.

## 15. Scale and memory acceptance

No layer should materialize the complete source file. Upload and download use
bounded chunks; Rust buffers only its first 10,000 rows. Profiles cap categories
at 1,000. COPY uses bounded blocks with explicit libpq socket backpressure;
otherwise a fast producer can accumulate a file-sized outbound buffer on Linux.
SQL joins may spill on the database side; worker RSS is measured separately.

**V-17:** generate approximately 50,000,000 and 200,000,000 bytes of payment-plan
CSV plus compatible credits; both syncs must SUCCEED and physical row counts
must match. Fresh worker-child peak RSS must be at most 256 MiB; the absolute
50/200 MB relative difference must be less than 20%. Record real durations, GC
duration and independent docker stats samples. `tools/bench.py` uses 10,000 valid
credit IDs and increasing installment numbers; it does not suffix IDs or use
private source data. Fresh evidence includes a source-code fingerprint.

Publish latency below 100 ms and 500-row API p95 below 300 ms remain design
performance targets; do not claim them from unmeasured estimates. The mandatory
measurement is V-17 and the V-15 read latency evidence.

## 16. Profiling

Compute summaries over normalized, storage-precision values during streaming.
Publish profiles with the snapshot. Every column has count/null_count/null_ratio.
Numeric columns have min/max/mean/sample stddev; dates have min/max; categorical
columns have exact distinct/mode/top ten while below the cardinality limit.
Above it, high_cardinality=true marks the bounded Rust accumulator; PostgreSQL
completes exact distinct/mode/top-ten summaries over the validated unpublished
batch before the publication transaction. Only ten grouped rows per column cross
the driver boundary. Ties use UTF-8 byte ordering (COLLATE "C"), matching Rust.
GET profiling reads only published profiles. Compare all columns and both credit
types against PostgreSQL aggregate functions. Rejected syncs preserve profiles.

## 17. REST API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/token`, `/api/auth/token/refresh` | JWT |
| POST | `/api/sync` | Tenant/type/optional force; 202 or active-run 409 |
| GET | `/api/sync/{uuid}` | Status, counts, decisions, issues summary |
| GET | `/api/runs?loan_type=` | Tenant history and source versions |
| GET | `/api/data?loan_type=&dataset=&cursor=&limit=` | Snapshot-bound keyset pages |
| GET | `/api/profiling?loan_type=` | Published credit and plan profiles |
| GET | `/api/validation-issues?sync_run_id=&severity=&cursor=&limit=` | Issue pages |
| GET | `/api/health`, `/api/schema/`, `/api/docs/` | Public health/schema/docs |

Tenant parameters are optional equality checks, not identity selectors. RFC 9457
problem responses use 401 unauthenticated, 403 tenant mismatch, 404 foreign run or
missing snapshot, 400 invalid parameters and 409 active-unit conflict. Amounts
remain decimal strings. Source metadata failure may leave source_versions null
without hiding stored run history.

## 18. Security

Access JWT lifetime is 15 minutes; refresh lifetime is one day. Claims include
sub, tenant_id and role. Default API permissions require authentication. V-01
enumerates all routes except a small explicit public whitelist. Secrets live in
ignored environment files; only demo defaults are committed. SQL values are
parameterized and dynamic identifiers come from enums through Identifier.
Bank keys belong only to the separate demo bank portal and server gateway.
API-key auth and rate limiting remain SHOULD.

## 19. Frontend

Login derives tenant from identity. Bank Portal supports replace/PATCH CSV upload,
progress, dataset/type selection and source metadata. Sync shows source versus
published version, force, live state and history. Data uses virtual rows and
cursor pages. Profiling displays null/numeric cards and category charts. Issues
shows severity/rule totals, raw/canonical details and rejection banners. Query
keys include tenant; logout clears cached data. V-22 MUST is manual browser
acceptance with synthetic screenshots; automated Playwright is SHOULD.

**Post-delivery revision:** HTTP failures without a JSON body retain their HTTP
status and display a readable fallback. Nested DRF validation details are
flattened into readable messages without Python object representations. Invalid
success bodies are reported as
invalid server responses. After a snapshot-bound cursor fails, the data screen
can discard its cached pages and restart from the first page; switching datasets
also resets the actual scroll viewport, preventing blank virtual rows.

Project attribution is metadata-only: Levent Çelik (`https://github.com/levend18`)
is listed in package manifests, HTML metadata, OCI image labels, OpenAPI contact
metadata and source entry-point headers. It adds no visible UI signature and no
GitHub authentication, network callbacks or account permissions.

## 20. Configuration

See `.env.example` and compose for exact wired settings. Database URLs are split
by migrator/writer/reader/Django roles. Runtime defaults include Redis at
redis://redis:6379/0, bank at http://bank:8001, 30-second polling, zero error
tolerance and 250 MB bank upload limit. Bank keys use BANK_KEY_BANK001 through
BANK_KEY_BANK003. Seed reads DATA_DIR or /app/data; temporary sync files use
WORK_DIR or /tmp. JWT signing material comes from the environment.

## 21. Tests

Rust tests/proptest cover pure normalization. Python domain tests use fake ports.
Integration tests use real PostgreSQL and bank HTTP. Verification maps tests to
V-IDs. Live polling and README curl examples run with worker/beat enabled;
isolated tests stop them to avoid races. Lint includes ruff, format, strict mypy,
import-linter, cargo fmt/clippy and frontend ESLint/Prettier. Vitest covers login,
HTTP errors, pagination recovery, dataset scroll reset and exact categorical
profile display.
Private source tests must be marked real_data and remain optional when data is
absent. No assertion weakening or artificial skip/xfail is allowed.

## 22. Repository layout

`adapter/{shared,ingestion,quality,warehouse,profiling}` contains the core;
`external_bank/` is the source simulator; `api/` and `workers/` are boundaries;
`frontend/src/features/` holds UI features; `tests/{unit,integration,verification}`
holds tests; `tools/` holds seed, synthetic/dirty generators, benchmark and report
orchestration. Local agent instructions are intentionally excluded from Git.

## 23. Delivery and verification report

`cp .env.example .env && make up && make seed && make verify` must work from a
clean clone with Docker and make only. README includes setup, demo accounts,
tenant rationale, commands, tested curl examples, screenshots, measured performance
and open questions. Architecture.md has component/sequence/state/ER diagrams;
architect.md records engineering challenges; CODE_TOUR follows a sync in code.

The runner creates fresh JUnit and benchmark evidence. Missing, failed, errored
or skipped MUST evidence cannot become PASS. Failures still produce a report and
a nonzero exit status. V-22 is explicitly labeled manual evidence. Benchmark
fingerprints prevent reuse against changed processing code. Tests alter demo
portfolios; reseed after verification to restore a useful interactive environment.

## 24. Deliberate trade-offs

Keep only current snapshots; use full replacement rather than deltas; perform DB
transactions in Python rather than Rust; avoid a generic rule expression engine,
Kubernetes and additional analytical databases. These choices reduce operational
complexity. GC bloat, separate source uploads and
missing crashed-worker reaping remain explicit limitations.

## 25. Open business questions

1. What do customer_type T and V mean? Preserve codes until clarified.
2. Are retail rates annual and commercial rates monthly? Convert units, not periods.
3. Are retail 100.00 interest values real? Publish with a warning.
4. Which installment total is authoritative? Warn without inventing values.
5. Does outstanding > original represent capitalization? Warn until confirmed.
6. Do external ratings share a scale? Preserve raw scales.
7. Is partial acceptance allowed? Default to zero ERROR tolerance.

## 26. Milestones

| Milestone | Level | Deliverable | Exit evidence |
|---|---|---|---|
| M0 | MUST | Containers, locks, guard, CI, public repository | Lint and CI |
| M1 | MUST | SQL schemas, roles, RLS, partitions, snapshots | V-05, V-15 SQL |
| M2 | MUST | Domain ports and use cases | Fake-adapter tests |
| M3 | MUST | Rust engine and contracts | Rust tests, V-11 |
| M4 | MUST | Bank simulator and seed | V-20, V-21 |
| M5 | MUST | Infrastructure and live worker | V-06–V-10, V-12–V-15 |
| M6 | MUST | JWT and tenant API | V-01–V-04, V-06 |
| M7 | MUST | Profiling API | V-18 |
| M8 | MUST | Frontend | V-22 manual |
| M9 | MUST | 50/200 MB benchmark | V-17 |
| M10 | MUST | Documentation, report, clean clone | V-23 and all MUST |
| M11 | SHOULD | Optional resilience/auth/UI automation | Optional V portions |
| M12 | COULD | Analyst/audit/archive/percentiles | Future scope |
