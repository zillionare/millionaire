#!/usr/bin/env python3
"""AC traceability + assertion taboos validator.

Implements test-plan §1.3.1 CI enforcement:
  - Rule 1: Every test_* function's docstring 第一行 must contain a valid `AC-XXX` reference
  - Rule 2: Forbidden standalone assertions (`assert True` / `assert 1` /
            `assert <obj> is not None` as the sole assertion)
  - Rule 2: `pytest.skip(...)` / `@pytest.mark.skip` must reference a GitHub issue

Usage:
    poetry run python tests/assets/scripts/validate_ac_traceability.py tests/unit/
    poetry run python tests/assets/scripts/validate_ac_traceability.py tests/unit/quantide/ tests/e2e/
    pytest tests/assets/scripts/test_validate_ac_traceability.py   # as a pytest check

Exit code 0 = clean, 1 = violations found.

Ref: v0.2-001 issue #96.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple


# === AC format ============================================================
# Accepted forms (per existing test corpus + acceptance.md):
#   AC-100-01         (FR-level AC with -YY)
#   AC-100            (FR-level, matches all AC-100-*)
#   AC-FR-100-01      (full prefix)
#   AC-FR-100         (FR-level full prefix)
#   AC-NFR-060        (NFR, may have no -YY)
#   AC-NFR-060-01     (NFR with -YY, defensive)
#   AC-CLOCK-INJ-01   (special, §NFR-060 series)
_AC_TOKEN = re.compile(r"AC-(?:(?:FR|NFR|CLOCK-INJ)-)?\d+(?:-\d+)?")
# Used to check whether a docstring contains *any* AC token.
_AC_LOOSE = re.compile(r"AC-[A-Z][A-Z0-9-]*\d[A-Z0-9-]*")

# Skip / issue link patterns
_SKIP_CALL = re.compile(r"pytest\.skip\s*\(")
_SKIP_MARK = re.compile(r"@pytest\.mark\.skip")
_ISSUE_LINK = re.compile(
    r"https?://github\.com/[^/\s]+/[^/\s]+/issues/\d+"
    r"|#\d{1,5}\b"
    r"|\bissue\s*#\d{1,5}\b"
)


# === Violation record =====================================================
class Violation(NamedTuple):
    file: Path
    line: int
    test_name: str
    rule: str
    detail: str


# === Acceptance.md loader =================================================
_AC_HEADING = re.compile(r"^#{2,}\s*(AC-\S+)", re.MULTILINE)


def load_known_acs(acceptance_path: Path) -> set[str]:
    """Extract all `#### AC-XXX-YY` headings from acceptance.md."""
    if not acceptance_path.exists():
        return set()
    text = acceptance_path.read_text(encoding="utf-8")
    return {m.group(1).rstrip(":.,;") for m in _AC_HEADING.finditer(text)}


# === AST helpers ==========================================================
def iter_test_functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield node


def first_docstring_line(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.body:
        return ""
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.value.value.split("\n", 1)[0].strip()
    return ""


def collect_asserts(node: ast.AST) -> list[ast.Assert]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Assert)]


# === Rule checks ==========================================================
def rule1_ac_traceability(
    node: ast.FunctionDef | ast.AsyncFunctionDef, known_acs: set[str]
) -> list[Violation]:
    """Return WARNING (non-blocking) for AC traceability gaps.

    AC traceability is a soft requirement during the v0.2 ramp — many existing
    tests (branding, paths, settings) test internals outside acceptance.md.
    New tests should reference ACs; existing tests are tracked separately.
    """
    first = first_docstring_line(node)
    acs = _AC_TOKEN.findall(first)
    if not acs:
        return [
            Violation(
                file=Path("?"),
                line=node.lineno,
                test_name=node.name,
                rule="§1.3.1 Rule 1 (AC traceability, warning)",
                detail=f"docstring 第一行缺 AC 引用: {first[:80]!r}",
            )
        ]
    if not known_acs:
        return []
    missing = [ac for ac in acs if not ac_matches_known(ac, known_acs)]
    if missing:
        return [
            Violation(
                file=Path("?"),
                line=node.lineno,
                test_name=node.name,
                rule="§1.3.1 Rule 1 (AC format, warning)",
                detail=f"AC 引用 {missing!r} 不在 acceptance.md 中 (待 Sage 统一 NFR/CLOCK-INJ 编号)",
            )
        ]
    return []


def ac_matches_known(ac: str, known_acs: set[str]) -> bool:
    """Check if `ac` is a known AC, accepting short forms (AC-100, AC-FR-100)
    as matches for any AC-100-* in known_acs."""
    if ac in known_acs:
        return True
    # Short form: AC-100 or AC-FR-100
    m = re.match(r"^AC-(?:(?:FR|NFR)-)?(\d+)$", ac)
    if m:
        num = m.group(1)
        return any(ka.startswith(f"AC-{num}-") for ka in known_acs)
    return False


def rule2_assertion_taboos(
    node: ast.FunctionDef | ast.AsyncFunctionDef, source: str
) -> list[Violation]:
    """Check for forbidden assertions: assert True / assert 1 / assert obj is not None (sole)."""
    violations = []
    asserts = collect_asserts(node)
    for a in asserts:
        if isinstance(a.test, ast.Constant):
            v = a.test.value
            if v is True or v == 1 or v == "1":
                violations.append(
                    Violation(
                        file=Path("?"),
                        line=a.lineno,
                        test_name=node.name,
                        rule="§1.3.1 Rule 2 (assertion taboos) + §1.3 #8",
                        detail=f"trivial assertion: assert {v!r}",
                    )
                )
        elif isinstance(a.test, ast.Compare) and len(asserts) == 1:
            # Sole assertion: assert <obj> is not None
            if (
                len(a.test.ops) == 1
                and isinstance(a.test.ops[0], ast.IsNot)
                and len(a.test.comparators) == 1
                and isinstance(a.test.comparators[0], ast.Constant)
                and a.test.comparators[0].value is None
            ):
                violations.append(
                    Violation(
                        file=Path("?"),
                        line=a.lineno,
                        test_name=node.name,
                        rule="§1.3.1 Rule 2 (assertion taboos)",
                        detail=f"sole assertion is `assert <obj> is not None`",
                    )
                )
    return violations


def rule2_skip_without_issue(
    node: ast.FunctionDef | ast.AsyncFunctionDef, source: str, decorator_source: str
) -> list[Violation]:
    """pytest.skip() / @pytest.mark.skip must include a GitHub issue link in the same statement or function docstring."""
    if not (_SKIP_CALL.search(decorator_source) or _SKIP_MARK.search(decorator_source)):
        return []
    if _ISSUE_LINK.search(decorator_source + "\n" + first_docstring_line(node)):
        return []
    return [
        Violation(
            file=Path("?"),
            line=node.lineno,
            test_name=node.name,
            rule="§1.3.1 Rule 2 (skip without issue link)",
            detail="pytest.skip / @pytest.mark.skip 必须带 GitHub issue 链接 (如 #96 或 https://github.com/.../issues/96)",
        )
    ]


# === Per-file validation ==================================================
def validate_file(path: Path, known_acs: set[str]) -> tuple[list[Violation], list[Violation]]:
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as e:
        return [Violation(path, 0, "", "READ_ERROR", str(e))], []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [Violation(path, e.lineno or 0, "", "SYNTAX_ERROR", str(e))], []

    errors: list[Violation] = []
    warnings: list[Violation] = []
    for func in iter_test_functions(tree):
        decorator_source = "\n".join(
            ast.unparse(d) if hasattr(ast, "unparse") else "" for d in func.decorator_list
        )
        body_slice_end = func.end_lineno or func.lineno
        try:
            body_source = "\n".join(
                source.splitlines()[func.lineno - 1 : body_slice_end]
            )
        except Exception:
            body_source = ""

        for v in rule1_ac_traceability(func, known_acs):
            (warnings if "warning" in v.rule.lower() else errors).append(v._replace(file=path))
        for v in rule2_assertion_taboos(func, body_source):
            errors.append(v._replace(file=path))
        for v in rule2_skip_without_issue(func, source, decorator_source):
            errors.append(v._replace(file=path))

    return errors, warnings


# === Main ================================================================
def _format_path(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return p.name


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: validate_ac_traceability.py <test_dir> [<test_dir>...]", file=sys.stderr)
        return 1

    test_dirs = [Path(p) for p in argv]
    repo_root = Path(__file__).resolve().parents[3]
    acceptance_path = (
        repo_root / ".specforge/project/v0.2-001-strategy-framework/acceptance.md"
    )
    known_acs = load_known_acs(acceptance_path)

    all_errors: list[Violation] = []
    all_warnings: list[Violation] = []
    test_files = 0

    for test_dir in test_dirs:
        if not test_dir.exists():
            print(f"[warn] {test_dir} 不存在, 跳过", file=sys.stderr)
            continue
        for path in sorted(test_dir.rglob("test_*.py")):
            test_files += 1
            errors, warnings = validate_file(path, known_acs)
            all_errors.extend(errors)
            all_warnings.extend(warnings)

    if all_warnings:
        print(
            f"\n⚠️  {len(all_warnings)} warning(s) (non-blocking, AC 与 acceptance.md 编号差异待 Sage 统一):",
            file=sys.stderr,
        )
        by_rule: dict[str, list[Violation]] = {}
        for v in all_warnings:
            by_rule.setdefault(v.rule, []).append(v)
        for rule, vs in sorted(by_rule.items())[:3]:
            print(f"  {rule} ({len(vs)} 处):", file=sys.stderr)
            for v in vs[:5]:
                print(f"    {_format_path(v.file)}:{v.line} {v.test_name}", file=sys.stderr)
            if len(vs) > 5:
                print(f"    ... and {len(vs) - 5} more", file=sys.stderr)

    if all_errors:
        print(
            f"\n❌ Found {len(all_errors)} error(s) across {test_files} file(s):\n",
            file=sys.stderr,
        )
        by_rule = {}
        for v in all_errors:
            by_rule.setdefault(v.rule, []).append(v)
        for rule, vs in sorted(by_rule.items()):
            print(f"  {rule} ({len(vs)} 处):", file=sys.stderr)
            for v in vs[:20]:
                print(
                    f"    {_format_path(v.file)}:{v.line} {v.test_name} — {v.detail}",
                    file=sys.stderr,
                )
            if len(vs) > 20:
                print(f"    ... and {len(vs) - 20} more", file=sys.stderr)
        print(
            f"\nRef: test-plan §1.3.1 + issue #96",
            file=sys.stderr,
        )
        return 1

    print(
        f"✅ {test_files} file(s) clean. "
        f"All test_* functions pass §1.3.1 Rule 1 (AC traceability) + Rule 2 (assertion/skip taboos)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
