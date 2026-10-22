from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from adapter.ingestion.domain import SyncRun


class PostgresRuns:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.conn = connection

    def save(self, run: SyncRun) -> None:
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO ops.sync_run(id,tenant_id,loan_type,trigger,force,status,source_version,batch_id,counts,issues_summary,unit_decisions,error) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET status=excluded.status,source_version=excluded.source_version,batch_id=excluded.batch_id,counts=excluded.counts,issues_summary=excluded.issues_summary,unit_decisions=excluded.unit_decisions,error=excluded.error,updated_at=now()",
                (
                    run.id,
                    run.unit.tenant,
                    run.unit.loan_type,
                    run.trigger,
                    run.force,
                    run.status,
                    run.source_version,
                    run.batch_id or None,
                    Jsonb(run.report.row_counts),
                    Jsonb(run.report.validation.counts),
                    Jsonb(run.report.unit_decisions),
                    run.error,
                ),
            )
            self.conn.execute("DELETE FROM ops.validation_issue WHERE run_id=%s", (run.id,))
            self.conn.execute("DELETE FROM ops.validation_issue_summary WHERE run_id=%s", (run.id,))
            with self.conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO ops.validation_issue(run_id,tenant_id,dataset,row_number,key,column_name,rule_id,severity,raw_value,normalized_value,message) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            run.id,
                            run.unit.tenant,
                            issue.dataset,
                            issue.row_number,
                            issue.key,
                            issue.column,
                            issue.rule_id,
                            issue.severity,
                            issue.raw_value,
                            issue.normalized_value,
                            issue.message,
                        )
                        for issue in run.report.validation.details
                    ],
                )
                cursor.executemany(
                    "INSERT INTO ops.validation_issue_summary VALUES(%s,%s,%s,%s)",
                    [
                        (run.id, run.unit.tenant, rule, count)
                        for rule, count in run.report.validation.counts.items()
                    ],
                )
