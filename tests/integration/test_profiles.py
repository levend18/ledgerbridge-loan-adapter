import math
from decimal import Decimal

import pytest
from psycopg import sql

from adapter.shared import LoanType, Unit, TenantId
from adapter.warehouse.infrastructure.postgres import Table
from tests.integration.test_api import api_users, client, login
from tests.integration.test_sync_pipeline import upload, run_sync
from tests.integration.test_warehouse import clean_warehouse, connect
from tools.generate_synthetic import columns, credit, payment

__all__ = ["api_users", "client", "clean_warehouse"]


@pytest.mark.parametrize("kind", list(LoanType))
def test_v18_every_profile_matches_sql(client, kind):
    target = Unit(TenantId.BANK001, kind)
    rows = [credit(i, kind.lower(), 1) for i in range(1, 21)]
    for index, row in enumerate(rows):
        row["original_loan_amount"] = str(Decimal("10000.255") + index)
        row["internal_rating"] = ["A", "B", "A", ""][index % 4]
    upload(rows, [payment(i, 1) for i in range(1, 21)], target)
    run = run_sync(target)
    assert run.status == "SUCCEEDED"
    login(client)
    response = client.get("/api/profiling", {"loan_type": kind})
    assert response.status_code == 200
    assert response.data["snapshot"]["batch_id"] == run.batch_id
    datasets = response.data["datasets"]
    assert datasets["credit"]["loan_closing_date"]["null_ratio"] == 1
    with connect("app_reader") as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id','BANK001',true)")
        for dataset in ("credit", "payment_plan"):
            table = (
                (Table.RETAIL if kind == LoanType.RETAIL else Table.COMMERCIAL)
                if dataset == "credit"
                else Table.PLAN
            )
            schema = columns(f"{kind.lower()}_credit" if dataset == "credit" else "payment_plan")
            assert set(datasets[dataset]) == set(schema)
            for name, definition in schema.items():
                column = sql.Identifier(name)
                predicate = (
                    sql.SQL("loan_type=%s")
                    if dataset == "payment_plan"
                    else sql.SQL("%s::text IS NOT NULL")
                )
                total, nonnull = conn.execute(
                    sql.SQL("SELECT count(*),count({}) FROM {} WHERE {}").format(
                        column, sql.Identifier("dwh", table), predicate
                    ),
                    (kind,),
                ).fetchone()
                stats = datasets[dataset][name]
                assert stats["null_ratio"] == (total - nonnull) / total
                assert stats["count"] == nonnull
                if definition["type"] in ("int", "money", "rate"):
                    aggregates = conn.execute(
                        sql.SQL(
                            "SELECT min({c}),max({c}),avg({c}),stddev_samp({c}) FROM {t} WHERE {p}"
                        ).format(c=column, t=sql.Identifier("dwh", table), p=predicate),
                        (kind,),
                    ).fetchone()
                    for field, expected in zip(("min", "max", "mean", "stddev"), aggregates):
                        if expected is None:
                            assert stats[field] is None
                        else:
                            assert math.isclose(
                                stats[field], float(expected), rel_tol=1e-9, abs_tol=1e-12
                            )
                elif definition["type"] == "date":
                    low, high = conn.execute(
                        sql.SQL("SELECT min({c}),max({c}) FROM {t} WHERE {p}").format(
                            c=column, t=sql.Identifier("dwh", table), p=predicate
                        ),
                        (kind,),
                    ).fetchone()
                    assert stats["min"] == (low.isoformat() if low else None)
                    assert stats["max"] == (high.isoformat() if high else None)
                else:
                    distinct, mode = conn.execute(
                        sql.SQL(
                            "SELECT count(DISTINCT {c}),mode() WITHIN GROUP(ORDER BY {c}) FROM {t} WHERE {p}"
                        ).format(c=column, t=sql.Identifier("dwh", table), p=predicate),
                        (kind,),
                    ).fetchone()
                    assert stats["distinct_count"] == distinct
                    if isinstance(mode, bool):
                        mode = str(mode).lower()
                    assert stats["most_frequent"] == mode
    rows[0]["original_loan_amount"] = "-1"
    upload(rows, [payment(i, 1) for i in range(1, 21)], target)
    rejected = run_sync(target)
    assert rejected.status == "REJECTED"
    after = client.get("/api/profiling", {"loan_type": kind})
    assert after.data == response.data


@pytest.mark.parametrize("kind", list(LoanType))
def test_v18_high_cardinality_profiles_are_exact(client, kind):
    target = Unit(TenantId.BANK001, kind)
    rows = [credit(i, kind.lower(), 1) for i in range(1, 1008)]
    for i in range(1001, 1007):
        rows[i]["customer_id"] = "CUST_000999" if i % 2 else "CUST_001000"
    upload(rows, [payment(i, 1) for i in range(1, 1008)], target)
    run = run_sync(target)
    assert run.status == "SUCCEEDED"
    login(client)
    response = client.get("/api/profiling", {"loan_type": kind})
    assert response.status_code == 200
    profile = response.data["datasets"]["credit"]["customer_id"]
    assert profile["count"] == 1007
    assert profile["null_ratio"] == 0
    assert profile["high_cardinality"] is True
    assert profile["distinct_count"] == 1001
    assert profile["most_frequent"] == "CUST_000999"
    assert profile["top"][:2] == [
        {"value": "CUST_000999", "count": 4},
        {"value": "CUST_001000", "count": 4},
    ]
    assert len(profile["top"]) == 10
    plans = response.data["datasets"]["payment_plan"]["loan_account_number"]
    assert plans["distinct_count"] == 1007
    assert plans["most_frequent"] == "LOAN_000001"
    assert len(plans["top"]) == 10
    login(client, 2)
    other = client.get("/api/profiling", {"tenant_id": "BANK001", "loan_type": kind})
    assert other.status_code == 403
