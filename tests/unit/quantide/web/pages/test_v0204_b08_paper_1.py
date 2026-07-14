"""B08-paper-1: Test paper.py small helpers + renderers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages import paper as paper_mod
from quantide.web.pages.paper import (
    _get_registry,
    _render_empty_paper,
    _render_no_registry,
    _render_paper_picker,
    _resolve_account_id,
    _resolve_default_paper_account,
)


# ---------------------------------------------------------------------------
# _get_registry
# ---------------------------------------------------------------------------


def test_get_registry_present():
    req = MagicMock()
    req.scope = {"registry": "reg-1"}
    assert _get_registry(req) == "reg-1"


def test_get_registry_missing():
    req = MagicMock()
    req.scope = {}
    assert _get_registry(req) is None


# ---------------------------------------------------------------------------
# _resolve_account_id
# ---------------------------------------------------------------------------


def test_resolve_account_id_present():
    req = MagicMock()
    req.query_params = {"account_id": "a1"}
    assert _resolve_account_id(req) == "a1"


def test_resolve_account_id_missing():
    req = MagicMock()
    req.query_params = {}
    assert _resolve_account_id(req) is None


# ---------------------------------------------------------------------------
# _resolve_default_paper_account
# ---------------------------------------------------------------------------


def test_resolve_default_paper_no_registry():
    req = MagicMock()
    req.scope = {}
    assert _resolve_default_paper_account(req) is None


def test_resolve_default_paper_no_sims():
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[])
    req = MagicMock()
    req.scope = {"registry": reg}
    assert _resolve_default_paper_account(req) is None


def test_resolve_default_paper_first_sim():
    reg = MagicMock()
    reg.list_by_kind = MagicMock(return_value=[{"id": "sim-1"}, {"id": "sim-2"}])
    req = MagicMock()
    req.scope = {"registry": reg}
    assert _resolve_default_paper_account(req) == "sim-1"


# ---------------------------------------------------------------------------
# _render_* (render functions)
# ---------------------------------------------------------------------------


def test_render_empty_paper():
    from quantide.web.layouts.main import MainLayout
    layout = MainLayout(title="x", user=None)
    out = _render_empty_paper(layout)
    assert out is not None


def test_render_no_registry():
    out = _render_no_registry({})
    assert out is not None


def test_render_no_registry_with_user():
    out = _render_no_registry({"auth": "alice"})
    assert out is not None


def test_render_paper_picker_empty():
    from quantide.web.layouts.main import MainLayout
    layout = MainLayout(title="x", user=None)
    out = _render_paper_picker(layout, [])
    assert out is not None


def test_render_paper_picker_with_sims():
    from quantide.web.layouts.main import MainLayout
    layout = MainLayout(title="x", user=None)
    sims = [{"id": "s1", "name": "S1"}, {"id": "s2", "name": "S2"}]
    out = _render_paper_picker(layout, sims)
    assert out is not None
