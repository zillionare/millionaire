"""[AC-NFR1101-01] trade_main page helpers."""

import datetime
from unittest.mock import MagicMock, patch
import polars as pl
from quantide.web.pages import trade_main as tm


def test_maybe_start_live_quote_returns_none():
    """Helper is idempotent and returns None."""
    out = tm._maybe_start_live_quote()
    assert out is None


def test_resolve_live_current_price_with_quote():
    """When live_quote has current price, returns it."""
    with patch.object(tm, "_maybe_start_live_quote"), \
         patch.object(tm.live_quote, "get_quote", return_value={"price": 10.5}):
        out = tm._resolve_live_current_price("000001.SZ")
    assert out == 10.5


def test_build_live_quote_payload():
    """Build a dict payload."""
    with patch.object(tm, "_resolve_live_current_price", return_value=10.0):
        out = tm._build_live_quote_payload("000001.SZ")
    assert isinstance(out, dict)
    assert out["current"] == "10.00"
    assert out["visible"] is True


def test_load_trade_reference_bars_exception():
    """When daily_bars and fetcher fail, returns empty DataFrame."""
    from quantide.web.pages.trade_main import _load_trade_reference_bars
    with patch.object(tm.daily_bars, "get_bars", side_effect=Exception("boom")), \
         patch.object(tm, "get_data_fetcher", side_effect=Exception("boom")):
        out = _load_trade_reference_bars("000001.SZ", datetime.date.today(), 30)
    assert isinstance(out, pl.DataFrame)
    assert out.is_empty()


def test_resolve_trade_reference_close_fallback():
    """When no close available, returns 0.0."""
    from quantide.web.pages.trade_main import _resolve_trade_reference_close
    with patch.object(tm, "_load_trade_reference_bars", return_value=pl.DataFrame()):
        out = _resolve_trade_reference_close("000001.SZ")
    assert out == 0.0
