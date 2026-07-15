"""[AC-NFR1101-01] B09 broker route handler tests.

Targets uncovered branches of ``web/apis/broker.py``:
- ``buy_percent`` / ``sell_percent`` with ``bid_time=None`` (400 path).
- ``delete_accounts`` admin / non-admin branches.
- ``get_assets`` date parsing + filter path.
- ``run_grid_search_job`` JSON parse failure + success path.
"""

from __future__ import annotations

import datetime
import pickle
from unittest.mock import AsyncMock, MagicMock, patch

import arrow
import numpy as np
import pandas as pd
import pytest
from starlette.responses import PlainTextResponse, Response

from quantide.web.apis import broker as broker_api
from quantide.web.apis.broker import (
    buy_percent,
    delete_accounts,
    get_assets,
    run_grid_search_job,
    sell_percent,
)


def _make_broker_req(
    *,
    fake_broker: MagicMock | None = None,
    args: dict | None = None,
    json_body: dict | None = None,
) -> MagicMock:
    """Build a fake request whose registry resolves to ``fake_broker``."""
    broker = fake_broker or MagicMock()
    reg = MagicMock()
    reg.get_default = MagicMock(return_value=("backtest", "b1"))
    reg.get = MagicMock(return_value=broker)
    req = MagicMock()
    req.scope = {"registry": reg, "session": {}}
    req.query_params = {}
    req.args = args or {}
    req.json = json_body or {}
    req.app.ctx.accounts = MagicMock()
    return req


# ---------------------------------------------------------------------------
# buy_percent / sell_percent - bid_time=None branches (lines 158, 214)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_percent_no_bid_time_in_backtest_returns_400():
    """[AC-NFR1101-01] buy_percent with bid_time=None in backtest -> 400."""
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    req = _make_broker_req()
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        resp = await buy_percent(req, asset="000001.SZ", percent=0.5, bid_time=None)
    assert resp.status_code == 400
    assert "bid_time must be provided" in resp.body.decode()


@pytest.mark.asyncio
async def test_sell_percent_no_bid_time_in_backtest_returns_400():
    """[AC-NFR1101-01] sell_percent with bid_time=None in backtest -> 400."""
    fake_settings = MagicMock()
    fake_settings.runtime_mode = "backtest"
    req = _make_broker_req()
    with patch.object(broker_api, "get_settings", return_value=fake_settings):
        resp = await sell_percent(req, asset="000001.SZ", percent=0.5, bid_time=None)
    assert resp.status_code == 400
    assert "bid_time must be provided" in resp.body.decode()


# ---------------------------------------------------------------------------
# delete_accounts - admin / non-admin branches (lines 325-337)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_accounts_no_name_admin_deletes_all():
    """[AC-NFR1101-01] name=None + admin broker -> delete_accounts() called."""
    fake_broker = MagicMock()
    fake_broker.account_name = "admin"
    req = _make_broker_req(fake_broker=fake_broker, args={})
    await delete_accounts(req)
    req.app.ctx.accounts.delete_accounts.assert_called_once_with()


@pytest.mark.asyncio
async def test_delete_accounts_no_name_non_admin_returns_403():
    """[AC-NFR1101-01] name=None + non-admin broker -> 403 PlainTextResponse."""
    fake_broker = MagicMock()
    fake_broker.account_name = "user1"
    req = _make_broker_req(fake_broker=fake_broker, args={})
    resp = await delete_accounts(req)
    assert isinstance(resp, PlainTextResponse)
    assert resp.status_code == 403
    assert "admin account required" in resp.body.decode()


@pytest.mark.asyncio
async def test_delete_accounts_name_matches_broker_deletes_named():
    """[AC-NFR1101-01] name == broker.account_name -> delete_accounts(name) called."""
    fake_broker = MagicMock()
    fake_broker.account_name = "user1"
    req = _make_broker_req(fake_broker=fake_broker, args={"name": "user1"})
    await delete_accounts(req)
    req.app.ctx.accounts.delete_accounts.assert_called_once_with("user1")


