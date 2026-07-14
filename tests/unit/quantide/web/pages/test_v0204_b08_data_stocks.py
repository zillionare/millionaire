"""B08-data-stocks-page-1: Tests for quantide/web/pages/data_stocks.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.data_stocks import _get_active_tab, _OverviewTab, _SearchTab, _UpdateTab, index


def _request(query=None):
    req = MagicMock()
    req.query_params = query or {}
    return req


# ---------------------------------------------------------------------------
# _get_active_tab
# ---------------------------------------------------------------------------


def test_get_active_tab_default():
    req = _request()
    assert _get_active_tab(req) == "overview"


def test_get_active_tab_search():
    req = _request({"tab": "search"})
    assert _get_active_tab(req) == "search"


def test_get_active_tab_update():
    req = _request({"tab": "update"})
    assert _get_active_tab(req) == "update"


def test_get_active_tab_unknown_passthrough():
    req = _request({"tab": "bogus"})
    assert _get_active_tab(req) == "bogus"


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------


def test_overview_tab_renders():
    out = _OverviewTab()
    assert out is not None


def test_search_tab_renders():
    req = _request()
    out = _SearchTab(req)
    assert out is not None


def test_search_tab_with_query():
    req = _request({"q": "test"})
    out = _SearchTab(req)
    assert out is not None


def test_update_tab_renders():
    out = _UpdateTab()
    assert out is not None


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_overview():
    req = _request()
    resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_search():
    req = _request({"tab": "search"})
    resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_update():
    req = _request({"tab": "update"})
    resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_with_query():
    req = _request({"q": "000001"})
    resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_page_2():
    req = _request({"page": "2"})
    resp = await index(req)
    assert resp is not None
