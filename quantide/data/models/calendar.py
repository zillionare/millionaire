#!/usr/bin/env python

# Legacy calendar API documentation contains intentionally empty Returns sections.
# ruff: noqa: D205,D414

from __future__ import annotations

import datetime
import itertools
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from arrow import Arrow
from loguru import logger

from quantide.config.settings import get_epoch, get_timezone
from quantide.core.atomic_files import atomic_path
from quantide.core.enums import FrameType
from quantide.core.singleton import singleton
from quantide.data.fetchers.registry import get_data_fetcher
from quantide.data.models.calendar_frames import CalendarFrameOperations

#: 日历至少从该日期开始拉取，保证 ``day_shift`` 在配置 epoch 附近可用。
_CALENDAR_FETCH_START = datetime.date(2005, 1, 1)


def _calendar_fetch_start() -> datetime.date:
    return min(get_epoch(), _CALENDAR_FETCH_START)


Frame = datetime.datetime | datetime.date


def _calendar_frames_by_count(
    self: Calendar, end: Frame, n: int, frame_type: FrameType
) -> list[Frame]:
    """Slice completed daily, weekly or monthly frames."""
    end_date = end.date() if isinstance(end, datetime.datetime) else end
    if frame_type == FrameType.DAY:
        arr = self.day_frames
    elif frame_type == FrameType.WEEK:
        arr = self.week_frames
    else:
        arr = self.month_frames

    if arr is None:
        raise ValueError("交易日历未初始化，请先调用 load()")
    le = pc.less_equal(arr, pa.scalar(end_date))
    pos = int(pc.sum(pc.cast(le, pa.int32())).as_py())
    start = max(0, pos - n)
    sliced = arr.slice(start, pos - start).to_pylist()

    return cast(list[Frame], sliced)


