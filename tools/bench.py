"""Measure two complete streaming syncs on fresh Celery child processes."""

import csv
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from adapter.shared import LoanType, TenantId, Unit
from tools.generate_synthetic import columns, credit, payment
from workers.runtime import connect, create_run
from workers.tasks import sync


def code_fingerprint():
    digest = hashlib.sha256()
    roots = [Path(p) for p in ("adapter", "workers", "external_bank", "api")]
    files = [
        p
        for root in roots
        for p in root.rglob("*")
        if p.is_file() and p.suffix in (".py", ".rs", ".toml", ".lock", ".yaml")
    ]
    files += [
        Path(p) for p in ("tools/bench.py", "pyproject.toml", "uv.lock", "docker/Dockerfile.dev")
    ]
    for path in sorted(files):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def docker_memory_samples(started, finished):
    samples = []
    for line in Path("artifacts/docker-stats.jsonl").read_text().splitlines():
        start, end = line.find("{"), line.rfind("}")
        if start < 0 or end < 0:
            continue
        item = json.loads(line[start : end + 1])
        if not started <= item["sampled_at"] <= finished:
            continue
        value = item["stats"]["MemUsage"].split(" / ")[0]
        for suffix, factor in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024), ("B", 1)):
            if value.endswith(suffix):
                samples.append(float(value.removesuffix(suffix)) * factor)
                break
    return samples


def generate(directory, target_bytes):
    counts = [0] * 10000
    plan = directory / "payment_plan.csv"
    template = payment(1, 1)
    size = 0
    rows = 0
    with plan.open("wb") as stream:
        header = (";".join(columns("payment_plan")) + "\n").encode()
        stream.write(header)
        size += len(header)
        while size < target_bytes:
            index = rows % len(counts)
            counts[index] += 1
            template["loan_account_number"] = f"LOAN_{index + 1:06d}"
            template["installment_number"] = str(counts[index])
            line = (";".join(template.values()) + "\n").encode()
            stream.write(line)
            size += len(line)
            rows += 1
    with (directory / "credit.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns("retail_credit"), delimiter=";")
        writer.writeheader()
        for index, count in enumerate(counts, 1):
            writer.writerow(credit(index, installments=count))
    return rows, size


def measure(directory, megabytes):
    sample_started = time.time()
    rows, size = generate(directory, megabytes * 1_000_000)
    print(f"Generated {size} bytes, {rows} plans for {megabytes} MB", flush=True)
    unit = Unit(TenantId.BANK001, LoanType.RETAIL)
    with httpx.Client(base_url="http://bank:8001", timeout=1200) as client:
        for dataset in ("credit", "payment_plan"):
            with (directory / f"{dataset}.csv").open("rb") as stream:
                response = client.put(
                    f"/v1/tenants/{unit.tenant}/loans/{unit.loan_type}/{dataset}",
                    content=iter(lambda: stream.read(65536), b""),
                    headers={"X-Bank-Key": "demo-bank001-key", "Content-Type": "text/csv"},
                )
                response.raise_for_status()
    run = create_run(unit, trigger="BENCH", force=True)
    sync.delay(run.id)
    started = time.monotonic()
    deadline = started + 1800
    with connect() as conn:
        while time.monotonic() < deadline:
            result = conn.execute(
                "SELECT status,duration_ms,peak_rss_kb,gc_duration_ms,error FROM ops.sync_run WHERE id=%s",
                (run.id,),
            ).fetchone()
            if result[0] in ("SUCCEEDED", "REJECTED", "FAILED") and result[1] > 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Benchmark exceeded 30 minutes")
        if result[0] != "SUCCEEDED":
            raise RuntimeError(f"Benchmark {run.id}: {result}")
        actual = conn.execute(
            "SELECT count(*) FROM dwh.fact_installment WHERE tenant_id=%s AND loan_type=%s",
            (unit.tenant, unit.loan_type),
        ).fetchone()[0]
        credits = conn.execute(
            "SELECT count(*) FROM dwh.fact_loan_retail WHERE tenant_id=%s", (unit.tenant,)
        ).fetchone()[0]
    assert actual == rows, (actual, rows)
    assert credits == 10000
    measurement = dict(
        target_mb=megabytes,
        source_bytes=size,
        plan_rows=rows,
        credit_rows=credits,
        status=result[0],
        duration_ms=result[1],
        peak_rss_kb=result[2],
        gc_duration_ms=result[3],
        run_id=run.id,
        sample_started=sample_started,
        sample_finished=time.time(),
    )
    print(json.dumps(measurement), flush=True)
    return measurement


def main():
    output = Path("artifacts/benchmark.json")
    output.parent.mkdir(exist_ok=True)
    output.unlink(missing_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="benchmark-") as directory:
        for size in (50, 200):
            results.append(measure(Path(directory), size))
    growth = abs(results[1]["peak_rss_kb"] / results[0]["peak_rss_kb"] - 1)
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "platform": platform.platform(),
        "code_fingerprint": code_fingerprint(),
        "python": platform.python_version(),
        "measurements": results,
        "rss_difference_ratio": growth,
        "passed": growth < 0.20 and max(r["peak_rss_kb"] for r in results) <= 256 * 1024,
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    if not result["passed"]:
        raise SystemExit("V-17 memory acceptance criteria failed; see artifacts/benchmark.json")


def finalize_stats():
    path = Path("artifacts/benchmark.json")
    result = json.loads(path.read_text())
    for row in result["measurements"]:
        samples = docker_memory_samples(row["sample_started"], row["sample_finished"])
        assert samples, "docker stats did not collect worker memory samples"
        row["docker_stats_peak_bytes"] = int(max(samples))
        row["docker_stats_samples"] = len(samples)
    path.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if "--finalize-stats" in sys.argv:
        finalize_stats()
    else:
        main()
