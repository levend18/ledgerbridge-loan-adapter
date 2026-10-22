from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TypeAlias

Json: TypeAlias = None | bool | int | float | str | list["Json"] | dict[str, "Json"]


class TenantId(StrEnum):
    BANK001 = "BANK001"
    BANK002 = "BANK002"
    BANK003 = "BANK003"


class LoanType(StrEnum):
    RETAIL = "RETAIL"
    COMMERCIAL = "COMMERCIAL"


class DatasetKind(StrEnum):
    CREDIT = "credit"
    PAYMENT_PLAN = "payment_plan"


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    CORRECTED = "CORRECTED"


@dataclass(frozen=True)
class Unit:
    tenant: TenantId
    loan_type: LoanType


@dataclass(frozen=True)
class Money:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("Money must be a finite Decimal")


@dataclass(frozen=True)
class Rate:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("Rate must be a finite Decimal")


@dataclass(frozen=True)
class DatasetMeta:
    sha256: str
    row_count: int


@dataclass(frozen=True)
class SourceMeta:
    version: int
    datasets: dict[DatasetKind, DatasetMeta]


@dataclass(frozen=True)
class Issue:
    dataset: str
    row_number: int
    key: str
    column: str
    rule_id: str
    severity: Severity
    raw_value: str = ""
    normalized_value: str = ""
    message: str = ""


@dataclass
class ValidationReport:
    details: list[Issue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    schema_error: bool = False

    def add(self, issue: Issue, count: int = 1, limit: int = 1000) -> None:
        key = f"{issue.severity}:{issue.rule_id}"
        self.counts[key] = self.counts.get(key, 0) + count
        if len(self.details) < limit:
            self.details.append(issue)

    def merge(self, other: "ValidationReport", limit: int = 1000) -> None:
        self.details.extend(other.details[: max(0, limit - len(self.details))])
        for key, value in other.counts.items():
            self.counts[key] = self.counts.get(key, 0) + value
        self.schema_error = self.schema_error or other.schema_error

    @property
    def errors(self) -> int:
        return sum(n for key, n in self.counts.items() if key.startswith("ERROR:"))


@dataclass
class ProcessReport:
    outputs: dict[DatasetKind, str] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)
    validation: ValidationReport = field(default_factory=ValidationReport)
    profiles: dict[str, Json] = field(default_factory=dict)
    unit_decisions: dict[str, Json] = field(default_factory=dict)


class BankUnavailable(Exception):
    pass


class DownloadIntegrityError(BankUnavailable):
    pass


class SchemaMismatch(Exception):
    pass
