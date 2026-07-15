"""RED check: enforce AC anchor references in B08 helper test docstrings.

Prism Blocker B1: 20 new/modified test files contain ZERO AC-FRXXXX-YY
or AC-NFRXXXX-YY anchor references in test function docstrings, violating
test-plan §1.4.1, acceptance AC-FR1601-02, and NFR-1101 AC-2.

Each test function must carry a docstring whose first line contains an
AC anchor like `[AC-FR1501-04]` or `[AC-NFR1101-01]`.
"""

from __future__ import annotations

import ast
import pathlib
import re


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_AC_PATTERN = re.compile(r"\[AC-(?:FR|NFR)\d{4}-\d{2}\]")


_B1_FILES = [
    "tests/unit/quantide/web/auth/test_v0204_b08_admin_routes.py",
    "tests/unit/quantide/web/auth/test_v0204_b08_forms.py",
    "tests/unit/quantide/web/auth/test_v0204_b08_middleware.py",
    "tests/unit/quantide/web/auth/test_v0204_b08_repository.py",
    "tests/unit/quantide/web/auth/test_v0204_b08_routes.py",
    "tests/unit/quantide/web/apis/analysis/test_v0204_b08_kline.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_accounts_2.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_data_market.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_home_1.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_init_wizard_helpers.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_live_1.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_paper_1.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_strategy_build_helpers.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_strategy_helpers.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_trade_lightning_helpers.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_trade_main_2.py",
    "tests/unit/quantide/web/pages/system/test_v0204_b08_datasource.py",
    "tests/unit/quantide/web/pages/system/test_v0204_b08_jobs_helpers_2.py",
    "tests/unit/quantide/web/pages/system/test_v0204_b08_system_gateway.py",
    "tests/unit/quantide/service/test_v0204_b08_init_wizard_helpers.py",
]


def _missing_ac_anchors(path: pathlib.Path) -> list[tuple[str, int]]:
    """Return (function_name, line) for test functions missing an AC anchor.

    Args:
        path: Absolute path to a Python test module.

    Returns:
        List of (function_name, line_number) tuples for `test_*` functions
        whose docstring is missing or whose first docstring line does not
        contain an `[AC-FRXXXX-YY]` or `[AC-NFRXXXX-YY]` anchor.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        doc = ast.get_docstring(node)
        if not doc or not _AC_PATTERN.search(doc.splitlines()[0]):
            missing.append((node.name, node.lineno))
    return missing


def test_b1_files_have_ac_anchors() -> None:
    """[AC-FR1601-02] B08 helper test functions must carry AC anchors.

    Each test function in the 20 files flagged by Prism Blocker B1 must
    have a docstring whose first line contains an AC anchor reference
    like `[AC-FR1501-04]` or `[AC-NFR1101-01]`.
    """
    offenders: list[str] = []
    for rel in _B1_FILES:
        path = _REPO_ROOT / rel
        if not path.exists():
            continue
        missing = _missing_ac_anchors(path)
        if missing:
            sample = missing[:3]
            offenders.append(
                f"{rel}: {len(missing)} missing (e.g. {sample})"
            )
    assert not offenders, "missing AC anchors:\n" + "\n".join(offenders)
