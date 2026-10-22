# Acceptance Scenarios

Each scenario maps to a requirement in `tecnic.md` and carries a MUST/SHOULD
priority. Automated tests live in `tests/verification/`. V-22 MUST uses a manual
browser record and screenshots; its automated test checks evidence files only.
`make verify` runs lint, isolated tests, live worker tests and a fresh benchmark,
then renders JUnit evidence into `verification-report.md`. Missing evidence fails.

## Prerequisites

```bash
cp .env.example .env
make up
make seed
make verify
```

Demo users: bank001_user, bank002_user, bank003_user; password demo1234 (local
simulation only). Seed uses read-only local data when present, otherwise synthetic
data. Acceptance tests use synthetic records and alter the demo environment.

## A. Authentication and isolation

### V-01 · Every non-public endpoint requires a token — MUST
Call data, sync, profiling, runs and validation-issues without Authorization.
Expect 401 and application/problem+json. Enumerate the entire URL configuration;
only health, auth, schema and documentation routes are whitelisted.

### V-02 · Invalid credentials are rejected — MUST (JWT) / SHOULD (API key)
Bad JWT signature and expired JWT return 401. An invalid X-API-Key does not grant
access. Valid tenant API-key authentication remains SHOULD and is not implemented.

### V-03 · A tenant receives only its own data — MUST
Publish distinct portfolios for three tenants and paginate all BANK001 records.
Every row has tenant_id BANK001, IDs do not intersect BANK002/003 source sets,
and the total equals the expected BANK001 input count.

### V-04 · Foreign tenant parameters and run IDs are denied — MUST
With BANK001 identity, request BANK002 on data, profiling, sync, runs and issues:
expect 403 tenant-mismatch. Access to a BANK002 run/issue list returns 404 without
revealing its existence.

### V-05 · RLS enforces tenant and snapshot isolation — MUST
As app_reader, set transaction-local app.tenant_id to BANK001. Read only BANK001
current facts; requesting BANK002 returns zero rows. With no tenant setting,
return zero rows. Direct child-partition SELECT is denied. A newly loaded but
unpublished batch is invisible. Repeat relevant checks after publication.

## B. Storage and replacement

### V-06 · Retail and commercial are independently available — MUST
Publish both types and query credit/payment_plan separately. Retail has
insurance_included and no sector_code; commercial has the inverse. Credit ID
sets do not intersect, and row counts match each source dataset.

### V-07 · Replacing 1000 credits with 2000 yields 2000 — MUST
PUT and sync 1,000 credits/plans, then 2,000. Published count and, after GC,
physical writer-visible count must equal 2,000. Plans belong only to the new
batch. Other units remain unchanged.

### V-08 · Invalid replacement preserves valid data and profiles — MUST
Publish valid batch A, then introduce ERRORs such as invalid maturity or orphan
plans. New run is REJECTED; API data and profiles retain A. Issues include source
row, rule and raw value. Rejected batch rows are physically removed.

## C. Validation and normalization

### V-09 · Field and schema validation — MUST
Use the dirty generator's field/schema cases: required blank, invalid amount abc,
negative amount, out-of-range rate, unknown category and wrong column name.
Expect the appropriate rule IDs and rejection. SchemaMismatch rejects the file,
including invalid headers on empty files.

### V-10 · Cross-file validation — MUST
Orphan LOAN_999999 produces ORPHAN_PAYMENT; duplicate loan key or duplicate
(loan, installment_number) produces DUPLICATE_KEY. Rejection includes source-row
evidence. Missing plans and plan-count mismatch warn but do not block publication.

### V-11 · Normalization preserves canonical values and evidence — MUST
Accept dates 20240115, 15.01.2024, 2024-01-15, 15/01/2024 and ISO datetime.
Accept 18.5%, 1850 bps, percent-column 18.5 and fraction-column 0.185.
K/Kapalı/KAPALI/kapali/Paid/Closed normalize to CLOSED; E/Evet/yes to true.
1.234,56 / 1,234.56 / 1234.56 normalize to decimal 1234.56. Persist raw→canonical
issue evidence and column-level unit decisions. Commercial default_probability
is fractional; retail nominal_interest_rate is percent.
The optional real-data case expects 127 RATE_IMPLAUSIBLE warnings for retail
100.00 rates without rejecting the portfolio. Synthetic tests do not claim this
private-data observation as fresh evidence.

