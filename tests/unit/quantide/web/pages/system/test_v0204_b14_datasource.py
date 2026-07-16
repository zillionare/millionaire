"""B14-datasource: Coverage tests for quantide/web/pages/system/datasource.py.

Target lines:
- 45-49: _load_datasource_config exception + settings fallback (empty app_state row)
- 79-81: _get_data_status daily_bars empty/error branches
- 94-96: stock_list empty/error branches
- 111-113: calendar empty/error branches
- 128-129: _get_sync_history exception path
- 139, 141: _build_status_badge empty/error branches
- 373-381: save_config success path (init_wizard.save_data_init_config)
- 420-422: daily_bars sync exception path
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages.system import datasource as ds_mod
from quantide.web.pages.system.datasource import (
    _build_status_badge,
    _get_data_status,
    _get_sync_history,
    _load_datasource_config,
    save_config as ds_save_config,
    sync_data as ds_sync_data,
)


# ---------------------------------------------------------------------------
# _load_datasource_config: exception path + missing row fallback
# ---------------------------------------------------------------------------


def test_load_datasource_config_exception_uses_settings_branch():
    """db['app_state'].get raises -> except branch (line 45-46) -> settings fallback."""
    with patch.object(ds_mod, "db") as mock_db:
        mock_table = MagicMock()
        mock_table.get = MagicMock(side_effect=RuntimeError("db down"))
        mock_db.__getitem__.return_value = mock_table
        out = _load_datasource_config()
    assert "data_source" in out
    assert "epoch" in out
    assert "history_years" in out
    # Settings fallback returns history_years=3
    assert out["history_years"] == 3


def test_load_datasource_config_row_none_falls_to_settings():
    """db['app_state'].get returns None -> falls to settings branch (line 48-49)."""
    with patch.object(ds_mod, "db") as mock_db:
        mock_table = MagicMock()
        mock_table.get = MagicMock(return_value=None)
        mock_db.__getitem__.return_value = mock_table
        out = _load_datasource_config()
    assert "data_source" in out
    # Settings fallback returns history_years=3
    assert out["history_years"] == 3


# ---------------------------------------------------------------------------
# _get_data_status: empty + error branches for daily_bars, stock_list, calendar
# ---------------------------------------------------------------------------


def test_get_data_status_daily_bars_empty():
    """daily_bars.total_dates == 0 -> 'empty' status."""
    with patch.dict("sys.modules", {}):
        # Patch daily_bars directly via the module attribute
        with patch("quantide.data.models.daily_bars.daily_bars") as mock_bars:
            mock_bars.total_dates = 0
            out = _get_data_status()
    assert out["daily_bars"]["status"] == "empty"


def test_get_data_status_daily_bars_exception():
    """daily_bars access raises -> 'error' status."""
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_bars:
        type(mock_bars).total_dates = property(MagicMock(side_effect=RuntimeError("boom")))
        out = _get_data_status()
    assert out["daily_bars"]["status"] == "error"
    assert "boom" in out["daily_bars"]["message"]


def test_get_data_status_stock_list_empty():
    """stock_list._data is None -> 'empty' status."""
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_bars, \
         patch("quantide.data.models.stocks.stock_list") as mock_stocks:
        mock_bars.total_dates = 0
        mock_stocks._data = None
        out = _get_data_status()
    assert out["stock_list"]["status"] == "empty"


def test_get_data_status_stock_list_exception():
    """stock_list access raises -> 'error' status."""
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_bars, \
         patch("quantide.data.models.stocks.stock_list") as mock_stocks:
        mock_bars.total_dates = 0
        type(mock_stocks)._data = property(MagicMock(side_effect=RuntimeError("stx")))
        out = _get_data_status()
    assert out["stock_list"]["status"] == "error"
    assert "stx" in out["stock_list"]["message"]


def test_get_data_status_calendar_empty():
    """calendar._data is None -> 'empty' status."""
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_bars, \
         patch("quantide.data.models.stocks.stock_list") as mock_stocks, \
         patch("quantide.data.models.calendar.calendar") as mock_cal:
        mock_bars.total_dates = 0
        mock_stocks._data = None
        mock_cal._data = None
        out = _get_data_status()
    assert out["calendar"]["status"] == "empty"


def test_get_data_status_calendar_exception():
    """calendar access raises -> 'error' status."""
    with patch("quantide.data.models.daily_bars.daily_bars") as mock_bars, \
         patch("quantide.data.models.stocks.stock_list") as mock_stocks, \
         patch("quantide.data.models.calendar.calendar") as mock_cal:
        mock_bars.total_dates = 0
        mock_stocks._data = None
        type(mock_cal)._data = property(MagicMock(side_effect=RuntimeError("calx")))
        out = _get_data_status()
    assert out["calendar"]["status"] == "error"
    assert "calx" in out["calendar"]["message"]


# ---------------------------------------------------------------------------
# _get_sync_history: exception path
# ---------------------------------------------------------------------------


def test_get_sync_history_db_exception_returns_empty_list():
    """db['job_history'].rows_where raises -> returns empty list."""
    with patch.object(ds_mod, "db") as mock_db:
        mock_table = MagicMock()
        mock_table.rows_where = MagicMock(side_effect=RuntimeError("no table"))
        mock_db.__getitem__.return_value = mock_table
        out = _get_sync_history()
    assert out == []


# ---------------------------------------------------------------------------
# _build_status_badge: empty and error branches
# ---------------------------------------------------------------------------


def test_build_status_badge_empty():
    """status='empty' -> '⚠️ 空数据' badge (line 139)."""
    out = _build_status_badge("empty")
    text = str(out)
    assert "空数据" in text


def test_build_status_badge_error():
    """status='error' -> '❌ 错误' badge (line 141)."""
    out = _build_status_badge("error")
    text = str(out)
    assert "错误" in text


# ---------------------------------------------------------------------------
# save_config: success path (init_wizard.save_data_init_config called)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_config_success_renders_success_message():
    """save_config with valid form -> save_data_init_config called -> success render."""
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "data_source": "tushare",
        "tushare_token": "abc",
        "epoch": "2024-01-01",
        "history_years": "5",
    })
    saved_cfg = {"data_source": "tushare", "tushare_token": "abc", "epoch": 7,
                 "history_years": 5}
    with patch.object(ds_mod, "_load_datasource_config", return_value={}), \
         patch.object(ds_mod, "_load_datasource_config", return_value=saved_cfg) as _load2, \
         patch.object(ds_mod, "init_wizard") as mock_iw, \
         patch.object(ds_mod, "_render_page", return_value="rendered") as mock_render:
        # First call returns {} for `current`, second call returns saved config.
        _load2.side_effect = [{}, saved_cfg]
        mock_iw.save_data_init_config = MagicMock()
        out = await ds_save_config(req)
    assert out == "rendered"
    mock_iw.save_data_init_config.assert_called_once()
    call_kwargs = mock_iw.save_data_init_config.call_args.kwargs
    assert call_kwargs["epoch"] == datetime.date(2024, 1, 1)
    assert call_kwargs["history_years"] == 5
    _, kwargs = mock_render.call_args
    assert kwargs.get("success_message") == "数据源配置已保存"


@pytest.mark.asyncio
async def test_save_config_invalid_epoch_renders_error_message():
    """save_config with bad epoch -> exception -> error render."""
    req = MagicMock()
    req.form = AsyncMock(return_value={
        "data_source": "tushare",
        "tushare_token": "",
        "epoch": "not-a-date",
        "history_years": "3",
    })
    with patch.object(ds_mod, "_load_datasource_config", return_value={}), \
         patch.object(ds_mod, "init_wizard") as mock_iw, \
         patch.object(ds_mod, "_render_page", return_value="rendered") as mock_render:
        mock_iw.save_data_init_config = MagicMock(side_effect=ValueError("bad date"))
        out = await ds_save_config(req)
    assert out == "rendered"
    _, kwargs = mock_render.call_args
    assert "保存失败" in kwargs.get("error_message", "")


# ---------------------------------------------------------------------------
# sync_data: daily_bars sync exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_data_daily_bars_exception_logs_error():
    """sync_data: daily_bars.store.update raises -> exception logged, continues."""
    with patch("quantide.data.models.calendar.calendar") as mock_cal, \
         patch("quantide.data.models.stocks.stock_list") as mock_stocks, \
         patch("quantide.data.models.daily_bars.daily_bars") as mock_bars:
        mock_cal.update = MagicMock()
        mock_stocks.update = MagicMock()
        mock_bars.store.update = MagicMock(side_effect=RuntimeError("bars err"))
        req = MagicMock()
        req.form = AsyncMock(return_value={})
        resp = await ds_sync_data(req)
    assert resp is not None
    text = str(resp)
    assert "日线数据同步失败" in text
