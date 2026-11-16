"""Keep build, test and documentation output outside the source checkout."""

import argparse
import hashlib
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNEXPECTED_ROOTS = (
    "data",
    "dist",
    "packaging",
    "quality-reports",
    "review",
    "site",
    "build",
    "pypi-dist",
    ".demo_store",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".sesskey",
    "logs",
    "models",
    "htmlcov",
    "coverage.json",
    "coverage.xml",
    "quantide.db",
    "quantide.db-wal",
    "quantide.db-shm",
    "millionaire-service.xml",
)


def layout_errors(root: Path) -> list[str]:
    """Reject checkout-local generated output and misplaced support resources."""
    misplaced = [name for name in UNEXPECTED_ROOTS if (root / name).exists()]
    misplaced.extend(
        path.name
        for path in root.glob(".coverage*")
        if path.is_file() and path.name != ".coveragerc"
    )
    return [f"Unexpected checkout artifact: {name}" for name in misplaced]


def external_path(value) -> Path:
    """Reject output paths inside the checkout, including symlink aliases."""
    path = Path(value).expanduser().resolve()
    if path.is_relative_to(ROOT.resolve()) or "\n" in str(path) or "\r" in str(path):
        raise ValueError("Artifact output must be outside the source checkout")
    return path


def artifact_root() -> Path:
    """Select /tmp on POSIX and the native temporary directory on Windows."""
    configured = os.environ.get("MILLIONAIRE_ARTIFACTS_DIR", "").strip()
    base = Path(tempfile.gettempdir()) if os.name == "nt" else Path("/tmp")
    workspace = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    return external_path(configured or base / "millionaire" / workspace)


def artifact_environment() -> dict[str, str]:
    """Configure native temporary paths for tools, including child processes."""
    root = artifact_root()
    for name in ("quality", "coverage", "dist", "installers", "work", "site", "pypi-dist"):
        (root / name).mkdir(parents=True, exist_ok=True)
    cache = shlex.quote(f"cache_dir={root / 'pytest-cache'}")
    return {
        "MILLIONAIRE_ARTIFACTS_DIR": str(root),
        "COVERAGE_FILE": str(root / "coverage/.coverage"),
        "RUFF_CACHE_DIR": str(root / "ruff-cache"),
        "MYPY_CACHE_DIR": str(root / "mypy-cache"),
        "PYTEST_ADDOPTS": f"{os.environ.get('PYTEST_ADDOPTS', '')} -o {cache}".strip(),
    }


def main(argv=None) -> int:
    """Print the workspace path, configure Actions, or run a development tool."""
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--github-env", action="store_true")
    options.add_argument("--run", nargs=argparse.REMAINDER)
    options.add_argument("--check-layout", action="store_true")
    args = parser.parse_args(argv)
    environment = artifact_environment()
    if args.check_layout:
        errors = layout_errors(ROOT)
        print("\n".join(errors) if errors else "Repository layout passed")
        return int(bool(errors))
    if args.github_env:
        with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
            output.write("".join(f"{key}={value}\n" for key, value in environment.items()))
    elif args.run is not None:
        if not args.run:
            parser.error("--run requires a command")
        return subprocess.run(args.run, env={**os.environ, **environment}, check=False).returncode
    else:
        print(environment["MILLIONAIRE_ARTIFACTS_DIR"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
