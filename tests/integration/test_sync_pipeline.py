import httpx
import pytest

from adapter.ingestion.infrastructure.bank import HttpBankGateway
from adapter.shared import DatasetKind, DownloadIntegrityError, LoanType, TenantId, Unit
from tests.integration.test_warehouse import clean_warehouse, connect
from tests.unit.test_bank import csv_bytes
from tools.generate_synthetic import credit, payment
from workers.runtime import create_run, execute

__all__ = ["clean_warehouse"]
UNIT = Unit(TenantId.BANK001, LoanType.RETAIL)


def upload(credits, plans, unit=UNIT):
    base = f"http://bank:8001/v1/tenants/{unit.tenant}/loans/{unit.loan_type}"
    for kind, rows in (("credit", credits), ("payment_plan", plans)):
        response = httpx.put(
            base + f"/{kind}",
            content=csv_bytes(rows),
            headers={"X-Bank-Key": f"demo-{unit.tenant.lower()}-key"},
            timeout=120,
        )
        response.raise_for_status()


def run_sync(unit=UNIT, force=False):
    run = create_run(unit, force=force)
    return execute(run.id)


def test_v07_replace_and_gc_and_v13_unchanged():
    other = Unit(TenantId.BANK002, LoanType.RETAIL)
    upload([credit(999)], [payment(999, 1)], other)
    assert run_sync(other).status == "SUCCEEDED"
    for count in (1000, 2000):
        upload(
            [credit(i, installments=1) for i in range(1, count + 1)],
            [payment(i, 1) for i in range(1, count + 1)],
        )
        run = run_sync()
        assert run.status == "SUCCEEDED"
        with connect() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK001'"
                ).fetchone()[0]
                == count
            )
            assert (
                conn.execute(
                    "SELECT count(*) FROM dwh.fact_installment WHERE tenant_id='BANK001'"
                ).fetchone()[0]
                == count
            )
            assert (
                conn.execute(
                    "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK002'"
                ).fetchone()[0]
                == 1
            )
    assert run_sync().status == "SKIPPED"
    forced = run_sync(force=True)
    assert forced.status == "SUCCEEDED"
    assert forced.batch_id != run.batch_id


def test_v08_rejection_preserves_snapshot_and_profiles():
    upload([credit(1, installments=1)], [payment(1, 1)])
    good = run_sync()
    bad = credit(1)
    bad["final_maturity_date"] = "19000101"
    upload([bad], [payment(1, 1)])
    rejected = run_sync()
    assert rejected.status == "REJECTED"
    assert rejected.report.validation.errors > 0
    with connect() as conn:
        assert (
            str(
                conn.execute(
                    "SELECT batch_id FROM dwh.current_snapshot WHERE tenant_id='BANK001' AND loan_type='RETAIL'"
                ).fetchone()[0]
            )
            == good.batch_id
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM dwh.fact_installment WHERE batch_id=%s", (rejected.batch_id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM ops.column_profile WHERE batch_id=%s", (good.batch_id,)
            ).fetchone()[0]
            > 0
        )
        assert conn.execute(
            "SELECT raw_value FROM ops.validation_issue WHERE run_id=%s AND rule_id='MATURITY_AFTER_START'",
            (rejected.id,),
        ).fetchone()


@pytest.mark.parametrize(
    "case,rule",
    [
        ("orphan", "ORPHAN_PAYMENT"),
        ("credit_duplicate", "DUPLICATE_KEY"),
        ("plan_duplicate", "DUPLICATE_KEY"),
        ("schema", "SCHEMA_MISMATCH"),
    ],
)
def test_v09_v10_cross_file_and_schema_rejection(case, rule):
    credits, plans = [credit(1, installments=1)], [payment(1, 1)]
    if case == "orphan":
        plans[0]["loan_account_number"] = "LOAN_999999"
    elif case == "credit_duplicate":
        credits.append(credits[0].copy())
    elif case == "plan_duplicate":
        plans.append(plans[0].copy())
    else:
        credits[0]["wrong"] = credits[0].pop("customer_id")
    upload(credits, plans)
    run = run_sync()
    assert run.status == "REJECTED"
    assert run.report.validation.counts[f"ERROR:{rule}"] > 0
    assert any(i.rule_id == rule for i in run.report.validation.details)


def test_download_rejects_content_changed_since_metadata(tmp_path):
    gateway = HttpBankGateway("http://bank:8001", {TenantId.BANK001: "demo-bank001-key"})
    upload([credit(1)], [payment(1, 1)])
    old = gateway.get_meta(UNIT)
    upload([credit(2)], [payment(2, 1)])
    with pytest.raises(DownloadIntegrityError):
        gateway.download(UNIT, old, str(tmp_path))
    current = gateway.get_meta(UNIT)
    files = gateway.download(UNIT, current, str(tmp_path))
    assert set(files) == set(DatasetKind)
    assert current.datasets[DatasetKind.CREDIT].row_count == 1


def test_v14_patch_updates_forty_and_adds_ten():
    upload(
        [credit(i, installments=1) for i in range(1, 101)], [payment(i, 1) for i in range(1, 101)]
    )
    assert run_sync().status == "SUCCEEDED"
    updated = [credit(i, installments=1) for i in [*range(1, 41), *range(101, 111)]]
    for row in updated:
        row["outstanding_principal_balance"] = "777.77"
    base = "http://bank:8001/v1/tenants/BANK001/loans/RETAIL"
    for kind, rows in (
        ("credit", updated),
        ("payment_plan", [payment(i, 1) for i in range(101, 111)]),
    ):
        response = httpx.patch(
            base + f"/{kind}", content=csv_bytes(rows), headers={"X-Bank-Key": "demo-bank001-key"}
        )
        response.raise_for_status()
    assert run_sync().status == "SUCCEEDED"
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK001'"
            ).fetchone()[0]
            == 110
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK001' AND loan_account_number<='LOAN_000040' AND outstanding_principal_balance=777.77"
            ).fetchone()[0]
            == 40
        )
