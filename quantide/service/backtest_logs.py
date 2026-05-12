"""回测文本日志服务。"""

from __future__ import annotations

import datetime
import json
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from quantide.config.paths import get_backtest_log_path
from quantide.data.sqlite import BacktestLogEntry, db

_FILE_FAILURE_WARNED: set[str] = set()


def _coerce_datetime(
    value: datetime.date | datetime.datetime | None,
) -> datetime.datetime:
    """规范化日志时间。"""
    if value is None:
        return datetime.datetime.now()
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.combine(value, datetime.time())


def _serialize_extra(extra: dict[str, Any] | None) -> str:
    """将额外字段序列化为 JSON 字符串。"""
    if not extra:
        return ""
    return json.dumps(extra, ensure_ascii=False, sort_keys=True)


def _format_extra_text(extra: Any) -> str:
    """将额外字段格式化为可展示文本。"""
    if extra in (None, "", {}):
        return ""
    if isinstance(extra, str):
        return extra
    return json.dumps(extra, ensure_ascii=False, sort_keys=True)


def _entry_to_row(entry: BacktestLogEntry) -> dict[str, str]:
    """将日志实体转换为页面可用结构。"""
    return {
        "dt": entry.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "level": str(entry.level or "INFO").upper(),
        "source": str(entry.source or "system"),
        "message": str(entry.message or ""),
        "extra": str(entry.extra or ""),
    }


def _append_entry_to_file(entry: BacktestLogEntry, path: Path) -> None:
    """将回测日志逐行追加到 JSONL 文件。"""
    payload = {
        "event_id": entry.event_id,
        "portfolio_id": entry.portfolio_id,
        "dt": entry.dt.isoformat(),
        "level": entry.level,
        "source": entry.source,
        "message": entry.message,
        "extra": entry.extra,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _record_file_failure_once(
    portfolio_id: str,
    failure: Exception,
    dt: datetime.datetime,
) -> None:
    """记录一次文件写入失败，避免每条日志重复告警。"""
    if portfolio_id in _FILE_FAILURE_WARNED:
        return
    _FILE_FAILURE_WARNED.add(portfolio_id)
    warning = BacktestLogEntry(
        event_id=uuid.uuid4().hex,
        portfolio_id=portfolio_id,
        dt=dt,
        level="WARNING",
        source="system",
        message=f"写入回测日志文件失败：{failure}",
        extra="",
    )
    db.insert_backtest_logs(warning)


def saved_backtest_log_path(portfolio_id: str) -> Path:
    """返回回测日志文件路径。"""
    return get_backtest_log_path(portfolio_id)


def saved_backtest_log_exists(portfolio_id: str) -> bool:
    """判断回测日志文件是否存在。"""
    return saved_backtest_log_path(portfolio_id).exists()


def record_backtest_log(
    portfolio_id: str,
    level: str,
    source: str,
    message: str,
    dt: datetime.date | datetime.datetime | None = None,
    extra: dict[str, Any] | None = None,
    save_to_file: bool = False,
) -> BacktestLogEntry:
    """记录一条回测文本日志。

    Args:
        portfolio_id: 组合 ID。
        level: 日志等级。
        source: 日志来源。
        message: 日志内容。
        dt: 日志时间。
        extra: 额外上下文。
        save_to_file: 是否同步写入文件。

    Returns:
        已写入的日志实体。
    """
    entry = BacktestLogEntry(
        event_id=uuid.uuid4().hex,
        portfolio_id=portfolio_id,
        dt=_coerce_datetime(dt),
        level=str(level or "INFO").upper(),
        source=str(source or "system"),
        message=str(message or ""),
        extra=_serialize_extra(extra),
    )
    db.insert_backtest_logs(entry)

    if save_to_file:
        try:
            _append_entry_to_file(entry, saved_backtest_log_path(portfolio_id))
        except Exception as exc:  # pragma: no cover - exercised via monkeypatch in tests
            _record_file_failure_once(portfolio_id, exc, entry.dt)

    return entry


def list_backtest_logs(portfolio_id: str, limit: int = 200) -> list[dict[str, str]]:
    """读取最近的回测文本日志。"""
    logs_df = db.get_backtest_logs(portfolio_id)
    if logs_df.is_empty():
        return []

    logs_df = logs_df.sort(["dt", "event_id"]).tail(limit)
    return [
        _entry_to_row(BacktestLogEntry(**row))
        for row in logs_df.iter_rows(named=True)
    ]


def load_saved_backtest_logs(
    portfolio_id: str,
    limit: int = 200,
) -> list[dict[str, str]]:
    """从已保存文件中加载回测日志。"""
    path = saved_backtest_log_path(portfolio_id)
    if not path.exists():
        raise FileNotFoundError(f"未找到已保存日志文件：{path}")

    rows: deque[dict[str, str]] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            dt_value = payload.get("dt") or datetime.datetime.now().isoformat()
            entry = BacktestLogEntry(
                event_id=str(payload.get("event_id") or uuid.uuid4().hex),
                portfolio_id=str(payload.get("portfolio_id") or portfolio_id),
                dt=dt_value,
                level=str(payload.get("level") or "INFO"),
                source=str(payload.get("source") or "system"),
                message=str(payload.get("message") or ""),
                extra=_format_extra_text(payload.get("extra")),
            )
            rows.append(_entry_to_row(entry))
    return list(rows)
