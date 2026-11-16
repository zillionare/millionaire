"""Reject empty, failed, skipped or xfailed release acceptance reports."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def validate(path: Path) -> int:
    """Require actual passing test cases; never trust an exit-zero empty run."""
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError(f"unsupported JUnit root: {root.tag}")
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("acceptance report contains no test cases")
    for suite in root.iter("testsuite"):
        for field in ("errors", "failures", "skipped"):
            if int(suite.get(field, "0")):
                raise ValueError(f"acceptance suite reports {field}")
    for case in cases:
        if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
            raise ValueError(f"acceptance did not pass: {case.get('name', '<unnamed>')}")
    return len(cases)


def main(argv: list[str] | None = None) -> int:
    """Use together with pytest --runxfail so expected failures cannot pass release."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        count = validate(args.report)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"Acceptance gate failed: {exc}", file=sys.stderr)
        return 1
    print(f"Acceptance gate passed: {count} tests, no skips or expected failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
