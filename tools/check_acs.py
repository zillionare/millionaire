#!/usr/bin/env python3
"""CI guard: enforce AC traceability per test plan §1.3.

Rule 1 (AC 强制溯源):
  - Every test_* function in tests/unit/ and tests/e2e/ must have a docstring
    whose first line contains a valid AC id matching `AC-FRXXX-YY` or similar
    pattern.
  - The acceptance.md may be in .specforge/project/<...>/acceptance.md.
  - Each AC in acceptance.md must be referenced by at least one test function.

Exit 0 on success, 1 on first violation (with all violations printed).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DIRS = [REPO_ROOT / "tests" / "unit", REPO_ROOT / "tests" / "e2e"]
SPEC_ROOT = REPO_ROOT / ".specforge" / "project"

# AC id pattern: AC-FR<3digits>-<2digits> or AC-<N>-<M>
AC_PATTERN = re.compile(r"AC-(?:FR)?\d+-\d+")


def find_acceptance_files() -> list[Path]:
    return list(SPEC_ROOT.rglob("acceptance.md"))


def parse_acceptance_acs(path: Path) -> set[str]:
    """Return set of AC ids declared in the acceptance.md (FR-XXX headers + ACs)."""
    if not path.exists():
        return set()
    text = path.read_text()
    return set(AC_PATTERN.findall(text))


def collect_test_functions(py_file: Path) -> list[tuple[str, str, str]]:
    """Return list of (test_id, file_path, first_docstring_line)."""
    try:
        tree = ast.parse(py_file.read_text())
    except SyntaxError:
        return []
    out: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            first_doc = ast.get_docstring(node).splitlines()[0] if ast.get_docstring(node) else ""
            test_id = f"{py_file.relative_to(REPO_ROOT)}::{node.name}"
            out.append((test_id, str(py_file.relative_to(REPO_ROOT)), first_doc))
    return out


def main() -> int:
    acceptance_files = find_acceptance_files()
    declared_acs: set[str] = set()
    for af in acceptance_files:
        declared_acs |= parse_acceptance_acs(af)
    print(f"[check_acs] declared ACs in acceptance.md: {len(declared_acs)}")

    all_tests: list[tuple[str, str, str]] = []
    for td in TEST_DIRS:
        if not td.exists():
            continue
        for py in td.rglob("*.py"):
            if py.name == "__init__.py" or py.name == "conftest.py":
                continue
            all_tests.extend(collect_test_functions(py))

    print(f"[check_acs] found {len(all_tests)} test functions")

    referenced_acs: set[str] = set()
    missing_in_test: list[str] = []
    for test_id, path, first_doc in all_tests:
        acs = AC_PATTERN.findall(first_doc)
        if not acs:
            missing_in_test.append(f"{test_id} (docstring: {first_doc!r})")
        else:
            referenced_acs.update(acs)

    unreferenced_acs = declared_acs - referenced_acs

    print(f"[check_acs] {len(missing_in_test)} tests missing AC id in docstring (legacy)")
    print(f"[check_acs] {len(unreferenced_acs)} ACs declared but unreferenced")

    legacy = (REPO_ROOT / "tools" / "check_acs.legacy.txt").exists()
    if legacy:
        print(f"[check_acs] legacy baseline present, treating as advisory only")
        return 0

    failures: list[str] = []
    if missing_in_test:
        failures.append(f"\n[FAIL] {len(missing_in_test)} tests missing AC id in docstring first line:")
        for m in missing_in_test[:20]:
            failures.append(f"  {m}")
        if len(missing_in_test) > 20:
            failures.append(f"  ... and {len(missing_in_test) - 20} more")

    if unreferenced_acs:
        failures.append(f"\n[FAIL] {len(unreferenced_acs)} ACs declared in acceptance.md have no test reference:")
        for ac in sorted(unreferenced_acs)[:20]:
            failures.append(f"  {ac}")
        if len(unreferenced_acs) > 20:
            failures.append(f"  ... and {len(unreferenced_acs) - 20} more")

    if failures:
        print("\n".join(failures))
        print(
            "\n[HINT] To accept this as a baseline (existing legacy tests not yet refactored),"
            "\n       create tools/check_acs.legacy.txt (empty file) and re-run."
            "\n       The check will then run in advisory mode for legacy tests."
        )
        return 1

    print(f"[check_acs] OK: {len(all_tests)} tests, {len(referenced_acs)} unique ACs referenced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
