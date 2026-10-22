from pathlib import Path


def test_v22_manual_acceptance_evidence():
    record = Path("docs/UI_VERIFICATION.md").read_text()
    for word in ("SUCCEEDED", "REJECTED", "BANK001", "BANK002", "version 63", "version 64"):
        assert word in record
    for name in ("login", "bank-upload", "sync", "data", "profiles", "validation-rejected"):
        image = Path(f"docs/screenshots/{name}.jpg").read_bytes()
        assert image[:2] == b"\xff\xd8"
        assert len(image) > 10000
