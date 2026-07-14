"""B08-data-stocks-2: Test tab content renderers + index routes for data_stocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.data_stocks import (
    _OverviewTab,
    _SearchTab,
    _UpdateTab,
    index,
)


def _req(query=None):
    req = MagicMock()
    req.query_params = query or {}
    return req


def test_overview_tab_normal_state():
    """_OverviewTab renders when stock_list is accessible."""
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        mock_sl.size = 5000
        mock_sl.last_update_time = "2024-01-01"
        mock_sl.path = Path("/data/stocks.parquet")
        out = _OverviewTab()
    assert out is not None


def test_overview_tab_handles_exception():
    """_OverviewTab renders error message on exception."""
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        type(mock_sl).size = property(lambda self: (_ for _ in ()).throw(Exception("boom")))
        out = _OverviewTab()
    assert out is not None


def test_update_tab_renders():
    out = _UpdateTab()
    assert out is not None


def test_search_tab_empty_query():
    """_SearchTab with no query shows placeholder."""
    out = _SearchTab(_req())
    assert out is not None


def test_search_tab_with_query():
    """_SearchTab with query attempts fuzzy search."""
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(return_value=[])
        out = _SearchTab(_req({"q": "test"}))
    assert out is not None


def test_search_tab_with_query_returns_results():
    """_SearchTab with query and matches renders results."""
    class _Result:
        def __init__(self, asset, name, pinyin):
            self.asset = asset
            self.name = name
            self.pinyin = pinyin
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(return_value=[
            _Result("000001.SZ", "X", "x"),
            _Result("000002.SZ", "Y", "y"),
        ])
        out = _SearchTab(_req({"q": "x"}))
    assert out is not None


def test_search_tab_with_query_handles_exception():
    """_SearchTab with query catches exceptions."""
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(side_effect=Exception("boom"))
        out = _SearchTab(_req({"q": "x"}))
    assert out is not None


# ---------------------------------------------------------------------------
# _run_stocks_sync — exercises status state machine
# ---------------------------------------------------------------------------


from quantide.web.pages.data_stocks import _run_stocks_sync, _sync_status

import asyncio


def test_run_stocks_sync_success_state_resets():
    """End state when sync succeeds."""
    _sync_status["is_running"] = False
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        mock_sl.update = MagicMock()
        asyncio.run(_run_stocks_sync())
    assert _sync_status["completed"] is True
    assert _sync_status["is_running"] is False


def test_run_stocks_sync_error_records():
    _sync_status["is_running"] = False
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        def _boom():
            raise Exception("sync failed")
        mock_sl.update = _boom
        asyncio.run(_run_stocks_sync())
    assert _sync_status["error"] is not None
    assert _sync_status["is_running"] is False


# Path import for OverviewTab test
from pathlib import Path


@pytest.mark.asyncio
async def test_index_overview_route():
    req = _req()
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        class _DF:
            def sort(self, *a, **kw):
                return self

            def is_empty(self_inner):
                return True

            def to_pandas(self_inner):
                return []

            def __len__(self_inner):
                return 0

        mock_sl.all_stocks.return_value = _DF()
        resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_search_route():
    req = _req({"tab": "search"})
    with patch("quantide.web.pages.data_stocks.stock_list") as mock_sl:
        mock_sl.fuzzy_search = MagicMock(return_value=[])
        resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_update_route():
    req = _req({"tab": "update"})
    resp = await index(req)
    assert resp is not None
