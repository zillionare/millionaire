"""Spawn worker with a large pre-existing virtual mapping for Linux RSS tests."""

from __future__ import annotations

import mmap
import sys

import polars as pl

_RESERVED = mmap.mmap(-1, 768 * 1024 * 1024, prot=0) if sys.platform.startswith("linux") else None


def healthy_polars_sum() -> int:
    """Run real Polars compute after the child has a large virtual baseline."""
    frame = pl.DataFrame({"x": list(range(20_000))})
    return int(frame.select((pl.col("x") * 2).sum()).item())
