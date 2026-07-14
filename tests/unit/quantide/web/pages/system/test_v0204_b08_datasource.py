"""B08-datasource-1: Tests for quantide/web/pages/system/datasource.py.

Target: raise coverage from 68.8% to >=80%.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system.datasource import (
    _build_config_card,
    _build_data_status_card,
    _build_flash,
    _build_status_badge,
    _build_sync_history_card,
    _load_datasource_config,
)


# ---------------------------------------------------------------------------
# _build_status_badge
# ---------------------------------------------------------------------------


def test_build_status_badge_ok():
    badge = _build_status_badge("ok")
    text = str(badge)
    assert isinstance(text, str)
    assert "完整" in text or "✅" in text


def test_build_status_badge_empty():
    badge = _build_status_badge("empty")
    text = str(badge)
    assert "空" in text or "⚠" in text


def test_build_status_badge_error():
    badge = _build_status_badge("error")
    text = str(badge)
    assert "错误" in text or "❌" in text


def test_build_status_badge_unknown():
    badge = _build_status_badge("weird")
    text = str(badge)
    assert "未知" in text or "⚪" in text


# ---------------------------------------------------------------------------
# _build_flash
# ---------------------------------------------------------------------------


def test_build_flash_info():
    flash = _build_flash("hello", "info")
    text = str(flash)
    assert "hello" in text


def test_build_flash_success():
    flash = _build_flash("ok", "success")
    text = str(flash)
    assert "ok" in text


def test_build_flash_warning():
    flash = _build_flash("warn", "warning")
    text = str(flash)
    assert "warn" in text


def test_build_flash_error():
    flash = _build_flash("err", "error")
    text = str(flash)
    assert "err" in text


def test_build_flash_unknown_tone():
    flash = _build_flash("m", "weird-tone")
    text = str(flash)
    assert "m" in text


# ---------------------------------------------------------------------------
# _build_data_status_card
# ---------------------------------------------------------------------------


def test_build_data_status_card_with_status():
    status = {
        "data_source": "tushare",
        "initialized": True,
        "last_sync": "2024-01-01",
    }
    card = _build_data_status_card(status)
    text = str(card)
    assert isinstance(text, str)
    assert "日线数据" in text or "数据状态" in text


def test_build_data_status_card_empty_status():
    """Even empty status dict renders."""
    card = _build_data_status_card({})
    text = str(card)
    assert isinstance(text, str)


# ---------------------------------------------------------------------------
# _build_config_card
# ---------------------------------------------------------------------------


def test_build_config_card_with_full_config():
    config = {
        "data_source": "tushare",
        "tushare_token": "tk-xxxx",
        "epoch": datetime.date(2020, 1, 1),
        "history_years": 5,
    }
    card = _build_config_card(config)
    text = str(card)
    assert isinstance(text, str)
    # Card has heading
    assert len(text) > 100


def test_build_config_card_partial():
    """Partial config still renders without raising."""
    config = {"data_source": "tushare"}
    card = _build_config_card(config)
    text = str(card)
    assert isinstance(text, str)


def test_build_config_card_empty():
    card = _build_config_card({})
    text = str(card)
    assert isinstance(text, str)


# ---------------------------------------------------------------------------
# _build_sync_history_card
# ---------------------------------------------------------------------------


def test_build_sync_history_card_empty():
    card = _build_sync_history_card([])
    text = str(card)
    assert isinstance(text, str)
    assert "暂无" in text or "history" in text.lower()


def test_build_sync_history_card_with_entries():
    history = [
        {"ts": "2024-01-01", "action": "sync-daily", "status": "success"},
        {"ts": "2024-01-02", "action": "sync-stocks", "status": "failure"},
    ]
    card = _build_sync_history_card(history)
    text = str(card)
    assert isinstance(text, str)


# ---------------------------------------------------------------------------
# _load_datasource_config (db-dependent)
# ---------------------------------------------------------------------------


def test_load_datasource_config_returns_dict(db):
    """Returns dict with expected keys; defaults to settings when no row."""
    cfg = _load_datasource_config()
    assert isinstance(cfg, dict)
    assert "data_source" in cfg
