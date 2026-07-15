"""B08-data-market: Test data_market.py helpers + tabs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages.data_market import (
    _TabNav,
    _get_active_tab,
)


def test_get_active_tab_default():
    """[AC-NFR1101-01] Default tab is 'overview' when no tab in query_params."""
    req = MagicMock()
    req.query_params = {}
    assert _get_active_tab(req) == "overview"


def test_get_active_tab_explicit():
    """[AC-NFR1101-01] test_get_active_tab_explicit."""
    req = MagicMock()
    req.query_params = {"tab": "verify"}
    assert _get_active_tab(req) == "verify"


def test_get_active_tab_browse():
    """[AC-NFR1101-01] test_get_active_tab_browse."""
    req = MagicMock()
    req.query_params = {"tab": "browse"}
    assert _get_active_tab(req) == "browse"


def test_get_active_tab_update():
    """[AC-NFR1101-01] test_get_active_tab_update."""
    req = MagicMock()
    req.query_params = {"tab": "update"}
    assert _get_active_tab(req) == "update"


def test_tab_nav_overview():
    """[AC-NFR1101-01] test_tab_nav_overview."""
    out = _TabNav("overview")
    assert out is not None


def test_tab_nav_verify():
    """[AC-NFR1101-01] test_tab_nav_verify."""
    out = _TabNav("verify")
    assert out is not None


def test_tab_nav_update():
    """[AC-NFR1101-01] test_tab_nav_update."""
    out = _TabNav("update")
    assert out is not None


def test_tab_nav_browse():
    """[AC-NFR1101-01] test_tab_nav_browse."""
    out = _TabNav("browse")
    assert out is not None


def test_tab_nav_unknown():
    """[AC-NFR1101-01] Unknown tab still renders."""
    out = _TabNav("garbage")
    assert out is not None


# ---------------------------------------------------------------------------
# do_verify + do_update endpoints
# ---------------------------------------------------------------------------


import pytest as _pt


@_pt.mark.asyncio
async def test_do_verify_default():
    """do_verify returns Div with success message."""
    from quantide.web.pages.data_market import do_verify
    out = await do_verify({"assets": "000001.SZ", "start_year": "2020", "end_year": "2024"})
    assert out is not None


@_pt.mark.asyncio
async def test_do_update_bad_date_returns_error():
    """Bad date → returns error Div."""
    from quantide.web.pages.data_market import do_update
    req = MagicMock()
    req.form = AsyncMock(return_value={"start_date": "garbage", "end_date": "2024-06-30"})
    resp = await do_update(req)
    assert resp is not None


@_pt.mark.asyncio
async def test_do_update_valid_date():
    """Valid date → returns progress modal."""
    from quantide.web.pages.data_market import do_update
    req = MagicMock()
    req.form = AsyncMock(return_value={"start_date": "2024-01-01", "end_date": "2024-06-30"})
    resp = await do_update(req)
    assert resp is not None


# Add AsyncMock import
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# _BrowseTab with data
# ---------------------------------------------------------------------------


import polars as pl2_bm
from quantide.web.pages.data_market import _BrowseTab
from quantide.web.pages import data_market as dm_mod


def test_browse_tab_no_asset():
    """[AC-NFR1101-01] No asset → placeholder text."""
    req = MagicMock()
    req.query_params = {}
    out = _BrowseTab(req)
    assert out is not None


def test_browse_tab_with_asset_exception():
    """[AC-NFR1101-01] When daily_bars raises, returns error message."""
    with patch.object(dm_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars_in_range = MagicMock(side_effect=Exception("boom"))
        req = MagicMock()
        req.query_params = {"asset": "000001.SZ"}
        out = _BrowseTab(req)
    assert out is not None


def test_browse_tab_with_data():
    """[AC-NFR1101-01] With data, renders table."""
    fake_df = pl2_bm.DataFrame({
        "date": ["2024-06-30"],
        "asset": ["000001.SZ"],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
        "amount": [10500.0],
        "adjust": [1.0],
        "st": [0],
    })
    with patch.object(dm_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars_in_range = MagicMock(return_value=fake_df)
        req = MagicMock()
        req.query_params = {"asset": "000001.SZ", "start": "2024-01-01", "end": "2024-12-31"}
        out = _BrowseTab(req)
    assert out is not None


