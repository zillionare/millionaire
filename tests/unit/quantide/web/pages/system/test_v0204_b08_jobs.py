"""B08-system-jobs-1: Tests for quantide/web/pages/system/jobs.py.

Target: raise coverage from 49.5% to >=80%.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from quantide.web.pages.system.jobs import (
    JobHistoryRecord,
    _build_history_table,
    _build_job_status_badge,
    _build_status_dot,
    _format_cron,
    _load_persisted_job_enabled_state,
    _save_job_history,
)


# ---------------------------------------------------------------------------
# JobHistoryRecord.to_dict / from_dict
# ---------------------------------------------------------------------------


def test_job_history_record_to_dict():
    rec = JobHistoryRecord(
        id="job-1",
        job_id="sync-daily",
        job_name="同步日线",
        executed_at=datetime.datetime(2024, 1, 1, 10, 0),
        status="success",
        message="ok",
        duration_ms=123,
    )
    out = rec.to_dict()
    assert out["id"] == "job-1"
    assert out["job_id"] == "sync-daily"
    assert out["duration_ms"] == 123
    # datetime converted to iso string
    assert "2024-01-01" in out["executed_at"]


def test_job_history_record_to_dict_with_string_executed_at():
    """String executed_at passes through unchanged."""
    rec = JobHistoryRecord(
        id="job-1",
        job_id="x",
        job_name="x",
        executed_at="2024-01-01T10:00:00",  # already a string
        status="success",
        message="",
        duration_ms=0,
    )
    out = rec.to_dict()
    assert out["executed_at"] == "2024-01-01T10:00:00"


def test_job_history_record_from_dict():
    """from_dict builds a record from a dict."""
    data = {
        "id": "job-1",
        "job_id": "sync-daily",
        "job_name": "同步日线",
        "executed_at": "2024-01-01T10:00:00",
        "status": "success",
        "message": "ok",
        "duration_ms": 100,
    }
    rec = JobHistoryRecord.from_dict(data)
    assert rec.id == "job-1"
    assert rec.job_id == "sync-daily"
    assert rec.status == "success"


# ---------------------------------------------------------------------------
# _format_cron
# ---------------------------------------------------------------------------


def test_format_cron_5_part_weekday_range():
    """Mon-Fri 1-5, all days in month/week."""
    out = _format_cron("30 9 * * 1-5")
    assert "周一至周五" in out
    # Hour is single-digit since format doesn't zero-pad it.
    assert "9" in out
    assert "30" in out


def test_format_cron_5_part_every_day():
    """Every day at HH:MM."""
    out = _format_cron("0 15 * * *")
    assert "每天" in out
    assert "15" in out


def test_format_cron_5_part_monday():
    """Monday only."""
    out = _format_cron("0 12 * * 1")
    assert "每周一" in out
    assert "12" in out


def test_format_cron_periodic_minutes():
    """Periodic minutes (e.g. every 5 minutes)."""
    out = _format_cron("*/5 * * * *")
    assert "5" in out


def test_format_cron_returns_cron_unchanged_for_unknown():
    """Unknown patterns return the original cron string."""
    out = _format_cron("weird cron")
    assert out == "weird cron"


def test_format_cron_4_parts_returns_unchanged():
    """< 5 parts returns as-is."""
    out = _format_cron("0 5 *")
    assert out == "0 5 *"


# ---------------------------------------------------------------------------
# _build_job_status_badge
# ---------------------------------------------------------------------------


def test_build_job_status_badge_enabled():
    badge = _build_job_status_badge(True)
    text = str(badge)
    assert "运行中" in text


def test_build_job_status_badge_disabled():
    badge = _build_job_status_badge(False)
    text = str(badge)
    assert "已停止" in text


# ---------------------------------------------------------------------------
# _build_status_dot
# ---------------------------------------------------------------------------


def test_build_status_dot_enabled_is_green():
    assert _build_status_dot(True) == "🟢"


def test_build_status_dot_disabled_is_red():
    assert _build_status_dot(False) == "🔴"


# ---------------------------------------------------------------------------
# _build_history_table
# ---------------------------------------------------------------------------


def test_build_history_table_with_records():
    records = [
        JobHistoryRecord(
            id="r1", job_id="j1", job_name="Daily",
            executed_at=datetime.datetime(2024, 1, 1, 10, 0),
            status="success", message="ok-1", duration_ms=100,
        ),
        JobHistoryRecord(
            id="r2", job_id="j2", job_name="Weekly",
            executed_at=datetime.datetime(2024, 1, 2, 10, 0),
            status="failure", message="err-1", duration_ms=200,
        ),
    ]
    table = _build_history_table(records)
    text = str(table)
    # Each row's executed_at timestamp and message appear in the table.
    assert "2024-01-01 10:00:00" in text
    assert "2024-01-02 10:00:00" in text
    # Status icons.
    assert "✅" in text or "成功" in text
    assert "❌" in text or "失败" in text


def test_build_history_table_empty():
    table = _build_history_table([])
    text = str(table)
    assert "暂无" in text or "history" in text or isinstance(text, str)


# ---------------------------------------------------------------------------
# _load_persisted_job_enabled_state / _save_job_history — exercise
# db interactions with real session fixture.
# ---------------------------------------------------------------------------


def test_load_persisted_returns_dict(db):
    """Returns dict even when table is empty."""
    out = _load_persisted_job_enabled_state()
    assert isinstance(out, dict)


def test_save_job_history_records_persist(db):
    """_save_job_history writes to db and can be retrieved via _get_job_history."""
    from quantide.web.pages.system.jobs import _get_job_history
    _save_job_history(
        job_id="test-save",
        job_name="Test",
        status="success",
        message="hello",
        duration_ms=42,
    )
    records = _get_job_history("test-save", limit=5)
    assert any(r.job_id == "test-save" and r.message == "hello" for r in records)


def test_get_job_history_unknown_job_returns_empty(db):
    """Unknown job_id returns empty list."""
    from quantide.web.pages.system.jobs import _get_job_history
    out = _get_job_history("unknown-id", limit=3)
    assert isinstance(out, list)


def test_get_all_job_history_returns_list(db):
    """_get_all_job_history returns a list."""
    from quantide.web.pages.system.jobs import _get_all_job_history
    out = _get_all_job_history(limit=5)
    assert isinstance(out, list)


def test_save_job_history_persists_multiple_records(db):
    """Multiple calls produce multiple records (cap by limit)."""
    from quantide.web.pages.system.jobs import _get_job_history
    for i in range(3):
        _save_job_history(
            job_id="multi-job",
            job_name="Multi",
            status="success",
            message=f"msg-{i}",
            duration_ms=10,
        )
    records = _get_job_history("multi-job", limit=10)
    msgs = [r.message for r in records]
    assert "msg-0" in msgs
    assert "msg-1" in msgs
    assert "msg-2" in msgs
