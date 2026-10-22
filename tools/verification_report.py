"""Render acceptance results from fresh JUnit evidence; missing tests never pass."""

import json
import platform
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("artifacts/verification")


def database_version():
    try:
        from workers.runtime import connect

        with connect() as connection:
            return connection.execute("SHOW server_version").fetchone()[0]
    except Exception:
        return "unavailable"


def render():
    tests = []
    for filename in ROOT.glob("*.xml"):
        for test in ET.parse(filename).iter("testcase"):
            ids = set(re.findall(r"v(\d{2})", test.get("name", "").lower()))
            if "bank_contract" in test.get("name", ""):
                ids.update(("20", "21"))
            tests.append((ids, test))
    stages = {}
    for name in ("lint", "tests", "live", "bench", "performance"):
        path = ROOT / f"{name}.exit"
        stages[name] = path.exists() and path.read_text().strip() == "0"
    requirements = re.findall(
        r"^### V-(\d+) · (.*?) — (.*)$", Path("docs/VERIFICATION.md").read_text(), re.M
    )
    lines = [
        "# Verification report",
        f"PostgreSQL: {database_version()}",
        "",
        f"Date (UTC): {datetime.now(UTC).isoformat()}",
        f"Git SHA: {subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}",
        f"Environment: {platform.platform()} · Python {platform.python_version()}",
        f"Rust: {subprocess.check_output(['rustc', '--version'], text=True).strip()}",
        "",
        "| V-ID | Priority | Title | Status | Duration | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    passed = 0
    total = 0
    for number, title, level in requirements:
        must = "MUST" in level
        matching = [t for ids, t in tests if number in ids]
        ok = bool(matching) and all(
            not any(t.find(tag) is not None for tag in ("failure", "error", "skipped"))
            for t in matching
        )
        if number == "23":
            ok = ok and stages["lint"]
        if number == "17":
            ok = ok and stages["bench"] and stages["performance"]
        duration = sum(float(t.get("time", 0)) for t in matching)
        evidence = (
            f"{len(matching)} test; artifacts/verification/*.xml" if matching else "Not executed"
        )
        if number == "22":
            evidence = "Manual browser record and screenshots; automated evidence-file check"
        if must:
            total += 1
            passed += int(ok)
        status = "PASS" if ok else ("FAIL / MISSING" if must else "NOT IMPLEMENTED")
        lines.append(
            f"| V-{number} | {'MUST' if must else 'SHOULD'} | {title} | {status} | {duration:.3f} s | {evidence} |"
        )
    lines += ["", f"**MUST result: {passed}/{total} PASS.**", "", "## Execution phases", ""]
    lines += [f"- {name}: {'PASS' if ok else 'FAIL / NOT EXECUTED'}" for name, ok in stages.items()]
    lines += ["", "## Measured evidence", ""]
    for _, test in tests:
        for prop in test.findall("./properties/property"):
            lines.append(f"- {test.get('name')}: {prop.get('name')} = {prop.get('value')}")
    benchmark = Path("artifacts/benchmark.json")
    if benchmark.exists():
        data = json.loads(benchmark.read_text())
        lines += [
            "",
            "## Performance",
            "",
            f"Measurement date: {data['created_at']}",
            "| Source | Plan rows | Sync duration | Peak RSS | Docker worker peak | GC |",
            "|---|---|---|---|---|---|",
        ]
        for row in data["measurements"]:
            docker_peak = (
                f"{row['docker_stats_peak_bytes'] / 1024**2:.2f} MiB"
                if "docker_stats_peak_bytes" in row
                else "not captured"
            )
            lines.append(
                f"| {row['source_bytes']} byte | {row['plan_rows']} | {row['duration_ms'] / 1000:.3f} s | {row['peak_rss_kb'] / 1024:.2f} MiB | {docker_peak} | {row['gc_duration_ms']} ms |"
            )
        lines += [
            "",
            f"RSS difference: {data['rss_difference_ratio'] * 100:.2f}%.",
            "Docker samples include parent and child working memory; the RSS acceptance threshold applies to the fresh child.",
        ]
    lines += [
        "",
        "SHOULD portions are incomplete: V-02 API keys, V-16 reaper, V-19 manifest and V-22 automated Playwright.",
        "Private source-data scenarios are not evidence from this synthetic verification run.",
        "",
    ]
    Path("verification-report.md").write_text("\n".join(lines))
    print(f"MUST: {passed}/{total}; report: verification-report.md")
    return 0 if passed == total and all(stages.values()) else 1


if __name__ == "__main__":
    raise SystemExit(render())