@singleton
class Calendar(CalendarFrameOperations):
    """交易日历

    提供交易日历以及相关计算，比如计算[start, end]之间有多少个交易周期，偏移等。
    """

    def __init__(self) -> None:
        self._path: Path | None = None
        self._data: pa.Table | None = None
        self.minute_level_frames = [
            FrameType.MIN1,
            FrameType.MIN5,
            FrameType.MIN15,
            FrameType.MIN30,
            FrameType.MIN60,
        ]
        self.day_level_frames = [
            FrameType.DAY,
            FrameType.WEEK,
            FrameType.MONTH,
            FrameType.YEAR,
        ]

        self.ticks = {
            FrameType.MIN1: [i for i in itertools.chain(range(571, 691), range(781, 901))],
            FrameType.MIN5: [i for i in itertools.chain(range(575, 695, 5), range(785, 905, 5))],
            FrameType.MIN15: [i for i in itertools.chain(range(585, 705, 15), range(795, 915, 15))],
            FrameType.MIN30: [
                int(s / 100) * 60 + int(s % 100)
                for s in [1000, 1030, 1100, 1130, 1330, 1400, 1430, 1500]
            ],
            FrameType.MIN60: [int(s / 100) * 60 + int(s % 100) for s in [1030, 1130, 1400, 1500]],
        }

        self.day_frames = None
        self.week_frames = None
        self.month_frames = None

    @property
    def epoch(self) -> datetime.date:
        """日历的起始日期"""
        if self._data is None or len(self._data) == 0:
            return get_epoch()
        dates = self._data.column("date")
        return cast(datetime.date, dates[0].as_py())

    @property
    def end(self) -> datetime.date:
        if self._data is None:
            raise ValueError("交易日历未初始化，请先调用 load()")
        dates = self._data.column("date")
        return cast(datetime.date, dates[-1].as_py())

    def last_trade_date(self) -> datetime.date:
        """获取最近一个交易日.

        Returns:
            最近一个交易日日期。
        """
        now = datetime.datetime.now(tz=get_timezone())
        return self.floor(now, FrameType.DAY)

    @property
    def path(self) -> Path:
        """获取日历数据文件路径

        Returns:
            日历数据文件路径
        """
        if self._path is None:
            raise ValueError("日历数据文件路径未指定")

        return self._path

    @property
    def data(self) -> pd.DataFrame:
        """获取Arrow格式的日历数据的 pandas 视图"""
        if self._data is None:
            raise ValueError("日历数据未加载")
        return self._data.to_pandas()

    def save(self, calendar_data: pd.DataFrame) -> None:
        """一次性写入整个trade_calendar表的数据（会先清空表）

        Args:
            calendar_data: 索引为 date, 字段 is_open, prev
        """
        with atomic_path(self.path) as temporary:
            calendar_data.to_parquet(temporary)

    def load(self, path: str | Path) -> Calendar:
        """加载日历数据，并构建日/周/月帧。

        如果指定文件不存在，则从服务器获取并保存。
        """
        if path is not None:
            _path = Path(path).expanduser()
            parent = _path.parent
            parent.mkdir(parents=True, exist_ok=True)
            logger.info("Calendar 将从 {}处加载数据", _path)
            self._path = _path

        try:
            self._data = pq.read_table(self.path)
        except Exception as e:
            logger.warning("Calendar 读取日历数据失败，重新从服务器获取")
            logger.exception(e)
            df = get_data_fetcher().fetch_calendar(_calendar_fetch_start())
            self._data = pa.Table.from_pandas(df)
            self.save(df)

        # 中文：基于 is_open==1 构建交易日、周、月帧（整数 YYYYMMDD）
        self.day_frames, self.week_frames, self.month_frames = self._build_frames_arrow(self._data)
        return self

    def update(self) -> None:
        """更新日历数据并重建帧。

        从固定/配置 epoch 的较早者拉取完整日历，不能从当前数据的第一天开始：
        否则一次局部同步会把历史日历截断，回测起始日的前一交易日将不存在。
        """
        df = get_data_fetcher().fetch_calendar(_calendar_fetch_start())
        self._data = pa.Table.from_pandas(df)
        self.save(df)
        self.day_frames, self.week_frames, self.month_frames = self._build_frames_arrow(self._data)

    def _build_frames_arrow(
        self, table: pa.Table
    ) -> tuple[pa.Array[Any], pa.Array[Any], pa.Array[Any]]:
        """构建交易日、周、月帧"""
        # 1) 只保留交易日
        is_open = pc.equal(table.column("is_open"), 1)  # type: ignore
        ft = table.filter(is_open)
        day_frames = ft.column("date").combine_chunks()  # pa.ChunkedArray(date32)

        # 2) 转成 DatetimeIndex，仅分组用（不会补齐自然日）
        idx = pd.to_datetime(cast(list[datetime.date], day_frames.to_pylist()))

        # 3) 每周最后交易日：按 (year, week) 分组后取最大日期
        iso = idx.isocalendar()  # 返回 DataFrame，含 year/week/day
        week_key = iso.year * 100 + iso.week
        week_last = (
            pd.Series(1, index=idx).groupby(week_key).apply(lambda x: x.index.max()).sort_values()
        )
        week_frames = pa.array(
            [cast(pd.Timestamp, d).date() for d in week_last.tolist()], type=pa.date32()
        )

        # 4) 每月最后交易日：按月分组后取最大日期
        month_last = (
            pd.Series(1, index=idx)
            .groupby(idx.to_period("M"))
            .apply(lambda x: x.index.max())
            .sort_values()
        )
        month_frames = pa.array(
            [cast(pd.Timestamp, d).date() for d in month_last.tolist()], type=pa.date32()
        )

        return day_frames, week_frames, month_frames

    def int2time(self, tm: int) -> datetime.datetime:
        """将整数表示的时间转换为`datetime`类型表示

        examples:
            >>> tf.int2time(202005011500)
            datetime.datetime(2020, 5, 1, 15, 0, tzinfo=tzfile('/usr/share/zoneinfo/Asia/Shanghai'))

        Args:
            tm: time in YYYYMMDDHHmm format

        Returns:

        """
        s = str(tm)
        # its 8 times faster than arrow.get()
        return datetime.datetime(
            int(s[:4]),
            int(s[4:6]),
            int(s[6:8]),
            int(s[8:10]),
            int(s[10:12]),
            tzinfo=get_timezone(),
        )

    def time2int(self, tm: datetime.datetime) -> int:
        """将时间类型转换为整数类型

        tm可以是datetime.datetime或者任何其它类型，只要它有year,month...等
        属性
        Examples:
            >>> tf.time2int(datetime.datetime(2020, 5, 1, 15))
            202005011500

        Args:
            tm:

        Returns:

        """
        return int(f"{tm.year:04}{tm.month:02}{tm.day:02}{tm.hour:02}{tm.minute:02}")

    def date2int(self, d: datetime.datetime | datetime.date) -> int:
        """将日期转换为整数表示

        在zillionare中，如果要对时间和日期进行持久化操作，我们一般将其转换为int类型

        Examples:
            >>> tf.date2int(datetime.date(2020,5,1))
            20200501

        Args:
            d: date

        Returns:

        """
        return int(f"{d.year:04}{d.month:02}{d.day:02}")

    def int2date(self, d: int | str) -> datetime.date:
        """将数字表示的日期转换成为日期格式

        Examples:
            >>> tf.int2date(20200501)
            datetime.date(2020, 5, 1)

        Args:
            d: YYYYMMDD表示的日期

        Returns:

        """
        s = str(d)
        # it's 8 times faster than arrow.get
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))

    def day_shift(self, start: datetime.date, offset: int) -> datetime.date:
        """对指定日期进行前后移位操作

        如果 n == 0，则返回d对应的交易日（如果是非交易日，则返回刚结束的一个交易日）
        如果 n > 0，则返回d对应的交易日后第 n 个交易日
        如果 n < 0，则返回d对应的交易日前第 n 个交易日

        Examples:
            >>> tf.day_shift(datetime.date(2019,12,13), 0)
            datetime.date(2019, 12, 13)

            >>> tf.day_shift(datetime.date(2019, 12, 15), 0)
            datetime.date(2019, 12, 13)

            >>> tf.day_shift(datetime.date(2019, 12, 15), 1)
            datetime.date(2019, 12, 16)

            >>> tf.day_shift(datetime.date(2019, 12, 13), 1)
            datetime.date(2019, 12, 16)

        Args:
            start: the origin day
            offset: days to shift, can be negative

        Returns:

        """
        # 中文：使用预先构建的 day_frames（Arrow date32 列）进行 floor + 移位
        arr = self.day_frames
        if arr is None:
            raise ValueError("day_frames 未初始化，请先调用 load()")

        le = pc.less_equal(arr, pa.scalar(start))
        cnt = int(pc.sum(pc.cast(le, pa.int32())).as_py())
        base_idx = max(0, cnt - 1)

        if offset == 0:
            return cast(datetime.date, arr[base_idx].as_py())

        new_idx = max(0, min(len(arr) - 1, base_idx + offset))
        return cast(datetime.date, arr[new_idx].as_py())

    def week_shift(self, start: datetime.date, offset: int) -> datetime.date:
        """对指定日期按周线帧进行前后移位操作

        仅在预构建的 `week_frames` 上进行 floor + 索引移位。
        """
        arr = self.week_frames
        if arr is None:
            raise ValueError("week_frames 未初始化，请先调用 load()")

        le = pc.less_equal(arr, pa.scalar(start))
        cnt = int(pc.sum(pc.cast(le, pa.int32())).as_py())
        base_idx = max(0, cnt - 1)

        if offset == 0:
            return cast(datetime.date, arr[base_idx].as_py())

        new_idx = max(0, min(len(arr) - 1, base_idx + offset))
        return cast(datetime.date, arr[new_idx].as_py())

    def month_shift(self, start: datetime.date, offset: int) -> datetime.date:
        """求`start`所在的月移位后的frame

        仅在预构建的 `month_frames` 上进行 floor + 索引移位。
        """
        arr = self.month_frames
        if arr is None:
            raise ValueError("month_frames 未初始化，请先调用 load()")

        le = pc.less_equal(arr, pa.scalar(start))
        cnt = int(pc.sum(pc.cast(le, pa.int32())).as_py())
        base_idx = max(0, cnt - 1)

        if offset == 0:
            return cast(datetime.date, arr[base_idx].as_py())

        new_idx = max(0, min(len(arr) - 1, base_idx + offset))
        return cast(datetime.date, arr[new_idx].as_py())

    def get_ticks(self, frame_type: FrameType) -> list[int] | pa.Array[Any] | None:
        """取月线、周线、日线及各分钟线对应的frame

        对分钟线，返回值仅包含时间，不包含日期（均为整数表示）

        Examples:
            >>> tf.get_ticks(FrameType.MONTH)[:3]
            array([20050131, 20050228, 20050331])

        Args:
            frame_type : [description]

        Raises:
            ValueError: [description]

        Returns:
            [description]
        """
        if frame_type in self.minute_level_frames:
            return self.ticks[frame_type]

        if frame_type == FrameType.DAY:
            return self.day_frames
        elif frame_type == FrameType.WEEK:
            return self.week_frames
        elif frame_type == FrameType.MONTH:
            return self.month_frames
        else:  # pragma: no cover
            raise ValueError(f"{frame_type} not supported!")

    def shift(
        self,
        moment: Frame | Arrow,
        n: int,
        frame_type: FrameType,
    ) -> Frame:
        """将指定的moment移动N个`frame_type`位置。

        当N为负数时，意味着向前移动；当N为正数时，意味着向后移动。如果n为零，意味着移动到最接近
        的一个已结束的frame。

        如果moment没有对齐到frame_type对应的时间，将首先进行对齐。

        See also:
        - [day_shift][omicron.core.timeframe.TimeFrame.day_shift]
        - [week_shift][omicron.core.timeframe.TimeFrame.week_shift]
        - [month_shift][omicron.core.timeframe.TimeFrame.month_shift]

        Examples:
            >>> tf.shift(datetime.date(2020, 1, 3), 1, FrameType.DAY)
            datetime.date(2020, 1, 6)

            >>> tf.shift(datetime.datetime(2020, 1, 6, 11), 1, FrameType.MIN30)
            datetime.datetime(2020, 1, 6, 11, 30)


        Args:
            moment:
            n:
            frame_type:

        Returns:

        """
        if isinstance(moment, Arrow):
            moment = moment.datetime
        if frame_type == FrameType.DAY:
            return self.day_shift(moment, n)

        elif frame_type == FrameType.WEEK:
            return self.week_shift(moment, n)
        elif frame_type == FrameType.MONTH:
            return self.month_shift(moment, n)
        elif frame_type in [
            FrameType.MIN1,
            FrameType.MIN5,
            FrameType.MIN15,
            FrameType.MIN30,
            FrameType.MIN60,
        ]:
            if not isinstance(moment, datetime.datetime):
                raise TypeError("分钟周期需要 datetime 时间")
            tm = moment.hour * 60 + moment.minute

            new_tick_pos = self.ticks[frame_type].index(tm) + n
            days = new_tick_pos // len(self.ticks[frame_type])
            min_part = new_tick_pos % len(self.ticks[frame_type])

            date_part = self.day_shift(moment.date(), days)
            minutes = self.ticks[frame_type][min_part]
            h, m = minutes // 60, minutes % 60
            return datetime.datetime(
                date_part.year,
                date_part.month,
                date_part.day,
                h,
                m,
                tzinfo=moment.tzinfo,
            )
        else:  # pragma: no cover
            raise ValueError(f"{frame_type} is not supported.")

    def _floor_idx(self, arr: pa.Array[Any] | pa.ChunkedArray[Any] | None, x: datetime.date) -> int:
        if arr is None:
            raise ValueError("交易日历未初始化，请先调用 load()")
        arr = arr.combine_chunks() if hasattr(arr, "combine_chunks") else arr
        le = pc.less_equal(arr, pa.scalar(x))
        cnt = int(pc.sum(pc.cast(le, pa.int32())).as_py())
        return max(0, min(len(arr) - 1, cnt - 1))

    def count_day_frames(self, start: datetime.date | Arrow, end: datetime.date | Arrow) -> int:
        """Calc trade days between start and end in close-to-close way.

        if start == end, this will returns 1. Both start/end will be aligned to open
        trade day before calculation.

        Examples:
            >>> start = datetime.date(2019, 12, 21)
            >>> end = datetime.date(2019, 12, 21)
            >>> tf.count_day_frames(start, end)
            1

            >>> # non-trade days are removed
            >>> start = datetime.date(2020, 1, 23)
            >>> end = datetime.date(2020, 2, 4)
            >>> tf.count_day_frames(start, end)
            3

        args:
            start:
            end:
        """
        # 使用 Arrow 帧进行 floor + 计数（含起止对齐到最近交易日）
        s = start
        e = end
        if isinstance(s, Arrow):
            s = s.date()
        elif isinstance(s, datetime.datetime):
            s = s.date()
        if isinstance(e, Arrow):
            e = e.date()
        elif isinstance(e, datetime.datetime):
            e = e.date()

        i = self._floor_idx(self.day_frames, s)
        j = self._floor_idx(self.day_frames, e)
        return max(0, j - i + 1)

    def count_week_frames(self, start: datetime.date, end: datetime.date) -> int:
        """
        Calc trade weeks between start and end in close-to-close way. Both start and
        end will be aligned to open trade day before calculation. After that, if start
         == end, this will returns 1

        See `count_day_frames` for examples.
        args:
            start:
            end:
        """
        i = self._floor_idx(self.week_frames, start)
        j = self._floor_idx(self.week_frames, end)
        return max(0, j - i + 1)

    def count_month_frames(self, start: datetime.date, end: datetime.date) -> int:
        """Calc trade months between start and end date in close-to-close way
        Both start and end will be aligned to open trade day before calculation. After
        that, if start == end, this will returns 1.

        See `count_day_frames` for examples.

        Args:
            start:
            end:

        Returns:

        """
        i = self._floor_idx(self.month_frames, start)
        j = self._floor_idx(self.month_frames, end)
        return max(0, j - i + 1)

    def count_frames(
        self,
        start: datetime.date | datetime.datetime | Arrow,
        end: datetime.date | datetime.datetime | Arrow,
        frame_type: FrameType,
    ) -> int:
        """计算start与end之间有多少个周期为frame_type的frames

        See also:
        - [count_day_frames][omicron.core.timeframe.TimeFrame.count_day_frames]
        - [count_week_frames][omicron.core.timeframe.TimeFrame.count_week_frames]
        - [count_month_frames][omicron.core.timeframe.TimeFrame.count_month_frames]

        Args:
            start : [description]
            end : [description]
            frame_type : [description]

        Raises:
            ValueError: 如果frame_type不支持(季线、年线），则会抛出此异常。

        Returns:
            从start到end的帧数
        """
        if frame_type == FrameType.DAY:
            return self.count_day_frames(start, end)
        elif frame_type == FrameType.WEEK:
            return self.count_week_frames(
                start.date() if isinstance(start, (Arrow, datetime.datetime)) else start,
                end.date() if isinstance(end, (Arrow, datetime.datetime)) else end,
            )
        elif frame_type == FrameType.MONTH:
            return self.count_month_frames(
                start.date() if isinstance(start, (Arrow, datetime.datetime)) else start,
                end.date() if isinstance(end, (Arrow, datetime.datetime)) else end,
            )
        elif frame_type in [
            FrameType.MIN1,
            FrameType.MIN5,
            FrameType.MIN15,
            FrameType.MIN30,
            FrameType.MIN60,
        ]:
            if not isinstance(start, (Arrow, datetime.datetime)) or not isinstance(
                end, (Arrow, datetime.datetime)
            ):
                raise TypeError("分钟周期需要 datetime 时间")
            tm_start = start.hour * 60 + start.minute
            tm_end = end.hour * 60 + end.minute
            days = self.count_day_frames(start.date(), end.date()) - 1

            tm_start_pos = self.ticks[frame_type].index(tm_start)
            tm_end_pos = self.ticks[frame_type].index(tm_end)

            min_bars = tm_end_pos - tm_start_pos + 1

            return days * len(self.ticks[frame_type]) + min_bars
        else:  # pragma: no cover
            raise ValueError(f"{frame_type} is not supported yet")

    def is_trade_day(self, dt: Frame | Arrow) -> bool:
        """判断`dt`是否为交易日

        Examples:
            >>> tf.is_trade_day(arrow.get('2020-1-1'))
            False

        Args:
            dt :

        Returns:
            [description]
        """
        moment = dt.date() if isinstance(dt, (Arrow, datetime.datetime)) else dt
        if self.day_frames is None:
            raise ValueError("交易日历未初始化，请先调用 load()")
        return self.day_frames.index(moment).as_py() >= 0

    def is_open_time(self, tm: datetime.datetime | Arrow | None = None) -> bool:
        """判断`tm`指定的时间是否处在交易时间段。

        交易时间段是指集合竞价时间段之外的开盘时间

        Examples:
            >>> tf.is_open_time(arrow.get('2020-1-1 14:59', tzinfo='Asia/Shanghai'))
            False
            >>> tf.is_open_time(arrow.get('2020-1-3 14:59', tzinfo='Asia/Shanghai'))
            True

        Args:
            tm : [description]. Defaults to None.

        Returns:
            [description]
        """
        tm = tm or datetime.datetime.now(tz=get_timezone())

        if not self.is_trade_day(tm):
            return False

        tick = tm.hour * 60 + tm.minute
        return tick in self.ticks[FrameType.MIN1]

    def is_opening_call_auction_time(self, tm: datetime.datetime | None = None) -> bool:
        """判断`tm`指定的时间是否为开盘集合竞价时间

        Args:
            tm : [description]. Defaults to None.

        Returns:
            [description]
        """
        if tm is None:
            tm = datetime.datetime.now(tz=get_timezone())

        if not self.is_trade_day(tm):
            return False

        minutes = tm.hour * 60 + tm.minute
        return 9 * 60 + 15 < minutes <= 9 * 60 + 25

    def is_closing_call_auction_time(self, tm: datetime.datetime | None = None) -> bool:
        """判断`tm`指定的时间是否为收盘集合竞价时间

        Fixme:
            此处实现有误，收盘集合竞价时间应该还包含上午收盘时间

        Args:
            tm : Defaults to None，使用系统时间
        """
        tm = tm or datetime.datetime.now(tz=get_timezone())

        if not self.is_trade_day(tm):
            return False

        minutes = tm.hour * 60 + tm.minute
        return 15 * 60 - 3 <= minutes < 15 * 60

    def get_frames(
        self, start: Frame, end: Frame, frame_type: FrameType
    ) -> list[datetime.date | datetime.datetime]:
        """取[start, end]间所有类型为frame_type的frames

        调用本函数前，请先通过`floor`或者`ceiling`将时间帧对齐到`frame_type`的边界值

        Example:
            >>> start = datetime.datetime(2020, 1, 13, 10, 0, tzinfo=get_timezone())
            >>> end = datetime.datetime(2020, 1, 13, 13, 30, tzinfo=get_timezone())
            >>> len(tf.get_frames(start, end, FrameType.MIN30))
            5

        Args:
            start:
            end:
            frame_type:

        Returns:

        """
        n = self.count_frames(start, end, frame_type)
        return self.get_frames_by_count(end, n, frame_type)

    def get_frames_by_count(
        self, end: datetime.datetime | datetime.date, n: int, frame_type: FrameType
    ) -> list[datetime.date | datetime.datetime]:
        """取以end为结束点,周期为frame_type的n个frame

        调用前请将`end`对齐到`frame_type`的边界

        Examples:
            >>> end = datetime.datetime(2020, 1, 6, 14, 30, tzinfo=get_timezone())
            >>> tf.get_frames_by_count(end, 2, FrameType.MIN30)
            [datetime.datetime(2020, 1, 6, 14, 0, tzinfo=get_timezone()),
             datetime.datetime(2020, 1, 6, 14, 30, tzinfo=get_timezone())]

        Args:
            end:
            n:
            frame_type:

        Returns:
            List[datetime.date|datetime.datetime]: 以end为结束点,周期为frame_type的n个frame
        """
        if frame_type in (FrameType.DAY, FrameType.WEEK, FrameType.MONTH):
            return _calendar_frames_by_count(self, end, n, frame_type)
        elif frame_type in {
            FrameType.MIN1,
            FrameType.MIN5,
            FrameType.MIN15,
            FrameType.MIN30,
            FrameType.MIN60,
        }:
            if not isinstance(end, datetime.datetime):
                raise TypeError("分钟周期需要 datetime 时间")
            n_days = n // len(self.ticks[frame_type]) + 2
            ticks = self.ticks[frame_type] * n_days

            days = self.get_frames_by_count(
                end.date() if isinstance(end, datetime.datetime) else end,
                n_days,
                FrameType.DAY,
            )
            repeated_days = np.repeat(
                np.asarray(days, dtype="datetime64[ms]"), len(self.ticks[frame_type])
            )

            np_timedeltas = [np.timedelta64(t, "m") for t in ticks]

            buckets = repeated_days + np_timedeltas

            # a[i-] < v <= a[i]
            pos = int(buckets.searchsorted(np.datetime64(end))) + 1
            result = buckets[max(0, pos - n + 1) : pos + 1]

            if end.tzinfo is None:
                return cast(list[Frame], result.tolist())

            # 回补时区信息
            return [x.astype(datetime.datetime).replace(tzinfo=end.tzinfo) for x in result]
        else:  # pragma: no cover
            raise ValueError(f"{frame_type} not support yet")

    def replace_time(
        self,
        date: datetime.date,
        hour: int,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tzinfo: str | datetime.tzinfo = "Asia/Shanghai",
    ) -> datetime.datetime:
        """用`date`指定的日期与`hour`, `minute`, `second`等参数一起合成新的时间

        Examples:
            >>> tf.replace_time(datetime.date(2020, 1, 1), 14, 30)
            datetime.datetime(2020, 1, 1, 14, 30, tzinfo='Asia/Shanghai')

        Args:
            date : [description]
            hour : [description]
            minute : [description]. Defaults to 0.
            second : [description]. Defaults to 0.
            microsecond : [description]. Defaults to 0.

        Returns:
            [description]
        """
        tz = ZoneInfo(tzinfo) if isinstance(tzinfo, str) else tzinfo
        return datetime.datetime(
            date.year,
            date.month,
            date.day,
            hour,
            minute,
            second,
            microsecond,
            tzinfo=tz,
        )

    def replace_date(
        self, dtm: datetime.time | datetime.datetime, dt: datetime.date
    ) -> datetime.datetime:
        """将`dtm`变量的日期更换为`dt`指定的日期

        Example:
            >>> tf.replace_date(arrow.get('2020-1-1 13:49').datetime, datetime.date(2019, 1,1))
            datetime.datetime(2019, 1, 1, 13, 49)

        Args:
            sel ([type]): [description]
            dtm (datetime.datetime): [description]
            dt (datetime.date): [description]

        Returns:
            datetime.datetime: [description]
        """
        return datetime.datetime(
            dt.year, dt.month, dt.day, dtm.hour, dtm.minute, dtm.second, dtm.microsecond
        )

    def get_trade_dates(self, start: datetime.date, end: datetime.date) -> list[datetime.date]:
        """获取指定日期范围内所有的交易日

        Args:
            start: 开始日期（包含）
            end: 结束日期（包含）

        Returns:
            List[datetime.date]: 指定范围内所有交易日的列表，按日期升序排列

        Raises:
            ValueError: 如果start > end则抛出异常
        """
        if start > end:
            raise ValueError(f"开始日期 {start} 不能大于结束日期 {end}")

        table = self._data
        if table is None:
            raise ValueError("交易日历未初始化，请先调用 load()")
        date_col = table.column("date")
        is_open_col = table.column("is_open")
        start_mask = pc.greater_equal(date_col, pa.scalar(start))
        end_mask = pc.less_equal(date_col, pa.scalar(end))
        open_mask = pc.equal(is_open_col, pa.scalar(1))

        combined_mask = pc.and_(pc.and_(start_mask, end_mask), open_mask)

        filtered_table = table.filter(combined_mask)

        filtered_dates = filtered_table.column("date")
        return [cast(datetime.date, date.as_py()) for date in filtered_dates]

    def count_trading_days(self, start: datetime.date, end: datetime.date) -> int:
        """[start, end] 区间内的交易日数(含起止)。

        spec FR-014 命名;等价于 count_day_frames。
        spec AC-014-03-03: start == end 且非交易日 → 0
        """
        if start > end:
            raise ValueError(f"开始日期 {start} 不能大于结束日期 {end}")
        # spec AC-014-03-03: start == end 且非交易日 → 0
        if start == end and not self.is_trade_day(start):
            return 0
        return self.count_day_frames(start, end)


calendar = Calendar()
