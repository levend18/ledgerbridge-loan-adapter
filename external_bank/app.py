# Maintainer: Levent Çelik — https://github.com/levend18
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from external_bank.storage import BankStore

TENANTS = ("BANK001", "BANK002", "BANK003")
Loan = Literal["RETAIL", "COMMERCIAL"]
Dataset = Literal["credit", "payment_plan"]


def create_app(path=None, keys=None):
    app = FastAPI(
        title="Bank simulator",
        contact={"name": "Levent Çelik", "url": "https://github.com/levend18"},
    )
    store = BankStore(path or os.environ.get("BANK_DB", "/tmp/ledgerbridge-bank.sqlite"))
    keys = keys or {t: os.environ.get(f"BANK_KEY_{t}", f"demo-{t.lower()}-key") for t in TENANTS}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "PUT", "PATCH"],
        allow_headers=["X-Bank-Key", "Content-Type"],
    )

    def authorize(tenant, key):
        identity = next((t for t, candidate in keys.items() if key == candidate), None)
        if identity is None:
            raise HTTPException(401, "Invalid bank key")
        if tenant != identity:
            raise HTTPException(403, "Tenant mismatch")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/v1/tenants/{tenant}/loans/{loan_type}/meta")
    def meta(tenant: str, loan_type: Loan, x_bank_key: str = Header(default="")):
        authorize(tenant, x_bank_key)
        return store.meta(tenant, loan_type)

    @app.api_route("/v1/tenants/{tenant}/loans/{loan_type}/{dataset}", methods=["PUT", "PATCH"])
    async def upload(
        tenant: str,
        loan_type: Loan,
        dataset: Dataset,
        request: Request,
        x_bank_key: str = Header(default=""),
    ):
        authorize(tenant, x_bank_key)
        fd, name = tempfile.mkstemp(suffix=".csv")
        try:
            size = 0
            with os.fdopen(fd, "wb") as target:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > int(os.environ.get("MAX_UPLOAD_MB", "250")) * 1024 * 1024:
                        raise HTTPException(413, "Upload exceeds MAX_UPLOAD_MB")
                    target.write(chunk)
            return await run_in_threadpool(
                store.upload, tenant, loan_type, dataset, name, request.method == "PUT"
            )
        except (csv.Error, UnicodeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            Path(name).unlink(missing_ok=True)

    @app.get("/v1/tenants/{tenant}/loans/{loan_type}/{dataset}/records")
    def records(
        tenant: str,
        loan_type: Loan,
        dataset: Dataset,
        format: Literal["ndjson", "json"] = "ndjson",
        cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
        x_bank_key: str = Header(default=""),
    ):
        authorize(tenant, x_bank_key)
        if format == "json":
            rows = list(store.records(tenant, loan_type, dataset, cursor, limit + 1))
            return {
                "results": [json.loads(payload) for _, payload in rows[:limit]],
                "next_cursor": rows[limit - 1][0] if len(rows) > limit else None,
            }
        return StreamingResponse(
            store.stream(tenant, loan_type, dataset),
            media_type="application/x-ndjson",
        )

    return app


app = create_app()
