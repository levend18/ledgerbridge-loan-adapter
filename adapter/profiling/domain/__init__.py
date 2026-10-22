from typing import Protocol
from adapter.shared import Unit, ProcessReport


class ProfileRepository(Protocol):
    def save(self, unit: Unit, batch: str, report: ProcessReport) -> None: ...
