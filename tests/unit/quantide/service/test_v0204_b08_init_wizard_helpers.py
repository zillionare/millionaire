"""B08 service/init_wizard — Tests for static helpers and pure functions."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_svc():
    """Build a real InitWizardService instance.

    InitWizardService.__init__ is trivial (sets _state=None, _initialized=True)
    and does not touch the DB, so we instantiate the real class and let
    private methods bind naturally through normal Python method resolution.
    This avoids the brittle `ClassName._method.__get__(stub)` descriptor
    pattern flagged by Prism Blocker B3.
    """
    from quantide.service.init_wizard import InitWizardService
    return InitWizardService()


@pytest.fixture
def svc():
    return _make_svc()


# ---------------------------------------------------------------------------
# _compose_gateway_url / _normalize_gateway_url
# ---------------------------------------------------------------------------


def test_compose_gateway_url_basic(svc):
    out = svc._compose_gateway_url("localhost", 8000, "/api")
    assert "localhost" in out
    assert "8000" in out


def test_compose_gateway_url_no_prefix(svc):
    out = svc._compose_gateway_url("localhost", 8000, "")
    assert "localhost" in out


def test_compose_gateway_url_slash_prefix(svc):
    out = svc._compose_gateway_url("localhost", 8000, "/")
    assert "localhost" in out


def test_compose_gateway_url_no_leading_slash(svc):
    out = svc._compose_gateway_url("localhost", 8000, "api")
    assert "/api" in out or "localhost" in out


def test_compose_gateway_url_with_trailing(svc):
    out = svc._compose_gateway_url("localhost", 8000, "/api/")
    assert "localhost" in out


def test_normalize_gateway_url_empty(svc):
    assert svc._normalize_gateway_url("") == ""


def test_normalize_gateway_url_slash(svc):
    assert svc._normalize_gateway_url("/") == ""


def test_normalize_gateway_url_relative(svc):
    assert svc._normalize_gateway_url("/foo") == ""


def test_normalize_gateway_url_full(svc):
    out = svc._normalize_gateway_url("http://localhost:8000/api/")
    assert "localhost" in out


def test_normalize_gateway_url_no_scheme(svc):
    """No scheme/netloc/path-dot returns empty."""
    out = svc._normalize_gateway_url("localhost:8000/api")
    assert out == ""


def test_normalize_gateway_url_with_path(svc):
    """Path without dot returns empty."""
    out = svc._normalize_gateway_url("example.com:8000/api")
    assert out == ""


# ---------------------------------------------------------------------------
# AppState defaults
# ---------------------------------------------------------------------------


def test_build_default_state(svc):
    state = svc._build_default_state()
    assert state is not None
    assert state.init_step == 0


def test_compute_history_start_date(svc):
    """With epoch in past, returns max(epoch, today-365*years)."""
    import datetime as dt
    import quantide.service.init_wizard as iw
    with patch.object(iw.datetime, "date", wraps=dt.date) as dmock:
        dmock.today = lambda: dt.date(2024, 6, 15)
        out = svc._compute_history_start_date(dt.date(2020, 1, 1), 3)
    assert out == dt.date(2021, 6, 16)


def test_compute_history_start_date_min_one_year(svc):
    """Even 0 years yields at least 1 year back."""
    import datetime as dt
    import quantide.service.init_wizard as iw
    with patch.object(iw.datetime, "date", wraps=dt.date) as dmock:
        dmock.today = lambda: dt.date(2024, 6, 15)
        out = svc._compute_history_start_date(dt.date(2025, 1, 1), 0)
    # 0 -> coerced to 1 (max(1, 0))
    # today - 365 days = 2023-06-16
    # max(2025-01-01, 2023-06-16) = 2025-01-01
    assert out == dt.date(2025, 1, 1)
