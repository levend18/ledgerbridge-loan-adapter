# Engineering Retrospective and Architectural Challenges

This document records the difficult parts of building LedgerBridge, the evidence
that exposed them, the decisions taken and remaining limits. The component,
sequence, state-machine and entity diagrams are in [Architecture.md](Architecture.md).
The full contracts and ADRs remain in [the technical design](docs/tecnic.md).

## Making publication atomic without blocking all tenants

Credit and payment plans must move together. DELETE/INSERT makes the publication
transaction large; partition swapping introduces parent-table locks and recurring
DDL/security choreography. The chosen design loads an invisible batch and changes
a small snapshot pointer in one transaction with its profiles. Readers use RLS
and repeatable-read transactions. Ten alternating 1,000/2,000 publications test
consistency under concurrent reads. GC is outside publication and must complete
before SUCCEEDED; a post-publication cleanup failure must not delete the new data.

The cost is DELETE bloat and temporary coexistence of batches. Autovacuum handles
reclamation; concurrent batch-partition retirement is a future alternative, not a
feature claimed by this delivery.

## Isolation that survives mistakes in application filtering

Tenant parameters alone are not trustworthy. Membership becomes signed JWT
claims; parameters merely check equality. app_reader is neither an owner nor a
BYPASSRLS role, and cannot SELECT child partitions directly. RLS restricts both
tenant and current batch. The writer remains a separate backend-only identity.
SQL and API tests independently exercise missing identity and cross-tenant access.

An additional complication was API enqueue bookkeeping: broad writer access would
break that boundary. app_django instead received narrowly constrained tenant-aware
run INSERT and queue-failure UPDATE permissions.

## Dirty financial values are not a binary parsing problem

Source dates use several formats, rates may be percent/fraction/basis points, and
categorical aliases include Turkish spellings. Rate detection uses a bounded
column sample, not independent guesses for each row. Explicit units win. Ambiguous
values generate warnings and persisted unit decisions. Monetary values stay
Decimal throughout; summary statistics explicitly use f64.

A profile-versus-SQL comparison exposed three-decimal amounts being rounded only
at storage time. The processor now quantizes to DWH precision before COPY and
profiling. Tests use such inputs deliberately; expectations follow the documented
storage contract rather than being changed simply to match a failing result.

## Streaming in Rust is insufficient if the database driver buffers output

The first full two-size benchmark functionally succeeded but failed the memory
contract: the 200 MB run reached 367,452 KiB peak RSS against a 256 MiB limit.
The Rust reader, sample, categories and issue details were bounded. Inspection of
the installed psycopg implementation showed that Linux COPY does not request an
explicit flush on each write. When PostgreSQL falls behind, libpq can accumulate
a large outbound buffer even though application rows are produced one at a time.

The correction uses bounded COPY blocks and waits for socket backpressure before
producing more. This is an implementation fix, not a higher memory limit, reduced
input size or weaker acceptance test. The initial successful 50/200 MB measurements validated
the correction: 103.64/103.71 MiB child RSS, a 0.064% difference, both below
256 MiB. The 200 MB sync processed 2,717,294 plan rows in 73.558 seconds.

## Exact categorical profiles without unbounded worker memory

A review against the original assignment exposed a gap in the bounded profiler:
above 1,000 distinct values, Rust returned null for distinct count and mode. The
assignment requires those statistics for categorical fields; labeling the limit
honestly did not satisfy that requirement.

Rust still uses bounded memory. After validation, `PostgresProfiles.prepare`
groups each overflowed column in PostgreSQL over the unpublished tenant/batch.
The database can spill aggregation to disk, and only the top ten values plus the
exact number of groups return to Python. Equal frequencies use byte ordering for
a deterministic mode. Preparation completes before pointer publication so a
failed aggregate cannot replace the old data or lengthen the publish transaction.
Tests cover both loan types, more than 1,000 categories, tied modes, plan fields,
tenant authorization and preparation failures. The dashboard displays these exact
results even when high_cardinality is true. Fresh performance evidence is linked
from the README; older measurements above describe the original debugging event.

## Recovering the portal after a new snapshot

A user can request page two after a newer portfolio has been published. Combining
those pages would mix snapshots. The API rejects the stale cursor; the portal now
offers a first-page restart scoped to the exact tenant/type/dataset cache. Dataset
switches also reset the actual scroll container to avoid empty virtual rows.
Nested DRF validation errors and non-JSON HTTP responses now become readable
messages. Regression tests and a manual 150-row synthetic browser run verified
recovery and successful continuation after restarting.

## PostgreSQL plans need statistics for each new batch

An early 50 MB sync took 217.547 seconds. The orphan anti-join selected a costly
plan with poor cardinality estimates after COPY. Refreshing the target partition's
statistics reduced subsequent 50 MB processing to roughly 13 seconds.

PostgreSQL 16 does not allow an ordinary writer to ANALYZE arbitrary tables;
the first direct attempt was ineffective. Granting ownership or superuser would
undermine least privilege. A SECURITY DEFINER function now has a fixed search_path,
only nine static CASE branches, no dynamic SQL and execution rights only for
app_writer. Tests verify actual statistics, reject invalid target names and deny
reader/Django invocation.

## ASGI iterators and SQLite connection ownership

A streaming response may advance a synchronous iterator on different thread-pool
threads. SQLite's default same-thread restriction caused failures even though
advancement was sequential. Request-scoped connections now have explicit lifetime
and thread policy; transactions retain a consistent read snapshot and 64 KB
network chunks keep streaming bounded. Regression tests exercise actual HTTP,
not only an in-process test client.

## Reproducible tooling on a space-constrained workstation

Docker installation initially hit busy DMG mounts and exhausted disk space.
User-authorized cleanup enabled installation; unrelated protected projects were
preserved. Docker builds, SQLite WAL, PostgreSQL and temporary NDJSON/COPY files
can consume many times the CSV's size. Cleanup is restricted to this task's
resources, and benchmark temporary directories are removed after execution.

Docker Desktop bind mounts also exposed a visibility delay while a host process
kept its statistics file open. The collector now writes timestamped snapshots
and finalizes the evidence after closing the writer. Missing samples fail the
measurement. Git hooks and CI run in containers; transient index visibility was
rechecked rather than bypassing the hook.

## Evidence and honest completion criteria

A passing unit suite is not an end-to-end delivery. The acceptance runner separates
isolated database tests, live polling, executable README examples and fresh
benchmarks. JUnit failures, errors, skipped tests and missing evidence cannot
become PASS. The report generator itself has a regression test for false positives.
A clean checkout must run the documented Docker-only sequence.

Manual UI evidence is labeled manual. Synthetic screenshots demonstrate upload,
success, data, profiles and rejection with old-data preservation; they do not
pretend to be an automated Playwright suite. API key auth, worker reaper, rate
limits and fault-injection manifests remain explicit optional gaps.

## Repository hygiene

Private datasets, credentials and local agent instructions are excluded by ignore
rules and the commit guard. A requested project-identity change requires updating
source, documentation, package metadata, image names, screenshots and reachable
Git history together. Rewriting Git references does not guarantee removal of
unreachable objects or redirects retained by the hosting provider. Those limits
must be stated rather than promising that every historic external copy vanished.
