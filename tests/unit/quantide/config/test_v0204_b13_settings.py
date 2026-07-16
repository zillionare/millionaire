"""B13 batch: cover missing branches in quantide.config.settings.

Targets specific missing lines reported by /tmp/gg.json:
  - _as_date string parse success/failure (lines 32-37)
  - _as_int fallback (lines 43-44)
  - parse_cheat_on_close_time non-string rejection (line 53)
  - _normalize_path_prefix default + prepend slash (lines 84, 86)
  - _load_app_state missing row (line 119)
  - _build_gateway_base_url full URL + server-with-scheme (lines 127, 138)
  - _apply_dev_stub_overrides no-op when runtime None (line 154)
  - get_cheat_on_close_time ValueError fallback (lines 290-291)
  - get_tushare_token dev stub path (line 311)
  - _normalize_receivers list input (line 336)
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

import quantide.config.settings as settings_module
from quantide.config.settings import (
    DEV_STUB_TUSHARE_TOKEN,
    _as_date,
    _as_int,
    _build_gateway_base_url,
    _normalize_path_prefix,
    _normalize_receivers,
    get_cheat_on_close_time,
    get_mail_receivers,
    get_tushare_token,
    parse_cheat_on_close_time,
)
from quantide.data.models.app_state import AppState


class _NoneTable:
    """Table-like object whose .get() always returns None."""

    def get(self, _pk):
        return None


class _FakeDb:
    """Minimal db stub exposing _initialized and __getitem__."""

    def __init__(self, table):
        self._initialized = True
        self._table = table

    def __getitem__(self, name):
        assert name == "app_state"
        return self._table


# --- _as_date ---------------------------------------------------------------


def test_as_date_parses_valid_iso_string():
    """Line 32-34: ISO string parsed into date."""
    default = datetime.date(2005, 1, 1)
    assert _as_date("2020-03-15", default) == datetime.date(2020, 3, 15)


def test_as_date_falls_back_on_invalid_string():
    """Line 35-36: malformed string falls back to default."""
    default = datetime.date(2010, 6, 1)
    assert _as_date("not-a-date", default) == default


def test_as_date_falls_back_on_unsupported_type():
    """Line 37: int (not date/str) falls back to default."""
    default = datetime.date(2010, 6, 1)
    assert _as_date(12345, default) == default


# --- _as_int ----------------------------------------------------------------


def test_as_int_falls_back_on_non_numeric_string():
    """Line 43-44: ValueError -> default."""
    assert _as_int("abc", 42) == 42


def test_as_int_falls_back_on_none():
    """Line 43-44: TypeError -> default."""
    assert _as_int(None, 7) == 7


# --- parse_cheat_on_close_time ----------------------------------------------


def test_parse_cheat_on_close_time_rejects_non_string():
    """Line 53: non-string input raises ValueError mentioning type."""
    with pytest.raises(ValueError, match="must be string"):
        parse_cheat_on_close_time(123)


# --- _normalize_path_prefix -------------------------------------------------


def test_normalize_path_prefix_returns_default_for_empty():
    """Line 84: empty/whitespace value -> default."""
    assert _normalize_path_prefix("") == "/"
    assert _normalize_path_prefix("   ") == "/"
    assert _normalize_path_prefix(None, default="/") == "/"


def test_normalize_path_prefix_prepends_leading_slash():
    """Line 86: value without leading slash gets one prepended."""
    assert _normalize_path_prefix("qmt") == "/qmt"


# --- _load_app_state --------------------------------------------------------


def test_load_app_state_returns_none_when_row_missing(monkeypatch):
    """Line 119: when db.get returns None -> _load_app_state returns None."""
    monkeypatch.setattr(settings_module, "_LAST_APP_STATE_LOAD_ERROR", None)
    monkeypatch.setattr("quantide.data.sqlite.db", _FakeDb(_NoneTable()))
    assert settings_module._load_app_state() is None


# --- _build_gateway_base_url ------------------------------------------------


def test_build_gateway_base_url_uses_configured_full_url():
    """Line 127: when configured has scheme+netloc, returns rstripped configured."""
    state = SimpleNamespace(
        gateway_base_url="http://gw.example.com/qmt/",
        gateway_server="ignored",
        gateway_scheme="http",
        gateway_port=9999,
    )
    assert settings_module._build_gateway_base_url(state) == "http://gw.example.com/qmt"


def test_build_gateway_base_url_when_server_already_has_scheme():
    """Line 138: server starts with http(s):// -> base = server.rstrip('/')."""
    state = SimpleNamespace(
        gateway_base_url="/qmt",
        gateway_server="http://gw.example.com/",
        gateway_scheme="http",
        gateway_port=8080,
    )
    assert settings_module._build_gateway_base_url(state) == "http://gw.example.com/qmt"


# --- _apply_dev_stub_overrides ----------------------------------------------


def test_apply_dev_stub_overrides_returns_settings_unchanged_when_runtime_none(monkeypatch):
    """Line 154: ensure_dev_stubs_started returns None -> settings returned as-is."""
    monkeypatch.setattr(settings_module, "ensure_dev_stubs_started", lambda: None)
    sentinel = object()
    assert settings_module._apply_dev_stub_overrides(sentinel) is sentinel


# --- get_cheat_on_close_time ------------------------------------------------


def test_get_cheat_on_close_time_falls_back_when_settings_value_invalid(monkeypatch):
    """Lines 290-291: parse raises ValueError -> fallback to '14:57'."""
    bad_settings = SimpleNamespace(cheat_on_close_time="99:99")
    monkeypatch.setattr(settings_module, "get_settings", lambda: bad_settings)
    assert get_cheat_on_close_time() == "14:57"


# --- get_tushare_token ------------------------------------------------------


def test_get_tushare_token_returns_dev_stub_token_when_enabled(monkeypatch):
    """Line 311: dev_stubs_enabled() -> return DEV_STUB_TUSHARE_TOKEN."""
    monkeypatch.setattr(settings_module, "dev_stubs_enabled", lambda: True)
    assert get_tushare_token() == DEV_STUB_TUSHARE_TOKEN


# --- _normalize_receivers ---------------------------------------------------


def test_normalize_receivers_strips_and_filters_list_items():
    """Line 336: list input -> stripped non-empty items."""
    result = _normalize_receivers(["a@x.com", "  b@x.com  ", "", "   "])
    assert result == ["a@x.com", "b@x.com"]


def test_get_mail_receivers_reads_list_from_state_object(monkeypatch):
    """Line 336 via get_mail_receivers: list-valued state object passes through.

    AppState serializes lists to JSON strings on SQLite round-trip, so we
    inject an in-memory state object that retains the list type to exercise
    the list branch of _normalize_receivers end-to-end.
    """
    state = SimpleNamespace(notify_mail_to=["a@x.com", " b@x.com ", ""])
    monkeypatch.setattr(settings_module, "_state_or_default", lambda: state)
    assert get_mail_receivers() == ["a@x.com", "b@x.com"]
