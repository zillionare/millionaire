"""指数成分（PIT）存储类.

按「快照日 + 指数 + 成分股」长表存储，支持 point-in-time 查询：
给定决策日，返回**当日可见**的成分（取 trade_date <= 决策日 的最近一期快照）。

存储布局：``partition_key_year=YYYY/partition_key_month=MM/part-0.parquet``
主键：``(date, index_code, con_code)``
"""

import datetime
from pathlib import Path
from typing import Literal

import polars as pl

from quantide.data.models.calendar import Calendar
from quantide.data.stores.base import ParquetStorage

#: 常见宽基指数及其中文名（发行版内置的关注清单）
DEFAULT_INDEX_CODES: dict[str, str] = {
    "000001.SH": "上证指数",
    "000016.SH": "上证50",
    "000300.SH": "沪深300",
    "000852.SH": "中证1000",
    "000903.SH": "中证A100",
    "000905.SH": "中证500",
    "000985.CSI": "中证全指",
    "399006.SZ": "创业板指",
    "932000.CSI": "中证2000",
}


class IndexWeightStore(ParquetStorage):
    """指数成分快照存储（point-in-time）。

    字段：date（快照日）, index_code, con_code, weight
    """

    def __init__(self, path: str | Path, calendar: Calendar) -> None:
        """初始化成分存储。

        Args:
            path: 存储路径（目录）。
            calendar: 日历对象。
        """
        path = Path(path).expanduser()
        partition_levels: tuple[Literal["year", "month", "day"], ...] | None = (
            None if path.suffix == ".parquet" else ("year", "month")
        )
        super().__init__(
            "IndexWeight",
            path,
            calendar,
            None,
            error_handler=None,
            partition_levels=partition_levels,
            id_cols=["date", "index_code", "con_code"],
            date_as_date=True,
        )

    def constituents(
        self,
        index_code: str,
        as_of: datetime.date | None = None,
        include_weight: bool = True,
    ) -> pl.DataFrame:
        """返回某指数在 ``as_of`` 当日**可见**的成分。

        PIT 语义：取 ``date <= as_of`` 的最近一个快照日（严格无前视）。

        Args:
            index_code: 指数代码，如 ``000300.SH``。
            as_of: 决策日；None 表示最新快照。
            include_weight: 是否返回 weight 列。

        Returns:
            pl.DataFrame: 成分列表（含 date/index_code/con_code[/weight]）。
        """
        lf = self._scan_store(keep_partition_col=False)
        if lf is None:
            return pl.DataFrame()
        lf = lf.filter(pl.col("index_code") == index_code)
        if as_of is not None:
            lf = lf.filter(
                pl.col("date")
                <= pl.lit(
                    datetime.datetime.combine(as_of, datetime.time.min), dtype=pl.Datetime("ms")
                )
            )
        snapshot_dates = (
            lf.select(pl.col("date").cast(pl.Date))
            .unique()
            .sort("date")
            .collect()
            .get_column("date")
        )
        if not len(snapshot_dates):
            return pl.DataFrame()
        latest = snapshot_dates[-1]
        out = lf.filter(pl.col("date").cast(pl.Date) == latest).collect().sort("con_code")
        if not include_weight and "weight" in out.columns:
            out = out.drop("weight")
        return out

    def snapshot_dates(self, index_code: str | None = None) -> list[datetime.date]:
        """列出某指数（或全部指数）已有的快照日。"""
        lf = self._scan_store(keep_partition_col=False)
        if lf is None:
            return []
        if index_code is not None:
            lf = lf.filter(pl.col("index_code") == index_code)
        return (
            lf.select(pl.col("date").cast(pl.Date))
            .unique()
            .sort("date")
            .collect()
            .get_column("date")
            .to_list()
        )

    def coverage(self) -> dict[str, dict[str, object]]:
        """统计各指数的成分快照覆盖情况（起始日/末期/期数）。

        发行版 UI 用它告诉用户"这个指数从哪年开始才有成分"。
        """
        lf = self._scan_store(keep_partition_col=False)
        if lf is None:
            return {}
        df = (
            lf.with_columns(pl.col("date").cast(pl.Date).alias("date"))
            .group_by(["index_code", "date"])
            .agg(pl.len().alias("n"))
            .collect()
        )
        result: dict[str, dict[str, object]] = {}
        for code, part in df.group_by("index_code"):
            key = str(code[0] if isinstance(code, tuple) else code)
            dates = sorted(part["date"].to_list())
            result[key] = {
                "name": DEFAULT_INDEX_CODES.get(key, key),
                "start": dates[0] if dates else None,
                "end": dates[-1] if dates else None,
                "snapshots": len(dates),
            }
        return result
