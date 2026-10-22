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
