"""Smoke test for the env fixture (tests/unit/conftest.py)."""
from __future__ import annotations


def test_env_fixture_loads(env) -> None:
    assert env.manifest["version"] == 1
    assert env.manifest["kind"] == "unit"
    assert env.calendar.height == 365
    assert env.daily_bars["asset"].n_unique() >= 100


def test_env_helper_is_trade_day(env) -> None:
    assert env.is_trade_day("20220615") is True
    assert env.is_trade_day("20220101") is False  # 2022-01-01 is Saturday
    assert env.is_trade_day("20220102") is False  # Sunday


def test_env_helper_count_trading_days(env) -> None:
    n = env.count_trading_days("20220101", "20221231")
    assert n == 242


def test_env_helper_day_shift(env) -> None:
    d = env.day_shift("20220615", 1)
    assert d == "20220616"
    d_back = env.day_shift("20220615", -1)
    assert d_back == "20220614"
