import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class BankStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY, tenant TEXT, loan_type TEXT,
                    dataset TEXT, business_key TEXT, payload TEXT);
                CREATE INDEX IF NOT EXISTS records_unit
                    ON records(tenant,loan_type,dataset,id);
                CREATE INDEX IF NOT EXISTS records_key
                    ON records(tenant,loan_type,dataset,business_key);
                CREATE TABLE IF NOT EXISTS versions (
                    tenant TEXT, loan_type TEXT, version INTEGER, updated_at TEXT,
                    PRIMARY KEY(tenant,loan_type));
                CREATE TABLE IF NOT EXISTS metadata (
                    tenant TEXT, loan_type TEXT, dataset TEXT, digest TEXT, count INTEGER,
                    PRIMARY KEY(tenant,loan_type,dataset));
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=60)

    def upload(self, tenant, loan_type, dataset, path, replace):
        unit = (tenant, loan_type, dataset)
        with self.connect() as conn, open(path, encoding="utf-8-sig", newline="") as source:
            conn.execute("BEGIN IMMEDIATE")
            reader = csv.DictReader(source, delimiter=";", strict=True)
            headers = reader.fieldnames
            if not headers or len(set(headers)) != len(headers) or any(not k for k in headers):
                raise ValueError("Invalid CSV header")
            if replace:
                conn.execute(
                    "DELETE FROM records WHERE tenant=? AND loan_type=? AND dataset=?", unit
                )
            batch = []
            for number, row in enumerate(reader):
                if None in row or None in row.values():
                    raise ValueError("CSV row width differs from header")
                key = [row.get("loan_account_number", f"row:{number}")]
                if dataset == "payment_plan":
                    key.append(row.get("installment_number", ""))
                key = json.dumps(key, ensure_ascii=False)
                if not replace:
                    conn.execute(
                        "DELETE FROM records WHERE tenant=? AND loan_type=? AND dataset=? AND business_key=?",
                        (*unit, key),
                    )
                payload = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                if replace:
                    batch.append((*unit, key, payload))
                    if len(batch) == 10000:
                        conn.executemany(
                            "INSERT INTO records(tenant,loan_type,dataset,business_key,payload) VALUES(?,?,?,?,?)",
                            batch,
                        )
                        batch.clear()
                else:
                    conn.execute(
                        "INSERT INTO records(tenant,loan_type,dataset,business_key,payload) VALUES(?,?,?,?,?)",
                        (*unit, key, payload),
                    )
            if batch:
                conn.executemany(
                    "INSERT INTO records(tenant,loan_type,dataset,business_key,payload) VALUES(?,?,?,?,?)",
                    batch,
                )
            digest, count = hashlib.sha256(), 0
            for (payload,) in conn.execute(
                "SELECT payload FROM records WHERE tenant=? AND loan_type=? AND dataset=? ORDER BY id",
                unit,
            ):
                digest.update(payload.encode())
                count += 1
            conn.execute(
                "INSERT INTO metadata VALUES(?,?,?,?,?) ON CONFLICT(tenant,loan_type,dataset) DO UPDATE SET digest=excluded.digest,count=excluded.count",
                (*unit, digest.hexdigest(), count),
            )
            conn.execute(
                "INSERT INTO versions VALUES(?,?,1,?) ON CONFLICT(tenant,loan_type) DO UPDATE SET version=version+1,updated_at=excluded.updated_at",
                (tenant, loan_type, datetime.now(timezone.utc).isoformat()),
            )
        return self.meta(tenant, loan_type)

    def meta(self, tenant, loan_type):
        with self.connect() as conn:
            conn.execute("BEGIN")
            version = conn.execute(
                "SELECT version,updated_at FROM versions WHERE tenant=? AND loan_type=?",
                (tenant, loan_type),
            ).fetchone()
            datasets = {
                kind: {"sha256": hashlib.sha256(b"").hexdigest(), "row_count": 0}
                for kind in ("credit", "payment_plan")
            }
            for kind, digest, count in conn.execute(
                "SELECT dataset,digest,count FROM metadata WHERE tenant=? AND loan_type=?",
                (tenant, loan_type),
            ):
                datasets[kind] = {"sha256": digest, "row_count": count}
            return {
                "version": version[0] if version else 0,
                "updated_at": version[1] if version else None,
                "datasets": datasets,
            }

    def records(self, tenant, loan_type, dataset, cursor=0, limit=None):
        with self.connect() as conn:
            conn.execute("BEGIN")
            for row in conn.execute(
                "SELECT id,payload FROM records WHERE tenant=? AND loan_type=? AND dataset=? AND id>? ORDER BY id LIMIT ?",
                (tenant, loan_type, dataset, cursor, limit if limit is not None else -1),
            ):
                yield row
