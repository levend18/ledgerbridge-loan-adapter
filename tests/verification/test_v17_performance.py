import json
from pathlib import Path

import pytest

from tools.bench import code_fingerprint

pytestmark = pytest.mark.performance


def test_v17_streaming_memory_and_counts(record_property):
    result = json.loads(Path("artifacts/benchmark.json").read_text())
    assert result["code_fingerprint"] == code_fingerprint(), "Benchmark evidence is stale"
    assert result["passed"]
    small, large = result["measurements"]
    assert [r["target_mb"] for r in (small, large)] == [50, 200]
    for row in (small, large):
        assert row["status"] == "SUCCEEDED"
        assert (
            row["target_mb"] * 1_000_000 <= row["source_bytes"] < row["target_mb"] * 1_000_000 + 200
        )
        assert row["plan_rows"] > 500000
        assert row["credit_rows"] == 10000
        assert 0 < row["peak_rss_kb"] <= 256 * 1024
        assert row["duration_ms"] > 0
        assert row["gc_duration_ms"] >= 0
        assert row["docker_stats_samples"] > 0
        assert row["docker_stats_peak_bytes"] > 0
        record_property(f"{row['target_mb']}mb", json.dumps(row))
    assert abs(large["peak_rss_kb"] / small["peak_rss_kb"] - 1) < 0.20
