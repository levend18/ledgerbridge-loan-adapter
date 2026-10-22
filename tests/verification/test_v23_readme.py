import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from adapter.shared import LoanType, TenantId, Unit
from tests.integration.test_sync_pipeline import upload
from tools.generate_synthetic import credit, payment
from tools.seed_users import seed_users
from workers.runtime import create_run, execute

pytestmark = pytest.mark.live_worker


def test_v23_readme_curl_examples():
    seed_users()
    unit = Unit(TenantId.BANK002, LoanType.RETAIL)
    run = create_run(unit, force=True)
    upload(
        [credit(i, installments=1) for i in (2001, 2002)],
        [payment(i, 1) for i in (2001, 2002)],
        unit,
    )
    assert execute(run.id).status == "SUCCEEDED"
    text = Path("README.md").read_text()
    blocks = re.findall(r"<!-- verification: curl -->\s*```bash\n(.*?)```", text, re.S)
    assert len(blocks) == 1
    result = subprocess.run(
        ["sh", "-c", blocks[0]],
        env={**os.environ, "API": "http://api:8000"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    data, profiles, run = [json.loads(line) for line in result.stdout.splitlines()]
    assert data["tenant_id"] == "BANK002"
    assert len(data["results"]) == 2
    assert {row["tenant_id"] for row in data["results"]} == {"BANK002"}
    assert profiles["tenant_id"] == "BANK002"
    assert run["status"] == "SUCCEEDED"
    for path in ("Architecture.md", "architect.md", "docs/CODE_TOUR.md"):
        assert len(Path(path).read_text()) > 1000
    for diagram in ("flowchart", "sequenceDiagram", "stateDiagram-v2", "erDiagram"):
        assert diagram in Path("Architecture.md").read_text()
