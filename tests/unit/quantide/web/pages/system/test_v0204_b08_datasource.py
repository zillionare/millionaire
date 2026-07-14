"""B08-datasource: Test datasource.py build_* helpers + loaders."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quantide.web.pages.system import datasource as ds_mod
from quantide.web.pages.system.datasource import (
    _build_config_card,
    _build_data_status_card,
    _build_flash,
    _build_status_badge,
    _build_sync_history_card,
    _get_data_status,
    _get_sync_history,
    _load_datasource_config,
)


# ---------------------------------------------------------------------------
# _build_status_badge
# ---------------------------------------------------------------------------


def test_build_status_badge_ok():
    out = _build_status_badge("ok")
    assert out is not None


def test_build_status_badge_partial():
    out = _build_status_badge("partial")
    assert out is not None


def test_build_status_badge_missing():
    out = _build_status_badge("missing")
    assert out is not None


def test_build_status_badge_unknown():
    out = _build_status_badge("garbage")
    assert out is not None


# ---------------------------------------------------------------------------
# _build_flash
# ---------------------------------------------------------------------------


def test_build_flash_success():
    out = _build_flash("All good", "success")
    assert out is not None


def test_build_flash_error():
    out = _build_flash("Boom", "error")
    assert out is not None


def test_build_flash_info():
    out = _build_flash("Note", "info")
    assert out is not None


# ---------------------------------------------------------------------------
# _build_data_status_card
# ---------------------------------------------------------------------------


def test_build_data_status_card_empty():
    out = _build_data_status_card({})
    assert out is not None


def test_build_data_status_card_full():
    out = _build_data_status_card({
        "daily_bars": {"status": "ok", "message": "ok", "count": 100},
        "stock_list": {"status": "ok", "message": "ok", "count": 5000},
        "calendar": {"status": "ok", "message": "ok", "count": 0},
    })
    assert out is not None


# ---------------------------------------------------------------------------
# _build_sync_history_card
# ---------------------------------------------------------------------------


def test_build_sync_history_card_empty():
    out = _build_sync_history_card([])
    assert out is not None


def test_build_sync_history_card_with_records():
    out = _build_sync_history_card([
        {"job_id": "x", "executed_at": "2024-01-01", "status": "success", "message": "ok"},
    ])
    assert out is not None


# ---------------------------------------------------------------------------
# _build_config_card
# ---------------------------------------------------------------------------


def test_build_config_card_full():
    out = _build_config_card({
        "data_source": "tushare",
        "tushare_token": "abc",
        "epoch": 5,
        "history_years": 3,
    })
    assert out is not None


def test_build_config_card_missing_keys():
    out = _build_config_card({})
    assert out is not None
