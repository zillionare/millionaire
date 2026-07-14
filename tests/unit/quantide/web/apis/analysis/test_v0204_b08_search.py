"""B08-search-api-1: Tests for quantide/web/apis/analysis/search.py.

Target: raise coverage from 37.5% to >=80%.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from quantide.data.models.stocks import StockList
from quantide.web.apis.analysis.search import get_stock_list, search_stocks


# ---------------------------------------------------------------------------
# get_stock_list
# ---------------------------------------------------------------------------


def test_get_stock_list_returns_stocklist_instance():
    sl = get_stock_list()
    # Singleton factory: type name should be StockList.
    assert type(sl).__name__ == "StockList"
    assert hasattr(sl, "data")


# ---------------------------------------------------------------------------
# search_stocks edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_stocks_empty_query_returns_empty():
    resp = await search_stocks(None, q="")
    import json
    assert resp.status_code == 200
    body = json.loads(resp.body)
    assert body["code"] == 0
    assert body["data"] == []


@pytest.mark.asyncio
async def test_search_stocks_empty_data_returns_empty():
    """When stock_list.data is empty, returns empty results."""
    fake_sl = MagicMock()
    fake_sl.data = pl.DataFrame(schema={"asset": pl.Utf8, "name": pl.Utf8, "pinyin": pl.Utf8, "list_date": pl.Date})
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="000")
    import json
    body = json.loads(resp.body)
    assert body["data"] == []


@pytest.mark.asyncio
async def test_search_stocks_finds_by_code():
    """Search by asset code matches polars str.contains."""
    test_data = pl.DataFrame({
        "asset": ["000001.SZ", "000002.SZ", "600000.SH"],
        "name": ["平安银行", "万科A", "浦发银行"],
        "pinyin": ["payh", "wanka", "pufayh"],
        "list_date": [None, None, None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="600")
    import json
    body = json.loads(resp.body)
    assert body["code"] == 0
    assert len(body["data"]) == 1
    assert body["data"][0]["symbol"] == "600000.SH"
    """Search by asset code matches polars str.contains."""
    test_data = pl.DataFrame({
        "asset": ["000001.SZ", "000002.SZ", "600000.SH"],
        "name": ["平安银行", "万科A", "浦发银行"],
        "pinyin": ["payh", "wanka", "pufayh"],
        "list_date": [None, None, None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="600")
    import json
    body = json.loads(resp.body)
    assert body["code"] == 0
    assert len(body["data"]) == 1
    assert body["data"][0]["symbol"] == "600000.SH"


@pytest.mark.asyncio
async def test_search_stocks_finds_by_name():
    """Search by name (Chinese) matches."""
    test_data = pl.DataFrame({
        "asset": ["000001.SZ", "000002.SZ"],
        "name": ["平安银行", "万科A"],
        "pinyin": ["payh", "wanka"],
        "list_date": [None, None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="平安")
    import json
    body = json.loads(resp.body)
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "平安银行"


@pytest.mark.asyncio
async def test_search_stocks_finds_by_pinyin():
    test_data = pl.DataFrame({
        "asset": ["000001.SZ", "000002.SZ"],
        "name": ["平安银行", "万科A"],
        "pinyin": ["payh", "wanka"],
        "list_date": [None, None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="wanka")
    import json
    body = json.loads(resp.body)
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_search_stocks_respects_limit():
    test_data = pl.DataFrame({
        "asset": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"],
        "name": ["A", "A", "A", "A", "A"],
        "pinyin": ["a", "a", "a", "a", "a"],
        "list_date": [None, None, None, None, None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="a", limit=2)
    import json
    body = json.loads(resp.body)
    assert len(body["data"]) == 2


@pytest.mark.asyncio
async def test_search_stocks_includes_list_date_as_isoformat():
    """When list_date is a date, format as ISO string."""
    import datetime
    test_data = pl.DataFrame({
        "asset": ["000001.SZ"],
        "name": ["X"],
        "pinyin": ["x"],
        "list_date": [datetime.date(2020, 1, 1)],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="x")
    import json
    body = json.loads(resp.body)
    assert body["data"][0]["list_date"] == "2020-01-01"


@pytest.mark.asyncio
async def test_search_stocks_handles_null_list_date():
    test_data = pl.DataFrame({
        "asset": ["000001.SZ"],
        "name": ["X"],
        "pinyin": ["x"],
        "list_date": [None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="x")
    import json
    body = json.loads(resp.body)
    assert body["data"][0]["list_date"] is None


@pytest.mark.asyncio
async def test_search_stocks_case_insensitive():
    """Uppercase code query still matches lowercase data."""
    test_data = pl.DataFrame({
        "asset": ["abc.sz"],
        "name": ["X"],
        "pinyin": ["x"],
        "list_date": [None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="ABC")
    import json
    body = json.loads(resp.body)
    assert len(body["data"]) == 1


@pytest.mark.asyncio
async def test_search_stocks_no_match_returns_empty():
    test_data = pl.DataFrame({
        "asset": ["000001.SZ"],
        "name": ["X"],
        "pinyin": ["x"],
        "list_date": [None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="ZZZZ")
    import json
    body = json.loads(resp.body)
    assert body["data"] == []


@pytest.mark.asyncio
async def test_search_stocks_returns_all_result_fields():
    """Result dict has symbol/name/pinyin/list_date keys."""
    test_data = pl.DataFrame({
        "asset": ["000001.SZ"],
        "name": ["Test"],
        "pinyin": ["test"],
        "list_date": [None],
    })
    fake_sl = MagicMock()
    fake_sl.data = test_data
    with patch(
        "quantide.web.apis.analysis.search.get_stock_list",
        return_value=fake_sl,
    ):
        resp = await search_stocks(None, q="test")
    import json
    body = json.loads(resp.body)
    assert set(body["data"][0].keys()) == {
        "symbol", "name", "pinyin", "list_date"
    }
