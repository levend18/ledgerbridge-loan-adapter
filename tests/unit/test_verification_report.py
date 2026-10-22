from pathlib import Path

from tools import verification_report


def test_report_fails_for_missing_failed_or_unchecked_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verification_report, "database_version", lambda: "16.10")
    monkeypatch.setattr(
        verification_report.subprocess, "check_output", lambda *a, **k: "test-version"
    )
    Path("docs").mkdir()
    Path("docs/VERIFICATION.md").write_text("### V-23 · Documentation — MUST\n")
    evidence = Path("artifacts/verification")
    evidence.mkdir(parents=True)
    for stage in ("lint", "tests", "live", "bench", "performance"):
        (evidence / f"{stage}.exit").write_text("0")
    assert verification_report.render() == 1
    (evidence / "live.xml").write_text(
        '<testsuite><testcase name="test_v23_readme"><failure>broken example</failure></testcase></testsuite>'
    )
    assert verification_report.render() == 1
    (evidence / "live.xml").write_text(
        '<testsuite><testcase name="test_v23_readme" time="1"/></testsuite>'
    )
    (evidence / "lint.exit").write_text("1")
    assert verification_report.render() == 1
    (evidence / "lint.exit").write_text("0")
    assert verification_report.render() == 0
