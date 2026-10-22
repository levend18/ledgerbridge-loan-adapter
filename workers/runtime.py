import json
import os
import resource
import tempfile
import time
import uuid
from contextlib import contextmanager

import psycopg

from adapter.ingestion.application import SyncDatasetUseCase
from adapter.ingestion.domain import SyncRun
from adapter.ingestion.infrastructure.bank import HttpBankGateway
from adapter.ingestion.infrastructure.runs import PostgresRuns
from adapter.profiling.infrastructure.postgres import PostgresProfiles
from adapter.quality import SeverityPolicy
from adapter.quality.infrastructure.processor import RustProcessor
from adapter.shared import LoanType, TenantId, Unit
from adapter.warehouse.infrastructure.postgres import PostgresWarehouse


def connect():
    return psycopg.connect(
        os.environ.get(
            "DATABASE_URL_WRITER",
            "postgresql://app_writer:local-demo-role-password@postgres/adapter",
        ),
        autocommit=True,
    )


def gateway():
    return HttpBankGateway(
        os.environ.get("BANK_BASE_URL", "http://bank:8001"),
        {t: os.environ.get(f"BANK_KEY_{t}", f"demo-{t.lower()}-key") for t in TenantId},
    )


def codes(connection):
    mappings = {}
    for domain, raw, canonical in connection.execute(
        "SELECT domain,raw_key,canonical FROM ref.code_mapping"
    ):
        mappings.setdefault(domain, {}).setdefault(canonical, []).append(raw)
    return json.dumps(mappings) if mappings else None


def create_run(unit, trigger="MANUAL", force=False):
    run = SyncRun(str(uuid.uuid4()), unit, trigger=trigger, force=force)
    with connect() as conn:
        PostgresRuns(conn).save(run)
    return run


@contextmanager
def services(connection):
    warehouse = PostgresWarehouse(connection)
    yield SyncDatasetUseCase(
        gateway(),
        RustProcessor(codes(connection)),
        warehouse,
        PostgresRuns(connection),
        PostgresProfiles(connection),
        warehouse,
        SeverityPolicy(int(os.environ.get("ERROR_TOLERANCE", "0"))),
    )


def execute(run_id):
    start = time.monotonic()
    with connect() as conn:
        row = conn.execute(
            "SELECT tenant_id,loan_type,trigger,force,status FROM ops.sync_run WHERE id=%s",
            (run_id,),
        ).fetchone()
        if row is None or row[4] != "PENDING":
            return
        run = SyncRun(
            str(run_id), Unit(TenantId(row[0]), LoanType(row[1])), trigger=row[2], force=row[3]
        )
        try:
            with (
                tempfile.TemporaryDirectory(
                    prefix=f"{run_id}-", dir=os.environ.get("WORK_DIR", "/tmp")
                ) as directory,
                services(conn) as use_case,
            ):
                use_case.execute(run, directory)
        finally:
            conn.execute(
                "UPDATE ops.sync_run SET duration_ms=%s,peak_rss_kb=%s,gc_duration_ms=%s WHERE id=%s",
                (
                    int((time.monotonic() - start) * 1000),
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    use_case.warehouse.gc_duration_ms,
                    run_id,
                ),
            )
    return run
