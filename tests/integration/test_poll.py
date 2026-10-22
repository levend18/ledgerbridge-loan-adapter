import time

import pytest

from adapter.shared import LoanType, TenantId, Unit
from tests.integration.test_sync_pipeline import upload
from tests.integration.test_warehouse import connect
from tools.generate_synthetic import credit, payment

pytestmark = pytest.mark.live_worker


def wait_for(predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError("Polling did not publish the expected version")


def test_v12_automatic_poll_and_v13_no_duplicate_work():
    unit = Unit(TenantId.BANK003, LoanType.COMMERCIAL)
    upload([credit(500001, "commercial", 1)], [payment(500001, 1)], unit)
    from workers.runtime import gateway

    version = gateway().get_meta(unit).version

    def published():
        with connect() as conn:
            return conn.execute(
                "SELECT id FROM ops.sync_run WHERE tenant_id=%s AND loan_type=%s AND source_version=%s AND trigger='POLL' AND status='SUCCEEDED'",
                (unit.tenant, unit.loan_type, version),
            ).fetchone()

    assert wait_for(published)
    with connect() as conn:
        before = conn.execute(
            "SELECT count(*) FROM ops.sync_run WHERE tenant_id=%s AND loan_type=%s",
            (unit.tenant, unit.loan_type),
        ).fetchone()[0]
    time.sleep(11)
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM ops.sync_run WHERE tenant_id=%s AND loan_type=%s",
                (unit.tenant, unit.loan_type),
            ).fetchone()[0]
            == before
        )


def test_v14_patch_is_published_by_poll():
    import httpx
    from tests.unit.test_bank import csv_bytes
    from workers.runtime import create_run, execute, gateway

    unit = Unit(TenantId.BANK003, LoanType.RETAIL)
    run = create_run(unit, force=True)
    upload(
        [credit(i, installments=1) for i in range(1, 101)],
        [payment(i, 1) for i in range(1, 101)],
        unit,
    )
    assert execute(run.id).status == "SUCCEEDED"
    updated = [credit(i, installments=1) for i in [*range(1, 41), *range(101, 111)]]
    for row in updated:
        row["outstanding_principal_balance"] = "777.77"
    response = httpx.patch(
        "http://bank:8001/v1/tenants/BANK003/loans/RETAIL/credit",
        content=csv_bytes(updated),
        headers={"X-Bank-Key": "demo-bank003-key"},
    )
    response.raise_for_status()
    version = gateway().get_meta(unit).version

    def published():
        with connect() as conn:
            return conn.execute(
                "SELECT id FROM ops.sync_run WHERE tenant_id='BANK003' AND loan_type='RETAIL' AND source_version=%s AND trigger='POLL' AND status='SUCCEEDED'",
                (version,),
            ).fetchone()

    assert wait_for(published)
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK003'"
            ).fetchone()[0]
            == 110
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK003' AND loan_account_number<='LOAN_000040' AND outstanding_principal_balance=777.77"
            ).fetchone()[0]
            == 40
        )
