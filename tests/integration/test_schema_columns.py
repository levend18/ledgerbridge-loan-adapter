import os
from pathlib import Path

import psycopg
import yaml


def test_yaml_columns_match_warehouse_columns():
    schemas = Path("adapter/quality/schemas")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for name, table in (
            ("retail_credit", "fact_loan_retail"),
            ("commercial_credit", "fact_loan_commercial"),
            ("payment_plan", "fact_installment"),
        ):
            columns = set(yaml.safe_load((schemas / f"{name}.yaml").read_text())["columns"])
            actual = {
                row[0]
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='dwh' AND table_name=%s",
                    (table,),
                )
            }
            metadata = {"tenant_id", "batch_id", "source_row_number"}
            if name == "payment_plan":
                metadata.add("loan_type")
            assert actual - metadata == columns
