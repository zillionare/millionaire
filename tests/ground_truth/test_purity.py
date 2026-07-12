"""Verify ground_truth/ purity per test plan §3.

Rule: ground_truth modules MUST NOT import `quantide.*`. They are the
independent oracle; importing the module-under-test would be circular.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

GROUND_TRUTH_DIR = Path(__file__).resolve().parent


def _collect_imports(py_file: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, module) for all `import X` and `from X import Y`."""
    tree = ast.parse(py_file.read_text())
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append((node.lineno, node.module))
    return out


def test_ground_truth_does_not_import_quantide() -> None:
    """No file in tests/ground_truth/ may import quantide.*"""
    py_files = list(GROUND_TRUTH_DIR.glob("*.py"))
    py_files = [p for p in py_files if p.name != "__init__.py" and p.name != "test_purity.py"]

    assert py_files, "no ground_truth implementation files found"

    violations: list[str] = []
    allowed_prefixes = ("polars", "pandas", "numpy", "empyrical", "datetime", "dataclasses",
                        "importlib", "inspect", "pathlib", "typing", "__future__", "pytest")

    for py_file in py_files:
        for lineno, mod in _collect_imports(py_file):
            if mod.startswith("quantide"):
                violations.append(f"{py_file.name}:{lineno} imports {mod!r}")
            if not any(mod == p or mod.startswith(p + ".") for p in allowed_prefixes):
                violations.append(
                    f"{py_file.name}:{lineno} imports {mod!r} (not in allowed list)"
                )

    assert not violations, "ground_truth purity violations:\n  " + "\n  ".join(violations)


def test_ground_truth_files_exist() -> None:
    """The 3 core ground_truth modules per task list (calendar, stocks, discovery)."""
    expected = ["calendar.py", "stocks.py", "discovery.py"]
    for name in expected:
        path = GROUND_TRUTH_DIR / name
        assert path.exists(), f"missing ground_truth module: {name}"
        assert path.stat().st_size > 100, f"ground_truth module too small: {name}"
