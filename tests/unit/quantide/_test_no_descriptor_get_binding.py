"""RED check: forbid brittle `__get__` descriptor binding in B08 helper tests.

Prism Blocker B3: tests used `ClassName._method.__get__(stub)` to bind
private methods to empty stub instances. This depends on CPython
descriptor protocol internals, tests private methods directly rather
than through public API, and silently breaks if the class hierarchy
changes. The fix is to use the real class with proper init mocks
(production code is frozen for this mission).
"""

from __future__ import annotations

import pathlib


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_FLAGGED_FILES = [
    "tests/unit/quantide/service/test_v0204_b08_init_wizard_helpers.py",
    "tests/unit/quantide/web/pages/test_v0204_b08_strategy_helpers.py",
]


def _uses_descriptor_get_binding(path: pathlib.Path) -> list[int]:
    """Return line numbers where `.__get__(` descriptor binding appears.

    Args:
        path: Absolute path to a Python test module.

    Returns:
        List of 1-based line numbers containing the brittle pattern.
    """
    offenders: list[int] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if ".__get__(" in line and "_method.__get__" not in stripped:
            offenders.append(lineno)
    return offenders


def test_no_descriptor_get_binding_in_b08_helper_tests() -> None:
    """[AC-NFR1101-02] B08 helper tests must not use `.__get__(stub)` binding.

    The flagged files must exercise private helpers via the real class
    instance (with init mocks where needed) or via `@staticmethod`/
    public API - never through CPython descriptor protocol internals
    that silently break when the class hierarchy changes.
    """
    offenders: list[str] = []
    for rel in _FLAGGED_FILES:
        path = _REPO_ROOT / rel
        lines = _uses_descriptor_get_binding(path)
        if lines:
            offenders.append(f"{rel}: lines {lines}")
    assert not offenders, "brittle __get__ descriptor binding found:\n" + "\n".join(offenders)
