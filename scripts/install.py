"""Create a local CE virtual environment and install the project.

This is a small, cross-platform developer installer. It intentionally does
not attempt to register an operating-system service or package the app into a
native installer.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VENV = PROJECT_ROOT / ".venv"


def _venv_python(venv_path: Path) -> Path:
    """Return the Python executable path for the current platform."""
    executable = "python.exe" if os.name == "nt" else "python"
    subdirectory = "Scripts" if os.name == "nt" else "bin"
    return venv_path / subdirectory / executable


def _run(command: list[str]) -> None:
    """Run a command while preserving its output and exit status."""
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> int:
    """Create the environment and install the current checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--venv",
        type=Path,
        default=DEFAULT_VENV,
        help="virtual-environment directory (default: .venv)",
    )
    parser.add_argument(
        "--ml30m",
        action="store_true",
        help="also install the optional LightGBM/Baostock 30-minute extra",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 13):  # noqa: UP036 - provide a clear installer error
        parser.error("Millionaire requires Python 3.13 or newer")

    venv_path = args.venv.expanduser()
    if not venv_path.is_absolute():
        venv_path = PROJECT_ROOT / venv_path
    if not (venv_path / "pyvenv.cfg").exists():
        print(f"Creating virtual environment: {venv_path}")
        venv.EnvBuilder(with_pip=True, clear=False).create(venv_path)

    python = _venv_python(venv_path)
    if not python.exists():
        raise RuntimeError(f"virtual-environment Python was not created: {python}")

    requirement = ".[ml30m]" if args.ml30m else "."
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(python), "-m", "pip", "install", "-e", requirement])

    print(f"Installed CE into {venv_path}")
    launcher = python.parent / ("millionaire.exe" if os.name == "nt" else "millionaire")
    print(f"Run: {launcher} --open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
