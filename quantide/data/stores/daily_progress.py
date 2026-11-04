"""Legacy per-day downloads with explicit partial failure and progress delivery."""

from __future__ import annotations

import datetime
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from quantide.core.enums import FrameType
from quantide.core.message import msg_hub

if TYPE_CHECKING:
    from quantide.data.stores.base import ParquetStorage


def _publish(payload: dict[str, Any] | None) -> None:
    try:
        msg_hub.publish(topic="fetch_data_progress", msg_content=payload)
    except Exception:
        logger.debug("Daily progress subscriber unavailable")


@dataclass
class DayProgress:
    """Progress for one requested day; reporting cannot change download facts."""

    date: datetime.date
    index: int
    total: int
    callback: Callable[..., None] | None

    def payload(self, phase: str) -> dict[str, str | int]:
        return {
            "phase": phase,
            "current_date": self.date.strftime("%Y-%m-%d"),
            "completed": self.index,
            "total": self.total,
        }

    def phase(self, phase: str) -> None:
        _publish(self.payload(phase))
        if self.callback:
            try:
                self.callback(self.date, self.index, self.total, phase)
            except TypeError:
                self.callback(self.date, self.index, self.total)


def _download_day(store: ParquetStorage, progress: DayProgress) -> None:
    fetch = store._fetch_data_func
    if fetch is None:
        raise ValueError("未提供 fetch_data_func")
    kwargs = (
        {"phase_callback": progress.phase}
        if "phase_callback" in inspect.signature(fetch).parameters
        else {}
    )
    frame, errors = fetch([progress.date], **kwargs)
    store._error_handler(errors)
    if errors:
        raise RuntimeError("; ".join(str(error[-1]) for error in errors if error))
    if frame is None or len(frame) == 0:
        raise RuntimeError(f"{progress.date} 行情返回空数据，未记为完成")
    store.append_data(frame)
    progress.phase("done")


def download_days(
    store: ParquetStorage,
    start: datetime.date,
    end: datetime.date,
    progress_callback: Callable[..., None] | None,
    force: bool,
) -> int:
    """Keep committed dates, but raise if any requested date failed."""
    start, end = (
        store._calendar.ceiling(start, FrameType.DAY),
        store._calendar.floor(end, FrameType.DAY),
    )
    expected = set(store._calendar.get_frames(start, end, FrameType.DAY))
    missing = sorted(expected if force else expected - set(store.available_dates))
    if not missing:
        return 0
    if store._fetch_data_func is None:
        raise ValueError("缓存中没有足够的数据，且未提供fetch_data_func方法")
    failures = []
    for index, date in enumerate(missing, start=1):
        progress = DayProgress(date, index, len(missing), progress_callback)
        try:
            _download_day(store, progress)
        except Exception as exc:
            logger.error("同步 {} 数据失败: {}", date, exc)
            failures.append(f"{date}: {exc}")
            _publish({**progress.payload("error"), "error": str(exc)})
    _publish(None)
    store._collect_dates()
    if failures:
        raise RuntimeError("日线同步未完成：" + "; ".join(failures))
    return len(missing)
