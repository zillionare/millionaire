"""B08-data-market: Test data_market.py helpers + tabs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages.data_market import (
    _TabNav,
    _get_active_tab,
)


def test_get_active_tab_default():
    """Default tab is 'overview' when no tab in query_params."""
    req = MagicMock()
    req.query_params = {}
    assert _get_active_tab(req) == "overview"


def test_get_active_tab_explicit():
    req = MagicMock()
    req.query_params = {"tab": "verify"}
    assert _get_active_tab(req) == "verify"


def test_get_active_tab_browse():
    req = MagicMock()
    req.query_params = {"tab": "browse"}
    assert _get_active_tab(req) == "browse"


def test_get_active_tab_update():
    req = MagicMock()
    req.query_params = {"tab": "update"}
    assert _get_active_tab(req) == "update"


def test_tab_nav_overview():
    out = _TabNav("overview")
    assert out is not None


def test_tab_nav_verify():
    out = _TabNav("verify")
    assert out is not None


def test_tab_nav_update():
    out = _TabNav("update")
    assert out is not None


def test_tab_nav_browse():
    out = _TabNav("browse")
    assert out is not None


def test_tab_nav_unknown():
    """Unknown tab still renders."""
    out = _TabNav("garbage")
    assert out is not None
