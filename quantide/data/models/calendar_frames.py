"""CalendarFrameOperations implementation."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

import arrow
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from quantide.config.settings import get_timezone
from quantide.core.enums import FrameType

Frame = datetime.datetime | datetime.date


def _previous_minute_session(
    day_offset: int, h: int, m: int, moment: datetime.datetime, self: CalendarFrameOperations
) -> tuple[int, int, datetime.date]:
    """Previous minute session."""
    if self.day_shift(moment, 0) < moment.date() or day_offset == -1:
        h = 15
        m = 0
        new_day = self.day_shift(moment, day_offset)
    else:
        new_day = moment.date()
    return h, m, new_day


class CalendarFrameOperations:
    """CalendarFrameOperations implementation."""

    if TYPE_CHECKING:
        minute_level_frames: list[FrameType]
        day_level_frames: list[FrameType]
        ticks: dict[FrameType, list[int]]
        day_frames: pa.Array[Any] | None
        week_frames: pa.Array[Any] | None
        month_frames: pa.Array[Any] | None

        def day_shift(self, start: datetime.date, offset: int) -> datetime.date: ...
        def is_trade_day(self, dt: Frame) -> bool: ...
        def shift(self, moment: Frame, n: int, frame_type: FrameType) -> Frame: ...
        def replace_time(
            self, date: datetime.date, hour: int, minute: int = 0
        ) -> datetime.datetime: ...

    def minute_frames_floor(self, ticks: Sequence[int], moment: int) -> tuple[int, int]:
        """
        返回分钟刻度及日期进位。

        对齐到上一个交易日时进位为 -1，否则为 0。

        Examples:
            >>> ticks = [600, 630, 660, 690, 810, 840, 870, 900]
            >>> minute_frames_floor(ticks, 545)
            (900, -1)
            >>> minute_frames_floor(ticks, 600)
            (600, 0)
            >>> minute_frames_floor(ticks, 605)
            (600, 0)
            >>> minute_frames_floor(ticks, 899)
            (870, 0)
            >>> minute_frames_floor(ticks, 900)
            (900, 0)
            >>> minute_frames_floor(ticks, 905)
            (900, 0)

        Args:
            ticks (np.array or list): frames刻度
            moment (int): 整数表示的分钟数，比如900表示15：00

        Returns:
            tuple, the first is the new moment, the second is carry-on
        """
        if moment < ticks[0]:
            return ticks[-1], -1
        # ’right' 相当于 ticks <= m
        index = np.searchsorted(ticks, moment, side="right")
        return ticks[int(index) - 1], 0

    def floor(self, moment: Frame, frame_type: FrameType) -> Frame:
        """求`moment`在指定的`frame_type`中的下界

        比如，如果`moment`为10:37，则当`frame_type`为30分钟时，对应的上界为10:00

        Examples:
            >>> # 如果moment为日期，则当成已收盘处理
            >>> tf.floor(datetime.date(2005, 1, 7), FrameType.DAY)
            datetime.date(2005, 1, 7)

            >>> # moment指定的时间还未收盘，floor到上一个交易日
            >>> tf.floor(datetime.datetime(2005, 1, 7, 14, 59), FrameType.DAY)
            datetime.date(2005, 1, 6)

            >>> tf.floor(datetime.date(2005, 1, 13), FrameType.WEEK)
            datetime.date(2005, 1, 7)

            >>> tf.floor(datetime.date(2005,2, 27), FrameType.MONTH)
            datetime.date(2005, 1, 31)

            >>> tf.floor(datetime.datetime(2005,1,5,14,59), FrameType.MIN30)
            datetime.datetime(2005, 1, 5, 14, 30)

            >>> tf.floor(datetime.datetime(2005, 1, 5, 14, 59), FrameType.MIN1)
            datetime.datetime(2005, 1, 5, 14, 59)

            >>> moment = arrow.get('2005-1-5 14:59', tzinfo='Asia/Shanghai').datetime
            >>> tf.floor(moment, FrameType.MIN1).isoformat()
            '2005-01-05T14:59:00+08:00'

        Args:
            moment:
            frame_type:

        Returns:
            Frame: 对应周期的交易时刻。
        """
        if frame_type in self.minute_level_frames:
            minute_moment = cast(datetime.datetime, moment)
            tm, day_offset = self.minute_frames_floor(
                self.ticks[frame_type], minute_moment.hour * 60 + minute_moment.minute
            )
            h, m = tm // 60, tm % 60
            h, m, new_day = _previous_minute_session(day_offset, h, m, minute_moment, self)
            return datetime.datetime(
                new_day.year, new_day.month, new_day.day, h, m, tzinfo=minute_moment.tzinfo
            )

        if type(moment) is datetime.date:
            if moment == datetime.date.today():
                moment = datetime.datetime.now(tz=get_timezone())
            else:
                moment = self.replace_time(moment, 15, 0)

        # 如果是交易日，但还未收盘，对回测也适用
        assert isinstance(moment, datetime.datetime)
        if self.is_trade_day(moment) and moment.hour * 60 + moment.minute < 900:
            moment = self.day_shift(moment, -1)

        if frame_type == FrameType.DAY:
            arr = self.day_frames
        elif frame_type == FrameType.WEEK:
            arr = self.week_frames
        elif frame_type == FrameType.MONTH:
            arr = self.month_frames
        else:  # pragma: no cover
            raise ValueError(f"frame type {frame_type} not supported.")

        if arr is None:
            raise ValueError("交易日历未初始化，请先调用 load()")
        # Arrow accepts Python date/datetime scalars, although its stubs omit them.
        result = arr.filter(cast(Any, pc.less_equal)(arr, moment))
        if len(result) == 0:
            return cast(Frame, arr[0].as_py())

        return cast(Frame, result[-1].as_py())

    def last_min_frame(self, day: str | datetime.date, frame_type: FrameType) -> Frame:
        """获取`day`日周期为`frame_type`的结束frame。

        Example:
            >>> tf.last_min_frame(arrow.get('2020-1-5').date(), FrameType.MIN30)
            datetime.datetime(2020, 1, 3, 15, 0, tzinfo=tzfile('/usr/share/zoneinfo/Asia/Shanghai'))

        Args:
            day:
            frame_type:

        Returns:
            Frame: 对应周期的交易时刻。
        """
        if isinstance(day, str):
            day = arrow.get(day).date()
        elif isinstance(day, datetime.datetime):
            day = day.date()
        elif isinstance(day, datetime.date):
            day = day
        else:
            raise TypeError(f"{type(day)} is not supported.")

        if not self.is_trade_day(day):
            day = self.floor(day, FrameType.DAY)

        if frame_type in self.minute_level_frames:
            return datetime.datetime(
                day.year,
                day.month,
                day.day,
                hour=15,
                minute=0,
                tzinfo=get_timezone(),
            )
        else:  # pragma: no cover
            raise ValueError(f"{frame_type} not supported")

    def frame_len(self, frame_type: FrameType) -> int:
        """返回以分钟为单位的frame长度。

        对日线以上级别没有意义，但会返回240

        Examples:
            >>> tf.frame_len(FrameType.MIN5)
            5

        Args:
            frame_type:

        Returns:
            Frame: 对应周期的交易时刻。
        """
        if frame_type == FrameType.MIN1:
            return 1
        elif frame_type == FrameType.MIN5:
            return 5
        elif frame_type == FrameType.MIN15:
            return 15
        elif frame_type == FrameType.MIN30:
            return 30
        elif frame_type == FrameType.MIN60:
            return 60
        else:
            return 240

    def first_min_frame(self, day: str | datetime.date, frame_type: FrameType) -> Frame:
        """获取指定日期下，类型为 `frame_type` 的第一个frame。

        每天的第一个分钟线、5分钟线、15分钟线都是不同的。比如，分钟线始于9:31, 5分钟线始于9:35。
        Examples:
            >>> tf.first_min_frame('2019-12-31', FrameType.MIN1).isoformat()
            '2019-12-31T09:31:00+08:00'

        Args:
            day: 日期
            frame_type: 周期类型

        Returns:
            Frame: 对应周期的交易时刻。
        """
        if isinstance(day, str):
            day = arrow.get(day).datetime

        if not self.is_trade_day(day):
            floor_day = self.floor(day, FrameType.DAY)
        else:
            floor_day = day
        if frame_type == FrameType.MIN1:
            return datetime.datetime(
                floor_day.year,
                floor_day.month,
                floor_day.day,
                hour=9,
                minute=31,
                tzinfo=get_timezone(),
            )
        elif frame_type == FrameType.MIN5:
            return datetime.datetime(
                floor_day.year,
                floor_day.month,
                floor_day.day,
                hour=9,
                minute=35,
                tzinfo=get_timezone(),
            )
        elif frame_type == FrameType.MIN15:
            return datetime.datetime(
                floor_day.year,
                floor_day.month,
                floor_day.day,
                hour=9,
                minute=45,
                tzinfo=get_timezone(),
            )
        elif frame_type == FrameType.MIN30:
            return datetime.datetime(
                floor_day.year,
                floor_day.month,
                floor_day.day,
                hour=10,
                tzinfo=get_timezone(),
            )
        elif frame_type == FrameType.MIN60:
            return datetime.datetime(
                floor_day.year,
                floor_day.month,
                floor_day.day,
                hour=10,
                minute=30,
                tzinfo=get_timezone(),
            )
        else:  # pragma: no cover
            raise ValueError(f"{frame_type} not supported")

    def ceiling(self, moment: Frame, frame_type: FrameType) -> Frame:
        """求`moment`所在类型为`frame_type`周期的上界

        比如`moment`为14:59分，如果`frame_type`为30分钟，则它的上界应该为15:00

        Example:
            >>> tf.ceiling(datetime.date(2005, 1, 7), FrameType.DAY)
            datetime.date(2005, 1, 7)

            >>> tf.ceiling(datetime.date(2005, 1, 4), FrameType.WEEK)
            datetime.date(2005, 1, 7)

            >>> tf.ceiling(datetime.date(2005,1,7), FrameType.WEEK)
            datetime.date(2005, 1, 7)

            >>> tf.ceiling(datetime.date(2005,1 ,1), FrameType.MONTH)
            datetime.date(2005, 1, 31)

            >>> tf.ceiling(datetime.datetime(2005,1,5,14,59), FrameType.MIN30)
            datetime.datetime(2005, 1, 5, 15, 0)

            >>> tf.ceiling(datetime.datetime(2005, 1, 5, 14, 59), FrameType.MIN1)
            datetime.datetime(2005, 1, 5, 14, 59)

            >>> moment = arrow.get('2005-1-5 14:59', tzinfo='Asia/Shanghai').datetime
            >>> tf.ceiling(moment, FrameType.MIN1).isoformat()
            '2005-01-05T14:59:00+08:00'

        Args:
            moment (datetime.datetime): [description]
            frame_type (FrameType): [description]

        Returns:
            [type]: [description]
        """
        if frame_type in self.day_level_frames and type(moment) is datetime.datetime:
            moment = moment.date()

        floor = self.floor(moment, frame_type)
        if floor == moment:
            return moment
        elif floor > moment:
            return floor
        else:
            return self.shift(floor, 1, frame_type)
