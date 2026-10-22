import os
import threading
import time
from enum import StrEnum
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


class Table(StrEnum):
    RETAIL = "fact_loan_retail"
    COMMERCIAL = "fact_loan_commercial"
    PLAN = "fact_installment"


def connect(role="app_writer"):
    return psycopg.connect(
        make_conninfo(
            os.environ["DATABASE_URL"], user=role, password=os.environ["DB_ROLE_PASSWORD"]
        ),
        autocommit=True,
    )


@pytest.fixture(autouse=True)
def clean_warehouse():
    with connect() as writer:
        for table in Table:
            writer.execute(sql.SQL("DELETE FROM dwh.{}").format(sql.Identifier(table)))
        writer.execute("DELETE FROM dwh.current_snapshot")
    yield


def load(writer, tenant, batch, count, loan_type="RETAIL"):
    table = Table.RETAIL if loan_type == "RETAIL" else Table.COMMERCIAL
    with writer.transaction():
        writer.execute(
            sql.SQL("""
                INSERT INTO dwh.{} (tenant_id, batch_id, source_row_number,
                    customer_id, customer_type, loan_account_number, loan_status_code,
                    days_past_due, final_maturity_date, original_loan_amount,
                    outstanding_principal_balance, loan_start_date)
                SELECT %s, %s, n, 'CUSTOMER', 'INDIVIDUAL',
                    'LOAN_' || lpad(n::text, 6, '0'), 'ACTIVE', 0,
                    DATE '2027-01-01', 1000.00, 900.00, DATE '2026-01-01'
                FROM generate_series(1, %s) AS n
            """).format(sql.Identifier(table)),
            (tenant, batch, count),
        )
        writer.execute(
            """INSERT INTO dwh.fact_installment
               (tenant_id,batch_id,source_row_number,loan_type,loan_account_number,installment_number)
               SELECT %s,%s,n,%s,'LOAN_' || lpad(n::text,6,'0'),1
               FROM generate_series(1,%s) AS n""",
            (tenant, batch, loan_type, count),
        )


def publish(writer, tenant, batch, loan_type="RETAIL"):
    writer.execute(
        """INSERT INTO dwh.current_snapshot
        (tenant_id,loan_type,batch_id,source_version,row_counts)
        VALUES (%s,%s,%s,1,'{}') ON CONFLICT (tenant_id,loan_type)
        DO UPDATE SET batch_id=EXCLUDED.batch_id""",
        (tenant, loan_type, batch),
    )


def collect(writer, tenant, batch):
    for table in (Table.RETAIL, Table.PLAN):
        extra = sql.SQL(" AND loan_type='RETAIL'") if table == Table.PLAN else sql.SQL("")
        writer.execute(
            sql.SQL("DELETE FROM dwh.{} WHERE tenant_id=%s AND batch_id<>%s{}").format(
                sql.Identifier(table), extra
            ),
            (tenant, batch),
        )


def read_pair(reader, tenant="BANK001"):
    with reader.transaction():
        reader.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        reader.execute("SELECT set_config('app.tenant_id',%s,true)", (tenant,))
        credit = reader.execute(
            "SELECT count(*),count(DISTINCT batch_id),min(batch_id::text) FROM dwh.fact_loan_retail"
        ).fetchone()
        time.sleep(0.001)
        plan = reader.execute(
            """SELECT count(*),count(DISTINCT batch_id),min(batch_id::text)
            FROM dwh.fact_installment WHERE loan_type='RETAIL'"""
        ).fetchone()
        return credit, plan


