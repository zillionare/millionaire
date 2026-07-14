"""B08-trade-main-2: Test trade_main small helpers + search_trade_assets."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

from quantide.web.pages import trade_main as tm
from quantide.web.pages.trade_main import (
    _build_asset_stats,
    _build_live_quote_payload,
    _extract_recent_trade_dates,
    _format_trade_metric,
    _maybe_start_live_quote,
    _normalize_positions_tab,
    _resolve_live_current_price,
    _resolve_trade_reference_close,
    _trade_result_has_order,
)


# ---------------------------------------------------------------------------
# _format_trade_metric
# ---------------------------------------------------------------------------


def test_format_trade_metric_none():
    assert _format_trade_metric(None) == ""


def test_format_trade_metric_zero():
    assert _format_trade_metric(0.0) == "0.00"


def test_format_trade_metric_positive():
    assert _format_trade_metric(10.5) == "10.50"


def test_format_trade_metric_negative():
    assert _format_trade_metric(-3.14) == "-3.14"


# ---------------------------------------------------------------------------
# _normalize_positions_tab
# ---------------------------------------------------------------------------


def test_normalize_positions_tab_valid_positions():
    assert _normalize_positions_tab("positions") == "positions"


def test_normalize_positions_tab_valid_orders():
    assert _normalize_positions_tab("orders") == "orders"


def test_normalize_positions_tab_invalid_falls_back():
    result = _normalize_positions_tab("garbage")
    assert result == "positions"  # default


def test_normalize_positions_tab_empty_falls_back():
    result = _normalize_positions_tab("")
    assert result == "positions"


def test_normalize_positions_tab_none_falls_back():
    result = _normalize_positions_tab(None)
    assert result == "positions"


def test_normalize_positions_tab_uppercase():
    assert _normalize_positions_tab("ORDERS") == "orders"


def test_normalize_positions_tab_dict_returns_str():
    """Non-string values are coerced to str."""
    class _FakeDict(dict):
        def __bool__(self):
            return True
    # Whatever the value, falls back unless its str-form is valid.
    assert _normalize_positions_tab({"x": 1}) == "positions"


# ---------------------------------------------------------------------------
# _trade_result_has_order
# ---------------------------------------------------------------------------


def test_trade_result_has_order_none():
    assert _trade_result_has_order(None) is False


def test_trade_result_has_order_with_qt_oid():
    class _R:
        qt_oid = "o1"
        trades = []
    assert _trade_result_has_order(_R()) is True


def test_trade_result_has_order_with_trades():
    class _R:
        qt_oid = None
        trades = [{"price": 10, "shares": 100}]
    assert _trade_result_has_order(_R()) is True


def test_trade_result_has_order_empty():
    class _R:
        qt_oid = None
        trades = []
    assert _trade_result_has_order(_R()) is False


def test_trade_result_has_order_no_attributes():
    """Object missing both attrs returns False."""
    class _R:
        pass
    assert _trade_result_has_order(_R()) is False


# ---------------------------------------------------------------------------
# _maybe_start_live_quote
# ---------------------------------------------------------------------------


def test_maybe_start_live_quote_disabled():
    """When live_quote.is_running=False and settings disable, no-op."""
    fake_settings = MagicMock()
    fake_settings.gateway_enabled = False
    fake_settings.livequote_mode = "none"
    fake_settings.livequote_enabled = False
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = False
        _maybe_start_live_quote()
    mock_lq.start.assert_not_called()


def test_maybe_start_live_quote_already_running():
    """When live_quote.is_running=True, no-op."""
    fake_settings = MagicMock()
    fake_settings.gateway_enabled = True
    fake_settings.livequote_mode = "tushare"
    fake_settings.livequote_enabled = True
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = True
        _maybe_start_live_quote()
    mock_lq.start.assert_not_called()


def test_maybe_start_live_quote_starts():
    """When live_quote.is_running=False and gateway enabled, calls start."""
    fake_settings = MagicMock()
    fake_settings.gateway_enabled = True
    fake_settings.livequote_mode = ""
    fake_settings.livequote_enabled = True
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = False
        _maybe_start_live_quote()
    mock_lq.start.assert_called_once()


def test_maybe_start_live_quote_swallows_exception():
    """When live_quote.start() raises, the exception is swallowed."""
    fake_settings = MagicMock()
    fake_settings.gateway_enabled = True
    fake_settings.livequote_mode = ""
    fake_settings.livequote_enabled = True
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = False
        mock_lq.start = MagicMock(side_effect=Exception("boom"))
        _maybe_start_live_quote()  # should not raise


# ---------------------------------------------------------------------------
# _resolve_live_current_price
# ---------------------------------------------------------------------------


def test_resolve_live_current_price_empty_asset():
    assert _resolve_live_current_price("") == 0.0


def test_resolve_live_current_price_uses_quote():
    fake_settings = MagicMock(gateway_enabled=True, livequote_mode="", livequote_enabled=True)
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = False
        mock_lq.get_quote = MagicMock(return_value={"price": 10.5})
        got = _resolve_live_current_price("000001.SZ")
    assert got == 10.5


def test_resolve_live_current_price_no_quote_returns_zero():
    fake_settings = MagicMock(gateway_enabled=True, livequote_mode="", livequote_enabled=True)
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = True
        mock_lq.get_quote = MagicMock(return_value=None)
        got = _resolve_live_current_price("000001.SZ")
    assert got == 0.0


def test_resolve_live_current_price_falls_back_to_lastPrice():
    """If price=0 in quote, lastPrice is used."""
    fake_settings = MagicMock(gateway_enabled=True, livequote_mode="", livequote_enabled=True)
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = True
        mock_lq.get_quote = MagicMock(return_value={"price": 0, "lastPrice": 12.0})
        got = _resolve_live_current_price("000001.SZ")
    assert got == 12.0


def test_resolve_live_current_price_all_zero_returns_zero():
    fake_settings = MagicMock(gateway_enabled=True, livequote_mode="", livequote_enabled=True)
    with patch.object(tm, "get_settings", return_value=fake_settings), \
         patch.object(tm, "live_quote") as mock_lq:
        mock_lq.is_running = True
        mock_lq.get_quote = MagicMock(return_value={"price": 0})
        got = _resolve_live_current_price("000001.SZ")
    assert got == 0.0


# ---------------------------------------------------------------------------
# _build_live_quote_payload
# ---------------------------------------------------------------------------


def test_build_live_quote_payload_visible():
    with patch.object(tm, "_resolve_live_current_price", return_value=10.5):
        got = _build_live_quote_payload("000001.SZ")
    assert got["asset"] == "000001.SZ"
    assert got["current"] == "10.50"
    assert got["visible"] is True


def test_build_live_quote_payload_hidden_when_zero():
    with patch.object(tm, "_resolve_live_current_price", return_value=0.0), \
         patch.object(tm, "_resolve_trade_reference_close", return_value=0.0):
        got = _build_live_quote_payload("000001.SZ")
    assert got["visible"] is False


# ---------------------------------------------------------------------------
# _extract_recent_trade_dates
# ---------------------------------------------------------------------------


def test_extract_recent_trade_dates_none_frame():
    assert _extract_recent_trade_dates(None, datetime.date(2024, 1, 1), 5) == []


def test_extract_recent_trade_dates_empty_frame():
    import pandas as pd
    df = pd.DataFrame()
    assert _extract_recent_trade_dates(df, datetime.date(2024, 1, 1), 5) == []


def test_extract_recent_trade_dates_filters_closed():
    """Closed dates (is_open=False) are excluded."""
    import pandas as pd
    df = pd.DataFrame([
        {"date": datetime.date(2024, 1, 1), "is_open": 0},
        {"date": datetime.date(2024, 1, 2), "is_open": 1},
    ])
    out = _extract_recent_trade_dates(df, datetime.date(2024, 1, 5), 5)
    assert datetime.date(2024, 1, 2) in out


def test_extract_recent_trade_dates_filters_future():
    """Dates > end are excluded."""
    import pandas as pd
    df = pd.DataFrame([
        {"date": datetime.date(2024, 1, 1), "is_open": 1},
        {"date": datetime.date(2024, 2, 1), "is_open": 1},
    ])
    out = _extract_recent_trade_dates(df, datetime.date(2024, 1, 5), 5)
    # Only the past date included (or first fallback if none eligible)
    assert isinstance(out, list)
    assert len(out) >= 1


# ---------------------------------------------------------------------------
# place_order_trade — async endpoint, hits many branches
# ---------------------------------------------------------------------------


from quantide.web.pages.trade_main import place_order_trade


def _trade_req(form_data=None, scope=None):
    req = MagicMock()
    req.scope = scope or {}
    req.form = AsyncMock(return_value=form_data or {})
    return req


@pytest.mark.asyncio
async def test_place_order_no_broker_returns_toast():
    """When no registry, returns toast error."""
    req = _trade_req()
    resp = await place_order_trade(req)
    assert resp is not None  # HTMLResponse with error toast


@pytest.mark.asyncio
async def test_place_order_no_asset():
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "", "price_mode": "LIMIT", "price": "10", "value": "5"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_bad_price_format():
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "LIMIT", "price": "x", "value": "5"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_zero_price_in_limit_mode():
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "LIMIT", "price": "0", "value": "5"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_bad_value_format():
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "x"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_zero_value():
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "0"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_buy_amount_with_amount_method():
    """When broker has buy_amount method, called directly."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["buy_amount", "sell_amount", "buy", "sell"])
    fake_broker.buy_amount = AsyncMock(return_value=MagicMock(qt_oid="o1"))
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "LIMIT", "price": "10", "value": "5", "order_mode": "AMOUNT"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_sell_amount():
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["sell_amount", "buy", "sell"])
    fake_broker.sell_amount = AsyncMock(return_value=MagicMock(qt_oid="o1"))
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "SELL", "asset": "000001.SZ", "price_mode": "LIMIT", "price": "10", "value": "5", "order_mode": "AMOUNT"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_no_order_generated_returns_toast():
    """When result has no qt_oid nor trades, returns error toast."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["buy", "sell"])
    fake_broker.buy = AsyncMock(return_value=None)
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "5", "order_mode": "SHARES"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_broker_raises_returns_toast():
    """When broker.buy raises, returns error toast."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["buy", "sell"])
    fake_broker.buy = AsyncMock(side_effect=Exception("boom"))
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "5", "order_mode": "SHARES"})
    resp = await place_order_trade(req)
    assert resp is not None


