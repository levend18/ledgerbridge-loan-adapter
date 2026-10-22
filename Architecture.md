# Architecture

The synchronization unit is **tenant × loan type**. Credit and payment plan
share one batch and are validated and published together with their profiles.
See [architect.md](architect.md) for implementation challenges and trade-offs.

## Components and trust boundaries

```mermaid
flowchart LR
  UI[React portal] -->|JWT| API[Django REST API]
  UI -->|Demo bank key| Bank[FastAPI bank simulator]
  API -->|Run ID| Redis[Redis queue]
  Beat[Celery beat] -->|Metadata| Bank
  Beat --> Redis
  Redis --> Worker[Celery worker]
  Worker -->|NDJSON stream| Bank
  Bank --> SQLite[(SQLite raw records)]
  Worker --> Rust[Rust normalization and profiles]
  Rust --> COPY[Bounded COPY stream]
  COPY --> Writer[app_writer]
  Writer --> PG[(PostgreSQL ref / ops / dwh)]
  API --> Reader[app_reader and RLS]
  Reader --> PG
  API --> Django[app_django identity and narrow enqueue access]
  Django --> PG
```

Only loopback ports 5173, 8000 and 8001 are exposed. Database and Redis stay on the
compose network. Django runserver, Vite dev server and demo credentials are local
evaluation choices, not a production deployment design.

## Synchronization sequence

```mermaid
sequenceDiagram
  participant U as User
  participant A as API
  participant Q as Celery worker
  participant B as Bank
  participant R as Rust
  participant P as PostgreSQL
  U->>A: POST /api/sync with JWT
  A->>P: Tenant-scoped PENDING run
  A->>Q: Enqueue run ID
  A-->>U: 202 Accepted
  Q->>P: Unit advisory lock
  Q->>B: Metadata, two NDJSON streams, metadata again
  Note over Q,B: Validate SHA-256, row counts and version
  Q->>R: File paths, schemas and code mapping
  R-->>Q: COPY files, bounded issue details and profiles
  Q->>P: COPY new batch, refresh statistics, cross-file SQL
  alt Errors or schema mismatch
    Q->>P: Discard new batch, REJECTED
  else Publishable
    Q->>P: Complete exact high-cardinality profiles
    Q->>P: One transaction: pointer and profiles
    Q->>P: Old-batch GC, SUCCEEDED
  end
  U->>A: GET /api/data
  A->>P: Read-only repeatable-read with tenant set_config
  P-->>A: Current tenant snapshot
  A-->>U: Data and snapshot metadata
```

## State machine

```mermaid
stateDiagram-v2
  [*] --> PENDING
  PENDING --> SKIPPED: Unchanged or lock unavailable
  PENDING --> FETCHING
  FETCHING --> PROCESSING
  PROCESSING --> VALIDATING
  VALIDATING --> REJECTED: ERROR
  VALIDATING --> PUBLISHING
  PUBLISHING --> SUCCEEDED: Publish and GC complete
  PENDING --> FAILED
  FETCHING --> FAILED
  PROCESSING --> FAILED
  VALIDATING --> FAILED
  PUBLISHING --> FAILED
  SUCCEEDED --> [*]
  REJECTED --> [*]
  SKIPPED --> [*]
  FAILED --> [*]
```

Network retries preserve the FAILED run and create a new RETRY run. A GC error
after publication does not delete the published batch. A crashed-worker reaper
remains optional work rather than an implemented recovery claim.

## Logical entity relationships

```mermaid
erDiagram
  TENANT ||--o{ MEMBERSHIP : authorizes
  TENANT ||--o{ SYNC_RUN : starts
  TENANT ||--o{ CURRENT_SNAPSHOT : owns
  SYNC_RUN ||--o{ VALIDATION_ISSUE : records
  SYNC_RUN ||--o{ VALIDATION_SUMMARY : counts
  CURRENT_SNAPSHOT ||--o{ FACT_LOAN_RETAIL : batch
  CURRENT_SNAPSHOT ||--o{ FACT_LOAN_COMMERCIAL : batch
  CURRENT_SNAPSHOT ||--o{ FACT_INSTALLMENT : batch
  CURRENT_SNAPSHOT ||--o{ COLUMN_PROFILE : batch
  CURRENT_SNAPSHOT {
    text tenant_id PK
    text loan_type PK
    uuid batch_id
    bigint source_version
  }
  SYNC_RUN {
    uuid id PK
    text tenant_id
    text loan_type
    text status
    bigint peak_rss_kb
    bigint duration_ms
    bigint gc_duration_ms
  }
  FACT_INSTALLMENT {
    text tenant_id
    uuid batch_id
    text loan_type
    text loan_account_number
    int installment_number
    numeric installment_amount
  }
```

Batch relationships are logical; not every line represents a physical FK.
Business keys are intentionally nonunique so duplicate/orphan inputs can be
loaded and reported before rejection. Each fact parent has three tenant
partitions. `ref.code_mapping` stores normalization aliases.

## Decision summary

- PyO3 keeps Rust processing inside the worker while Python owns I/O and transactions.
- PostgreSQL combines atomic multi-table publication and RLS without another database.
- Tenant identity comes from JWT; reader transactions enforce both tenant and snapshot.
- Pointer publication avoids parent-table DDL locks; GC cost is measured separately.
- Metadata polling avoids unchanged downloads; Celery provides asynchronous work.
- ERROR/WARNING/CORRECTED preserve distinctions required by dirty financial data.
- Decimal normalization/storage and explicitly floating-point statistics have separate roles.
- Import contracts enforce architecture rather than leaving it as diagram-only intent.

## Profile completeness and portal recovery

Validated, unpublished rows are the source for SQL profile completion. The unit
lock prevents concurrent publication; aggregation finishes before the short
pointer/profile transaction. Failure discards the new batch and retains the
previous data and profiles. The high_cardinality flag describes the Rust memory
threshold, not missing API statistics.

Data-page cursors contain the snapshot identity. A stale cursor returns a readable
400 problem; the portal can clear only the selected tenant/type/dataset pages and
restart. Dataset switches reset the scroll viewport. Metadata attributes package,
image and API ownership to Levent Çelik without a visible UI signature.

## Limits

Bank credit/plan uploads are separate operations. Intermediate polls may reject
an incomplete source update while DWH readers retain the old snapshot. Rust caps its category map at 1,000; PostgreSQL completes exact distinct counts,
modes and top-ten values before publication, returning only bounded summaries. Archived
snapshots, API-key authentication, reaper and rate limiting are not complete.
See the technical design for all ADRs and the report for measured acceptance.