def test_rls_is_fail_closed_and_partitions_are_private():
    with connect() as writer, connect("app_reader") as reader:
        published = {}
        for tenant in ("BANK001", "BANK002", "BANK003"):
            for kind in ("RETAIL", "COMMERCIAL"):
                batch = uuid4()
                published[tenant, kind] = batch
                load(writer, tenant, batch, 3, kind)
                publish(writer, tenant, batch, kind)
        unpublished = uuid4()
        load(writer, "BANK001", unpublished, 5)
        for replacement in (False, True):
            if replacement:
                publish(writer, "BANK001", unpublished)
            expected = 5 if replacement else 3
            assert read_pair(reader)[0] == (
                expected,
                1,
                str(unpublished if replacement else published["BANK001", "RETAIL"]),
            )
            with reader.transaction():
                reader.execute("SELECT set_config('app.tenant_id','BANK001',true)")
                for table in Table:
                    tenants = reader.execute(
                        sql.SQL("SELECT DISTINCT tenant_id FROM dwh.{}").format(
                            sql.Identifier(table)
                        )
                    ).fetchall()
                    assert tenants == [("BANK001",)]
                assert reader.execute(
                    "SELECT count(*) FROM dwh.fact_installment WHERE tenant_id='BANK002'"
                ).fetchone() == (0,)
                assert reader.execute(
                    "SELECT DISTINCT tenant_id FROM dwh.v_loan_common"
                ).fetchall() == [("BANK001",)]
            for table in Table:
                assert reader.execute(
                    sql.SQL("SELECT count(*) FROM dwh.{}").format(sql.Identifier(table))
                ).fetchone() == (0,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                reader.execute("SELECT count(*) FROM dwh.fact_loan_retail_bank002")
        assert reader.execute(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == (False, False)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader.execute("DELETE FROM dwh.fact_loan_retail")
    with connect("app_django") as django:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            django.execute("SELECT * FROM dwh.current_snapshot")


def test_publish_rollback_preserves_old_snapshot_and_gc_is_scoped():
    with connect() as writer, connect("app_reader") as reader:
        first, second, other = uuid4(), uuid4(), uuid4()
        load(writer, "BANK001", first, 3)
        publish(writer, "BANK001", first)
        load(writer, "BANK002", other, 7)
        publish(writer, "BANK002", other)
        load(writer, "BANK001", second, 5)
        with pytest.raises(RuntimeError):
            with writer.transaction():
                publish(writer, "BANK001", second)
                raise RuntimeError("Injected failure before commit")
        assert read_pair(reader)[0] == (3, 1, str(first))
        publish(writer, "BANK001", second)
        collect(writer, "BANK001", second)
        collect(writer, "BANK001", second)
        assert read_pair(reader) == ((5, 1, str(second)), (5, 1, str(second)))
        assert read_pair(reader, "BANK002")[0] == (7, 1, str(other))
        assert writer.execute(
            "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id='BANK001'"
        ).fetchone() == (5,)


def test_atomic_publish_under_concurrent_reads(record_property):
    ready, stop = threading.Event(), threading.Event()
    observations, errors, latencies = [], [], []
    with connect() as writer:
        initial = uuid4()
        load(writer, "BANK001", initial, 1000)
        publish(writer, "BANK001", initial)

        def read_loop():
            try:
                with connect("app_reader") as reader:
                    reader.execute("SET statement_timeout='2s'")
                    while not stop.is_set():
                        start = time.monotonic()
                        pair = read_pair(reader)
                        latencies.append(time.monotonic() - start)
                        observations.append(pair)
                        ready.set()
            except BaseException as error:
                errors.append(error)
                ready.set()

        thread = threading.Thread(target=read_loop)
        thread.start()
        try:
            assert ready.wait(5)
            for index in range(10):
                batch = uuid4()
                load(writer, "BANK001", batch, 2000 if index % 2 == 0 else 1000)
                with writer.transaction():
                    publish(writer, "BANK001", batch)
                collect(writer, "BANK001", batch)
        finally:
            stop.set()
            thread.join(timeout=5)
        assert not thread.is_alive()
        assert not errors
        assert len(observations) >= 10
        for credit, plan in observations:
            assert credit == plan
            assert credit[0] in (1000, 2000)
            assert credit[1] == 1
        p99 = sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.99))]
        record_property("sql_read_p99_ms", round(p99 * 1000, 3))


def test_partition_statistics_are_available_only_through_bounded_writer_entrypoint():
    with connect() as writer:
        batch = str(uuid4())
        load(writer, "BANK001", batch, 123)
        writer.execute("SELECT ops.analyze_partition(%s,%s)", ("fact_loan_retail", "BANK001"))
        assert (
            writer.execute(
                "SELECT reltuples FROM pg_class WHERE oid='dwh.fact_loan_retail_bank001'::regclass"
            ).fetchone()[0]
            == 123
        )
        with pytest.raises(psycopg.errors.RaiseException, match="Invalid warehouse partition"):
            writer.execute(
                "SELECT ops.analyze_partition(%s,%s)",
                ("fact_loan_retail; DROP SCHEMA dwh CASCADE", "BANK001"),
            )
    for role in ("app_reader", "app_django"):
        with connect(role) as reader, pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader.execute("SELECT ops.analyze_partition(%s,%s)", ("fact_loan_retail", "BANK001"))
