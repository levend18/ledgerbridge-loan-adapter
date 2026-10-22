from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any
import time

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from adapter.shared import (
    DatasetKind,
    Issue,
    LoanType,
    ProcessReport,
    Severity,
    Unit,
    ValidationReport,
)


class Table(StrEnum):
    RETAIL = "fact_loan_retail"
    COMMERCIAL = "fact_loan_commercial"
    PLAN = "fact_installment"


def credit_table(unit: Unit) -> Table:
    return Table.RETAIL if unit.loan_type == LoanType.RETAIL else Table.COMMERCIAL


class PostgresWarehouse:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.conn = connection
        self.gc_duration_ms = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.conn.transaction():
            yield

    @contextmanager
    def lock(self, unit: Unit) -> Iterator[bool]:
        key = f"{unit.tenant}:{unit.loan_type}"
        row = self.conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (key,)).fetchone()
        acquired = bool(row and row[0])
        try:
            yield acquired
        finally:
            if acquired:
                self.conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))

    def current_version(self, unit: Unit) -> int | None:
        row = self.conn.execute(
            "SELECT source_version FROM dwh.current_snapshot WHERE tenant_id=%s AND loan_type=%s",
            (unit.tenant, unit.loan_type),
        ).fetchone()
        return int(row[0]) if row else None

    def load(self, unit: Unit, batch: str, report: ProcessReport) -> None:
        with self.conn.transaction():
            for kind, filename in report.outputs.items():
                table = credit_table(unit) if kind == DatasetKind.CREDIT else Table.PLAN
                columns = [
                    r[0]
                    for r in self.conn.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='dwh' AND table_name=%s AND column_name NOT IN ('tenant_id','batch_id','loan_type','source_row_number') ORDER BY column_name",
                        (table,),
                    )
                ]
                prefix = [str(unit.tenant), batch]
                metadata = ["tenant_id", "batch_id"]
                if kind == DatasetKind.PAYMENT_PLAN:
                    prefix.append(str(unit.loan_type))
                    metadata.append("loan_type")
                statement = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
                    sql.Identifier("dwh"),
                    sql.Identifier(table),
                    sql.SQL(",").join(
                        map(sql.Identifier, [*metadata, "source_row_number", *columns])
                    ),
                )
                with self.conn.cursor().copy(statement) as copy, Path(filename).open() as source:
                    for line in source:
                        copy.write("\t".join(prefix) + "\t" + line)

    def validate(self, unit: Unit, batch: str) -> ValidationReport:
        report = ValidationReport()
        credit = sql.Identifier("dwh", credit_table(unit))
        plan = sql.Identifier("dwh", Table.PLAN)
        checks = [
            (
                "credit",
                "DUPLICATE_KEY",
                Severity.ERROR,
                sql.SQL(
                    "SELECT source_row_number,loan_account_number FROM (SELECT source_row_number,loan_account_number,count(*) OVER(PARTITION BY loan_account_number) AS n FROM {} WHERE tenant_id=%s AND batch_id=%s) s WHERE n>1"
                ).format(credit),
                (unit.tenant, batch),
            ),
            (
                "payment_plan",
                "DUPLICATE_KEY",
                Severity.ERROR,
                sql.SQL(
                    "SELECT source_row_number,loan_account_number FROM (SELECT source_row_number,loan_account_number,count(*) OVER(PARTITION BY loan_account_number,installment_number) AS n FROM {} WHERE tenant_id=%s AND batch_id=%s AND loan_type=%s) s WHERE n>1"
                ).format(plan),
                (unit.tenant, batch, unit.loan_type),
            ),
            (
                "payment_plan",
                "ORPHAN_PAYMENT",
                Severity.ERROR,
                sql.SQL(
                    "SELECT p.source_row_number,p.loan_account_number FROM {} p WHERE p.tenant_id=%s AND p.batch_id=%s AND p.loan_type=%s AND NOT EXISTS(SELECT 1 FROM {} c WHERE c.tenant_id=p.tenant_id AND c.batch_id=p.batch_id AND c.loan_account_number=p.loan_account_number)"
                ).format(plan, credit),
                (unit.tenant, batch, unit.loan_type),
            ),
            (
                "credit",
                "MISSING_PAYMENT_PLAN",
                Severity.WARNING,
                sql.SQL(
                    "SELECT c.source_row_number,c.loan_account_number FROM {} c WHERE c.tenant_id=%s AND c.batch_id=%s AND NOT EXISTS(SELECT 1 FROM {} p WHERE p.tenant_id=c.tenant_id AND p.batch_id=c.batch_id AND p.loan_type=%s AND p.loan_account_number=c.loan_account_number)"
                ).format(credit, plan),
                (unit.tenant, batch, unit.loan_type),
            ),
            (
                "credit",
                "PLAN_COUNT_MISMATCH",
                Severity.WARNING,
                sql.SQL(
                    "SELECT c.source_row_number,c.loan_account_number FROM {} c LEFT JOIN (SELECT loan_account_number,count(*) AS n FROM {} WHERE tenant_id=%s AND batch_id=%s AND loan_type=%s GROUP BY loan_account_number) p USING(loan_account_number) WHERE c.tenant_id=%s AND c.batch_id=%s AND c.total_installment_count<>coalesce(p.n,0)"
                ).format(credit, plan),
                (unit.tenant, batch, unit.loan_type, unit.tenant, batch),
            ),
        ]
        for dataset, rule, severity, query, params in checks:
            bounded = sql.SQL(
                "SELECT source_row_number,loan_account_number,count(*) OVER() FROM ({}) AS issues ORDER BY source_row_number LIMIT 1000"
            ).format(query)
            for index, (row, key, total) in enumerate(self.conn.execute(bounded, params)):
                report.add(
                    Issue(
                        dataset,
                        row,
                        key,
                        "loan_account_number",
                        rule,
                        severity,
                        raw_value=key,
                        message=rule,
                    ),
                    count=total if index == 0 else 0,
                )
        return report

    def discard(self, unit: Unit, batch: str) -> None:
        with self.conn.transaction():
            self.conn.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id=%s AND batch_id=%s").format(
                    sql.Identifier("dwh", credit_table(unit))
                ),
                (unit.tenant, batch),
            )
            self.conn.execute(
                "DELETE FROM dwh.fact_installment WHERE tenant_id=%s AND loan_type=%s AND batch_id=%s",
                (unit.tenant, unit.loan_type, batch),
            )

    def publish(self, unit: Unit, batch: str, version: int, report: ProcessReport) -> None:
        self.conn.execute(
            "INSERT INTO dwh.current_snapshot(tenant_id,loan_type,batch_id,source_version,row_counts) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,loan_type) DO UPDATE SET batch_id=excluded.batch_id,source_version=excluded.source_version,row_counts=excluded.row_counts,published_at=now()",
            (unit.tenant, unit.loan_type, batch, version, Jsonb(report.row_counts)),
        )

    def collect_garbage(self, unit: Unit) -> None:
        start = time.monotonic()
        with self.conn.transaction():
            self.conn.execute(
                sql.SQL(
                    "DELETE FROM {} WHERE tenant_id=%s AND batch_id IS DISTINCT FROM (SELECT batch_id FROM dwh.current_snapshot WHERE tenant_id=%s AND loan_type=%s)"
                ).format(sql.Identifier("dwh", credit_table(unit))),
                (unit.tenant, unit.tenant, unit.loan_type),
            )
            self.conn.execute(
                "DELETE FROM dwh.fact_installment WHERE tenant_id=%s AND loan_type=%s AND batch_id IS DISTINCT FROM (SELECT batch_id FROM dwh.current_snapshot WHERE tenant_id=%s AND loan_type=%s)",
                (unit.tenant, unit.loan_type, unit.tenant, unit.loan_type),
            )
        self.gc_duration_ms = int((time.monotonic() - start) * 1000)
