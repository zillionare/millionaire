"""B09-trade-lightning-routes: route handler branches in trade_lightning.py.

Targets uncovered branches of the lightning routes: ``trade_lightning_search``'s
empty/exception/empty-result paths, ``trade_lightning_execute`` error branches
(no broker, unresolvable price, zero shares, broker exception, missing qt_oid),
``_resolve_lightning_broker`` registry/session branches, and the create/update
validation failure branches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from starlette.responses import HTMLResponse

from quantide.core.enums import BrokerKind
from quantide.web.pages import trade_lightning as tl_mod
from quantide.web.pages.trade_lightning import (
    _resolve_lightning_broker,
    trade_lightning_clear,
    trade_lightning_create,
    trade_lightning_execute,
    trade_lightning_search,
    trade_lightning_update,
)


def _make_req(
    *,
    path_params: dict | None = None,
    form_data: dict | None = None,
    scope: dict | None = None,
    query_params: dict | None = None,
) -> MagicMock:
    """Build a fake Starlette request for lightning route handlers."""
    req = MagicMock()
    req.path_params = path_params or {}
    req.scope = scope or {}
    req.query_params = query_params or {}
    req.form = AsyncMock(return_value=form_data or {})
    return req


# ---------------------------------------------------------------------------
# trade_lightning_search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_empty_query_returns_hidden_dropdown():
    """[AC-NFR1101-01] Empty asset_query returns a hidden dropdown."""
    req = _make_req(query_params={"asset_query": ""})
    resp = await trade_lightning_search(req)
    assert isinstance(resp, HTMLResponse)
    assert "hidden" in resp.body.decode()


@pytest.mark.asyncio
async def test_search_fuzzy_raises_returns_hidden_dropdown():
    """[AC-NFR1101-01] When stock_list.fuzzy_search raises, returns hidden dropdown."""
    req = _make_req(query_params={"asset_query": "abc"})
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(side_effect=Exception("boom"))
        resp = await trade_lightning_search(req)
    assert isinstance(resp, HTMLResponse)
    assert "hidden" in resp.body.decode()


@pytest.mark.asyncio
async def test_search_no_matches_returns_empty_dropdown():
    """[AC-NFR1101-01] When fuzzy_search returns empty df, returns the 'no match' dropdown."""
    req = _make_req(query_params={"asset_query": "xyz"})
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(return_value=pd.DataFrame())
        resp = await trade_lightning_search(req)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode()
    assert "无匹配结果" in body


@pytest.mark.asyncio
async def test_search_with_matches_renders_items():
    """[AC-NFR1101-01] Fuzzy search matches render as dropdown items."""
    req = _make_req(query_params={"asset_query": "000001"})
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(
            return_value=pd.DataFrame(
                [
                    {"asset": "000001.SZ", "name": "平安银行", "pinyin": "pingan"},
                ]
            )
        )
        resp = await trade_lightning_search(req)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode()
    assert "平安银行" in body
    assert "000001.SZ" in body


# ---------------------------------------------------------------------------
# _resolve_lightning_broker
# ---------------------------------------------------------------------------


def test_resolve_lightning_broker_no_registry():
    """[AC-NFR1101-01] When scope has no 'registry', returns None."""
    req = _make_req(scope={})
    assert _resolve_lightning_broker(req, "p1") is None


def test_resolve_lightning_broker_active_session_match():
    """[AC-NFR1101-01] Active account matches portfolio_id -> registry.get is called."""
    reg = MagicMock()
    fake_broker = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = _make_req(
        scope={
            "registry": reg,
            "session": {
                "active_account_kind": BrokerKind.SIMULATION.value,
                "active_account_id": "p1",
            },
        }
    )
    broker = _resolve_lightning_broker(req, "p1")
    assert broker is fake_broker
    reg.get.assert_called_once_with(BrokerKind.SIMULATION, "p1")


def test_resolve_lightning_broker_active_session_get_raises_returns_none():
    """[AC-NFR1101-01] When reg.get raises during active-account lookup, returns None."""
    reg = MagicMock()
    reg.get = MagicMock(side_effect=Exception("nope"))
    req = _make_req(
        scope={
            "registry": reg,
            "session": {
                "active_account_kind": BrokerKind.SIMULATION.value,
                "active_account_id": "p1",
            },
        }
    )
    assert _resolve_lightning_broker(req, "p1") is None


def test_resolve_lightning_broker_falls_back_to_kind_scan():
    """[AC-NFR1101-01] No active session match -> scans QMT/SIMULATION brokers."""
    reg = MagicMock()
    fake_broker = MagicMock()
    # First kind has no matching id; second returns the broker.
    reg.list_by_kind = MagicMock(
        side_effect=[
            [{"id": "other"}],
            [{"id": "p1"}],
        ]
    )
    reg.get = MagicMock(return_value=fake_broker)
    req = _make_req(scope={"registry": reg, "session": {}})
    broker = _resolve_lightning_broker(req, "p1")
    assert broker is fake_broker
    reg.get.assert_called_once_with(BrokerKind.SIMULATION, "p1")


def test_resolve_lightning_broker_kind_scan_raises_returns_none():
    """[AC-NFR1101-01] When list_by_kind raises during the kind scan, returns None."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(side_effect=Exception("boom"))
    req = _make_req(scope={"registry": reg, "session": {}})
    assert _resolve_lightning_broker(req, "p1") is None


