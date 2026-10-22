from enum import StrEnum
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from adapter.shared import DatasetKind, LoanType, ProcessReport, Unit


class ProfileTable(StrEnum):
    RETAIL = "fact_loan_retail"
    COMMERCIAL = "fact_loan_commercial"
    PLAN = "fact_installment"


class PostgresProfiles:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.conn = connection

    def prepare(self, unit: Unit, batch: str, report: ProcessReport) -> None:
        for dataset, columns in report.profiles.items():
            if not isinstance(columns, dict):
                raise ValueError("Expected column profiles")
            kind = DatasetKind(dataset)
            table = (
                ProfileTable.PLAN
                if kind == DatasetKind.PAYMENT_PLAN
                else ProfileTable.RETAIL
                if unit.loan_type == LoanType.RETAIL
                else ProfileTable.COMMERCIAL
            )
            for name, stats in columns.items():
                if not isinstance(stats, dict) or not stats.get("high_cardinality"):
                    continue
                # Aggregate before pointer publication; only ten rows enter worker memory.
                rows = self.conn.execute(
                    sql.SQL(
                        "SELECT {column}::text AS value, count(*) AS frequency, "
                        "count(*) OVER () AS distinct_count FROM {table} "
                        "WHERE tenant_id=%s AND batch_id=%s AND {column} IS NOT NULL "
                        'GROUP BY {column} ORDER BY frequency DESC, {column}::text COLLATE "C" LIMIT 10'
                    ).format(column=sql.Identifier(name), table=sql.Identifier("dwh", table)),
                    (unit.tenant, batch),
                ).fetchall()
                stats["distinct_count"] = rows[0][2] if rows else 0
                stats["most_frequent"] = rows[0][0] if rows else None
                stats["top"] = [{"value": row[0], "count": row[1]} for row in rows]

    def save(self, unit: Unit, batch: str, report: ProcessReport) -> None:
        for dataset, columns in report.profiles.items():
            if not isinstance(columns, dict):
                raise ValueError("Expected column profiles")
            with self.conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO ops.column_profile VALUES(%s,%s,%s,%s,%s,%s)",
                    [
                        (unit.tenant, unit.loan_type, batch, dataset, name, Jsonb(stats))
                        for name, stats in columns.items()
                    ],
                )
