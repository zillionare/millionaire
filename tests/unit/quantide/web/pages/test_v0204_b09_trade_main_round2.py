"""B09-trade-main-round2: Targeted coverage for ``quantide/web/pages/trade_main.py``.

Covers missing branches:
- ``_extract_recent_trade_dates``: skips closed days / unsorted input
- ``_resolve_trade_reference_close``: empty asset string returns 0
- ``_safe_orders`` / ``_safe_positions``: dict / list / exception paths
- ``_resolve_broker_for_refresh``: registry None / active present / no-active-default
- ``_fetch_positions_orders_via_gateway``: empty config, html response, JSONDecode, etc.
- ``_coerce_gateway_position`` / ``_coerce_gateway_order``: payload mapping
- ``_parse_order_time_text``: various formats
- ``TodayOrdersTable``: SELL / UNKNOWN side branches
- ``place_order_trade``: validation branches
- ``search_trade_assets``: empty query / no-match / fuzzy_search exception
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import polars as pl
import pytest
from starlette.responses import HTMLResponse, JSONResponse

from quantide.core.enums import BidType, BrokerKind, OrderSide, OrderStatus
from quantide.data.models import Order, Position
from quantide.web.pages import trade_main as tm
from quantide.web.pages.trade_main import (
    TodayOrdersTable,
    _coerce_gateway_order,
    _coerce_gateway_position,
    _extract_recent_trade_dates,
    _fetch_positions_orders_via_gateway,
    _parse_order_time_text,
    _resolve_broker_for_refresh,
    _resolve_positions_orders_from_settings,
    _resolve_trade_reference_close,
    _safe_orders,
    _safe_positions,
    place_order_trade,
    search_trade_assets,
)


def _make_req(
    *,
    scope: dict | None = None,
    form_data: dict | None = None,
    query_params: dict | None = None,
) -> MagicMock:
    req = MagicMock()
    req.scope = scope or {}
    req.query_params = query_params or {}
    req.form = AsyncMock(return_value=form_data or {})
    return req


# ---------------------------------------------------------------------------
# _extract_recent_trade_dates - closed-day skip + is_open falsy branch
# ---------------------------------------------------------------------------


def test_extract_recent_trade_dates_skips_closed_days():
    """[AC-NFR1101-01] Rows with is_open=False are skipped."""
    df = pd.DataFrame({
        "date": [datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)],
        "is_open": [1, 0],
    })
    out = _extract_recent_trade_dates(df, datetime.date(2024, 1, 5), 3)
    assert len(out) == 1
    assert out[0] == datetime.date(2024, 1, 2)


# ---------------------------------------------------------------------------
# _resolve_trade_reference_close - empty asset returns 0
# ---------------------------------------------------------------------------


def test_resolve_trade_reference_close_returns_zero_for_empty_asset():
    """[AC-NFR1101-01] Empty asset string returns 0.0 without loading bars."""
    out = _resolve_trade_reference_close("")
    assert out == 0.0


# ---------------------------------------------------------------------------
# _safe_orders / _safe_positions - dict / list / exception paths
# ---------------------------------------------------------------------------


def test_safe_orders_returns_empty_when_broker_is_none():
    """[AC-NFR1101-01] None broker yields [] early."""
    assert _safe_orders(None) == []


def test_safe_orders_returns_empty_when_broker_lacks_orders_attr():
    """[AC-NFR1101-01] Broker without orders attr yields [] early."""
    broker = SimpleNamespace()
    assert _safe_orders(broker) == []


def test_safe_orders_returns_list_values_from_dict():
    """[AC-NFR1101-01] When orders is a dict, returns list of its values."""
    broker = SimpleNamespace(orders={"o1": "order1", "o2": "order2"})
    out = _safe_orders(broker)
    assert sorted(out) == ["order1", "order2"]


def test_safe_orders_returns_list_when_orders_is_list():
    """[AC-NFR1101-01] When orders is a non-empty list, returns it as-is."""
    broker = SimpleNamespace(orders=[1, 2, 3])
    assert _safe_orders(broker) == [1, 2, 3]


def test_safe_orders_returns_empty_on_exception():
    """[AC-NFR1101-01] When accessing .orders raises (after hasattr), returns []."""

    class _BrokenOrders:
        _orders_accessed = False

        @property
        def orders(self):
            # First call (from hasattr) returns something; second call raises.
            if _BrokenOrders._orders_accessed:
                raise RuntimeError("boom")
            _BrokenOrders._orders_accessed = True
            return {"a": 1}

    out = _safe_orders(_BrokenOrders())
    assert out == []


def test_safe_positions_returns_empty_when_broker_is_none():
    """[AC-NFR1101-01] None broker yields [] early."""
    assert _safe_positions(None) == []


def test_safe_positions_returns_empty_when_broker_lacks_positions_attr():
    """[AC-NFR1101-01] Broker without positions attr yields [] early."""
    broker = SimpleNamespace()
    assert _safe_positions(broker) == []


def test_safe_positions_returns_list_values_from_dict():
    """[AC-NFR1101-01] When positions is a dict, returns list of its values."""
    broker = SimpleNamespace(positions={"a": "p1"})
    assert _safe_positions(broker) == ["p1"]


def test_safe_positions_returns_empty_on_exception():
    """[AC-NFR1101-01] When accessing .positions raises (after hasattr), returns []."""

    class _BrokenPositions:
        _accessed = False

        @property
        def positions(self):
            if _BrokenPositions._accessed:
                raise RuntimeError("boom")
            _BrokenPositions._accessed = True
            return {"a": 1}

    out = _safe_positions(_BrokenPositions())
    assert out == []


# ---------------------------------------------------------------------------
# _resolve_broker_for_refresh - registry None / active present / no-active-default
# ---------------------------------------------------------------------------


def test_resolve_broker_for_refresh_returns_none_when_registry_is_none():
    """[AC-NFR1101-01] No registry returns None."""
    req = _make_req(scope={})
    with patch.object(tm, "_get_registry", return_value=None):
        assert _resolve_broker_for_refresh(req) is None


def test_resolve_broker_for_refresh_returns_broker_when_active_present():
    """[AC-NFR1101-01] Session has active kind/id, broker resolved from registry."""
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        }
    )
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get.return_value = fake_broker
    with patch.object(tm, "_get_registry", return_value=reg):
        out = _resolve_broker_for_refresh(req)
    assert out is fake_broker


def test_resolve_broker_for_refresh_returns_none_when_active_get_raises():
    """[AC-NFR1101-01] When reg.get raises, returns None (swallowed)."""
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        }
    )
    reg = MagicMock()
    reg.get.side_effect = RuntimeError("boom")
    with patch.object(tm, "_get_registry", return_value=reg):
        assert _resolve_broker_for_refresh(req) is None


def test_resolve_broker_for_refresh_returns_default_broker():
    """[AC-NFR1101-01] No active session; default used from registry."""
    req = _make_req(scope={"session": {}})
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get_default.return_value = (BrokerKind.QMT.value, "default-id")
    reg.get.return_value = fake_broker
    with patch.object(tm, "_get_registry", return_value=reg):
        assert _resolve_broker_for_refresh(req) is fake_broker


def test_resolve_broker_for_refresh_returns_none_when_default_get_raises():
    """[AC-NFR1101-01] Default reg.get raising returns None."""
    req = _make_req(scope={"session": {}})
    reg = MagicMock()
    reg.get_default.return_value = (BrokerKind.QMT.value, "default-id")
    reg.get.side_effect = RuntimeError("boom")
    with patch.object(tm, "_get_registry", return_value=reg):
        assert _resolve_broker_for_refresh(req) is None


# ---------------------------------------------------------------------------
# _fetch_positions_orders_via_gateway - empty config / html response
# ---------------------------------------------------------------------------


def test_fetch_positions_orders_via_gateway_returns_empty_when_no_base_url():
    """[AC-NFR1101-01] Missing base_url returns ([], []) early."""
    out = _fetch_positions_orders_via_gateway(base_url="", api_key="key")
    assert out == ([], [])


def test_fetch_positions_orders_via_gateway_returns_empty_when_no_api_key():
    """[AC-NFR1101-01] Missing api_key returns ([], []) early."""
    out = _fetch_positions_orders_via_gateway(base_url="http://gw", api_key="")
    assert out == ([], [])


def test_fetch_positions_orders_via_gateway_returns_empty_on_url_error(monkeypatch):
    """[AC-NFR1101-01] URLError caught, returns ([], [])."""
    import urllib.error as urlerr

    def _fake_urlopen(*_args, **_kwargs):
        raise urlerr.URLError("conn refused")

    monkeypatch.setattr(tm.urllib.request, "urlopen", _fake_urlopen)
    out = _fetch_positions_orders_via_gateway(base_url="http://gw", api_key="key")
    assert out == ([], [])


def test_fetch_positions_orders_via_gateway_returns_empty_on_json_decode_error(monkeypatch):
    """[AC-NFR1101-01] JSONDecodeError caught, returns ([], [])."""
    fake_resp = MagicMock()
    fake_resp.headers = {"Content-Type": "application/json"}
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    fake_resp.read = MagicMock(return_value=b"not-json")
    monkeypatch.setattr(tm.urllib.request, "urlopen", lambda *a, **k: fake_resp)
    out = _fetch_positions_orders_via_gateway(base_url="http://gw", api_key="key")
    assert out == ([], [])


def test_fetch_positions_orders_via_gateway_skips_html_response(monkeypatch):
    """[AC-NFR1101-01] HTML Content-Type response is skipped, returns ([], [])."""
    fake_resp = MagicMock()
    fake_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    fake_resp.read = MagicMock(return_value=b"<html>")
    monkeypatch.setattr(tm.urllib.request, "urlopen", lambda *a, **k: fake_resp)
    out = _fetch_positions_orders_via_gateway(base_url="http://gw", api_key="key")
    assert out == ([], [])


def test_fetch_positions_orders_via_gateway_returns_positions_and_orders(monkeypatch):
    """[AC-NFR1101-01] JSON list responses populate positions and orders lists."""
    payloads = [
        b'[{"symbol": "000001.SZ"}]',  # positions
        b'[{"symbol": "000002.SZ"}]',  # orders
    ]

    class _FakeResp:
        def __init__(self):
            self.headers = {"Content-Type": "application/json"}
            self._idx = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            payload = payloads[self._idx]
            self._idx += 1
            return payload

    fake_resp = _FakeResp()
    monkeypatch.setattr(tm.urllib.request, "urlopen", lambda *a, **k: fake_resp)
    out = _fetch_positions_orders_via_gateway(base_url="http://gw", api_key="key")
    assert out[0] == [{"symbol": "000001.SZ"}]
    assert out[1] == [{"symbol": "000002.SZ"}]


# ---------------------------------------------------------------------------
# _coerce_gateway_position / _coerce_gateway_order
# ---------------------------------------------------------------------------


def test_coerce_gateway_position_maps_payload_to_position():
    """[AC-NFR1101-01] Payload dict maps to Position dataclass."""
    payload = {
        "symbol": "000001.SZ",
        "shares": "100",
        "avail": "100",
        "price": "10.5",
        "market_value": "1050",
        "float_profit": "50",
    }
    pos = _coerce_gateway_position(payload, "gw-1")
    assert isinstance(pos, Position)
    assert pos.asset == "000001.SZ"
    assert pos.shares == 100.0
    assert pos.mv == 1050.0


def test_coerce_gateway_order_maps_payload_to_order():
    """[AC-NFR1101-01] Payload dict maps to Order dataclass with coerced enums."""
    payload = {
        "symbol": "000001.SZ",
        "side": "buy",
        "status": "filled",
        "shares": "100",
        "price": "10.5",
        "filled": "100",
        "time": "10:30:00",
        "qtoid": "qt-1",
    }
    order = _coerce_gateway_order(payload, "gw-1")
    assert isinstance(order, Order)
    assert order.side == OrderSide.BUY
    assert order.status == OrderStatus.SUCCEEDED


def test_coerce_gateway_order_generates_qtoid_when_missing():
    """[AC-NFR1101-01] Missing qtoid/order_id/foid generates a gw-* uuid."""
    payload = {"symbol": "000001.SZ", "side": "sell", "status": "reported"}
    order = _coerce_gateway_order(payload, "gw-1")
    assert order.foid.startswith("gw-")


# ---------------------------------------------------------------------------
# _parse_order_time_text
# ---------------------------------------------------------------------------


def test_parse_order_time_text_returns_now_for_empty():
    """[AC-NFR1101-01] Empty text returns datetime.now()."""
    out = _parse_order_time_text("")
    assert isinstance(out, datetime.datetime)


def test_parse_order_time_text_parses_iso_with_t():
    """[AC-NFR1101-01] 'YYYY-MM-DDTHH:MM:SS' format parses correctly."""
    out = _parse_order_time_text("2024-06-17T10:30:00")
    assert out.year == 2024
    assert out.hour == 10


def test_parse_order_time_text_parses_iso_with_microseconds():
    """[AC-NFR1101-01] 'YYYY-MM-DDTHH:MM:SS.ffffff' format parses correctly."""
    out = _parse_order_time_text("2024-06-17T10:30:00.123456")
    assert out.microsecond == 123456


def test_parse_order_time_text_parses_time_only():
    """[AC-NFR1101-01] 'HH:MM:SS' format parses correctly."""
    out = _parse_order_time_text("10:30:00")
    assert out.hour == 10


def test_parse_order_time_text_returns_now_for_unparseable():
    """[AC-NFR1101-01] Unparseable text returns datetime.now()."""
    out = _parse_order_time_text("garbage")
    assert isinstance(out, datetime.datetime)


# ---------------------------------------------------------------------------
# TodayOrdersTable - SELL / UNKNOWN side branches
# ---------------------------------------------------------------------------


def test_today_orders_table_renders_sell_side_text():
    """[AC-NFR1101-01] Order with SELL side renders '卖出' text."""
    order = Order(
        portfolio_id="p1",
        asset="000001.SZ",
        side=OrderSide.SELL,
        shares=100,
        bid_type=BidType.FIXED,
        price=10.0,
        filled=0,
        tm=datetime.datetime(2024, 6, 17, 10, 30),
        status=OrderStatus.WAIT_REPORTING,
    )
    out = TodayOrdersTable([order])
    rendered = tm.to_xml(out)
    assert "卖出" in rendered


def test_today_orders_table_renders_unknown_side_text():
    """[AC-NFR1101-01] Order with UNKNOWN side renders '未知' text."""
    order = Order(
        portfolio_id="p1",
        asset="000001.SZ",
        side=OrderSide.UNKNOWN,
        shares=100,
        bid_type=BidType.FIXED,
        price=10.0,
        filled=0,
        tm=datetime.datetime(2024, 6, 17, 10, 30),
        status=OrderStatus.WAIT_REPORTING,
    )
    out = TodayOrdersTable([order])
    rendered = tm.to_xml(out)
    assert "未知" in rendered


def test_today_orders_table_renders_cancel_button_for_cancellable_status():
    """[AC-NFR1101-01] UNREPORTED status shows the cancel button."""
    order = Order(
        portfolio_id="p1",
        asset="000001.SZ",
        side=OrderSide.BUY,
        shares=100,
        bid_type=BidType.FIXED,
        price=10.0,
        filled=0,
        tm=datetime.datetime(2024, 6, 17, 10, 30),
        status=OrderStatus.UNREPORTED,
    )
    out = TodayOrdersTable([order])
    rendered = tm.to_xml(out)
    assert "撤单" in rendered


def test_today_orders_table_renders_empty_message_when_no_orders():
    """[AC-NFR1101-01] Empty orders list renders '暂无当日委托' message."""
    out = TodayOrdersTable([])
    rendered = tm.to_xml(out)
    assert "暂无当日委托" in rendered


# ---------------------------------------------------------------------------
# place_order_trade - validation branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_order_trade_no_asset_returns_toast():
    """[AC-NFR1101-01] Missing asset returns '请输入股票代码' toast."""
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get.return_value = fake_broker
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        },
        form_data={"side": "BUY", "asset": "", "price_mode": "MARKET", "order_mode": "AMOUNT", "value": "1"},
    )
    with patch.object(tm, "_get_registry", return_value=reg):
        resp = await place_order_trade(req)
    assert isinstance(resp, HTMLResponse)
    assert "请输入股票代码" in resp.body.decode()


@pytest.mark.asyncio
async def test_place_order_trade_invalid_price_returns_toast():
    """[AC-NFR1101-01] Non-numeric price returns '价格格式错误' toast."""
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get.return_value = fake_broker
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        },
        form_data={
            "side": "BUY",
            "asset": "000001.SZ",
            "price_mode": "LIMIT",
            "order_mode": "AMOUNT",
            "price": "abc",
            "value": "1",
        },
    )
    with patch.object(tm, "_get_registry", return_value=reg):
        resp = await place_order_trade(req)
    assert "价格格式错误" in resp.body.decode()


@pytest.mark.asyncio
async def test_place_order_trade_non_positive_price_returns_toast():
    """[AC-NFR1101-01] Zero price in LIMIT mode returns '价格必须大于0' toast."""
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get.return_value = fake_broker
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        },
        form_data={
            "side": "BUY",
            "asset": "000001.SZ",
            "price_mode": "LIMIT",
            "order_mode": "AMOUNT",
            "price": "0",
            "value": "1",
        },
    )
    with patch.object(tm, "_get_registry", return_value=reg):
        resp = await place_order_trade(req)
    assert "价格必须大于0" in resp.body.decode()


@pytest.mark.asyncio
async def test_place_order_trade_invalid_value_returns_toast():
    """[AC-NFR1101-01] Non-numeric value returns '金额/数量格式错误' toast."""
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get.return_value = fake_broker
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        },
        form_data={
            "side": "BUY",
            "asset": "000001.SZ",
            "price_mode": "MARKET",
            "order_mode": "AMOUNT",
            "value": "abc",
        },
    )
    with patch.object(tm, "_get_registry", return_value=reg):
        resp = await place_order_trade(req)
    assert "金额/数量格式错误" in resp.body.decode()


@pytest.mark.asyncio
async def test_place_order_trade_non_positive_value_returns_toast():
    """[AC-NFR1101-01] Non-positive value returns '金额/数量必须大于0' toast."""
    fake_broker = MagicMock()
    reg = MagicMock()
    reg.get.return_value = fake_broker
    req = _make_req(
        scope={
            "session": {
                "active_account_kind": BrokerKind.QMT.value,
                "active_account_id": "p1",
            }
        },
        form_data={
            "side": "BUY",
            "asset": "000001.SZ",
            "price_mode": "MARKET",
            "order_mode": "AMOUNT",
            "value": "0",
        },
    )
    with patch.object(tm, "_get_registry", return_value=reg):
        resp = await place_order_trade(req)
    assert "金额/数量必须大于0" in resp.body.decode()


# ---------------------------------------------------------------------------
# search_trade_assets - empty query / no-match / fuzzy_search exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_trade_assets_empty_query_returns_hidden_dropdown():
    """[AC-NFR1101-01] Empty query returns hidden dropdown HTMLResponse."""
    req = _make_req(query_params={"q": ""})
    resp = await search_trade_assets(req)
    assert isinstance(resp, HTMLResponse)
    assert "hidden" in resp.body.decode()


@pytest.mark.asyncio
async def test_search_trade_assets_no_match_renders_no_match_dropdown():
    """[AC-NFR1101-01] No fuzzy matches renders '无匹配结果' dropdown."""
    req = _make_req(query_params={"q": "nonexistent"})
    with patch.object(tm, "stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(return_value=pd.DataFrame())
        resp = await search_trade_assets(req)
    assert isinstance(resp, HTMLResponse)
    assert "无匹配结果" in resp.body.decode()


@pytest.mark.asyncio
async def test_search_trade_assets_fuzzy_exception_returns_hidden_dropdown():
    """[AC-NFR1101-01] fuzzy_search raising returns hidden dropdown."""
    req = _make_req(query_params={"q": "000001"})
    with patch.object(tm, "stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(side_effect=RuntimeError("boom"))
        resp = await search_trade_assets(req)
    assert isinstance(resp, HTMLResponse)
    assert "hidden" in resp.body.decode()
