"""v0.2-003 NFR-0010 AC-NFR-0010-1..4 coverage gate contracts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/unit-coverage.yml"
WAIVERS = ROOT / ".louke/project/specs/v0.2-003-coverage/coverage-waivers.json"


def test_ci_uses_blocking_95_percent_overall_coverage_gate():
    """AC-NFR-0010-1,4: the canonical overall threshold remains blocking at 95%."""
    workflow = WORKFLOW.read_text()

    assert "--cov=quantide --cov-fail-under=95" in workflow
    assert "continue-on-error: true" not in workflow


def test_default_waivers_are_empty_and_have_the_required_container_schema():
    """AC-NFR-0010-2,3: waivers are explicit and empty by default."""
    waiver_data = json.loads(WAIVERS.read_text())

    assert waiver_data["spec_id"] == "v0.2-003-coverage"
    assert waiver_data["waivers"] == []
