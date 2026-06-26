import datetime
from pathlib import Path

import polars as pl
from loguru import logger

from quantide.config.settings import get_timezone
from quantide.core.enums import FrameType
from quantide.core.ports import DataFetcherPort
from quantide.core.singleton import singleton
from quantide.data.fetchers.registry import get_data_fetcher
from quantide.data.helper import hfq_adjustment, qfq_adjustment
from quantide.data.models.calendar import Calendar
from quantide.data.stores.base import ParquetStorage


@singleton
class DailyBars(ParquetStorage):
    """日线行情数据存储与查询。

    继承 ParquetStorage 提供统一的存储、更新和查询能力。
    .store 属性返回 self，保持向后兼容。
    """

    def __init__(self):
        # 占位初始化；connect() 会用真实路径重新初始化 ParquetStorage
        ParquetStorage.__init__(
            self,
            store_name="DailyBars",
            store_path="/dev/null",
            calendar=Calendar(),
            fetch_data_func=None,
        )
        self._calendar: Calendar | None = None
        self._data_fetcher: DataFetcherPort | None = None
        self._initialized = False

    def connect(self, store_path: str | Path, calendar_store_path: str | Path) -> None:
        if self._initialized:
            logger.warning("重加载 daily bars store")

        self._calendar = Calendar().load(calendar_store_path)
        self._data_fetcher = get_data_fetcher()

        path = Path(store_path).expanduser()
        partition_by = None if path.suffix == ".parquet" else "year"

        # 用真实路径重新初始化 ParquetStorage
        ParquetStorage.__init__(
            self,
            store_name="DailyBars",
            store_path=path,
            calendar=self._calendar,
            fetch_data_func=self._fetch_bars_ext,
            error_handler=None,
            partition_by=partition_by,
        )
        self._initialized = True

    @property
    def store(self) -> "DailyBars":
        """向后兼容属性：返回 self。

        合并 DailyBarsStore 后，DailyBars 自身即为存储层。
        旧代码 ``daily_bars.store.update()`` 等价于 ``daily_bars.update()``。
        """
        if not self._initialized:
            raise RuntimeError("daily bars store 未初始化，请先调用 connect()")
        return self

    def _fetch_bars_ext(
        self,
        dates: list[datetime.date] | datetime.date,
        phase_callback=None,
    ):
        return self._data_fetcher.fetch_bars_ext(dates, phase_callback=phase_callback)

    def rec_counts_per_date(
        self, start: datetime.date | None = None, end: datetime.date | None = None
    ) -> dict[datetime.date, int]:
        """获取每个交易日期的记录数量统计。"""
        lazy = self._scan_store(keep_partition_col=False)
        lazy = lazy.with_columns(pl.col("date").cast(pl.Date))

        if start is not None:
            lazy = lazy.filter(pl.col("date").dt.strftime("%F") >= start.isoformat())
        if end is not None:
            lazy = lazy.filter(pl.col("date").dt.strftime("%F") <= end.isoformat())
        df = lazy.group_by("date").agg(pl.len().alias("n")).collect()
        dates = df["date"].to_list()
        counts = df["n"].to_list()
        result: dict[datetime.date, int] = {}
        for d, c in zip(dates, counts, strict=True):
            result[d] = int(c)
        return result

    def _normalize_bar_schema(
        self, frame: pl.DataFrame | pl.LazyFrame
    ) -> pl.DataFrame | pl.LazyFrame:
        if isinstance(frame, pl.LazyFrame):
            columns = set(frame.collect_schema().names())
        else:
            columns = set(frame.columns)

        if "st" in columns and "is_st" not in columns:
            frame = frame.rename({"st": "is_st"})
            columns.remove("st")
            columns.add("is_st")

        exprs: list[pl.Expr] = []
        if "volume" in columns:
            exprs.append(pl.col("volume").cast(pl.Float64).alias("volume"))
        if "is_st" in columns:
            exprs.append(pl.col("is_st").fill_null(False).cast(pl.Boolean).alias("is_st"))

        if exprs:
            frame = frame.with_columns(exprs)
        return frame

    def get_bars_in_range(
        self,
        start: datetime.date | datetime.datetime,
        end: datetime.date | datetime.datetime | None = None,
        assets: list[str] | None = None,
        adjust: str | None = "qfq",
        eager_mode: bool = True,
    ) -> pl.DataFrame | pl.LazyFrame:
        """获取指定日期范围内的日线数据。

        参数：
            assets: 需要获取的股票列表
            start: 开始日期/时间
            end: 结束日期/时间，默认为 None，表示获取缓存中最后一个交易日
        """
        if adjust not in ("qfq", "hfq"):
            raw = self.get(assets, start, end, eager_mode=eager_mode)
            return self._normalize_bar_schema(raw)

        lf = self._normalize_bar_schema(
            self.get(assets, start, end, eager_mode=False)
        )
        if adjust == "qfq":
            return qfq_adjustment(lf, eager_mode=eager_mode)
        else:
            return hfq_adjustment(lf, eager_mode=eager_mode)

    def get_bars(
        self,
        n: int,
        end: datetime.date | datetime.datetime | None = None,
        assets: list[str] | None = None,
        adjust: str | None = "qfq",
        eager_mode: bool = True,
    ) -> pl.DataFrame | pl.LazyFrame:
        """获取最近 n 个交易日的行情数据

        Args:
            n (int): 最近 n 个交易日
            end (datetime.date | datetime.datetime | None, optional): 结束日期/时间，默认为 None，表示获取缓存中最后一个交易日。 Defaults to None.
            assets (list[str] | None, optional): 获取指定股票的行情数据，默认为 None，表示获取所有股票。 Defaults to None.
        """
        assert self._calendar is not None

        if end is None:
            end = datetime.datetime.now(tz=get_timezone())
        end_date = self._calendar.floor(end, FrameType.DAY)
        start_date = self._calendar.shift(end_date, -n + 1, FrameType.DAY)

        return self.get_bars_in_range(
            start_date, end_date, assets, adjust=adjust, eager_mode=eager_mode
        )

    def get_price(
        self,
        asset: str,
        date: datetime.date | datetime.datetime,
        adjust: str | None = None,
    ) -> tuple[float]:
        """返回`date`日（时间）的`asset`的收盘价、涨跌停价

        Args:
            asset (str): 资产代码
            date (datetime.date | datetime.datetime): 日期
            adjust (str | None, optional): 复权类型。默认为None
        """
        df = self.get_bars(1, end=date, assets=[asset], eager_mode=True, adjust=adjust)

        return df.select(pl.col("close"), pl.col("up_limit"), pl.col("down_limit")).row(
            0
        )

    def get_trade_price_limits(
        self, asset: str, dt: datetime.date
    ) -> tuple[float, float]:
        """获取指定资产在指定日期的涨跌停限价。

        Returns:
            (down_limit, up_limit)
        """
        # 获取当天行情
        df = self.get_bars(1, end=dt, assets=[asset], adjust=None, eager_mode=True)
        if df.is_empty():
            return 0.0, 0.0

        row = df.row(0, named=True)
        return row.get("down_limit", 0.0), row.get("up_limit", 0.0)

    def get_close_adjust_factor(
        self, assets: list[str], start: datetime.date, end: datetime.date
    ) -> pl.DataFrame:
        """获取指定日期范围内的收盘价和复权因子。

        Args:
            assets: 资产列表
            start: 开始日期
            end: 结束日期

        Returns:
            pl.DataFrame: 包含字段 [date, asset, close, adjust]
        """
        cols = ["date", "asset", "close", "adjust"]
        lf = self.get(assets, start, end, cols=cols, eager_mode=False)
        return lf.with_columns(pl.col("date").cast(pl.Date)).collect()

    def get_price_for_match(self, asset: str, tm: datetime.datetime) -> pl.DataFrame:
        """获取用于撮合的行情数据。"""
        # 对于日线级别，返回当天的 bar
        dt = tm.date() if isinstance(tm, datetime.datetime) else tm
        df = self.get_bars_in_range(
            dt, dt, assets=[asset], adjust=None, eager_mode=True
        )
        return df


daily_bars = DailyBars()
