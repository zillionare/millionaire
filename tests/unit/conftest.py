"""Pytest configuration for tests/unit/quantide/.

Provides session-scoped `env` fixture that loads the unit test data
(tests/assets/unit/fixtures/data/) per test plan §2.6.1.

Usage in test files:
    def test_xxx(env):
        cal = env.calendar
        opens = env.is_trade_day("20220615")
        n = env.count_trading_days("20220101", "20221231")
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

if TYPE_CHECKING:
    from polars import DataFrame


UNIT_ASSETS = Path(__file__).resolve().parents[2] / "tests" / "assets" / "unit"
FIXTURES = UNIT_ASSETS / "fixtures" / "data"
MANIFEST_PATH = UNIT_ASSETS / "env_manifest.json"
UNIVERSE_PATH = UNIT_ASSETS / "universe.json"
EXPECTED_VERSION = 1


@dataclass
class TestEnv:
    """In-memory view of the unit test environment (per test plan §2.6.1).

    Attributes mirror the fixture files. Tests should access data via these
    typed attributes, not by re-reading parquet files.
    """
    manifest: dict
    universe: "DataFrame"
    calendar: "DataFrame"
    daily_bars: "DataFrame"
    adj_factor: "DataFrame"
    st_info: "DataFrame"
    limit_price: "DataFrame"

    def is_trade_day(self, date: str) -> bool:
        row = self.calendar.filter(pl.col("date") == date)
        if row.is_empty():
            return False
        return bool(row["is_open"].item() == 1)

    def count_trading_days(self, start: str, end: str) -> int:
        return self.calendar.filter(
            (pl.col("is_open") == 1) & (pl.col("date") >= start) & (pl.col("date") <= end)
        ).height

    def day_shift(self, date: str, n: int) -> str:
        from tests.ground_truth.calendar import day_shift as _gt_day_shift
        return _gt_day_shift(self.calendar, date, n)

    def last_trade_date(self, on_or_before: str) -> str | None:
        from tests.ground_truth.calendar import last_trade_date as _gt_last
        return _gt_last(self.calendar, on_or_before)

    def first_trade_date(self, on_or_after: str) -> str | None:
        from tests.ground_truth.calendar import first_trade_date as _gt_first
        return _gt_first(self.calendar, on_or_after)

    def stocks_listed(self, on_date: str) -> list[str]:
        from tests.ground_truth.stocks import stocks_listed as _gt_stocks_listed
        return _gt_stocks_listed(self.universe, on_date)

    def is_st(self, asset: str, on_date: str) -> bool:
        from tests.ground_truth.stocks import is_st as _gt_is_st
        return _gt_is_st(self.st_info, asset, on_date)

    def days_since_ipo(self, asset: str, on_date: str) -> int:
        from tests.ground_truth.stocks import days_since_ipo as _gt_days
        return _gt_days(self.universe, asset, on_date)


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"env_manifest.json not found at {MANIFEST_PATH}. "
            "Run tests/assets/unit/scripts/build_env.py first."
        )
    return json.loads(MANIFEST_PATH.read_text())


def _require_assets() -> None:
    missing = []
    for f in ["daily_bars.parquet", "calendar.parquet", "adj_factor.parquet",
              "st_info.parquet", "limit_price.parquet"]:
        if not (FIXTURES / f).exists():
            missing.append(f)
    if missing:
        raise FileNotFoundError(
            f"Missing fixture files in {FIXTURES}: {missing}. "
            "Run tests/assets/unit/scripts/build_env.py first."
        )


def _close_subscribed_paper_brokers() -> None:
    """Close PaperBroker owners currently subscribed to the global MessageHub."""
    from quantide.core.message import msg_hub
    from quantide.service.sim_broker import PaperBroker

    with msg_hub._lock:
        callbacks = tuple(
            callback
            for topic_callbacks in msg_hub._subscribers.values()
            for callback in topic_callbacks
        )
    brokers = {
        owner
        for callback in callbacks
        if isinstance(owner := getattr(callback, "__self__", None), PaperBroker)
    }
    for broker in brokers:
        broker.close()


class _PaperBrokerCleanupProbe:
    """Records one broker whose MessageHub cleanup is asserted after test teardown."""

    def __init__(self) -> None:
        self._broker: object | None = None

    def expect_closed(self, broker: object) -> None:
        """Record a broker expected to be unsubscribed by the unit cleanup fixture.

        Args:
            broker: The directly constructed PaperBroker to verify.

        Returns:
            None.
        """
        self._broker = broker

    def assert_cleaned(self) -> None:
        """Assert that the recorded broker is absent from global MessageHub callbacks.

        Returns:
            None.

        Raises:
            AssertionError: If teardown leaves the recorded broker subscribed.
        """
        if self._broker is None:
            return
        from quantide.core.message import msg_hub

        with msg_hub._lock:
            callbacks = tuple(
                callback
                for topic_callbacks in msg_hub._subscribers.values()
                for callback in topic_callbacks
            )
        assert all(
            getattr(callback, "__self__", None) is not self._broker
            for callback in callbacks
        )


@pytest.fixture
def paper_broker_cleanup_probe():
    """Provide a teardown probe for direct PaperBroker cleanup tests."""
    probe = _PaperBrokerCleanupProbe()
    yield probe
    probe.assert_cleaned()


@pytest.fixture(autouse=True)
def close_unit_paper_brokers(paper_broker_cleanup_probe):
    """Release global MessageHub subscriptions owned by unit-test PaperBrokers."""
    yield
    _close_subscribed_paper_brokers()


@pytest.fixture(scope="session")
def env() -> TestEnv:
    """Session-scoped test environment per test plan §2.6.1."""
    _require_assets()
    manifest = _load_manifest()
    if manifest.get("version") != EXPECTED_VERSION:
        raise RuntimeError(
            f"env_manifest version mismatch: got {manifest.get('version')}, "
            f"expected {EXPECTED_VERSION}. Rebuild env."
        )
    return TestEnv(
        manifest=manifest,
        universe=pl.read_json(UNIVERSE_PATH),
        calendar=pl.read_parquet(FIXTURES / "calendar.parquet"),
        daily_bars=pl.read_parquet(FIXTURES / "daily_bars.parquet"),
        adj_factor=pl.read_parquet(FIXTURES / "adj_factor.parquet"),
        st_info=pl.read_parquet(FIXTURES / "st_info.parquet"),
        limit_price=pl.read_parquet(FIXTURES / "limit_price.parquet"),
    )


@pytest.fixture(scope="session")
def env_manifest() -> dict:
    """Just the manifest, for tests that don't need data."""
    return _load_manifest()


@pytest.fixture(scope="session")
def env_universe() -> "DataFrame":
    """Just the universe, for tests that need asset metadata only."""
    return pl.read_json(UNIVERSE_PATH)
