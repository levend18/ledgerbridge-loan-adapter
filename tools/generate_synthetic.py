import argparse
import csv
from functools import cache
from pathlib import Path

import yaml

SCHEMAS = Path(__file__).resolve().parents[1] / "adapter/quality/schemas"


@cache
def columns(dataset):
    return yaml.safe_load((SCHEMAS / f"{dataset}.yaml").read_text())["columns"]


def credit(index, loan_type="retail", installments=12):
    row = {k: "" for k in columns(f"{loan_type}_credit")}
    row.update(
        loan_account_number=f"LOAN_{index:06d}",
        customer_id=f"CUST_{index:06d}",
        customer_type="I" if loan_type == "retail" else "V",
        loan_status_code="A",
        days_past_due="0",
        loan_start_date="20240115",
        final_maturity_date="20300115",
        first_payment_date="2024-02-15",
        original_loan_amount="12000.00",
        outstanding_principal_balance="12000.00",
        nominal_interest_rate="18.5",
        total_installment_count=str(installments),
        outstanding_installment_count=str(installments),
        paid_installment_count="0",
        total_interest_amount="120.00",
        kkdf_rate="0",
        kkdf_amount="0",
        bsmv_rate="0",
        bsmv_amount="0",
        grace_period_months="0",
        installment_frequency="1",
        internal_rating="A",
        external_rating="A",
    )
    if loan_type == "retail":
        row.update(insurance_included="E", customer_province_code="34", customer_district_code="1")
    else:
        row.update(default_probability="0.185", loan_status_flag="A", sector_code="4")
    return row


def payment(index, number):
    row = {k: "" for k in columns("payment_plan")}
    row.update(
        loan_account_number=f"LOAN_{index:06d}",
        installment_number=str(number),
        scheduled_payment_date="2025-01-15",
        installment_amount="1010.00",
        principal_component="1000.00",
        interest_component="10.00",
        kkdf_component="0",
        bsmv_component="0",
        installment_status="A",
        remaining_principal="1000.00",
        remaining_interest="10.00",
        remaining_kkdf="0",
        remaining_bsmv="0",
    )
    return row


def generate(directory, count=100, installments=12):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if count > 400000 or count < 1:
        raise ValueError("count must be between 1 and 400000")
    for loan_type, offset in (("retail", 0), ("commercial", 500000)):
        with (
            (directory / f"{loan_type}_credit_masked.csv").open("w", newline="") as credits,
            (directory / f"{loan_type}_payment_plan_masked.csv").open("w", newline="") as plans,
        ):
            cw = csv.DictWriter(credits, fieldnames=columns(f"{loan_type}_credit"), delimiter=";")
            pw = csv.DictWriter(plans, fieldnames=columns("payment_plan"), delimiter=";")
            cw.writeheader()
            pw.writeheader()
            for index in range(offset + 1, offset + count + 1):
                cw.writerow(credit(index, loan_type, installments))
                for number in range(1, installments + 1):
                    pw.writerow(payment(index, number))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/synthetic")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--installments", type=int, default=12)
    args = parser.parse_args()
    generate(args.output, args.count, args.installments)
