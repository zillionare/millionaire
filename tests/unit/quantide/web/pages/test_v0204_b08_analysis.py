"""B08-pages-analysis-1: Tests for quantide/web/pages/analysis.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages.analysis import analysis_handler, analysis_page


def _request_with_session(session_data: dict | None = None) -> MagicMock:
    req = MagicMock()
    req.scope = {"session": session_data or {}}
    return req


def test_analysis_page_no_session():
    """Without auth session, page renders without raising."""
    req = _request_with_session()
    resp = analysis_page(req)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "板块与指数分析已下线" in body


def test_analysis_page_with_auth_session():
    req = _request_with_session({"auth": "admin"})
    resp = analysis_page(req)
    assert resp.status_code == 200


def test_analysis_page_contains_navigation():
    req = _request_with_session()
    resp = analysis_page(req)
    body = resp.body.decode("utf-8")
    # Header navigation links should be present.
    assert "首页" in body
    assert "交易" in body
    assert "分析" in body


def test_analysis_page_contains_retirement_message():
    req = _request_with_session()
    resp = analysis_page(req)
    body = resp.body.decode("utf-8")
    assert "下线" in body


def test_analysis_page_contains_theme_headers():
    req = _request_with_session()
    resp = analysis_page(req)
    body = resp.body.decode("utf-8")
    # HTML/XML header tags present
    assert "<!DOCTYPE" in body or "<html" in body or "<title" in body.lower()


@pytest.mark.asyncio
async def test_analysis_handler_returns_page():
    """Async handler proxies to analysis_page."""
    req = _request_with_session()
    resp = await analysis_handler(req)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "板块与指数分析已下线" in body
