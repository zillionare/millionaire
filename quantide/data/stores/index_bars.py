"""指数行情存储类.

读取本地已落盘数据属于正常能力；主体侧不再提供指数抓取入口。
"""

import datetime
from collections.abc import Callable
from pathlib import Path

import polars as pl

from quantide.data.models.calendar import Calendar
from quantide.data.stores.bar_store import BarStore

_REMOVED_MESSAGE = "指数抓取功能已从 quantide 主体移除。"


class IndexBarsStore(BarStore):
    """指数行情存储类

    使用 Parquet 文件存储，按年分区。
    字段：symbol, date, open, high, low, close, volume, amount
    """

    def __init__(self, path: str | Path, calendar: Calendar) -> None:
        """初始化指数行情存储

        Args:
            path: 存储路径（目录）
            calendar: 日历对象
        """
        super().__init__("IndexBars", path, calendar, "sector_id")

    def get(
        self,
        symbols: list[str] | None = None,
        start: datetime.date | datetime.datetime | None = None,
        end: datetime.date | datetime.datetime | None = None,
        eager_mode: bool = True,
    ) -> pl.DataFrame | pl.LazyFrame:
        """获取指数行情数据

        Args:
            symbols: 指数代码列表，None 表示所有指数
            start: 开始日期
            end: 结束日期
            eager_mode: 是否立即执行

        Returns:
            行情数据 DataFrame 或 LazyFrame
        """
        return self._read_bars(symbols, start, end, eager_mode, full_day=False)

    def fetch(
        self,
        symbol: str,
        start: datetime.date,
        end: datetime.date,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> int:
        """获取并保存指数行情数据

        Args:
            symbol: 指数代码
            start: 开始日期
            end: 结束日期
            progress_callback: 进度回调函数 (current, total, message)

        Returns:
            获取的记录数
        """
        raise RuntimeError(_REMOVED_MESSAGE)
