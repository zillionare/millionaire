"""Spawn worker with a large pre-existing virtual mapping for Linux RSS tests."""

from __future__ import annotations

import mmap
import sys
import time
from pathlib import Path

_RESERVED = mmap.mmap(-1, 768 * 1024 * 1024, prot=0) if sys.platform.startswith("linux") else None


def allocate_beyond_budget(marker: str) -> int:
    """Mark entry, touch 256 MB, then stay alive long enough for RSS sampling."""
    Path(marker).write_text("entered", encoding="utf-8")
    data = bytearray(256 * 1024 * 1024)
    for offset in range(0, len(data), 4096):
        data[offset] = offset % 251
    time.sleep(0.3)
    return len(data)


def healthy_polars_sum() -> int:
    """Run real Polars compute after the child has a large virtual baseline."""
    import polars as pl

    frame = pl.DataFrame({"x": list(range(20_000))})
    return int(frame.select((pl.col("x") * 2).sum()).item())
