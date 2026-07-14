"""B08-data-market-page-1: Tests for quantide/web/pages/data_market.py.

Target: raise coverage from 52.9% to >=80%.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.data_market import _BrowseTab, _OverviewTab, _VerifyTab, _UpdateTab, _get_active_tab


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


def test_get_active_tab_verify():
    req = _request({"tab": "verify"})
    assert _get_active_tab(req) == "verify"


def test_get_active_tab_update():
    req = _request({"tab": "update"})
    assert _get_active_tab(req) == "update"


def test_get_active_tab_browse():
    req = _request({"tab": "browse"})
    assert _get_active_tab(req) == "browse"


def test_get_active_tab_passes_through_unknown():
    req = _request({"tab": "bogus"})
    assert _get_active_tab(req) == "bogus"


# ---------------------------------------------------------------------------
# Tab renderers (must not raise)
# ---------------------------------------------------------------------------


def test_overview_tab_renders():
    out = _OverviewTab()
    assert out is not None
    text = str(out)
    assert isinstance(text, str)


def test_verify_tab_renders():
    out = _VerifyTab()
    assert out is not None
    text = str(out)
    assert isinstance(text, str)


def test_update_tab_renders():
    out = _UpdateTab()
    assert out is not None
    text = str(out)
    assert isinstance(text, str)


def test_browse_tab_renders():
    req = _request()
    with patch("quantide.web.pages.data_market.daily_bars") as mock_db:
        # Empty data scenario
        class _DF:
            def sort(self, *args, **kwargs):
                return self

            def is_empty(self_inner):
                return True

            def __len__(self_inner):
                return 0

        mock_db.get_bars.return_value = _DF()
        out = _BrowseTab(req)
    assert out is not None


def test_browse_tab_with_data():
    """BrowseTab with rows renders."""
    req = _request()
    with patch("quantide.web.pages.data_market.daily_bars") as mock_db:
        # Return a small DataFrame-like object
        class _DF:
            def sort(self, *args, **kwargs):
                return self

            def is_empty(self_inner):
                return False

            def __len__(self_inner):
                return 1

            def head(self, n):
                return self

            def to_pandas(self_inner):
                return MagicMock(
                    to_dict=lambda *a, **kw: [
                        {"date": "2024-01-01", "open": 10.0, "high": 10.5,
                         "low": 9.5, "close": 10.2, "volume": 100}
                    ]
                )
            def iter_rows(self_inner, named=True):
                yield {"date": "2024-01-01", "open": 10.0, "high": 10.5,
                       "low": 9.5, "close": 10.2, "volume": 100}

        mock_db.get_bars.return_value = _DF()
        out = _BrowseTab(req)
    assert out is not None


@pytest.mark.asyncio
async def test_index_overview():
    """index(req) for overview tab."""
    from quantide.web.pages.data_market import index as mkt_index
    req = _request()
    resp = await mkt_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_verify():
    from quantide.web.pages.data_market import index as mkt_index
    req = _request({"tab": "verify"})
    resp = await mkt_index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_update():
    from quantide.web.pages.data_market import index as mkt_index
    req = _request({"tab": "update"})
    resp = await mkt_index(req)


@pytest.mark.asyncio
async def test_index_browse():
    from quantide.web.pages.data_market import index as mkt_index
    req = _request({"tab": "browse"})
    resp = await mkt_index(req)
    assert resp is not None
