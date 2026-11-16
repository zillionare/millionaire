"""Resolve generated runtime output independently of the working directory."""

import hashlib
import os
import tempfile
from pathlib import Path


def external_runtime_path(value: str | Path) -> Path:
    """Reject runtime output inside the source tree, including symlink aliases."""
    path = Path(value).expanduser().absolute()
    source = Path(__file__).resolve().parents[2]
    if (source / "pyproject.toml").is_file() and path.resolve().is_relative_to(source):
        raise ValueError("Runtime output must be outside the source checkout")
    return path


def temporary_runtime_dir() -> Path:
    """Use a stable per-user subdirectory of /tmp, or native Windows TEMP."""
    base = Path(tempfile.gettempdir()) if os.name == "nt" else Path("/tmp")
    profile = hashlib.sha256(str(Path.home()).encode()).hexdigest()[:12]
    return external_runtime_path(base / "millionaire" / f"runtime-{profile}")


def console_log_path() -> Path:
    """Read the development log directory from configuration, falling back to tmp."""
    configured = os.environ.get("QUANTIDE_LOG_HOME", "").strip()
    directory = external_runtime_path(configured or temporary_runtime_dir() / "logs")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory / "development.log"
