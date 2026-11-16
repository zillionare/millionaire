"""Realtime publisher ownership and source selection without external requests."""

import datetime
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from quantide.providers import tushare_publisher as module
from quantide.providers.tushare_publisher import TusharePublisher


def publisher(monkeypatch, *, symbols=("000001.SZ",), trade_day=True, hour=10):
    monkeypatch.setattr(module, "scheduler", Mock())
    monkeypatch.setattr(module, "publish_quotes", Mock())
    fetcher = Mock()
    fetcher.fetch_quote_snapshot.return_value = {
        "000001.SZ": {"price": 10, "up_limit": 11, "down_limit": 9}
    }
    return TusharePublisher(
        fetcher, SimpleNamespace(subscribed_symbols=lambda: list(symbols)),
        SimpleNamespace(is_trade_day=lambda now: trade_day),
        lambda: datetime.datetime(2024, 1, 3, hour, 0),
    )


def test_start_is_idempotent_and_stop_allows_restart(monkeypatch):
    source = publisher(monkeypatch)
    source.start()
    source.start()
    assert module.scheduler.add_job.call_count == 1
    assert source.publish_once() == 1
    module.publish_quotes.assert_called_once()
    source.stop()
    assert source.publish_once() == 0
    assert source._cancel.is_set()
    source.stop()
    source.start()
    assert not source._cancel.is_set()
    assert module.scheduler.add_job.call_count == 2


@pytest.mark.parametrize("options", [{"symbols": ()}, {"trade_day": False}, {"hour": 12}])
def test_no_subscription_or_closed_market_makes_no_request(monkeypatch, options):
    source = publisher(monkeypatch, **options)
    source.start()
    assert source.publish_once() == 0
    source._fetcher.fetch_quote_snapshot.assert_not_called()


def test_stopping_during_request_prevents_late_publication(monkeypatch):
    source = publisher(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    rows = source._fetcher.fetch_quote_snapshot.return_value

    def fetch(*args):
        entered.set()
        assert release.wait(5)
        return rows

    source._fetcher.fetch_quote_snapshot.side_effect = fetch
    source.start()
    worker = threading.Thread(target=source.publish_once)
    worker.start()
    try:
        assert entered.wait(5)
        source.stop()
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    module.publish_quotes.assert_not_called()


def test_source_failure_does_not_publish_or_expose_exception(monkeypatch, capsys):
    source = publisher(monkeypatch)
    source._fetcher.fetch_quote_snapshot.side_effect = RuntimeError("secret-token")
    source.start()
    assert source.publish_once() == 0
    module.publish_quotes.assert_not_called()
    assert "secret-token" not in capsys.readouterr().err


def test_boundary_minute_can_receive_the_final_snapshot(monkeypatch):
    source = publisher(monkeypatch)
    source._clock = lambda: datetime.datetime(2024, 1, 3, 15, 0, 45)
    source.start()
    assert source.publish_once() == 1
    source._clock = lambda: datetime.datetime(2024, 1, 3, 15, 1)
    assert source.publish_once() == 0
