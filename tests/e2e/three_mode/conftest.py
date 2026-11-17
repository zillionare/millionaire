"""Fixtures for cross-mode parity journeys."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_three_mode_data_state() -> Iterator[None]:
    """Keep parity brokers isolated from market data opened by earlier tests."""
    import quantide.data as data_module
    from quantide.data.models.daily_bars import daily_bars

    data_module._limit_price_store = None
    daily_bars._initialized = False
    daily_bars._store_path = Path("/dev/null")
    yield
