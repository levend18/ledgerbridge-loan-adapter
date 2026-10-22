import json
from datetime import date
from pathlib import Path

import adapter_engine

from adapter.shared import DatasetKind, Issue, ProcessReport, SchemaMismatch, Severity, Unit

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


class RustProcessor:
    def __init__(self, codes: str | None = None) -> None:
        self.codes = codes or (SCHEMAS / "codes.yaml").read_text()

    def process(self, unit: Unit, files: dict[DatasetKind, str], directory: str) -> ProcessReport:
        report = ProcessReport()
        for kind, source in files.items():
            schema = (
                f"{unit.loan_type.lower()}_credit" if kind == DatasetKind.CREDIT else "payment_plan"
            )
            target = str(Path(directory) / f"{kind}.copy")
            try:
                result = json.loads(
                    adapter_engine.process_dataset(
                        source,
                        target,
                        (SCHEMAS / f"{schema}.yaml").read_text(),
                        self.codes,
                        date.today().isoformat(),
                    )
                )
            except ValueError as exc:
                if "SCHEMA_MISMATCH" in str(exc):
                    raise SchemaMismatch(str(exc)) from exc
                raise
            report.outputs[kind] = target
            report.row_counts[kind] = result["written_count"]
            report.profiles[kind] = result["profiles"]
            report.unit_decisions[kind] = result["unit_decisions"]
            for key, count in result["counts"].items():
                report.validation.counts[key] = report.validation.counts.get(key, 0) + count
            for issue in result["issues"]:
                if len(report.validation.details) < 1000:
                    report.validation.details.append(
                        Issue(**{**issue, "severity": Severity(issue["severity"])})
                    )
        return report
