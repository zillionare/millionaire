"""B08-history-pages-1: Tests for quantide/web/pages/history_* pages.

Target: push coverage of history_orders / history_positions / history_trades
from 14-15% to >=80%.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from quantide.web.pages.history_orders import _get_active_account, history_orders_list
from quantide.web.pages.history_positions import history_positions_list
from quantide.web.pages.history_trades import history_trades_list


def _request_with_session(session_data: dict | None = None,
                         query: dict | None = None):
    """Build a minimal request with session and query params."""
    req = MagicMock()
    req.scope = {"session": session_data or {}}
    req.query_params = query or {}
    return req


# ---------------------------------------------------------------------------
# _get_active_account helper (history_orders)
# ---------------------------------------------------------------------------


def test_get_active_account_none_when_no_session():
    req = _request_with_session()
    assert _get_active_account(req) is None


def test_get_active_account_returns_kind_and_id_when_present():
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    result = _get_active_account(req)
    assert result == ("sim", "p1")


def test_get_active_account_returns_none_when_only_kind():
    req = _request_with_session({"active_account_kind": "sim"})
    assert _get_active_account(req) is None


def test_get_active_account_returns_none_when_only_id():
    req = _request_with_session({"active_account_id": "p1"})
    assert _get_active_account(req) is None


# ---------------------------------------------------------------------------
# history_orders_list
# ---------------------------------------------------------------------------


def test_history_orders_list_no_active_account_returns_no_account_html():
    req = _request_with_session()
    resp = history_orders_list(req)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
    assert "请先选择活动账户" in body


def test_history_orders_list_with_active_account_no_orders():
    """Active account but no orders → empty table."""
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_orders.db") as mock_db:
        mock_db.get_orders.return_value = pl.DataFrame()
        resp = history_orders_list(req)
    assert resp.status_code == 200


def test_history_orders_list_with_orders():
    """Active account + orders returns rendering."""
    import datetime
    df = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "name": ["Test"],
        "side": ["BUY"],
        "price": [10.0],
        "shares": [100.0],
        "filled": [100.0],
        "status": ["已成"],
    })
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
        query={"start_date": "2024-01-01", "end_date": "2024-01-31"},
    )
    with patch("quantide.web.pages.history_orders.db") as mock_db:
        mock_db.get_orders.return_value = df
        resp = history_orders_list(req)
    assert resp.status_code == 200


def test_history_orders_list_default_date_range():
    """When no dates passed, defaults to last 30 days."""
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_orders.db") as mock_db:
        mock_db.get_orders.return_value = pl.DataFrame()
        resp = history_orders_list(req)
    assert mock_db.get_orders.called


def test_history_orders_list_handles_db_exception():
    """When db raises, exception is caught (no error propagates)."""
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_orders.db") as mock_db:
        mock_db.get_orders.side_effect = Exception("boom")
        # Should not raise.
        resp = history_orders_list(req)
    assert resp.status_code == 200


def test_history_orders_list_sell_side_renders_correctly():
    """A SELL-side order row renders '卖出' label."""
    import datetime
    df = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "name": ["Test"],
        "side": ["SELL"],
        "price": [10.0],
        "shares": [100.0],
        "filled": [100.0],
        "status": ["已成"],
    })
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_orders.db") as mock_db:
        mock_db.get_orders.return_value = df
        resp = history_orders_list(req)
    body = resp.body.decode("utf-8")
    assert "卖出" in body


# ---------------------------------------------------------------------------
# history_positions_list
# ---------------------------------------------------------------------------


def test_history_positions_list_no_active_account():
    req = _request_with_session()
    resp = history_positions_list(req)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
    assert "请先选择活动账户" in body


def test_history_positions_list_with_active_account():
    """Active account + positions renders."""
    df = pl.DataFrame({
        "asset": ["000001.SZ"],
        "name": ["Test"],
        "shares": [100.0],
        "avail": [100.0],
        "price": [10.0],
        "cost": [9.5],
        "profit": [50.0],
    })
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_positions.db") as mock_db:
        mock_db.query_positions.return_value = df
        resp = history_positions_list(req)
    assert resp.status_code == 200


def test_history_positions_list_with_date_range():
    df = pl.DataFrame()
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
        query={"start_date": "2024-01-01", "end_date": "2024-01-31"},
    )
    with patch("quantide.web.pages.history_positions.db") as mock_db:
        mock_db.query_positions.return_value = df
        resp = history_positions_list(req)
    assert mock_db.query_positions.called


def test_history_positions_list_handles_db_exception():
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_positions.db") as mock_db:
        mock_db.query_positions.side_effect = Exception("boom")
        resp = history_positions_list(req)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# history_trades_list
# ---------------------------------------------------------------------------


def test_history_trades_list_no_active_account():
    req = _request_with_session()
    resp = history_trades_list(req)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
    assert "请先选择活动账户" in body


def test_history_trades_list_with_active_account():
    import datetime
    df = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "name": ["Test"],
        "side": ["BUY"],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
    })
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_trades.db") as mock_db:
        mock_db.get_trades.return_value = df
        resp = history_trades_list(req)
    assert resp.status_code == 200


def test_history_trades_list_default_date_range():
    df = pl.DataFrame()
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_trades.db") as mock_db:
        mock_db.get_trades.return_value = df
        resp = history_trades_list(req)
    assert mock_db.get_trades.called


def test_history_trades_list_handles_db_exception():
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_trades.db") as mock_db:
        mock_db.get_trades.side_effect = Exception("boom")
        resp = history_trades_list(req)
    assert resp.status_code == 200


def test_history_trades_list_sell_side():
    import datetime
    df = pl.DataFrame({
        "tm": [datetime.datetime(2024, 1, 1, 10, 0)],
        "asset": ["000001.SZ"],
        "name": ["Test"],
        "side": ["SELL"],
        "price": [10.0],
        "shares": [100.0],
        "amount": [1000.0],
    })
    req = _request_with_session(
        {"active_account_kind": "sim", "active_account_id": "p1"},
    )
    with patch("quantide.web.pages.history_trades.db") as mock_db:
        mock_db.get_trades.return_value = df
        resp = history_trades_list(req)
    body = resp.body.decode("utf-8")
    assert "卖出" in body