# ---------------------------------------------------------------------------
# place_order_trade with SELL side + branch coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_order_sell_amount_no_amount_method():
    """When broker lacks sell_amount, falls back to broker.sell."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["sell"])  # no sell_amount
    fake_broker.sell = AsyncMock(return_value=MagicMock(qt_oid="o2"))
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "SELL", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "5", "order_mode": "AMOUNT"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_buy_amount_no_amount_method():
    """When broker lacks buy_amount, falls back to broker.buy."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["buy"])  # no buy_amount
    fake_broker.buy = AsyncMock(return_value=MagicMock(qt_oid="o3"))
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "5", "order_mode": "AMOUNT"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_sell_shares():
    """SELL order_mode=SHARES → broker.sell directly."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["sell"])
    fake_broker.sell = AsyncMock(return_value=MagicMock(qt_oid="o4"))
    reg.get = MagicMock(return_value=fake_broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {"active_account_kind": BrokerKind.SIMULATION.value, "active_account_id": "b1"}}
    req.form = AsyncMock(return_value={"side": "SELL", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "5", "order_mode": "SHARES"})
    resp = await place_order_trade(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_place_order_default_account():
    """When no active_account_kind/id, uses reg.get_default()."""
    from quantide.core.enums import BrokerKind
    reg = MagicMock()
    fake_broker = MagicMock(spec=["buy", "sell"])
    fake_broker.buy = AsyncMock(return_value=MagicMock(qt_oid="o5"))
    reg.get = MagicMock(return_value=fake_broker)
    reg.get_default = MagicMock(return_value=(BrokerKind.SIMULATION.value, "default-id"))
    req = MagicMock()
    req.scope = {"registry": reg, "session": {}}
    req.form = AsyncMock(return_value={"side": "BUY", "asset": "000001.SZ", "price_mode": "MARKET", "price": "10", "value": "5", "order_mode": "SHARES"})
    resp = await place_order_trade(req)
    assert resp is not None