## D. Synchronization

### V-12 · A new source version triggers automatic sync — MUST
With five-second polling, PUT a new bank version without manual sync. Expect a
POLL run to succeed within two poll intervals plus processing time, with the new
version visible to the tenant.

### V-13 · Unchanged sources do not trigger duplicate work — MUST
Observe several unchanged polling cycles: no new run. Manual force=false returns
SKIPPED and preserves batch identity. Force=true may republish.

### V-14 · PATCH changes are automatically synchronized — MUST
PATCH 40 existing credits with changed balances and add ten new credits. Missing
plans are warnings, not publication errors.
Polling publishes the new version. Total increases by ten; all 40 existing
balances match the update. Test direct PATCH semantics and the live poll path.

## E. Atomicity and resilience

### V-15 · Readers never see a partial or mixed publication — MUST
Read continuously while publishing 1,000 ↔ 2,000 rows ten times. SQL paired reads
and API reads see one complete batch, valid counts and consistent credit/plan
snapshot metadata. No read errors or lock stalls. Record read p99 latency.

### V-16 · Concurrent sync and worker recovery — SHOULD
Concurrent POST should return 409 for the second active request. Killing a worker
must preserve the published batch; a reaper should fail abandoned runs and a
later sync should succeed. 409 is implemented; the reaper portion is not complete.

## F. Scale and profiling

### V-17 · 200 MB processing uses bounded memory — MUST
Generate approximately 50 MB and 200 MB payment-plan CSVs with compatible credits,
upload and sync through actual Celery workers. Both runs must SUCCEED and physical
row counts must match generation. Fresh child peak RSS ≤256 MiB; absolute relative
RSS difference between sizes <20%. Capture ops.sync_run metrics and independent
docker stats. Report duration and GC cost in README and verification-report.md.

### V-18 · Profiles agree with stored SQL values — MUST
Compare every column's null ratio and numeric min/max/avg/stddev_samp or exact
categorical distinct/mode to PostgreSQL results for both credit types and plans.
Numeric relative error <1e-9; other values exact. A fully empty closing-date column
has null_ratio 1.0. Rejected batches must not alter the published profile. Include more than 1,000
distinct categories in both loan types, tied modes with deterministic ordering,
and payment-plan categories; counts/modes/top ten must remain exact in the API.
Profile preparation failures must preserve the previous publication.

### V-19 · Fault-injection manifest matches results — SHOULD
A reproducible mixed dirty-data generator should create expected.json, with
severity/rule counters and decisions matching actual results. Not completed.

## G. Bank, frontend and documentation

### V-20 · Bank API contract — MUST
Test PUT, PATCH, metadata, chunked NDJSON and paginated JSON. Each successful write
increments unit version; digest/count agree with downloaded bytes. A valid key
used with a different tenant path returns 403.

### V-21 · Bank storage preserves raw strings — MUST
Upload strings such as 15.01.2024, 18.5% and Kapalı; records must return those
values unchanged. Normalization belongs to the adapter, not the bank.

### V-22 · Frontend acceptance — MUST (manual evidence) / SHOULD (Playwright)
Login as bank001_user → upload CSVs → manual sync SUCCEEDED → Data table →
Profiling charts → invalid CSV and sync → REJECTED banner and issue table.
BANK001 must not see BANK002 data. Save synthetic screenshots under docs/screenshots
and observations in UI_VERIFICATION.md. Automated Playwright remains optional.

### V-23 · Documentation and architecture contracts — MUST
Run lint (ruff, mypy, import-linter, Rust fmt/clippy, ESLint/Prettier). Extract
README curl examples and execute them through real HTTP in test_v23_readme.py.
README must include setup, accounts, tenant rationale, commands, API examples,
screenshots, measured performance and open questions. Architecture.md and
CODE_TOUR.md must exist; architect.md records engineering challenges.

## Report contract

Each V-ID has priority, title, result, duration and evidence. Include git SHA,
timestamp, environment versions, benchmark metrics and V-15 read latency.
Every MUST must PASS; unimplemented SHOULD portions are explicitly identified.
Do not substitute static example numbers for measurements. Run the quick-start
sequence in a genuinely clean checkout before declaring delivery complete.
