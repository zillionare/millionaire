"""Historical trade limits are retrieved for the requested trading date."""

import datetime
from unittest.mock import MagicMock

from quantide.service.datafeed import BarsFeedImpl


def test_trade_price_limits_use_requested_date() -> None:
    daily_bars = MagicMock()
    daily_bars.get_trade_price_limits.return_value = (8.0, 12.0)
    feed = BarsFeedImpl(daily_bars=daily_bars)
    trade_date = datetime.date(2024, 1, 2)

    assert feed.get_trade_price_limits("000001.SZ", trade_date) == (8.0, 12.0)
    daily_bars.get_trade_price_limits.assert_called_once_with("000001.SZ", trade_date)


def test_trade_price_limits_fail_closed_without_daily_data() -> None:
    feed = BarsFeedImpl()
    assert feed.get_trade_price_limits("000001.SZ", datetime.date(2024, 1, 2)) == (0.0, 0.0)