def test_resolve_lightning_broker_kind_scan_no_match_returns_none():
    """[AC-NFR1101-01] When no broker info matches portfolio_id, returns None."""
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[{"id": "other"}])
    req = _make_req(scope={"registry": reg, "session": {}})
    assert _resolve_lightning_broker(req, "p1") is None


# ---------------------------------------------------------------------------
# trade_lightning_execute
# ---------------------------------------------------------------------------


def _entry(asset: str = "000001.SZ", price_ref: str = "current", cached_price: float = 0.0,
           amount_wan: float = 5.0) -> MagicMock:
    entry = MagicMock()
    entry.asset = asset
    entry.price_ref = price_ref
    entry.cached_price = cached_price
    entry.amount_wan = amount_wan
    return entry


@pytest.mark.asyncio
async def test_execute_entry_missing_returns_toast():
    """[AC-NFR1101-01] When entry is None, returns toast."""
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=None):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "闪电买入单不存在" in resp.body.decode()


@pytest.mark.asyncio
async def test_execute_no_broker_returns_toast():
    """[AC-NFR1101-01] When _resolve_lightning_broker returns None, returns toast."""
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=_entry()), \
         patch.object(tl_mod, "_resolve_lightning_broker", return_value=None):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "未找到可用的交易账号" in resp.body.decode()


@pytest.mark.asyncio
async def test_execute_current_price_zero_returns_toast():
    """[AC-NFR1101-01] When current price resolves to 0, returns toast."""
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    broker = MagicMock()
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=_entry()), \
         patch.object(tl_mod, "_resolve_lightning_broker", return_value=broker), \
         patch.object(tl_mod, "_resolve_lightning_price", return_value=0.0):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "无法解析" in resp.body.decode()


@pytest.mark.asyncio
async def test_execute_zero_shares_returns_toast():
    """[AC-NFR1101-01] Broker without buy_amount; computed shares <= 0 -> toast."""
    entry = _entry(price_ref="close", cached_price=1e9, amount_wan=0.01)
    broker = MagicMock(spec=["buy"])
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=entry), \
         patch.object(tl_mod, "_resolve_lightning_broker", return_value=broker):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "可买股数为 0" in resp.body.decode()


@pytest.mark.asyncio
async def test_execute_broker_raises_returns_toast():
    """[AC-NFR1101-01] Broker.buy raises -> returns toast with the exception text."""
    entry = _entry(price_ref="close", cached_price=10.0, amount_wan=1.0)
    broker = MagicMock(spec=["buy"])
    broker.buy = AsyncMock(side_effect=Exception("boom"))
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=entry), \
         patch.object(tl_mod, "_resolve_lightning_broker", return_value=broker):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "闪电买入失败" in resp.body.decode()


@pytest.mark.asyncio
async def test_execute_no_qt_oid_returns_toast():
    """[AC-NFR1101-01] Buy returns result without qt_oid -> returns toast."""
    entry = _entry(price_ref="close", cached_price=10.0, amount_wan=1.0)
    broker = MagicMock(spec=["buy"])
    broker.buy = AsyncMock(return_value=MagicMock(spec=[]))  # no qt_oid attr
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=entry), \
         patch.object(tl_mod, "_resolve_lightning_broker", return_value=broker):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "未生成有效委托" in resp.body.decode()


@pytest.mark.asyncio
async def test_execute_buy_amount_success_returns_success_toast():
    """[AC-NFR1101-01] buy_amount path with qt_oid -> success toast."""
    entry = _entry(price_ref="current", amount_wan=1.0)
    broker = MagicMock(spec=["buy_amount"])
    broker.buy_amount = AsyncMock(return_value=MagicMock(qt_oid="o1"))
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=entry), \
         patch.object(tl_mod, "_resolve_lightning_broker", return_value=broker), \
         patch.object(tl_mod, "_resolve_lightning_price", return_value=10.0):
        resp = await trade_lightning_execute(req)
    assert isinstance(resp, HTMLResponse)
    assert "闪电买入已提交" in resp.body.decode()


# ---------------------------------------------------------------------------
# trade_lightning_create - validation branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_empty_asset_query_returns_toast():
    """[AC-NFR1101-01] Empty asset_query -> toast asking for input."""
    req = _make_req(
        path_params={"portfolio_id": "p1"},
        form_data={"asset_query": "", "amount_wan": "10", "price_ref": "current"},
    )
    resp = await trade_lightning_create(req)
    assert isinstance(resp, HTMLResponse)
    assert "请输入股票代码" in resp.body.decode()


