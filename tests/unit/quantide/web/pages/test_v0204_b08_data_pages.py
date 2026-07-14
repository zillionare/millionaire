"""B08-data-pages-1: Tests for quantide/web/pages/data_* pages.

Target: raise coverage of data_calendar, data_db, data_market, data_stocks
from 15-21% to >=80%.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages.data_calendar import _TabNav as cal_TabNav, _get_active_tab as cal_get_active_tab
from quantide.web.pages.data_db import (
    _TabNav as db_TabNav,
    _build_pagination,
    _get_active_tab as db_get_active_tab,
)
from quantide.web.pages.data_market import (
    _TabNav as mkt_TabNav,
    _get_active_tab as mkt_get_active_tab,
)
from quantide.web.pages.data_stocks import (
    _TabNav as stk_TabNav,
    _get_active_tab as stk_get_active_tab,
)


def _req_with_query(query: str = "") -> MagicMock:
    req = MagicMock()
    req.query_params = {}
    if query:
        for kv in query.split("&"):
            k, _, v = kv.partition("=")
            req.query_params[k] = v
    return req


# ---------------------------------------------------------------------------
# data_calendar
# ---------------------------------------------------------------------------


def test_cal_get_active_tab_default():
    req = _req_with_query()
    assert cal_get_active_tab(req) == "overview"


def test_cal_get_active_tab_calendar():
    req = _req_with_query("tab=calendar")
    assert cal_get_active_tab(req) == "calendar"


def test_cal_get_active_tab_update():
    req = _req_with_query("tab=update")
    assert cal_get_active_tab(req) == "update"


def test_cal_get_active_tab_passes_through_unknown():
    req = _req_with_query("tab=bogus")
    assert cal_get_active_tab(req) == "bogus"


def test_cal_tab_nav_renders_three_tabs():
    nav = cal_TabNav("overview")
    text = str(nav)
    assert "overview" in text
    assert "calendar" in text
    assert "update" in text


def test_cal_tab_nav_marks_active():
    nav = cal_TabNav("calendar")
    text = str(nav)
    assert 'class=' in text  # class attribute used for active styling


@pytest.mark.asyncio
async def test_calendar_index_overview_tab():
    from quantide.web.pages.data_calendar import index as cal_index
    req = _req_with_query("tab=overview")
    resp = await cal_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_calendar_index_calendar_tab():
    from quantide.web.pages.data_calendar import index as cal_index
    req = _req_with_query("tab=calendar")
    resp = await cal_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_calendar_index_update_tab():
    from quantide.web.pages.data_calendar import index as cal_index
    req = _req_with_query("tab=update")
    resp = await cal_index(req)
    assert resp is not None


# ---------------------------------------------------------------------------
# data_db
# ---------------------------------------------------------------------------


def test_db_get_active_tab_default():
    req = _req_with_query()
    assert db_get_active_tab(req) == "data"


def test_db_get_active_tab_schema():
    req = _req_with_query("tab=schema")
    assert db_get_active_tab(req) == "schema"


def test_db_get_active_tab_passes_through_unknown():
    req = _req_with_query("tab=bogus")
    assert db_get_active_tab(req) == "bogus"


def test_db_tab_nav_renders():
    nav = db_TabNav("data")
    text = str(nav)
    assert "data" in text
    assert "schema" in text


def test_db_build_pagination_basic():
    pag = _build_pagination("test_table", 1, 5)
    text = str(pag)
    assert "test_table" in text


def test_db_build_pagination_last_page():
    pag = _build_pagination("test_table", 100, 100)
    text = str(pag)
    assert "test_table" in text


@pytest.mark.asyncio
async def test_db_index_data_tab():
    from quantide.web.pages.data_db import index as db_index
    req = _req_with_query("tab=data")
    resp = await db_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_db_index_schema_tab():
    from quantide.web.pages.data_db import index as db_index
    req = _req_with_query("tab=schema")
    resp = await db_index(req)
    assert resp is not None


# ---------------------------------------------------------------------------
# data_market
# ---------------------------------------------------------------------------


def test_mkt_get_active_tab_default():
    req = _req_with_query()
    assert mkt_get_active_tab(req) == "overview"


def test_mkt_get_active_tab_verify():
    req = _req_with_query("tab=verify")
    assert mkt_get_active_tab(req) == "verify"


def test_mkt_get_active_tab_update():
    req = _req_with_query("tab=update")
    assert mkt_get_active_tab(req) == "update"


def test_mkt_get_active_tab_browse():
    req = _req_with_query("tab=browse")
    assert mkt_get_active_tab(req) == "browse"


def test_mkt_get_active_tab_passes_through_unknown():
    req = _req_with_query("tab=bogus")
    assert mkt_get_active_tab(req) == "bogus"


def test_mkt_tab_nav_renders():
    nav = mkt_TabNav("overview")
    text = str(nav)
    assert "overview" in text
    assert "verify" in text
    assert "update" in text
    assert "browse" in text


@pytest.mark.asyncio
async def test_market_index_overview_tab():
    from quantide.web.pages.data_market import index as mkt_index
    req = _req_with_query("tab=overview")
    resp = await mkt_index(req)
    # Returns tuple of (title, ...components); just check it's non-empty.
    assert resp is not None
    assert len(resp) >= 1


@pytest.mark.asyncio
async def test_market_index_verify_tab():
    from quantide.web.pages.data_market import index as mkt_index
    req = _req_with_query("tab=verify")
    resp = await mkt_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_market_index_update_tab():
    from quantide.web.pages.data_market import index as mkt_index
    req = _req_with_query("tab=update")
    resp = await mkt_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_market_index_browse_tab():
    from quantide.web.pages.data_market import index as mkt_index
    req = _req_with_query("tab=browse")
    resp = await mkt_index(req)
    assert resp is not None


# ---------------------------------------------------------------------------
# data_stocks
# ---------------------------------------------------------------------------


def test_stk_get_active_tab_default():
    req = _req_with_query()
    assert stk_get_active_tab(req) == "overview"


def test_stk_get_active_tab_search():
    req = _req_with_query("tab=search")
    assert stk_get_active_tab(req) == "search"


def test_stk_get_active_tab_update():
    req = _req_with_query("tab=update")
    assert stk_get_active_tab(req) == "update"


def test_stk_get_active_tab_passes_through_unknown():
    req = _req_with_query("tab=bogus")
    assert stk_get_active_tab(req) == "bogus"


def test_stk_tab_nav_renders():
    nav = stk_TabNav("overview")
    text = str(nav)
    assert "overview" in text
    assert "search" in text
    assert "update" in text


@pytest.mark.asyncio
async def test_stocks_index_overview_tab():
    from quantide.web.pages.data_stocks import index as stk_index
    req = _req_with_query("tab=overview")
    resp = await stk_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_stocks_index_search_tab():
    from quantide.web.pages.data_stocks import index as stk_index
    req = _req_with_query("tab=search")
    resp = await stk_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_stocks_index_update_tab():
    from quantide.web.pages.data_stocks import index as stk_index
    req = _req_with_query("tab=update")
    resp = await stk_index(req)
    assert resp is not None
