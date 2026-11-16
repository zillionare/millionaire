"""Market session clocks must agree on UTC hosts and local desktop installations."""

import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from quantide.core.market_time import market_now, market_today
from quantide.core.runtime.clock_bridge import SystemClockAdapter
from quantide.providers.tencent_publisher import TencentPublisher


def test_utc_morning_runs_inside_the_shanghai_session(monkeypatch):
    monkeypatch.setattr("quantide.config.settings.get_timezone", lambda: ZoneInfo("Asia/Shanghai"))
    with freeze_time("2024-01-02 01:45:00+00:00"):
        assert market_now() == datetime.datetime(2024, 1, 2, 9, 45)
        assert SystemClockAdapter().now() == datetime.datetime(2024, 1, 2, 9, 45)
        publisher = TencentPublisher(
            calendar=SimpleNamespace(is_trade_day=lambda now: True), access_check=lambda: None
        )
        assert publisher._in_session()


def test_exchange_day_rolls_over_before_a_utc_host_day(monkeypatch):
    monkeypatch.setattr("quantide.config.settings.get_timezone", lambda: ZoneInfo("Asia/Shanghai"))
    with freeze_time("2024-01-01 18:30:00+00:00"):
        assert market_today() == datetime.date(2024, 1, 2)
        assert market_now() == datetime.datetime(2024, 1, 2, 2, 30)
