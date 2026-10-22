import psycopg

from adapter.shared import Json, Unit


class ProfileQueries:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def current(self, unit: Unit) -> dict[str, Json]:
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SELECT set_config('app.tenant_id',%s,true)", (unit.tenant,))
            snapshot = conn.execute(
                "SELECT batch_id,source_version,published_at FROM dwh.current_snapshot WHERE loan_type=%s",
                (unit.loan_type,),
            ).fetchone()
            if snapshot is None:
                raise LookupError("no-snapshot")
            datasets: dict[str, Json] = {}
            for dataset, column, stats in conn.execute(
                "SELECT dataset,column_name,stats FROM ops.column_profile WHERE loan_type=%s ORDER BY dataset,column_name",
                (unit.loan_type,),
            ):
                columns = datasets.setdefault(dataset, {})
                if not isinstance(columns, dict):
                    raise TypeError("Expected profile columns")
                columns[column] = stats
            return {
                "tenant_id": unit.tenant,
                "loan_type": unit.loan_type,
                "snapshot": {
                    "batch_id": str(snapshot[0]),
                    "source_version": snapshot[1],
                    "published_at": snapshot[2].isoformat(),
                },
                "datasets": datasets,
            }