@pytest.mark.asyncio
async def test_create_unresolvable_asset_returns_toast():
    """[AC-NFR1101-01] asset_query cannot be resolved -> toast."""
    req = _make_req(
        path_params={"portfolio_id": "p1"},
        form_data={"asset_query": "zzz", "amount_wan": "10", "price_ref": "current"},
    )
    with patch.object(tl_mod, "_resolve_asset_input", return_value=None):
        resp = await trade_lightning_create(req)
    assert isinstance(resp, HTMLResponse)
    assert "未找到唯一匹配" in resp.body.decode()


@pytest.mark.asyncio
async def test_create_invalid_amount_returns_toast():
    """[AC-NFR1101-01] Invalid amount -> toast asking for valid amount."""
    req = _make_req(
        path_params={"portfolio_id": "p1"},
        form_data={"asset_query": "000001.SZ", "amount_wan": "abc", "price_ref": "current"},
    )
    with patch.object(tl_mod, "_resolve_asset_input", return_value="000001.SZ"):
        resp = await trade_lightning_create(req)
    assert isinstance(resp, HTMLResponse)
    assert "请输入有效的买入金额" in resp.body.decode()


@pytest.mark.asyncio
async def test_create_invalid_price_ref_returns_toast():
    """[AC-NFR1101-01] Invalid price_ref -> toast asking for valid price."""
    req = _make_req(
        path_params={"portfolio_id": "p1"},
        form_data={"asset_query": "000001.SZ", "amount_wan": "5", "price_ref": "garbage"},
    )
    with patch.object(tl_mod, "_resolve_asset_input", return_value="000001.SZ"):
        resp = await trade_lightning_create(req)
    assert isinstance(resp, HTMLResponse)
    assert "请选择有效的买入价格" in resp.body.decode()


@pytest.mark.asyncio
async def test_create_duplicate_returns_error_toast():
    """[AC-NFR1101-01] add_trade_lightning_entry returns created=False -> error toast."""
    req = _make_req(
        path_params={"portfolio_id": "p1"},
        form_data={"asset_query": "000001.SZ", "amount_wan": "5", "price_ref": "current"},
    )
    with patch.object(tl_mod, "_resolve_asset_input", return_value="000001.SZ"), \
         patch.object(tl_mod, "add_trade_lightning_entry", return_value=("000001.SZ", False)):
        resp = await trade_lightning_create(req)
    assert isinstance(resp, HTMLResponse)
    assert "该股票已存在" in resp.body.decode()


# ---------------------------------------------------------------------------
# trade_lightning_update - validation branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_entry_missing_returns_toast():
    """[AC-NFR1101-01] When entry is None, returns toast."""
    req = _make_req(
        path_params={"portfolio_id": "p1", "asset": "000001.SZ"},
        form_data={"amount_wan": "5", "price_ref": "current"},
    )
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=None):
        resp = await trade_lightning_update(req)
    assert isinstance(resp, HTMLResponse)
    assert "闪电买入单不存在" in resp.body.decode()


@pytest.mark.asyncio
async def test_update_invalid_amount_returns_toast():
    """[AC-NFR1101-01] Invalid amount_wan -> toast."""
    entry = _entry()
    req = _make_req(
        path_params={"portfolio_id": "p1", "asset": "000001.SZ"},
        form_data={"amount_wan": "abc", "price_ref": "current"},
    )
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=entry):
        resp = await trade_lightning_update(req)
    assert isinstance(resp, HTMLResponse)
    assert "请输入有效的买入金额" in resp.body.decode()


@pytest.mark.asyncio
async def test_update_invalid_price_ref_returns_toast():
    """[AC-NFR1101-01] Invalid price_ref -> toast."""
    entry = _entry()
    req = _make_req(
        path_params={"portfolio_id": "p1", "asset": "000001.SZ"},
        form_data={"amount_wan": "5", "price_ref": "garbage"},
    )
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=entry):
        resp = await trade_lightning_update(req)
    assert isinstance(resp, HTMLResponse)
    assert "请选择有效的买入价格" in resp.body.decode()


# ---------------------------------------------------------------------------
# trade_lightning_clear - both branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_zero_entries_returns_toast():
    """[AC-NFR1101-01] removed_count == 0 -> 'no entries' toast."""
    req = _make_req(path_params={"portfolio_id": "p1"})
    with patch.object(tl_mod, "clear_trade_lightning_entries", return_value=0):
        resp = await trade_lightning_clear(req)
    assert isinstance(resp, HTMLResponse)
    assert "当前没有可清空" in resp.body.decode()


@pytest.mark.asyncio
async def test_clear_removes_entries_returns_success_toast():
    """[AC-NFR1101-01] removed_count > 0 -> success toast."""
    req = _make_req(path_params={"portfolio_id": "p1"})
    with patch.object(tl_mod, "clear_trade_lightning_entries", return_value=3):
        resp = await trade_lightning_clear(req)
    assert isinstance(resp, HTMLResponse)
    assert "已清空 3 条" in resp.body.decode()
