"""FR-0102 + NFR-0010: per-file coverage checker end-to-end (synthetic coverage.json).

E2E contract (M-E2E Stage 2, v0.2-003-coverage):

* ``tests/unit/_checkers/per_file_coverage.py`` exits 0 when every
  ``quantide/**/*.py`` file with ``num_statements>0`` is at >=80% and the
  overall percent is >=95 (AC-FR-0102-2 + NFR-0010 AC-1).
* The checker exits non-zero when an un-waived file drops below 80%
  (AC-FR-0102-1).

The checker CLI takes positional arguments: ``coverage.json [waivers.json]``.
A waiver file path is optional; when omitted, the checker falls back to a
default under ``.louke/project/specs/v0.2-003-coverage/`` (we never want to
read that on disk in this isolated subprocess, so we always pass a custom
``waivers.json`` of our own).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

CHECKER = Path("tests/unit/_checkers/per_file_coverage.py")


def _run_checker(cov: dict, waivers: dict) -> subprocess.CompletedProcess:
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        (tmp_p / "coverage.json").write_text(json.dumps(cov))
        (tmp_p / "waivers.json").write_text(json.dumps(waivers))
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                str(tmp_p / "coverage.json"),
                str(tmp_p / "waivers.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )


def test_checker_passes_when_all_above_threshold() -> None:
    """AC-FR0102-02 / AC-NFR0010-01: all files >=80% + overall >=95% -> exit 0."""
    cov = {
        "totals": {"percent_covered": 96.0, "num_statements": 1000},
        "files": {
            "quantide/core/foo.py": {
                "summary": {"percent_covered": 85.0, "num_statements": 100}
            },
            "quantide/core/bar.py": {
                "summary": {"percent_covered": 92.0, "num_statements": 200}
            },
        },
    }
    r = _run_checker(cov, {"waivers": []})
    assert r.returncode == 0, (
        f"checker failed unexpectedly:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    )


def test_checker_fails_when_file_below_threshold() -> None:
    """AC-FR0102-01: file at 79.99% without waiver -> exit non-zero."""
    cov = {
        "totals": {"percent_covered": 96.0, "num_statements": 1000},
        "files": {
            "quantide/core/foo.py": {
                "summary": {"percent_covered": 79.99, "num_statements": 100}
            },
        },
    }
    r = _run_checker(cov, {"waivers": []})
    assert r.returncode != 0
    assert "below 80%" in r.stderr or "is below 80%" in r.stderr


def test_checker_fails_when_overall_below_threshold() -> None:
    """AC-FR0102-02 / AC-NFR0010-01: overall <95% with files >=80% -> exit non-zero."""
    cov = {
        "totals": {"percent_covered": 94.99, "num_statements": 1000},
        "files": {
            "quantide/core/foo.py": {
                "summary": {"percent_covered": 95.0, "num_statements": 100}
            },
        },
    }
    r = _run_checker(cov, {"waivers": []})
    assert r.returncode != 0
    assert "overall coverage" in r.stderr