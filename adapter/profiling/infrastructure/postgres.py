from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from adapter.shared import ProcessReport, Unit


class PostgresProfiles:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.conn = connection

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
