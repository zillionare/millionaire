"""[AC-NFR1101-01] B09 trade_main route handler tests.

Targets uncovered branches of ``trade_main.py`` route handlers:
``place_order_trade`` (no-broker toast, success toast), ``search_trade_assets``
(valid query path), ``set_active_account`` (valid form + invalid form),
``trade_live_quote`` (returns dict), ``trade_asset_stats`` (valid asset).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from quantide.core.enums import BrokerKind
from quantide.web.pages import trade_main as tm
from quantide.web.pages.trade_main import (
    place_order_trade,
    search_trade_assets,
    set_active_account,
    trade_asset_stats,
    trade_live_quote,
)


def _make_req(
    *,
    scope: dict | None = None,
    form_data: dict | None = None,
    query_params: dict | None = None,
) -> MagicMock:
    """Build a fake Starlette request for trade_main route handlers."""
    req = MagicMock()
    req.scope = scope or {}
    req.query_params = query_params or {}
    req.form = AsyncMock(return_value=form_data or {})
    return req


# ---------------------------------------------------------------------------
# place_order_trade - success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_order_trade_buy_amount_success_returns_success_toast():
    """[AC-NFR1101-01] BUY with AMOUNT mode and buy_amount hook -> success toast."""
    fake_broker = MagicMock()
    fake_broker.buy_amount = AsyncMock(return_value=MagicMock(qt_oid="o1"))
    reg = MagicMock()
    reg.get = MagicMock(return_value=fake_broker)
    req = _make_req(
        scope={
            "registry": reg,
            "session": {"active_account_kind": BrokerKind.QMT.value, "active_account_id": "p1"},
        },
        form_data={
            "side": "BUY",
            "asset": "000001.SZ",
            "price_mode": "LIMIT",
            "order_mode": "AMOUNT",
            "price": "10.0",
            "value": "5",
        },
    )
    resp = await place_order_trade(req)
    assert isinstance(resp, HTMLResponse)
    assert "买入委托已提交" in resp.body.decode()


@pytest.mark.asyncio
async def test_place_order_trade_no_broker_returns_error_toast():
    """[AC-NFR1101-01] No broker resolvable -> '未找到可用的交易账号' toast."""
    req = _make_req(scope={"session": {}}, form_data={"asset": "000001.SZ"})
    resp = await place_order_trade(req)
    assert isinstance(resp, HTMLResponse)
    assert "未找到可用的交易账号" in resp.body.decode()


# ---------------------------------------------------------------------------
# search_trade_assets - valid query path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_trade_assets_with_valid_query_renders_dropdown_items():
    """[AC-NFR1101-01] Valid query with matches renders the asset-search dropdown."""
    req = _make_req(query_params={"q": "000001"})
    with patch.object(tm, "stock_list") as mock_sl, \
         patch.object(tm, "daily_bars") as mock_bars:
        mock_sl.fuzzy_search = MagicMock(
            return_value=pd.DataFrame(
                [{"asset": "000001.SZ", "name": "平安银行", "pinyin": "pingan"}]
            )
        )
        mock_bars.get_price = MagicMock(return_value=(0.0, 0.0, 0.0))
        resp = await search_trade_assets(req)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode()
    assert "平安银行" in body
    assert "000001.SZ" in body


# ---------------------------------------------------------------------------
# set_active_account - valid form + invalid form branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_active_account_valid_form_redirects_to_trade():
    """[AC-NFR1101-01] Valid kind+id form sets session and redirects to /trade."""
    session: dict = {}
    req = _make_req(form_data={"kind": BrokerKind.QMT.value, "id": "p1"})
    resp = await set_active_account(req, session)
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/trade"
    assert session["active_account_kind"] == BrokerKind.QMT.value
    assert session["active_account_id"] == "p1"


@pytest.mark.asyncio
async def test_set_active_account_missing_params_returns_error_div():
    """[AC-NFR1101-01] Missing kind or id returns a '参数错误' error div."""
    req = _make_req(form_data={"kind": "", "id": ""})
    session: dict = {}
    resp = await set_active_account(req, session)
    # Returns a fasthtml Div (not an HTTPResponse); just verify the rendered text.
    rendered = tm.to_xml(resp)
    assert "参数错误" in rendered


# ---------------------------------------------------------------------------
# trade_live_quote / trade_asset_stats - JSON return paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_live_quote_returns_jsonresponse_dict():
    """[AC-NFR1101-01] trade_live_quote returns a JSONResponse wrapping a dict."""
    req = _make_req(query_params={"asset": "000001.SZ"})
    with patch.object(tm, "_build_live_quote_payload", return_value={"asset": "000001.SZ", "current": "10.0", "visible": True}):
        resp = await trade_live_quote(req)
    assert isinstance(resp, JSONResponse)
    body = resp.body.decode() if hasattr(resp, "body") else ""
    assert "000001.SZ" in body
    assert "10.0" in body


@pytest.mark.asyncio
async def test_trade_asset_stats_with_valid_asset_returns_jsonresponse():
    """[AC-NFR1101-01] trade_asset_stats with valid asset returns JSON payload."""
    req = _make_req(query_params={"asset": "000001.SZ"})
    fake_payload = {"visible": True, "close": "10.5", "current": "10.6", "ma5": "10.4"}
    with patch.object(tm, "_build_asset_stats", return_value=fake_payload):
        resp = await trade_asset_stats(req)
    assert isinstance(resp, JSONResponse)
    body = resp.body.decode() if hasattr(resp, "body") else ""
    assert "10.5" in body
    assert "10.6" in body
