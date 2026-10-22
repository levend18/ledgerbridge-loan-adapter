import argparse
import csv
from pathlib import Path

from tools.generate_synthetic import credit, payment


def write_csv(path, rows):
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def make_dirty(directory, profile):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    credits = [credit(i, installments=1) for i in range(1, 7)]
    plans = [payment(i, 1) for i in range(1, 7)]
    if profile == "field":
        for row, (key, value) in zip(
            credits,
            [
                ("customer_id", ""),
                ("original_loan_amount", "abc"),
                ("original_loan_amount", "-1"),
                ("nominal_interest_rate", "999%"),
                ("customer_type", "unknown"),
                ("final_maturity_date", "19000101"),
            ],
        ):
            row[key] = value
    elif profile == "schema":
        for row in credits:
            row["wrong_column"] = row.pop("customer_id")
    elif profile == "normalize":
        for index, row in enumerate(credits):
            row.update(
                loan_start_date=[
                    "20240115",
                    "15.01.2024",
                    "2024-01-15",
                    "15/01/2024",
                    "2024-01-15T00:00:00",
                    "2024/01/15",
                ][index],
                nominal_interest_rate=["18.5%", "1850 bps", "18.5"][index % 3],
                original_loan_amount=["1.234,56", "1,234.56", "1234.56"][index % 3],
                insurance_included=["E", "Evet", "yes"][index % 3],
            )
        for index, row in enumerate(plans):
            row.update(
                installment_status=["K", "Kapalı", "KAPALI ", "kapali", "Paid", "Closed"][index],
                actual_payment_date="20240115",
            )
    elif profile == "cross":
        plans[0]["loan_account_number"] = "LOAN_999999"
        credits.append(credits[1].copy())
        plans.append(plans[1].copy())
    write_csv(directory / "credit.csv", credits)
    write_csv(directory / "payment_plan.csv", plans)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile", choices=["field", "schema", "normalize", "cross"], required=True
    )
    parser.add_argument("--output", default="/tmp/dirty")
    args = parser.parse_args()
    make_dirty(args.output, args.profile)
