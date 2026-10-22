import os
from datetime import timedelta
from uuid import uuid4

import pytest

from adapter.shared import LoanType, TenantId, Unit
from tests.integration.test_sync_pipeline import run_sync, upload
from tests.integration.test_warehouse import clean_warehouse
from tools.generate_synthetic import credit, payment

__all__ = ["clean_warehouse"]


@pytest.fixture(scope="module")
def api_users():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.config.settings")
    from tools.seed_users import seed_users

    seed_users()


@pytest.fixture
def client(api_users):
    from rest_framework.test import APIClient

    return APIClient()


def token(client, tenant=1):
    response = client.post(
        "/api/auth/token",
        {"username": f"bank00{tenant}_user", "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 200
    return response.data["access"]


def login(client, tenant=1):
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token(client, tenant))


def test_v01_every_non_whitelisted_route_requires_auth(client):
    from api.config.urls import urlpatterns

    whitelist = {
        "api/health",
        "api/auth/token",
        "api/auth/token/refresh",
        "api/schema/",
        "api/docs/",
    }
    for entry in urlpatterns:
        route = str(entry.pattern)
        if route in whitelist:
            continue
        path = "/" + route.replace("<uuid:run_id>", str(uuid4()))
        response = client.get(path)
        assert response.status_code == 401, path
        assert response["Content-Type"] == "application/problem+json"


def test_v02_invalid_and_expired_tokens(client):
    from rest_framework_simplejwt.tokens import AccessToken

    valid = token(client)
    bad = valid[:-10] + "aaaaaaaaaa"
    expired = AccessToken(valid)
    expired.set_exp(lifetime=timedelta(seconds=-10))
    for value in (bad, str(expired)):
        client.credentials(HTTP_AUTHORIZATION="Bearer " + value)
        response = client.get("/api/data")
        assert response.status_code == 401
        assert response["Content-Type"] == "application/problem+json"
    client.credentials(HTTP_X_API_KEY="invalid-key")
    assert client.get("/api/data").status_code == 401


def test_v03_v06_data_isolated_and_paginated(client):
    sets = {}
    for index, tenant in enumerate(TenantId):
        for kind in LoanType:
            offset = index * 1000 + (500000 if kind == LoanType.COMMERCIAL else 0)
            ids = list(range(offset + 1, offset + 8))
            target = Unit(tenant, kind)
            upload(
                [credit(i, kind.lower(), 2) for i in ids],
                [payment(i, n) for i in ids for n in (1, 2)],
                target,
            )
            assert run_sync(target).status == "SUCCEEDED"
            sets[(tenant, kind)] = {f"LOAN_{i:06d}" for i in ids}
    login(client)
    for kind in LoanType:
        for dataset in ("credit", "payment_plan"):
            cursor, rows = "", []
            while True:
                response = client.get(
                    "/api/data",
                    {
                        "tenant_id": "BANK001",
                        "loan_type": kind,
                        "dataset": dataset,
                        "limit": 3,
                        "cursor": cursor,
                    },
                )
                assert response.status_code == 200, response.data
                rows.extend(response.data["results"])
                cursor = response.data["next_cursor"]
                if not cursor:
                    break
            assert len(rows) == (7 if dataset == "credit" else 14)
            assert {r["tenant_id"] for r in rows} == {"BANK001"}
            assert {r["loan_account_number"] for r in rows} == sets[(TenantId.BANK001, kind)]
            assert not {r["loan_account_number"] for r in rows}.intersection(
                sets[(TenantId.BANK002, kind)]
            )
            if dataset == "credit":
                assert isinstance(rows[0]["original_loan_amount"], str)
                assert ("insurance_included" in rows[0]) == (kind == LoanType.RETAIL)
                assert ("sector_code" in rows[0]) == (kind == LoanType.COMMERCIAL)


def test_v04_tenant_mismatch_and_hidden_runs(client):
    target = Unit(TenantId.BANK002, LoanType.RETAIL)
    upload([credit(2001)], [payment(2001, 1)], target)
    run = run_sync(target)
    login(client)
    for path in ("/api/data", "/api/runs", "/api/validation-issues", "/api/profiling"):
        response = client.get(path, {"tenant_id": "BANK002", "sync_run_id": run.id})
        assert response.status_code == 403
        assert "tenant-mismatch" in response.data["type"]
    assert (
        client.post(
            "/api/sync", {"tenant_id": "BANK002", "loan_type": "RETAIL"}, format="json"
        ).status_code
        == 403
    )
    assert client.get(f"/api/sync/{run.id}").status_code == 404
    assert client.get("/api/validation-issues", {"sync_run_id": run.id}).status_code == 404


def test_sync_post_conflict_and_status(client):
    from workers.runtime import execute

    upload([credit(1)], [payment(1, 1)])
    login(client)
    response = client.post(
        "/api/sync", {"tenant_id": "BANK001", "loan_type": "RETAIL"}, format="json"
    )
    assert response.status_code == 202
    run_id = response.data["sync_run_id"]
    duplicate = client.post("/api/sync", {"loan_type": "RETAIL"}, format="json")
    assert duplicate.status_code == 409
    assert duplicate.data["sync_run_id"] == run_id
    execute(run_id)
    detail = client.get(f"/api/sync/{run_id}")
    assert detail.status_code == 200
    assert detail.data["status"] == "SUCCEEDED"
    assert detail.data["counts"] == {"credit": 1, "payment_plan": 1}
    assert detail.data["duration_ms"] > 0


def test_bad_parameters_and_no_snapshot_are_problems(client):
    login(client)
    assert client.get("/api/data").status_code == 404
    for query in ({"loan_type": "other"}, {"dataset": "other"}, {"limit": "-1"}, {"limit": "1001"}):
        response = client.get("/api/data", query)
        assert response.status_code == 400
        assert response["Content-Type"] == "application/problem+json"


def test_v15_api_reads_remain_consistent_during_ten_publications(client, record_property):
    import threading
    import time
    from rest_framework.test import APIClient

    upload(
        [credit(i, installments=1) for i in range(1, 1001)], [payment(i, 1) for i in range(1, 1001)]
    )
    assert run_sync().status == "SUCCEEDED"
    access = token(client)
    ready, stop = threading.Event(), threading.Event()
    errors, timings, observations = [], [], []

    def read_loop():
        reader = APIClient()
        reader.credentials(HTTP_AUTHORIZATION="Bearer " + access)
        try:
            while not stop.is_set():
                start = time.monotonic()
                response = reader.get("/api/data", {"limit": 1000})
                timings.append(time.monotonic() - start)
                assert response.status_code == 200
                snapshot = response.data["snapshot"]
                assert snapshot["row_counts"]["credit"] == snapshot["row_counts"]["payment_plan"]
                assert snapshot["row_count"] in (1000, 2000)
                assert len(response.data["results"]) == 1000
                assert {r["batch_id"] for r in response.data["results"]} == {snapshot["batch_id"]}
                observations.append(snapshot["batch_id"])
                ready.set()
        except BaseException as exc:
            errors.append(exc)
            ready.set()

    thread = threading.Thread(target=read_loop)
    thread.start()
    try:
        assert ready.wait(10)
        for index in range(10):
            count = 2000 if index % 2 == 0 else 1000
            upload(
                [credit(i, installments=1) for i in range(1, count + 1)],
                [payment(i, 1) for i in range(1, count + 1)],
            )
            assert run_sync().status == "SUCCEEDED"
    finally:
        stop.set()
        thread.join(10)
    assert not thread.is_alive()
    assert not errors
    assert len(observations) >= 10
    record_property("api_read_p99_ms", sorted(timings)[int(len(timings) * 0.99)] * 1000)


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("Snapshot changed; restart pagination", "Snapshot changed; restart pagination"),
        (["First issue", "Second issue"], "First issue; Second issue"),
        ({"loan_type": ["Invalid choice"]}, "loan_type: Invalid choice"),
    ],
)
def test_problem_details_are_readable_without_python_representations(client, detail, expected):
    from api.views import problem_handler
    from rest_framework.exceptions import ValidationError

    response = problem_handler(ValidationError(detail), {})
    assert response.status_code == 400
    assert response.content_type == "application/problem+json"
    assert response.data["detail"] == expected
    assert response.data["title"] == expected


def test_stale_cursor_returns_a_readable_problem(client):
    login(client)
    upload([credit(i, installments=1) for i in (1, 2)], [payment(i, 1) for i in (1, 2)])
    assert run_sync(force=True).status == "SUCCEEDED"
    page = client.get("/api/data", {"limit": 1})
    assert page.status_code == 200
    cursor = page.data["next_cursor"]
    assert cursor
    assert run_sync(force=True).status == "SUCCEEDED"
    stale = client.get("/api/data", {"limit": 1, "cursor": cursor})
    assert stale.status_code == 400
    assert stale["Content-Type"] == "application/problem+json"
    assert stale.data["detail"] == "Snapshot changed; restart pagination"
