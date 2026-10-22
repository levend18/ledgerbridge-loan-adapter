import csv
import hashlib
import os
import sqlite3
import tempfile
from contextlib import ExitStack
from pathlib import Path

import httpx

from tools.generate_synthetic import generate

TENANTS = ("BANK001", "BANK002", "BANK003")


def tenant_for(customer):
    return TENANTS[int.from_bytes(hashlib.sha256(customer.encode()).digest()[:8], "big") % 3]


def split_sources(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination / "mapping.sqlite") as mapping:
        mapping.execute(
            "CREATE TABLE loans (kind TEXT, id TEXT, tenant TEXT, PRIMARY KEY(kind,id))"
        )
        for kind in ("retail", "commercial"):
            for dataset in ("credit", "payment_plan"):
                with ExitStack() as stack:
                    stream = stack.enter_context(
                        (source / f"{kind}_{dataset}_masked.csv").open(
                            encoding="utf-8-sig", newline=""
                        )
                    )
                    reader = csv.DictReader(stream, delimiter=";")
                    writers = {}
                    for tenant in TENANTS:
                        target = stack.enter_context(
                            (destination / f"{tenant}_{kind}_{dataset}.csv").open("w", newline="")
                        )
                        writers[tenant] = csv.DictWriter(
                            target, fieldnames=reader.fieldnames, delimiter=";"
                        )
                        writers[tenant].writeheader()
                    for row in reader:
                        if dataset == "credit":
                            tenant = tenant_for(row["customer_id"])
                            mapping.execute(
                                "INSERT INTO loans VALUES(?,?,?)",
                                (kind, row["loan_account_number"], tenant),
                            )
                        else:
                            match = mapping.execute(
                                "SELECT tenant FROM loans WHERE kind=? AND id=?",
                                (kind, row["loan_account_number"]),
                            ).fetchone()
                            if match is None:
                                raise ValueError("Source plan has no matching loan")
                            tenant = match[0]
                        writers[tenant].writerow(row)


def main():
    with tempfile.TemporaryDirectory(prefix="ledgerbridge-seed-") as work:
        root = Path(work)
        source = Path(os.environ.get("DATA_DIR", "/app/data"))
        if not (source / "retail_credit_masked.csv").exists():
            source = root / "synthetic"
            generate(source)
        parts = root / "parts"
        split_sources(source, parts)
        updates = Path("artifacts/seed-v2")
        updates.mkdir(parents=True, exist_ok=True)
        for part in parts.glob("*_credit.csv"):
            with (
                part.open(newline="") as stream,
                (updates / part.name).open("w", newline="") as output,
            ):
                reader = csv.DictReader(stream, delimiter=";")
                writer = csv.DictWriter(output, fieldnames=reader.fieldnames, delimiter=";")
                writer.writeheader()
                for index, row in enumerate(reader):
                    if index == 50:
                        break
                    row["outstanding_principal_balance"] = "100.00"
                    writer.writerow(row)
        with httpx.Client(
            base_url=os.environ.get("BANK_BASE_URL", "http://bank:8001"), timeout=300
        ) as client:
            for tenant in TENANTS:
                for kind in ("retail", "commercial"):
                    for dataset in ("credit", "payment_plan"):
                        with (parts / f"{tenant}_{kind}_{dataset}.csv").open("rb") as source_file:
                            response = client.put(
                                f"/v1/tenants/{tenant}/loans/{kind.upper()}/{dataset}",
                                headers={
                                    "X-Bank-Key": os.environ.get(
                                        f"BANK_KEY_{tenant}", f"demo-{tenant.lower()}-key"
                                    ),
                                    "Content-Type": "text/csv",
                                },
                                content=source_file,
                            )
                            response.raise_for_status()
        print("Loaded six units into the bank simulator")


if __name__ == "__main__":
    main()
