from adapter.ingestion.domain import Status, SyncRun
from adapter.ingestion.domain.ports import (
    BankGateway,
    PollScheduler,
    RunRepository,
    UnitOfWork,
)
from adapter.quality import SeverityPolicy, DatasetProcessor
from adapter.warehouse import Warehouse
from adapter.profiling import ProfileRepository
from adapter.shared import (
    BankUnavailable,
    Issue,
    LoanType,
    SchemaMismatch,
    Severity,
    TenantId,
    Unit,
)


class SyncDatasetUseCase:
    def __init__(
        self,
        bank: BankGateway,
        processor: DatasetProcessor,
        warehouse: Warehouse,
        runs: RunRepository,
        profiles: ProfileRepository,
        uow: UnitOfWork,
        policy: SeverityPolicy,
    ) -> None:
        self.bank = bank
        self.processor = processor
        self.warehouse = warehouse
        self.runs = runs
        self.profiles = profiles
        self.uow = uow
        self.policy = policy

    def _advance(self, run: SyncRun, state: Status) -> None:
        run.advance(state)
        self.runs.save(run)

    def execute(self, run: SyncRun, directory: str) -> None:
        published = False
        try:
            with self.warehouse.lock(run.unit) as acquired:
                if not acquired:
                    self._advance(run, Status.SKIPPED)
                    return
                meta = self.bank.get_meta(run.unit)
                run.source_version = meta.version
                if not run.force and meta.version == self.warehouse.current_version(run.unit):
                    self.warehouse.collect_garbage(run.unit)
                    self._advance(run, Status.SKIPPED)
                    return
                self._advance(run, Status.FETCHING)
                files = self.bank.download(run.unit, meta, directory)
                self._advance(run, Status.PROCESSING)
                try:
                    run.report = self.processor.process(run.unit, files, directory)
                except SchemaMismatch as error:
                    run.report.validation.schema_error = True
                    run.report.validation.add(
                        Issue("", 0, "", "", "SCHEMA_MISMATCH", Severity.ERROR, message=str(error))
                    )
                self._advance(run, Status.VALIDATING)
                if not run.report.validation.schema_error:
                    run.batch_id = run.id
                    self.warehouse.load(run.unit, run.batch_id, run.report)
                    run.report.validation.merge(self.warehouse.validate(run.unit, run.batch_id))
                if self.policy.rejects(run.report.validation):
                    if run.batch_id:
                        self.warehouse.discard(run.unit, run.batch_id)
                    self._advance(run, Status.REJECTED)
                    return
                self._advance(run, Status.PUBLISHING)
                with self.uow.transaction():
                    self.warehouse.publish(run.unit, run.batch_id, meta.version, run.report)
                    self.profiles.save(run.unit, run.batch_id, run.report)
                    self.runs.save(run)
                published = True
                self.warehouse.collect_garbage(run.unit)
                self._advance(run, Status.SUCCEEDED)
        except Exception as error:
            if run.batch_id and not published:
                self.warehouse.discard(run.unit, run.batch_id)
            run.error = str(error)
            self._advance(run, Status.FAILED)
            raise


class CheckForUpdatesUseCase:
    def __init__(self, bank: BankGateway, warehouse: Warehouse, scheduler: PollScheduler) -> None:
        self.bank, self.warehouse, self.scheduler = bank, warehouse, scheduler

    def execute(self) -> None:
        for tenant in TenantId:
            for loan_type in LoanType:
                unit = Unit(tenant, loan_type)
                try:
                    meta = self.bank.get_meta(unit)
                except BankUnavailable:
                    continue
                if meta.version > 0 and meta.version != self.warehouse.current_version(unit):
                    self.scheduler.enqueue(unit)
