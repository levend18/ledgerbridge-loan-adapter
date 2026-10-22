import psycopg

from adapter.ingestion.application import CheckForUpdatesUseCase
from adapter.shared import BankUnavailable, LoanType, TenantId, Unit
from adapter.warehouse.infrastructure.postgres import PostgresWarehouse
from workers.celery_app import app
from workers.runtime import connect, create_run, execute, gateway


class Scheduler:
    def enqueue(self, unit):
        try:
            run = create_run(unit, trigger="POLL")
        except psycopg.errors.UniqueViolation:
            return
        sync.delay(run.id)


@app.task(bind=True, max_retries=5)
def sync(self, run_id):
    try:
        execute(run_id)
    except BankUnavailable as exc:
        if self.request.retries >= self.max_retries:
            raise
        with connect() as conn:
            row = conn.execute(
                "SELECT tenant_id,loan_type FROM ops.sync_run WHERE id=%s", (run_id,)
            ).fetchone()
        try:
            retry = create_run(
                Unit(TenantId(row[0]), LoanType(row[1])), trigger="RETRY", force=True
            )
        except psycopg.errors.UniqueViolation:
            return
        raise self.retry(exc=exc, args=[retry.id], countdown=2**self.request.retries)


@app.task
def poll():
    with connect() as conn:
        CheckForUpdatesUseCase(gateway(), PostgresWarehouse(conn), Scheduler()).execute()
