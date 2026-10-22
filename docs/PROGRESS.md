# Progress and Evidence

## Scope and working agreement

Complete M0–M10 without pausing for milestone approval, test each change, commit
and push, and verify a clean Docker-only checkout. Actual source data and secrets
remain outside Git. Local agent instructions are also excluded from all published
history. The latest user request changes the project identity to LedgerBridge and
requires English Markdown documentation, including an engineering retrospective.

## Completed foundations: M0–M7

- **M0:** Docker Desktop/CLI and GitHub authentication established. Containerized
  Python/Rust tooling, private-file guard, import contracts and CI added. Initial
  CI issues were Git safe.directory in a bind mount and empty untracked test
  directories; both were corrected without bypassing checks.
- **M1:** ref/ops/dwh, three roles plus migrator, static partitions, reader RLS,
  snapshot pointers and SQL concurrency tests. Reader has no direct partition
  access. Initial SQL read p99 was 4.391 ms on the local arm64 environment.
- **M2:** Pure domain values, Protocol ports, state machine, severity policy and
  use cases with fake adapters. Publish/GC failure behavior is explicit.
- **M3:** Streaming Rust normalization, schema checks, bounded issue details,
  Welford summaries, category cap, COPY output and property tests. No float for
  monetary normalization/storage. Full input schemas retained.
- **M4:** FastAPI/SQLite bank, raw-value preservation, PUT/PATCH, stable digests,
  stream/pagination, deterministic seed and synthetic/dirty generators.
- **M5:** HTTP integrity checks, COPY, SQL cross-file checks, atomic publication,
  persistent runs/profiles, live worker/beat and network retry. A SQLite iterator
  crossing ASGI thread-pool threads was fixed with explicit connection lifetime
  and thread policy. Network chunks remain bounded.
- **M6:** JWT membership claims, tenant-scoped endpoints, RFC 9457 errors,
  snapshot-bound cursors and narrow enqueue permissions. Actual source seed once
  completed all six units: 25,430 retail and 4,440 commercial credits, with
  269,442 and 25,070 plans. Files were not modified or committed.
- **M7:** Published profile API and all-column SQL comparisons. Money/rate
  precision is aligned before COPY and profiling; overflow becomes field ERROR.
  At this milestone Rust 3, Python 81 and existing verification 33 tests passed.
  CI run 39766682120 passed.

Historical commit IDs changed during requested history cleanup. CI run IDs above
identify the original validation runs; they are not claims that later work passed.

## M8 — Frontend

Implemented feature-based React portal: login, CSV replace/PATCH and progress,
source/published versions, manual sync with status polling, virtual data rows,
ECharts profiles and filtered validation evidence. Tenant is included in query
keys; logout clears cache. Dependency versions are locked; the npm audit at
implementation time reported zero vulnerabilities.

Rust 3, Python 81, Vitest 2 and lint passed. Manual browser flow exercised valid
upload → SUCCEEDED → data/profiles → invalid upload → REJECTED, with the old six
rows preserved. CI run 39772208224 passed. The manual workflow was repeated with LedgerBridge branding: version 63
published six credits/plans; version 64 was rejected and version 63 preserved.
All six screenshots were refreshed. Old branded screenshots are excluded from
the rewritten history.

## M9 — Measurements and corrections verified

The benchmark generates 10,000 compatible credits and approximately 50/200 MB of
plan CSVs, uses real fresh Celery child processes and compares physical row counts.
It records worker RSS, duration, GC cost and Docker memory samples.

1. Initial 50 MB sync took 217.547 seconds. A bad anti-join plan exposed missing
   batch statistics. Direct ANALYZE as app_writer silently lacked table-owner
   privileges on PostgreSQL 16. A narrowly scoped SECURITY DEFINER function now
   handles nine static partitions; reader/Django access and invalid inputs are
   rejected. The follow-up 50 MB sync took roughly 13 seconds.
2. Continuous host-written Docker stats output was not immediately visible through
   the Desktop bind mount. Timestamped snapshots are now finalized after the host
   collector closes its file; missing stats are a failure, not fabricated data.
3. The first complete two-size measurement succeeded functionally but **failed
   memory acceptance**: 50 MB 12.277 s / 170,836 KiB, 200 MB 73.246 s / 367,452 KiB.
   Linux libpq could grow its outbound COPY buffer when the producer outran the
   database. COPY now uses bounded blocks and explicit socket backpressure.
   The fresh run passed: 50 MB 10.976 s / 106,132 KiB; 200 MB 73.558 s /
   106,200 KiB, 2,717,294 plans. RSS difference 0.064%; Docker peaks
   120.5/149.1 MiB. GC 25/2,374 ms.

After the COPY correction, lint and the regression suite passed Rust 3,
Python 83 and Vitest 2 tests.

## M10 — Documentation and report in progress

README, architecture diagrams, code tour, manual UI evidence and an engineering
retrospective are being completed in English. The verification runner separates
isolated tests, live polling/README examples and performance phases, and generates
an honest JUnit-derived report even after failures. Missing/failed/skipped MUST
evidence cannot pass. A unit test covers false-positive report prevention.

Outstanding: validate the COPY fix, refresh UI evidence with the new identity,
finish all MUST verification, push cleaned history, obtain green CI and run the
quick-start sequence in a clean clone. No final delivery claim has been made.

## Environment difficulties

Docker installation originally failed because the disk was full and the DMG
mount was busy. User-authorized cleanup freed space; unrelated protected projects
were not removed. Docker image caches and temporary benchmark files also require
care on this machine. Only current-task build/test resources are eligible for
further cleanup. Benchmark temporary files are deleted after runs.
