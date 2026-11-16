from quantide.web.services import trade_quote_view as trade_quotes
"""[AC-NFR1101-01] trade_main page helpers."""

import datetime
from unittest.mock import patch

import polars as pl
from fasthtml.common import to_xml

from quantide.web.pages import trade_main as tm


def test_maybe_start_live_quote_returns_none():
    """Helper is idempotent and returns None."""
    out = tm._maybe_start_live_quote()
    assert out is None


def test_resolve_live_current_price_with_quote():
    """When live_quote has current price, returns it."""
    with patch.object(trade_quotes, "_maybe_start_live_quote"), \
        patch.object(trade_quotes.market_data_hub, "get_quote", return_value={"price": 10.5}):
        out = tm._resolve_live_current_price("000001.SZ")
    assert out == 10.5


def test_build_live_quote_payload():
    """Build a dict payload."""
    with patch.object(trade_quotes, "_resolve_live_current_price", return_value=10.0):
        out = tm._build_live_quote_payload("000001.SZ")
    assert isinstance(out, dict)
    assert out["current"] == "10.00"
    assert out["visible"] is True


def test_load_trade_reference_bars_exception():
    """When daily_bars and fetcher fail, returns empty DataFrame."""
    from quantide.web.pages.trade_main import _load_trade_reference_bars
    with patch.object(trade_quotes.daily_bars, "get_bars", side_effect=Exception("boom")), \
         patch.object(trade_quotes, "get_data_fetcher", side_effect=Exception("boom")):
        out = _load_trade_reference_bars("000001.SZ", datetime.date.today(), 30)
    assert isinstance(out, pl.DataFrame)
    assert out.is_empty()


def test_resolve_trade_reference_close_fallback():
    """When no close available, returns 0.0."""
    from quantide.web.pages.trade_main import _resolve_trade_reference_close
    with patch.object(trade_quotes, "_load_trade_reference_bars", return_value=pl.DataFrame()):
        out = _resolve_trade_reference_close("000001.SZ")
    assert out == 0.0


def test_asset_info_bar_shows_pnl_percentage_without_absolute_pnl():
    """资产信息栏显示基于本金的盈亏比例，不显示盈亏绝对值。"""
    html = to_xml(tm.AssetInfoBar(110_000, 20_000, 90_000, 100_000))

    assert "盈亏比例" in html
    assert "+10.00%" in html
    assert "10000.00" not in html
