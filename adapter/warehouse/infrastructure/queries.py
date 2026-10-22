import base64
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from adapter.shared import DatasetKind, Json, TenantId, Unit
from adapter.warehouse.infrastructure.postgres import Table, credit_table


def json_value(value: Any) -> Json:
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(type(value).__name__)


class ReaderQueries:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def transaction(self, tenant: TenantId) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SELECT set_config('app.tenant_id',%s,true)", (tenant,))
            yield conn

    def data(self, unit: Unit, dataset: DatasetKind, cursor: str = "", limit: int = 100) -> Json:
        table = credit_table(unit) if dataset == DatasetKind.CREDIT else Table.PLAN
        with self.transaction(unit.tenant) as conn:
            snapshot = conn.execute(
                "SELECT batch_id,source_version,published_at,row_counts FROM dwh.current_snapshot WHERE loan_type=%s",
                (unit.loan_type,),
            ).fetchone()
            if snapshot is None:
                raise LookupError("no-snapshot")
            key, number = "", 0
            if cursor:
                try:
                    decoded = json.loads(base64.urlsafe_b64decode(cursor))
                    if str(snapshot["batch_id"]) != decoded["batch"]:
                        raise ValueError("Snapshot changed; restart pagination")
                    key, number = str(decoded["key"]), int(decoded["number"])
                except (KeyError, TypeError, UnicodeError) as exc:
                    raise ValueError("Invalid cursor") from exc
            where = (
                sql.SQL(" AND (loan_account_number,installment_number)>(%s,%s) AND loan_type=%s")
                if dataset == DatasetKind.PAYMENT_PLAN
                else sql.SQL(" AND loan_account_number>%s")
            )
            params: tuple[Any, ...] = (
                (key, number, unit.loan_type, limit + 1)
                if dataset == DatasetKind.PAYMENT_PLAN
                else (key, limit + 1)
            )
            order = (
                sql.SQL("loan_account_number,installment_number")
                if dataset == DatasetKind.PAYMENT_PLAN
                else sql.SQL("loan_account_number")
            )
            rows = conn.execute(
                sql.SQL("SELECT * FROM {} WHERE true {} ORDER BY {} LIMIT %s").format(
                    sql.Identifier("dwh", table), where, order
                ),
                params,
            ).fetchall()
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps(
                        {
                            "batch": str(snapshot["batch_id"]),
                            "key": last["loan_account_number"],
                            "number": last.get("installment_number", 0),
                        }
                    ).encode()
                ).decode()
            snapshot["row_count"] = snapshot["row_counts"].get(dataset, 0)
            return json_value(
                {
                    "tenant_id": unit.tenant,
                    "loan_type": unit.loan_type,
                    "dataset": dataset,
                    "snapshot": snapshot,
                    "results": rows[:limit],
                    "next_cursor": next_cursor,
                }
            )

    def runs(
        self, tenant: TenantId, loan_type: str | None = None, run_id: str | None = None
    ) -> Json:
        with self.transaction(tenant) as conn:
            rows = conn.execute(
                "SELECT * FROM ops.sync_run WHERE (%s::text IS NULL OR loan_type=%s) AND (%s::uuid IS NULL OR id=%s::uuid) ORDER BY created_at DESC LIMIT 100",
                (loan_type, loan_type, run_id, run_id),
            ).fetchall()
            if run_id:
                if not rows:
                    raise LookupError("not-found")
                return json_value(rows[0])
            return json_value({"results": rows})

    def issues(
        self, tenant: TenantId, run_id: str, severity: str | None, cursor: int, limit: int
    ) -> Json:
        with self.transaction(tenant) as conn:
            if not conn.execute("SELECT id FROM ops.sync_run WHERE id=%s", (run_id,)).fetchone():
                raise LookupError("not-found")
            rows = conn.execute(
                "SELECT id,run_id,dataset,row_number,key,column_name AS column,rule_id,severity,raw_value,normalized_value,message FROM ops.validation_issue WHERE run_id=%s AND (%s::text IS NULL OR severity=%s) AND id>%s ORDER BY id LIMIT %s",
                (run_id, severity, severity, cursor, limit + 1),
            ).fetchall()
            return json_value(
                {
                    "results": rows[:limit],
                    "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
                }
            )
