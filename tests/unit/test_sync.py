from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest

from adapter.ingestion.application import CheckForUpdatesUseCase, SyncDatasetUseCase
from adapter.ingestion.domain import Status, SyncRun
from adapter.quality import SeverityPolicy
from adapter.shared import (
    BankUnavailable,
    DownloadIntegrityError,
    Issue,
    LoanType,
    Money,
    ProcessReport,
    Rate,
    SchemaMismatch,
    Severity,
    SourceMeta,
    TenantId,
    Unit,
    ValidationReport,
)

UNIT = Unit(TenantId.BANK001, LoanType.RETAIL)


class Fakes:
    def __init__(self):
        self.version = None
        self.report = ProcessReport()
        self.cross = ValidationReport()
        self.events = []
        self.published = None
        self.failure = None
        self.acquired = True

    def get_meta(self, unit):
        if self.failure == "meta":
            raise BankUnavailable("Offline")
        return SourceMeta(1, {})

    def current_version(self, unit):
        return self.version

    def download(self, unit, meta, directory):
        self.events.append("download")
        if self.failure == "download":
            raise DownloadIntegrityError("Hash mismatch")
        return {}

    def process(self, unit, files, directory):
        if self.failure == "schema":
            raise SchemaMismatch("Missing column")
        return self.report

    @contextmanager
    def lock(self, unit):
        yield self.acquired

    @contextmanager
    def transaction(self):
        before = self.published
        try:
            yield
        except Exception:
            self.published = before
            raise

    def load(self, unit, batch, report):
        self.events.append("load")

    def validate(self, unit, batch):
        return self.cross

    def discard(self, unit, batch):
        self.events.append("discard")

    def publish(self, unit, batch, version, report):
        self.published = batch
        self.events.append("publish")

    def save(self, *args):
        if len(args) == 1:
            self.events.append(deepcopy(args[0].status))
        else:
            if self.failure == "profile":
                raise RuntimeError("Profile store failed")
            self.events.append("profile")

    def collect_garbage(self, unit):
        if self.failure == "gc":
            raise RuntimeError("GC failed")
        self.events.append("gc")

    def enqueue(self, unit):
        self.events.append(unit)


def execute(fakes, force=False):
    run = SyncRun(str(uuid4()), UNIT, force=force)
    use_case = SyncDatasetUseCase(fakes, fakes, fakes, fakes, fakes, fakes, SeverityPolicy())
    return run, use_case


def test_publish_follows_validation_and_gc_precedes_success():
    f = Fakes()
    run, uc = execute(f)
    uc.execute(run, "/unused")
    assert run.status == Status.SUCCEEDED
    assert f.published == run.id
    assert f.events.index(Status.VALIDATING) < f.events.index("publish")
    assert f.events.index("gc") < f.events.index(Status.SUCCEEDED)


@pytest.mark.parametrize("source", ["field", "cross"])
def test_any_error_rejects_without_publication(source):
    f = Fakes()
    report = f.report.validation if source == "field" else f.cross
    report.add(Issue("credit", 2, "LOAN_000001", "", "INVALID", Severity.ERROR))
    run, uc = execute(f)
    uc.execute(run, "/unused")
    assert run.status == Status.REJECTED
    assert f.published is None
    assert "discard" in f.events


def test_warnings_and_corrections_allow_publication():
    f = Fakes()
    for severity in (Severity.WARNING, Severity.CORRECTED):
        f.report.validation.add(Issue("credit", 2, "", "", "CHECK", severity))
    run, uc = execute(f)
    uc.execute(run, "/unused")
    assert run.status == Status.SUCCEEDED


def test_schema_mismatch_is_rejected_without_loading():
    f = Fakes()
    f.failure = "schema"
    run, uc = execute(f)
    uc.execute(run, "/unused")
    assert run.status == Status.REJECTED
    assert "load" not in f.events


def test_same_version_skips_and_force_reprocesses():
    f = Fakes()
    f.version = 1
    run, uc = execute(f)
    uc.execute(run, "/unused")
    assert run.status == Status.SKIPPED
    assert "download" not in f.events
    run, uc = execute(f, force=True)
    uc.execute(run, "/unused")
    assert run.status == Status.SUCCEEDED


def test_busy_unit_skips_without_downloading():
    f = Fakes()
    f.acquired = False
    run, uc = execute(f)
    uc.execute(run, "/unused")
    assert run.status == Status.SKIPPED
    assert "download" not in f.events


@pytest.mark.parametrize("failure", ["meta", "download", "profile", "gc"])
def test_technical_failures_preserve_publication_boundaries(failure):
    f = Fakes()
    f.failure = failure
    run, uc = execute(f)
    with pytest.raises((BankUnavailable, RuntimeError)):
        uc.execute(run, "/unused")
    assert run.status == Status.FAILED
    assert f.published == (run.id if failure == "gc" else None)
    if failure == "gc":
        assert "discard" not in f.events


def test_state_machine_prevents_invalid_and_terminal_transitions():
    run = SyncRun("id", UNIT)
    with pytest.raises(ValueError):
        run.advance(Status.SUCCEEDED)
    run.advance(Status.SKIPPED)
    with pytest.raises(ValueError):
        run.advance(Status.FETCHING)


def test_money_and_rate_require_finite_decimal():
    for kind in (Money, Rate):
        assert kind(Decimal("0.185")).value == Decimal("0.185")
        for invalid in (0.185, Decimal("NaN"), Decimal("Infinity")):
            with pytest.raises(ValueError):
                kind(invalid)


def test_report_limits_details_without_losing_error_counts():
    report = ValidationReport()
    for row in range(1200):
        report.add(Issue("credit", row, "", "", "INVALID", Severity.ERROR))
    assert len(report.details) == 1000
    assert report.errors == 1200
    assert SeverityPolicy().rejects(report)
    report.schema_error = True
    assert SeverityPolicy(2000).rejects(report)


def test_poll_queues_only_changed_units_and_tolerates_bank_outage():
    f = Fakes()
    poll = CheckForUpdatesUseCase(f, f, f)
    poll.execute()
    assert len(f.events) == 6
    f.events.clear()
    f.version = 1
    poll.execute()
    assert f.events == []
    f.failure = "meta"
    poll.execute()
    assert f.events == []
