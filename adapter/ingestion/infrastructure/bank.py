import hashlib
from pathlib import Path
from typing import Any

import httpx

from adapter.shared import (
    BankUnavailable,
    DatasetKind,
    DatasetMeta,
    DownloadIntegrityError,
    SourceMeta,
    TenantId,
    Unit,
)


class HttpBankGateway:
    def __init__(self, url: str, keys: dict[TenantId, str]) -> None:
        self.url, self.keys = url, keys

    def _path(self, unit: Unit) -> str:
        return f"{self.url}/v1/tenants/{unit.tenant}/loans/{unit.loan_type}"

    def get_meta(self, unit: Unit) -> SourceMeta:
        try:
            response = httpx.get(
                self._path(unit) + "/meta",
                headers={"X-Bank-Key": self.keys[unit.tenant]},
                timeout=30,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return SourceMeta(
                data["version"],
                {DatasetKind(k): DatasetMeta(**v) for k, v in data["datasets"].items()},
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise BankUnavailable(str(exc)) from exc

    def download(self, unit: Unit, meta: SourceMeta, directory: str) -> dict[DatasetKind, str]:
        files = {}
        for kind in DatasetKind:
            path = Path(directory) / f"{kind}.ndjson"
            digest, count = hashlib.sha256(), 0
            try:
                with (
                    httpx.stream(
                        "GET",
                        self._path(unit) + f"/{kind}/records",
                        headers={"X-Bank-Key": self.keys[unit.tenant]},
                        timeout=120,
                    ) as response,
                    path.open("wb") as target,
                ):
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        digest.update(chunk)
                        count += chunk.count(b"\n")
                        target.write(chunk)
            except httpx.HTTPError as exc:
                raise BankUnavailable(str(exc)) from exc
            expected = meta.datasets[kind]
            if digest.hexdigest() != expected.sha256 or count != expected.row_count:
                raise DownloadIntegrityError(f"{kind}: digest or row count changed")
            files[kind] = str(path)
        if self.get_meta(unit).version != meta.version:
            raise DownloadIntegrityError("Unit version changed during download")
        return files