# ---------------------------------------------------------------------------
# get_assets - start/end date parse + filter path (lines 358-373)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_assets_with_explicit_start_end_returns_binary_payload():
    """[AC-NFR1101-01] start/end args -> date parse + filter + pickle response."""
    dates = np.array(
        [datetime.date(2024, 1, 1), datetime.date(2024, 6, 1), datetime.date(2024, 9, 1)],
        dtype="datetime64[D]",
    )
    fake_assets = np.array(
        [(dates[0], 100.0), (dates[1], 110.0), (dates[2], 120.0)],
        dtype=[("date", "datetime64[D]"), ("total", "f8")],
    )
    fake_broker = MagicMock()
    fake_broker._assets = fake_assets
    fake_broker.bt_start = datetime.date(2024, 1, 1)
    req = _make_broker_req(
        fake_broker=fake_broker,
        args={"start": "2024-03-01", "end": "2024-12-31"},
    )
    resp = await get_assets(req)
    assert isinstance(resp, Response)
    assert resp.media_type == "application/octet-stream"
    payload = pickle.loads(resp.body)
    # start=2024-03-01 excludes 2024-01-01 row -> only 2 rows survive.
    assert len(payload) == 2


@pytest.mark.asyncio
async def test_get_assets_without_args_falls_back_to_broker_bounds():
    """[AC-NFR1101-01] no start/end -> broker.bt_start and broker._assets[-1] used."""
    dates = np.array(
        [datetime.date(2024, 1, 1), datetime.date(2024, 6, 1)],
        dtype="datetime64[D]",
    )
    fake_assets = np.array(
        [(dates[0], 100.0), (dates[1], 110.0)],
        dtype=[("date", "datetime64[D]"), ("total", "f8")],
    )
    fake_broker = MagicMock()
    fake_broker._assets = fake_assets
    fake_broker.bt_start = datetime.date(2024, 1, 1)
    req = _make_broker_req(fake_broker=fake_broker, args={})
    resp = await get_assets(req)
    payload = pickle.loads(resp.body)
    assert len(payload) == 2


# ---------------------------------------------------------------------------
# run_grid_search_job - JSON parse failure + success path (lines 480-525)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_grid_search_json_parse_failure_falls_back_to_empty():
    """[AC-NFR1101-01] req.json() raising -> params defaults to {} -> 404 strategy."""
    req = MagicMock()
    req.json = AsyncMock(side_effect=Exception("not json"))
    with patch.object(broker_api, "strategy_loader") as mock_loader:
        mock_loader.load_from_cache = MagicMock(return_value={})
        resp = await run_grid_search_job(req)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_grid_search_success_returns_json_records():
    """[AC-NFR1101-01] Full success path -> returns df JSON records response."""
    strategy_cls = MagicMock(name="StrategyCls")
    results_df = pd.DataFrame(
        [{"return": 0.15, "sharpe": 1.5}, {"return": 0.10, "sharpe": 1.2}]
    )
    req = MagicMock()
    req.json = AsyncMock(
        return_value={
            "strategy_name": "demo",
            "base_config": {"k": 1},
            "param_grid": {"k": [1, 2]},
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "interval": "1d",
            "initial_cash": 1_000_000,
            "max_workers": 2,
        }
    )
    with patch.object(broker_api, "strategy_loader") as mock_loader, \
         patch.object(broker_api, "GridSearch") as mock_gs_cls:
        mock_loader.load_from_cache = MagicMock(return_value={"demo": strategy_cls})
        gs_inst = MagicMock()
        gs_inst.run = MagicMock(return_value=results_df)
        mock_gs_cls.return_value = gs_inst
        resp = await run_grid_search_job(req)
    assert resp.status_code == 200
    assert resp.media_type == "application/json"
    body = resp.body.decode()
    assert "0.15" in body
    mock_gs_cls.assert_called_once()
    gs_inst.run.assert_called_once_with(save_logs=True)
