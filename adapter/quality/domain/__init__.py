from typing import Protocol
from adapter.shared import Unit, DatasetKind, ProcessReport
from dataclasses import dataclass

from adapter.shared import ValidationReport


@dataclass(frozen=True)
class SeverityPolicy:
    error_tolerance: int = 0

    def __post_init__(self) -> None:
        if self.error_tolerance < 0:
            raise ValueError("Error tolerance cannot be negative")

    def rejects(self, report: ValidationReport) -> bool:
        return report.schema_error or report.errors > self.error_tolerance


class DatasetProcessor(Protocol):
    def process(
        self, unit: Unit, files: dict[DatasetKind, str], directory: str
    ) -> ProcessReport: ...
