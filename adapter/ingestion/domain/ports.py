from contextlib import AbstractContextManager
from typing import Protocol

from adapter.ingestion.domain import SyncRun
from adapter.shared import DatasetKind, SourceMeta, Unit


class BankGateway(Protocol):
    def get_meta(self, unit: Unit) -> SourceMeta: ...

    def download(self, unit: Unit, meta: SourceMeta, directory: str) -> dict[DatasetKind, str]: ...


class RunRepository(Protocol):
    def save(self, run: SyncRun) -> None: ...


class UnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...


class PollScheduler(Protocol):
    def enqueue(self, unit: Unit) -> None: ...
