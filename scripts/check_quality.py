"""Run the same strict production quality gate locally and in CI."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from scripts.artifact_paths import artifact_root, external_path, layout_errors

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("quantide", "scripts")
TOOLS = ("ruff", "flake8", "flake8-cognitive-complexity", "cognitive-complexity", "pylint")


def commands(python: str) -> list[tuple[str, list[str]]]:
    """Keep duplicate detection global, including when only one file changed."""
    # Pylint's package recursion skips namespace directories without __init__.py.
    # Pass the same explicit inventory to every analyzer so service/ is covered.
    paths = [path.relative_to(ROOT).as_posix() for path in production_paths(ROOT)]
    return [
        ("lint-and-line-width", [python, "-m", "ruff", "check", *paths]),
        ("cognitive-complexity", [python, "-m", "flake8", "--disable-noqa", *paths]),
        (
            "duplication-and-size",
            [python, "-m", "pylint", "--rcfile=pyproject.toml", "--score=n", *paths],
        ),
    ]


def tool_versions(root: Path) -> dict[str, str]:
    """Reject absent or mismatched tools rather than silently changing the metric."""
    with (root / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    pins = config["tool"]["poetry"]["group"]["quality"]["dependencies"]
    versions = {name: importlib.metadata.version(name) for name in TOOLS}
    for name, actual in versions.items():
        if actual != pins[name]:
            raise ValueError(f"{name}: expected {pins[name]}, installed {actual}")
    return versions


def production_paths(root: Path) -> list[Path]:
    """Include namespace modules and reject an absent production inventory."""
    files = sorted(path for source in SOURCES for path in (root / source).rglob("*.py"))
    if any(not (root / source).is_dir() for source in SOURCES) or not files:
        raise ValueError("quality source inventory is missing or empty")
    return files


def source_digest(root: Path) -> tuple[int, str]:
    """Bind the evidence to every production source and its quality configuration."""
    files = production_paths(root)
    digest = hashlib.sha256()
    for path in [*files, root / "pyproject.toml", root / ".flake8"]:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return len(files), digest.hexdigest()


def run_check(name: str, command: list[str], root: Path) -> dict:
    """Capture every result; a failed check never prevents the other scans."""
    started = time.monotonic()
    try:
        process = subprocess.run(
            command, cwd=root, capture_output=True, text=True, check=False, timeout=300
        )
        code, output = process.returncode, process.stdout + process.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        code, output = 127, str(exc)
    print(f"[{name}] {'PASS' if code == 0 else 'FAIL'} (exit {code})", flush=True)
    if output:
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
    return {
        "name": name,
        "command": command,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 3),
        "output": output,
    }


def main(argv: list[str] | None = None) -> int:
    """Exit nonzero for any violation, missing tool or incomplete scan."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report", type=external_path, default=artifact_root() / "quality/quality.json"
    )
    args = parser.parse_args(argv)
    report: dict = {"schema_version": 1, "passed": False, "python": sys.version}
    try:
        report["tools"] = tool_versions(ROOT)
        report["source_files"], report["source_sha256"] = source_digest(ROOT)
        report["checks"] = [
            run_check(name, command, ROOT) for name, command in commands(sys.executable)
        ]
        misplaced = layout_errors(ROOT)
        report["checks"].append(
            {
                "name": "repository-layout",
                "exit_code": int(bool(misplaced)),
                "output": "\n".join(misplaced),
            }
        )
        report["passed"] = all(item["exit_code"] == 0 for item in report["checks"])
        if source_digest(ROOT) != (report["source_files"], report["source_sha256"]):
            raise ValueError("production sources or quality configuration changed during scan")
    except (OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError) as exc:
        report["error"] = str(exc)
        report["passed"] = False
        print(f"Quality gate cannot run: {exc}", file=sys.stderr)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
