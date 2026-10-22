import json
from pathlib import Path

import adapter_engine
import pytest
import yaml

SCHEMAS = Path("adapter/quality/schemas")
CODES = (SCHEMAS / "codes.yaml").read_text()


def credit_row(**overrides):
    schema = yaml.safe_load((SCHEMAS / "retail_credit.yaml").read_text())
    row = {name: "" for name in schema["columns"]}
    row.update(
        customer_id="CUST_1",
        customer_type="I",
        loan_account_number="LOAN_000001",
        loan_status_code="A",
        days_past_due="0",
        final_maturity_date="20270115",
        loan_start_date="15.01.2024",
        original_loan_amount="1.234,56",
        outstanding_principal_balance="1234.56",
        nominal_interest_rate="18.5%",
        insurance_included="Evet",
    )
    row.update(overrides)
    return row


def process(tmp_path, rows, dataset="retail_credit"):
    source, output = tmp_path / "input.ndjson", tmp_path / "output.copy"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = json.loads(
        adapter_engine.process_dataset(
            str(source),
            str(output),
            (SCHEMAS / f"{dataset}.yaml").read_text(),
            CODES,
            "2026-10-22",
        )
    )
    normalized = [
        dict(zip(["source_row_number", *report["columns"]], line.split("\t")))
        for line in output.read_text().splitlines()
    ]
    return report, normalized


@pytest.mark.parametrize(
    "date", ["20240115", "15.01.2024", "2024-01-15", "15/01/2024", "2024-01-15T00:00:00"]
)
@pytest.mark.parametrize("rate", ["18.5%", "1850 bps", "18.5"])
def test_v11_date_rate_money_and_boolean_examples(tmp_path, date, rate):
    report, rows = process(tmp_path, [credit_row(loan_start_date=date, nominal_interest_rate=rate)])
    assert rows[0]["loan_start_date"] == "2024-01-15"
    assert rows[0]["nominal_interest_rate"] == "0.185"
    assert rows[0]["original_loan_amount"] == "1234.56"
    assert rows[0]["insurance_included"] == "true"
    assert report["profiles"]["loan_closing_date"]["null_ratio"] == 1
    assert not any(key.startswith("ERROR:") for key in report["counts"])
    assert any(
        i["raw_value"] == "1.234,56" and i["normalized_value"] == "1234.56"
        for i in report["issues"]
    )


@pytest.mark.parametrize(
    "field,value,rule",
    [
        ("customer_id", "", "REQUIRED"),
        ("original_loan_amount", "abc", "INVALID_NUMBER"),
        ("original_loan_amount", "-1", "OUT_OF_RANGE"),
        ("nominal_interest_rate", "201%", "OUT_OF_RANGE"),
        ("customer_type", "UNKNOWN", "UNKNOWN_CODE"),
        ("loan_start_date", "30.02.2024", "INVALID_DATE"),
        ("final_maturity_date", "20200101", "MATURITY_AFTER_START"),
    ],
)
def test_invalid_fields_are_reported_and_not_written(tmp_path, field, value, rule):
    report, rows = process(tmp_path, [credit_row(**{field: value})])
    assert report["counts"][f"ERROR:{rule}"] == 1
    assert rows == []
    assert report["written_count"] == 0


def test_wrong_header_is_schema_mismatch(tmp_path):
    row = credit_row()
    row["wrong_column"] = row.pop("customer_id")
    with pytest.raises(ValueError, match="SCHEMA_MISMATCH"):
        process(tmp_path, [row])


def test_issue_cap_preserves_counts_and_rates_do_not_guess_per_row(tmp_path):
    rows = [credit_row(nominal_interest_rate="18.5") for _ in range(1001)]
    rows.append(credit_row(nominal_interest_rate="0.185"))
    report, output = process(tmp_path, rows)
    assert len(report["issues"]) == 1000
    assert report["counts"]["CORRECTED:NORMALIZED"] > 1000
    assert report["unit_decisions"]["nominal_interest_rate"] == "percent"
    assert output[-1]["nominal_interest_rate"] == "0.00185"
    assert report["counts"]["WARNING:UNIT_AMBIGUOUS_VALUE"] == 1


def test_rate_one_hundred_warns_but_remains_publishable(tmp_path):
    report, rows = process(tmp_path, [credit_row(nominal_interest_rate="100.00")])
    assert rows[0]["nominal_interest_rate"] == "1"
    assert report["counts"]["WARNING:RATE_IMPLAUSIBLE"] == 1
    assert not any(key.startswith("ERROR:") for key in report["counts"])


@pytest.mark.parametrize("code", ["K", "Kapalı", "KAPALI ", "kapali", "Paid", "Closed"])
def test_closed_installments_zero_remaining_and_preserve_correction_evidence(tmp_path, code):
    schema = yaml.safe_load((SCHEMAS / "payment_plan.yaml").read_text())
    row = {name: "" for name in schema["columns"]}
    row.update(
        loan_account_number="LOAN_000001",
        installment_number="1",
        scheduled_payment_date="20240115",
        installment_amount="100",
        installment_status=code,
        remaining_principal="20",
        remaining_interest="1",
        remaining_kkdf="0",
        remaining_bsmv="0",
    )
    report, rows = process(tmp_path, [row], "payment_plan")
    assert rows[0]["installment_status"] == "CLOSED"
    assert rows[0]["remaining_principal"] == "0"
    assert report["counts"]["CORRECTED:CLOSED_REMAINING"] == 2
    assert report["counts"]["WARNING:CLOSED_WITHOUT_PAYMENT"] == 1


def test_welford_profile_matches_known_sample(tmp_path):
    report, _ = process(tmp_path, [credit_row(original_loan_amount=str(n)) for n in (10, 20, 30)])
    stats = report["profiles"]["original_loan_amount"]
    assert stats["min"] == 10
    assert stats["max"] == 30
    assert stats["mean"] == 20
    assert stats["stddev"] == 10


@pytest.mark.parametrize("header", ["wrong", "customer_id;customer_id", ""])
def test_empty_csv_rejects_invalid_headers(tmp_path, header):
    source = tmp_path / "empty.csv"
    source.write_text(header + "\n")
    with pytest.raises(ValueError, match="SCHEMA_MISMATCH"):
        adapter_engine.process_dataset(
            str(source),
            str(tmp_path / "out.copy"),
            (SCHEMAS / "retail_credit.yaml").read_text(),
            CODES,
            "2026-10-22",
        )


def test_ambiguous_money_uses_column_evidence(tmp_path):
    report, rows = process(
        tmp_path,
        [
            credit_row(original_loan_amount="1.234,56"),
            credit_row(original_loan_amount="1.234"),
        ],
    )
    assert rows[1]["original_loan_amount"] == "1234"
    assert "WARNING:AMBIGUOUS_NUMBER" not in report["counts"]
    report, rows = process(tmp_path, [credit_row(original_loan_amount="1,234")])
    assert rows[0]["original_loan_amount"] == "1.23"
    assert report["counts"]["WARNING:AMBIGUOUS_NUMBER"] == 1


def test_high_cardinality_profile_marks_its_bounded_summary(tmp_path):
    report, _ = process(tmp_path, [credit_row(customer_id=f"CUST_{i}") for i in range(1001)])
    profile = report["profiles"]["customer_id"]
    assert profile["count"] == 1001
    assert profile["high_cardinality"] is True
    assert profile["distinct_count"] is None
    assert profile["top"] == []
