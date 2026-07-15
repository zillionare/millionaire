"""RED check: detect duplicate test function definitions in test modules.

Prism Blocker B2 flagged `test_resolve_lightning_price_unknown_ref` defined
twice in `test_v0204_b08_trade_lightning_helpers.py`. Such duplicates are
silently shadowed by pytest collection. This regression test fails whenever
that file (or any sibling B08 helper test file flagged by Prism) defines
the same test name more than once.
"""

from __future__ import annotations

import ast
import pathlib


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _collect_duplicate_test_functions(path: pathlib.Path) -> dict[str, list[int]]:
    """Return mapping of duplicated test function name -> [line numbers].

    Args:
        path: Absolute path to a Python test module.

    Returns:
        Mapping of duplicated test function name -> list of line numbers
        where that name is defined. Empty dict if no duplicates.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return {}
    line_map: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            line_map.setdefault(node.name, []).append(node.lineno)
    return {name: lines for name, lines in line_map.items() if len(lines) > 1}


def test_no_duplicate_test_functions_in_b08_lightning_helpers() -> None:
    """[AC-FR1601-02] B08 lightning helpers must not define the same test twice.

    Prism Blocker B2: `test_resolve_lightning_price_unknown_ref` was defined
    at both line 226 and line 302 with identical bodies. The second
    definition silently shadowed the first; pytest only collected the last
    definition, so earlier coverage was lost without warning.
    """
    module = _REPO_ROOT / "tests/unit/quantide/web/pages/test_v0204_b08_trade_lightning_helpers.py"
    dups = _collect_duplicate_test_functions(module)
    assert not dups, f"duplicate test functions in {module.name}: {dups}"
