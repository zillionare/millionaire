"""涨跌停限价存储类.

每日每只股票的涨跌停价格。
历史限价随日线一起抓取并写入 ``daily_bars``；本存储保存**当日早晨**
Tushare ``stk_limit`` 的结果，使 Paper 撮合与 30 分钟线读取不必等待
当日日线入库。运行时由 ``LimitPriceRefresher`` 写入。

字段：date, asset, up_limit, down_limit
"""

import datetime
from pathlib import Path
from typing import Literal

import polars as pl

from quantide.data.models.calendar import Calendar
from quantide.data.stores.base import ParquetStorage


class LimitPriceStore(ParquetStorage):
    """涨跌停限价存储。"""

    def __init__(self, path: str | Path, calendar: Calendar) -> None:
        """初始化涨跌停存储。

        Args:
            path: 存储路径（目录或 .parquet 文件）。
            calendar: 日历对象。
        """
        path = Path(path).expanduser()
        partition_levels: tuple[Literal["year", "month", "day"], ...] | None = (
            None if path.suffix == ".parquet" else ("year", "month")
        )
        super().__init__(
            "LimitPrice",
            path,
            calendar,
            None,
            error_handler=None,
            partition_levels=partition_levels,
            date_as_date=True,
        )

    def get_limits(
        self,
        asset: str,
        dt: datetime.date,
    ) -> tuple[float, float]:
        """返回某资产某日的 (down_limit, up_limit)；缺失返回 (0.0, 0.0)。"""
        frame = self.get(assets=[asset], start=dt, end=dt, eager_mode=True)
        if isinstance(frame, pl.LazyFrame):
            frame = frame.collect()
        if frame is None or frame.is_empty():
            return 0.0, 0.0
        row = frame.row(0, named=True)
        return (
            float(row.get("down_limit") or 0.0),
            float(row.get("up_limit") or 0.0),
        )

    def limits_map(
        self,
        dt: datetime.date,
        assets: list[str] | None = None,
    ) -> dict[str, tuple[float, float]]:
        """返回某日全部（或指定）资产的涨跌停映射。"""
        frame = self.get(assets=assets, start=dt, end=dt, eager_mode=True)
        if isinstance(frame, pl.LazyFrame):
            frame = frame.collect()
        if frame is None or frame.is_empty():
            return {}
        result: dict[str, tuple[float, float]] = {}
        for row in frame.iter_rows(named=True):
            result[str(row["asset"])] = (
                float(row.get("down_limit") or 0.0),
                float(row.get("up_limit") or 0.0),
            )
        return result
