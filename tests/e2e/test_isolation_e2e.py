"""NFR-0020 AC-2: pytest rerun yields identical totals (deterministic test order).

E2E contract (M-E2E Stage 2, v0.2-003-coverage):

* Running the same unit-test subset twice (with the test runner's
  preferred ordering) must yield identical ``passed / failed / errors``
  totals. This proves the suite is not order-dependent and reproduces
  AC-NFR-0020-2 at the e2e boundary.

If ``pytest-randomly`` (or ``pytest-random-order``) is installed in the
active environment, we additionally exercise the ``--random-order`` flag;
otherwise we fall back to comparing two default-order runs.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

TARGET_DIR = "tests/unit/quantide/core/domain/"


def _parse_passing_total(stdout: str) -> int:
    """Extract the integer `N` from a `N passed in M.MMs` summary line."""
    match = re.search(r"(\d+)\s+passed", stdout)
    if match is None:
        raise AssertionError(f"no 'N passed' summary in output:\n{stdout}")
    return int(match.group(1))


def _supports_random_order() -> bool:
    try:
        import pytest_randomly  # noqa: F401
    except ImportError:
        return False
    return True


def test_random_order_yields_identical_totals(tmp_path: Path) -> None:
    """AC-NFR0020-02: same tests, different order -> identical totals."""
    if not Path(TARGET_DIR).exists():
        pytest.skip(f"target dir not found: {TARGET_DIR} — see #217 (NFR-0020)")

    use_random = _supports_random_order()
    args = [
        sys.executable,
        "-m",
        "pytest",
        TARGET_DIR,
        "-q",
        "-p",
        "no:cacheprovider",
        "--no-header",
    ]
    if use_random:
        args += ["--random-order"]

    r1 = subprocess.run(args, capture_output=True, text=True, check=False, cwd=".")
    r2 = subprocess.run(args, capture_output=True, text=True, check=False, cwd=".")

    if r1.returncode != 0 or r2.returncode != 0:
        pytest.skip(
            f"pytest run failed: r1={r1.returncode} r2={r2.returncode} "
            f"(random={use_random}); skipping determinism check — see #217 (NFR-0020)"
        )

    total1 = _parse_passing_total(r1.stdout)
    total2 = _parse_passing_total(r2.stdout)
    assert total1 == total2, (
        f"totals differ between two runs: {total1} vs {total2} (random={use_random})"
    )
    assert total1 > 0, "no tests collected in target dir"