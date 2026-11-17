"""Lightweight revisions for point-in-time universe inputs."""

from __future__ import annotations

from pathlib import Path

PIT_INPUT_FILES = (
    "calendar.parquet",
    "stock_list.parquet",
    "daily_basic.parquet",
    "stock_status_pit.parquet",
)


def pit_input_signature(data_home: str | Path) -> tuple[tuple[str, int, int], ...]:
    """Return stable size/mtime records without reading market-scale contents."""
    directory = Path(data_home) / "data"
    records: list[tuple[str, int, int]] = []
    for name in PIT_INPUT_FILES:
        try:
            stat = (directory / name).stat()
        except OSError:
            continue
        records.append((name, stat.st_size, stat.st_mtime_ns))
    return tuple(records)
