"""B09-trade-lightning-lines: targeted tests for uncovered lines in trade_lightning.py.

The fresh coverage report (generated after B09 routes/helpers tests landed)
shows only 9 missing lines in ``quantide/web/pages/trade_lightning.py``:

* Line 899  - ``trade_lightning_edit_modal`` entry-None branch
* Lines 1091-1092 - ``_resolve_lightning_price`` current_premium when current<=0
* Lines 1101-1102 - ``_resolve_lightning_price`` current branch float() raises
* Lines 1118-1119 - ``_resolve_lightning_price`` close branch float() raises
* Lines 1131-1132 - ``_resolve_lightning_price`` ma branch get_bars raises
* Line 1137     - ``_resolve_lightning_price`` ma branch len(closes)<period

Each test below constructs a request/state that drives the corresponding
missing line and asserts a substantive outcome.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest
from starlette.responses import HTMLResponse
from unittest.mock import AsyncMock, MagicMock, patch

from quantide.web.pages import trade_lightning as tl_mod
from quantide.web.pages.trade_lightning import (
    _resolve_lightning_price,
    trade_lightning_edit_modal,
)


def _make_req(
    *,
    path_params: dict | None = None,
    scope: dict | None = None,
    query_params: dict | None = None,
) -> MagicMock:
    """Build a fake Starlette request for lightning modal handlers."""
    req = MagicMock()
    req.path_params = path_params or {}
    req.scope = scope or {}
    req.query_params = query_params or {}
    req.form = AsyncMock(return_value={})
    return req


# ---------------------------------------------------------------------------
# Line 899: trade_lightning_edit_modal - entry is None branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_modal_entry_missing_returns_toast():
    """[AC-NFR1101-01] When entry is None, edit_modal returns the not-found toast.

    Covers line 899 (the ``entry is None`` return inside trade_lightning_edit_modal).
    The sibling delete_modal branch is already covered; this completes the modal
    pair.
    """
    req = _make_req(path_params={"portfolio_id": "p1", "asset": "000001.SZ"})
    with patch.object(tl_mod, "get_trade_lightning_entry", return_value=None):
        resp = await trade_lightning_edit_modal(req)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode()
    # Both the cleared modal container and the OOB toast should be present.
    assert "trade-lightning-modal-container" in body
    assert "该闪电单条目不存在" in body


# ---------------------------------------------------------------------------
# Lines 1091-1092: _resolve_lightning_price - current_premium when current <= 0
# ---------------------------------------------------------------------------


def test_resolve_lightning_price_current_premium_zero_current_returns_zero():
    """[AC-NFR1101-01] current_p1 with current<=0 returns 0.0 (no premium applied).

    Covers lines 1091-1092: when the recursive ``current`` price resolves to a
    non-positive value, the premium branch must short-circuit to 0.0 rather
    than multiply a non-positive base.
    """
    with patch.object(tl_mod, "live_quote") as mock_lq, \
         patch.object(tl_mod, "daily_bars") as mock_dbars:
        # live_quote returns a quote with price=0 -> current falls through to
        # close, and close's bars are empty -> current == 0 -> premium returns 0.
        mock_lq.is_running = True
        mock_lq.get_quote = MagicMock(return_value={"price": 0.0})
        mock_dbars.get_bars = MagicMock(return_value=pl.DataFrame())
        got = _resolve_lightning_price("000001.SZ", "current_p1")
    assert got == 0.0


# ---------------------------------------------------------------------------
# Lines 1101-1102: _resolve_lightning_price - current branch float() raises
# ---------------------------------------------------------------------------


def test_resolve_lightning_price_current_quote_bad_float_falls_back():
    """[AC-NFR1101-01] current branch: a non-numeric quote value is treated as 0.

    Covers lines 1101-1102 (``except (TypeError, ValueError): value = 0.0``).
    The quote dict has ``price``/``lastPrice`` set to non-numeric junk and
    ``close`` missing; each key fails ``float()`` and falls back, eventually
    delegating to the ``close`` path which returns a real bar's close.
    """
    fake_bars = pl.DataFrame({
        "date": [datetime.date(2024, 6, 1)],
        "close": [42.5],
    })
    with patch.object(tl_mod, "live_quote") as mock_lq, \
         patch.object(tl_mod, "daily_bars") as mock_dbars:
        mock_lq.is_running = True
        # Non-numeric values trigger the TypeError/ValueError branch.
        mock_lq.get_quote = MagicMock(
            return_value={"price": "N/A", "lastPrice": None, "close": object()}
        )
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "current")
    # All three quote keys fail float(); fallback to close path -> 42.5.
    assert got == 42.5


# ---------------------------------------------------------------------------
# Lines 1118-1119: _resolve_lightning_price - close branch float() raises
# ---------------------------------------------------------------------------


def test_resolve_lightning_price_close_row_access_raises_returns_zero():
    """[AC-NFR1101-01] close branch: when row()/get() raises, returns 0.0.

    Covers lines 1118-1119 (``except Exception: return 0.0`` around the
    close extraction). We make ``bars.sort(...).row(...)`` raise so the
    broad except path is taken instead of returning the parsed close.
    """
    fake_bars = MagicMock()
    # is_empty() is False (so we proceed past the empty check), but row()
    # raises to exercise the except branch.
    fake_bars.is_empty.return_value = False
    fake_bars.sort.return_value.row.side_effect = RuntimeError("row boom")
    with patch.object(tl_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "close")
    assert got == 0.0


# ---------------------------------------------------------------------------
# Lines 1131-1132: _resolve_lightning_price - ma branch get_bars raises
# ---------------------------------------------------------------------------


def test_resolve_lightning_price_ma_get_bars_raises_returns_zero():
    """[AC-NFR1101-01] ma5 branch: when daily_bars.get_bars raises, returns 0.0.

    Covers lines 1131-1132 (``except Exception: return 0.0`` around the ma
    get_bars call). Distinct from the close-branch exception because the ma
    path has its own try/except after the period parse.
    """
    with patch.object(tl_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(side_effect=RuntimeError("ma boom"))
        got = _resolve_lightning_price("000001.SZ", "ma5")
    assert got == 0.0


# ---------------------------------------------------------------------------
# Line 1137: _resolve_lightning_price - ma branch len(closes) < period
# ---------------------------------------------------------------------------


def test_resolve_lightning_price_ma_closes_fewer_than_period_returns_zero():
    """[AC-NFR1101-01] ma5 branch: bars len>=period but closes list < period -> 0.

    Covers line 1137 (``if len(closes) < period: return 0.0``). The earlier
    ``len(bars) < period`` guard (line 1133) checks row count, but the
    ``closes`` list comprehension can produce fewer entries if the column
    contains non-numeric junk that ``float()`` would reject. We simulate that
    by making ``get_column(...).to_list()`` return a short list while the
    frame's own length passes the first guard.
    """
    fake_bars = MagicMock()
    # len(fake_bars) >= period so the line 1133 guard passes...
    fake_bars.__len__ = MagicMock(return_value=5)
    fake_bars.is_empty.return_value = False
    # ...but the extracted closes list is shorter than period.
    short_closes_col = MagicMock()
    short_closes_col.to_list.return_value = [100.0, 110.0]  # only 2 < 5
    fake_bars.sort.return_value.get_column.return_value = short_closes_col
    with patch.object(tl_mod, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "ma5")
    assert got == 0.0
