"""Durable same-directory replacement for small state and Parquet files."""

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from filelock import FileLock


@contextlib.contextmanager
def atomic_path(destination: str | Path) -> Iterator[Path]:
    """Yield a temporary path; publish only after the writer succeeds."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        if os.name != "nt":
            descriptor = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def read_json_dict(path: str | Path) -> dict[str, Any]:
    """Read a JSON object; missing, unreadable or non-object files are empty."""
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(destination: str | Path, payload: Any) -> None:
    """Validate and atomically publish JSON, preserving the previous file on failure."""
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(destination) + ".lock", timeout=30):
        if destination.exists():
            previous = destination.read_text(encoding="utf-8")
            # Never overwrite a known-good backup with a corrupt current file.
            json.loads(previous)
            with atomic_path(str(destination) + ".bak") as backup:
                backup.write_text(previous, encoding="utf-8")
        with atomic_path(destination) as temporary:
            temporary.write_text(encoded, encoding="utf-8")


def write_parquet(frame: Any, destination: str | Path, **kwargs: Any) -> None:
    """Publish a completed Parquet file; readers never see a truncated file."""
    kwargs.pop("mkdir", None)
    with atomic_path(destination) as temporary:
        frame.write_parquet(temporary, **kwargs)
