"""测试用虚拟时钟.

v0.2-001 test-plan §5.4.1 职责: 替换"真实墙钟", 框架读到的时间可被测试任意快进.

实现策略:
- 默认虚拟时刻 = 一个固定起点 (2022-12-29 09:30:00), 避免 now() 在 setup 阶段返回 wall clock 导致不可重现
- 推进时刻有 3 种方式:
  1. set_now(tm): 直接设置到指定时刻
  2. advance(seconds): 相对当前时刻推进 N 秒
  3. advance_to_next_frame(frame_type, calendar): 推进到下一帧 (1d/30m/...), 由 `quantide.data.models.calendar.calendar` 提供帧边界
- iter_frames 实现与 BacktestClockAdapter 一致 (委托 calendar.get_frames)
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable

from quantide.core.enums import FrameType
from quantide.core.ports import ClockPort
from quantide.data.models.calendar import calendar

DEFAULT_VIRTUAL_T0 = datetime.datetime(2022, 12, 29, 9, 30, 0)


class VirtualClock(ClockPort):
    def __init__(self, t0: datetime.datetime | None = None):
        self._now: datetime.datetime = t0 or DEFAULT_VIRTUAL_T0

    def now(self) -> datetime.datetime:
        return self._now

    def set_now(self, tm: datetime.datetime) -> None:
        self._now = tm

    def advance(self, seconds: float) -> None:
        self._now = self._now + datetime.timedelta(seconds=seconds)

    def advance_to(self, tm: datetime.datetime) -> None:
        """推进到指定时刻. 早于当前时刻时**不**回退, 抛 ValueError (避免 paper E2E 时间倒流破坏可重现性)."""
        if tm < self._now:
            raise ValueError(
                f"VirtualClock.advance_to: target {tm} is before current {self._now}"
            )
        self._now = tm

    def advance_to_next_frame(
        self, frame_type: FrameType, calendar_model=None
    ) -> datetime.datetime:
        cal = calendar_model or calendar
        current = self._now
        for frame in cal.get_frames(current.date(), current.date() + datetime.timedelta(days=7), frame_type):
            if frame > current:
                self._now = frame
                return frame
        raise RuntimeError(
            f"VirtualClock.advance_to_next_frame: no next {frame_type} frame within 7 days of {current}"
        )

    def iter_frames(
        self,
        start: datetime.date | datetime.datetime,
        end: datetime.date | datetime.datetime,
        frame_type: FrameType,
    ) -> Iterable[datetime.date | datetime.datetime]:
        return calendar.get_frames(start, end, frame_type)
