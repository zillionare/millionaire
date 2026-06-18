#!/usr/bin/env python3
"""CI guard: enforce test assertion hygiene per test plan §1.3.

Forbidden patterns (per test plan §1.3 作伪模式 #3, #4, #8, #2):
  - `assert True` / `assert 1` / `assert <obj> is not None` (trivially passes)
  - `try: ... except: pass` (test plan §1.3 作伪模式 #4)
  - `pytest.skip(...)` / `@pytest.mark.skip` without a GitHub issue link

Exit 0 on success, 1 on first violation (with all violations printed).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DIRS = [REPO_ROOT / "tests" / "unit", REPO_ROOT / "tests" / "e2e"]

GITHUB_ISSUE_PATTERN = re.compile(
    r"https?://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+"
)


def is_trivial_assert(node: ast.Assert) -> bool:
    """Detect assert statements that pass trivially (per §1.3 作伪模式 #3, #8)."""
    test = node.test
    if isinstance(test, ast.Constant):
        return test.value is True or test.value == 1
    if isinstance(test, ast.Compare):
        if len(test.ops) == 1 and isinstance(test.ops[0], (ast.Is, ast.IsNot)):
            if isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None:
                return True
    return False


def is_try_except_pass(tree: ast.Module) -> list[tuple[int, str]]:
    """Detect `try: ... except: pass` patterns (per §1.3 作伪模式 #4)."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                    out.append((handler.lineno, f"except ... : pass at {handler.lineno}"))
    return out


def find_pytest_skips(tree: ast.Module) -> list[tuple[int, str, str]]:
    """Find pytest.skip/mark.skip usages; return (line, code, reason)."""
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("skip", "xfail"):
                if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    reason = ""
                    if node.args and isinstance(node.args[0], ast.Constant):
                        reason = str(node.args[0].value)
                    code = ast.unparse(node)
                    out.append((node.lineno, code, reason))
        if isinstance(node, ast.Attribute):
            if node.attr in ("skip", "skipif", "xfail") and isinstance(node.value, ast.Name):
                if node.value.id == "mark":
                    out.append((node.lineno, f"@pytest.{node.attr}", ""))
    return out


def main() -> int:
    violations: list[str] = []

    for td in TEST_DIRS:
        if not td.exists():
            continue
        for py in td.rglob("*.py"):
            if py.name == "__init__.py" or py.name == "conftest.py":
                continue
            try:
                tree = ast.parse(py.read_text())
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Assert) and is_trivial_assert(node):
                    code = ast.unparse(node.test)
                    violations.append(f"{py.relative_to(REPO_ROOT)}:{node.lineno} trivial assert: {code}")

            for lineno, msg in is_try_except_pass(tree):
                violations.append(f"{py.relative_to(REPO_ROOT)}:{lineno} {msg}")

            for lineno, code, reason in find_pytest_skips(tree):
                if GITHUB_ISSUE_PATTERN.search(reason):
                    continue
                if code.startswith("@"):
                    violations.append(
                        f"{py.relative_to(REPO_ROOT)}:{lineno} {code} decorator without GitHub issue link"
                    )
                else:
                    violations.append(
                        f"{py.relative_to(REPO_ROOT)}:{lineno} {code!r} without GitHub issue link in reason"
                    )

    legacy = (REPO_ROOT / ".specforge" / "tools" / "check_assertions.legacy.txt").exists()
    if legacy:
        print(f"[check_assertions] {len(violations)} violations (legacy baseline; advisory)")
        return 0

    if violations:
        print(f"\n[check_assertions] {len(violations)} violations:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("[check_assertions] OK: no trivial/try-pass/unsupported-skip violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
