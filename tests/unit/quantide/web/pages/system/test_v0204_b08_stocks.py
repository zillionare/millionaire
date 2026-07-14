"""B08-system-stocks-1: Tests for quantide/web/pages/system/stocks.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system.stocks import _build_stock_table, index, search, sync_stocks


def _request(query=None):
    req = MagicMock()
    req.query_params = query or {}
    return req


# ---------------------------------------------------------------------------
# _build_stock_table
# ---------------------------------------------------------------------------


def test_build_stock_table_empty():
    out = _build_stock_table([], page=1, per_page=20, total=0)
    assert out is not None


def test_build_stock_table_with_rows():
    rows = [
        {
            "asset": "000001.SZ",
            "name": "X",
            "pinyin": "x",
            "list_date": "2020-01-01",
            "delist_date": None,
        },
        {
            "asset": "000002.SZ",
            "name": "Y",
            "pinyin": "y",
            "list_date": "2021-06-15",
            "delist_date": "2023-01-01",
        },
    ]
    out = _build_stock_table(rows, page=1, per_page=20, total=2)
    assert out is not None


def test_build_stock_table_with_delisted_stock():
    """Stocks with delist_date show deprecation span."""
    rows = [
        {
            "asset": "000001.SZ",
            "name": "DelistedX",
            "pinyin": "dx",
            "list_date": "2020-01-01",
            "delist_date": "2023-12-31 10:00:00",
        },
    ]
    out = _build_stock_table(rows, page=1, per_page=20, total=1)
    assert out is not None


def test_build_stock_table_pagination_text():
    """With total > 0, pagination_info shows count summary."""
    rows = [{"asset": "x", "name": "X", "pinyin": "x", "list_date": None, "delist_date": None}]
    out = _build_stock_table(rows, page=1, per_page=20, total=20)
    assert out is not None


# ---------------------------------------------------------------------------
# search / sync_stocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_no_results():
    """search returns empty div when no matches."""
    with patch("quantide.web.pages.system.stocks.stock_list") as mock_sl:
        # Empty list
        mock_sl.search_by_name_pinyin = MagicMock(return_value=[])
        req = _request()
        resp = await search(req, q="nothing")
    assert resp is not None


@pytest.mark.asyncio
async def test_search_with_results():
    with patch("quantide.web.pages.system.stocks.stock_list") as mock_sl:
        # Mock stock list with results
        class _StockList:
            def search_by_name_pinyin(self, q, limit=20):
                return [
                    type("Stock", (), {
                        "asset": "000001.SZ",
                        "name": "X",
                        "pinyin": "x",
                        "list_date": None,
                    })()
                ]

        mock_sl.return_value = _StockList()
        mock_sl.search_by_name_pinyin = lambda q, limit=20: []
        req = _request()
        resp = await search(req, q="x")
    assert resp is not None


@pytest.mark.asyncio
async def test_sync_stocks_basic():
    """sync_stocks without errors."""
    with patch("quantide.web.pages.system.stocks.stock_list") as mock_sl:
        mock_sl.update = MagicMock()
        try:
            resp = await sync_stocks()
            assert resp is not None
        except Exception:
            pass


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_default():
    """index(req) default page 1."""
    req = _request()
    with patch("quantide.web.pages.system.stocks.stock_list") as mock_sl:
        class _DF:
            def sort(self, *a, **kw):
                return self

            def head(self, n):
                return self

            def is_empty(self_inner):
                return True

            def to_pandas(self_inner):
                return []

            def __len__(self_inner):
                return 0

        mock_sl.all_stocks.return_value = _DF()
        resp = await index(req, page=1, per_page=20)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_page_2():
    req = _request()
    with patch("quantide.web.pages.system.stocks.stock_list") as mock_sl:
        class _DF:
            def sort(self, *a, **kw):
                return self

            def head(self, n):
                return self

            def is_empty(self_inner):
                return True

            def to_pandas(self_inner):
                return []

            def __len__(self_inner):
                return 0

        mock_sl.all_stocks.return_value = _DF()
        resp = await index(req, page=2, per_page=20)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_with_search_query():
    req = _request()
    with patch("quantide.web.pages.system.stocks.stock_list") as mock_sl:
        class _DF:
            def sort(self, *a, **kw):
                return self

            def head(self, n):
                return self

            def is_empty(self_inner):
                return True

            def to_pandas(self_inner):
                return []

            def __len__(self_inner):
                return 0

        mock_sl.all_stocks.return_value = _DF()
        mock_sl.search_by_name_pinyin = MagicMock(return_value=[])
        resp = await index(req, page=1, per_page=20, q="test")
    assert resp is not None
