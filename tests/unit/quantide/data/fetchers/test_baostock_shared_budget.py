"""Quotas survive process boundaries and sessions cannot interleave across instances."""

import concurrent.futures
import datetime
from unittest.mock import MagicMock

import pytest

from quantide.data.fetchers.baostock_budget import BaostockBudget, BaostockThrottledError
from quantide.data.fetchers.baostock_minute import BaostockMinuteFetcher


def test_shared_budget_reserves_atomically_and_survives_recreation(tmp_path):
    path = tmp_path / "budget.json"
    def request(_):
        try:
            BaostockBudget(path, 5).consume()
            return True
        except BaostockThrottledError:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(request, range(20))) == 5
    assert BaostockBudget(path, 5).status()["used"] == 5
    with pytest.raises(BaostockThrottledError, match="预算"):
        BaostockBudget(path, 5).consume()


def test_persistent_freeze_increases_and_includes_cooldown(tmp_path, monkeypatch):
    now = datetime.datetime(2026, 1, 1, 12)
    monkeypatch.setattr("quantide.data.fetchers.baostock_budget.market_now", lambda: now)
    path = tmp_path / "budget.json"
    assert BaostockBudget(path, 100).freeze() == "2026-01-01T18:05:00"
    now = datetime.datetime(2026, 1, 2, 12)
    assert BaostockBudget(path, 100).freeze() == "2026-01-03T00:05:00"
    with pytest.raises(BaostockThrottledError, match="黑名单"):
        BaostockBudget(path, 100).check()


def test_corrupt_budget_fails_closed(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        BaostockBudget(path, 100).consume()


def test_fetcher_instances_share_socket_lock_and_each_query_reserves(tmp_path, monkeypatch):
    import baostock
    monkeypatch.setattr("quantide.data.fetchers.baostock_minute.get_app_config_dir", lambda: tmp_path)
    first, second = BaostockMinuteFetcher(daily_budget=1), BaostockMinuteFetcher(daily_budget=1)
    assert first._lock is second._lock
    monkeypatch.setattr(baostock, "login", lambda: MagicMock(error_code="0"))
    monkeypatch.setattr(baostock, "logout", lambda: None)
    response = MagicMock(error_code="0")
    response.next.return_value = False
    query = MagicMock(return_value=response)
    monkeypatch.setattr(baostock, "query_history_k_data_plus", query)
    day = datetime.date(2024, 1, 2)
    first.fetch_minute_bars("600000.SH", day, day)
    with pytest.raises(BaostockThrottledError, match="预算"):
        second.fetch_minute_bars("600000.SH", day, day)
    assert query.call_count == 1
