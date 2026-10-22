import csv
import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient

from external_bank.app import create_app
from tools.generate_synthetic import credit, generate
from tools.seed import split_sources, tenant_for


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


@pytest.fixture
def bank(tmp_path):
    with TestClient(create_app(tmp_path / "bank.sqlite")) as client:
        yield client


BASE = "/v1/tenants/BANK001/loans/RETAIL"
HEADERS = {"X-Bank-Key": "demo-bank001-key", "Content-Type": "text/csv"}


def test_bank_contract_and_raw_values(bank):
    rows = [credit(i) for i in (1, 2)]
    rows[0].update(
        loan_start_date="15.01.2024", nominal_interest_rate="18.5%", loan_status_code="Kapalı"
    )
    result = bank.put(BASE + "/credit", content=csv_bytes(rows), headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["version"] == 1
    response = bank.get(BASE + "/credit/records", headers=HEADERS)
    assert response.headers["content-type"] == "application/x-ndjson"
    assert [json.loads(line) for line in response.content.splitlines()] == rows
    meta = bank.get(BASE + "/meta", headers=HEADERS).json()
    assert meta["datasets"]["credit"] == {
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "row_count": 2,
    }
    update = credit(1)
    update["outstanding_principal_balance"] = "999.99"
    result = bank.patch(BASE + "/credit", content=csv_bytes([update, credit(3)]), headers=HEADERS)
    assert result.json()["version"] == 2
    cursor, items = 0, []
    while True:
        page = bank.get(
            BASE + f"/credit/records?format=json&limit=1&cursor={cursor}", headers=HEADERS
        ).json()
        items.extend(page["results"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(items) == 3
    assert next(r for r in items if r["loan_account_number"] == "LOAN_000001") == update
    assert (
        bank.get(BASE.replace("BANK001", "BANK002") + "/meta", headers=HEADERS).status_code == 403
    )
    assert bank.get(BASE + "/meta").status_code == 401


def test_bank_put_preserves_duplicates_and_malformed_csv_rolls_back(bank):
    rows = [credit(1), credit(1)]
    assert (
        bank.put(BASE + "/credit", content=csv_bytes(rows), headers=HEADERS).json()["datasets"][
            "credit"
        ]["row_count"]
        == 2
    )
    before = bank.get(BASE + "/meta", headers=HEADERS).json()
    assert bank.put(BASE + "/credit", content=b"a;b\n1;2;3\n", headers=HEADERS).status_code == 400
    assert bank.get(BASE + "/meta", headers=HEADERS).json() == before
    assert (
        bank.put(BASE + "/credit", content=csv_bytes([credit(4)]), headers=HEADERS).json()[
            "datasets"
        ]["credit"]["row_count"]
        == 1
    )


def test_synthetic_seed_keeps_loans_and_plans_in_same_tenant(tmp_path):
    source, parts = tmp_path / "source", tmp_path / "parts"
    generate(source, count=30, installments=3)
    split_sources(source, parts)
    all_ids = set()
    for kind in ("retail", "commercial"):
        for tenant in ("BANK001", "BANK002", "BANK003"):
            with (parts / f"{tenant}_{kind}_credit.csv").open() as stream:
                rows = list(csv.DictReader(stream, delimiter=";"))
            assert rows
            ids = {r["loan_account_number"] for r in rows}
            assert not all_ids.intersection(ids)
            all_ids.update(ids)
            assert all(tenant_for(row["customer_id"]) == tenant for row in rows)
            with (parts / f"{tenant}_{kind}_payment_plan.csv").open() as stream:
                plans = list(csv.DictReader(stream, delimiter=";"))
            assert len(plans) == len(rows) * 3
            assert {p["loan_account_number"] for p in plans} == ids
