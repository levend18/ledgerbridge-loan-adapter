from dataclasses import dataclass, field
from enum import StrEnum

from adapter.shared import ProcessReport, Unit


class Status(StrEnum):
    PENDING = "PENDING"
    FETCHING = "FETCHING"
    PROCESSING = "PROCESSING"
    VALIDATING = "VALIDATING"
    PUBLISHING = "PUBLISHING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


TRANSITIONS = {
    Status.PENDING: {Status.FETCHING, Status.SKIPPED, Status.FAILED},
    Status.FETCHING: {Status.PROCESSING, Status.FAILED},
    Status.PROCESSING: {Status.VALIDATING, Status.FAILED},
    Status.VALIDATING: {Status.PUBLISHING, Status.REJECTED, Status.FAILED},
    Status.PUBLISHING: {Status.SUCCEEDED, Status.FAILED},
}


@dataclass
class SyncRun:
    id: str
    unit: Unit
    trigger: str = "MANUAL"
    force: bool = False
    status: Status = Status.PENDING
    batch_id: str = ""
    source_version: int = 0
    report: ProcessReport = field(default_factory=ProcessReport)
    error: str = ""

    def advance(self, target: Status) -> None:
        if target not in TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid transition: {self.status} -> {target}")
        self.status = target
