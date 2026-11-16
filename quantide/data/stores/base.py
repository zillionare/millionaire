"""基础的数据存储和缓存类。在提供了 fetcher 方法的前提下，能够自动从数据源获取数据，

从而使得应用层无须操心本地数据是否全面。

需要与一个日历类一起使用。日历类的作用是，协助 fetcher 数据是否有缺失，是否要从远程获取。
一般使用 alpha.data.models.calendar；
但如果要处理的是财数据（或者任何在非交易日可能发布的数据，则子类需要将日历改写为自然日历，
以使得 Calendar.get_trade_dates能返回自然日历。
"""

from __future__ import annotations

import datetime
import glob
import hashlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Literal, overload

import pandas as pd
import polars as pl
from loguru import logger

from quantide.config.settings import get_timezone
from quantide.core.atomic_files import atomic_path, write_parquet
from quantide.core.enums import FrameType
from quantide.core.message import msg_hub
from quantide.data.models.calendar import Calendar
from quantide.data.store_lock import locked_store
from quantide.data.stores.bounds import _as_date_bound as _as_date_bound
from quantide.data.stores.bounds import _as_datetime_bound as _as_datetime_bound
from quantide.data.stores.partitions import PartitionOperations


def _scan_storage_range(
    end: datetime.date | None, self: ParquetStorage, start: datetime.date | None
) -> pl.LazyFrame | None:
    """Scan storage range."""
    if self._partition_by is None:
        lf = self._scan_store(keep_partition_col=False)
    else:
        lf = self._scan_store_range(
            start,
            end,
            keep_partition_col=False,
        )
        if lf is None:
            lf = self._read_partition(
                self._to_partition_key(start),
                self._to_partition_key(end),
                keep_partition_col=False,
            )
    return lf


class ParquetStorage(PartitionOperations):
    """基于Parquet文件的统一数据存储类。

    被存储的数据必须有使用"asset" 和 "date"的组合作为惟一的键值，以区分数据。

    在内部使用 Apache Arrow 和 polars 来管理数据，提供高性能的内存操作。

    获取数据的主要方法是 get_with_fetch, get, get_by_date. get_with_fetch 在数据不存在时，会调用
    fetch_data_func 获取数据并保存； get, get_by_date 则不会。

    更新数据的主要方法是 fetch 和 append_data。
    """

    def __init__(
        self,
        store_name: str,
        store_path: str | Path,
        calendar: Calendar,
        fetch_data_func: Callable[..., Any] | None = None,
        error_handler: Callable[[list[list[Any]]], None] | None = None,
        partition_by: Literal["year", "month", "day"] | None = None,
        partition_levels: tuple[Literal["year", "month", "day"], ...] | None = None,
        id_cols: list[str] | None = None,
        date_as_date: bool = False,
    ) -> None:
        """初始化ParquetStorage

        Args:
            store_name: 存储名称
            store_path: Parquet文件路径
            calendar: 日历模型
            fetch_data_func: 数据获取回调函数
            error_handler: 错误处理函数
            partition_by: 单级分区方式，可选 'year', 'month', 'day', None
            partition_levels: 多级分区（自粗到细），如 ``("year", "month")``；
                目录形如 ``partition_key_year=2024/partition_key_month=03/``。
                读取时只扫描命中的分区文件，避免数据量增长后读放大。
            id_cols: 去重主键列，默认 ``["date", "asset"]``；成分类数据可改为
                ``["date", "index_code", "con_code"]``。
            date_as_date: 写入时把 ``date`` 统一为 ``pl.Date``（默认保留原始类型）。
                日线/成分等跨 fetcher 混写的数据应设为 True，避免 Date/Datetime
                schema 冲突。
        """
        self.store_name = store_name
        self._id_cols = list(id_cols) if id_cols else ["date", "asset"]
        self._date_as_date = date_as_date
        self._store_path = Path(store_path).expanduser()

        if partition_by is not None and self._store_path.suffix == ".parquet":
            raise ValueError(
                f"partition_by is not allowed when store_path is a parquet file: {self._store_path}"
            )

        if partition_by is not None or partition_levels is not None:
            if not self._store_path.exists():
                self._store_path.mkdir(parents=True, exist_ok=True)
            assert self._store_path.is_dir(), f"store_path {self._store_path} must be a directory"

        self._fetch_data_func = fetch_data_func
        self._error_handler = error_handler or self.default_error_handler
        if partition_levels is not None:
            self._partition_levels: tuple[str, ...] = tuple(
                f"partition_key_{level}" for level in partition_levels
            )
            self._partition_by = self._partition_levels[-1]
        else:
            self._partition_levels = ()
            self._partition_by = (
                f"partition_key_{partition_by}" if partition_by is not None else None
            )

        self._calendar = calendar
        self._dates: pl.Series = pl.Series([], dtype=pl.Date)
        self._last_update_time: datetime.datetime | None = None

        # lz4是最快的压缩算法
        self._compression = "lz4"

        try:
            self._collect_dates()
        except Exception as e:
            logger.warning(f"ParquetStore {store_path} 初始化失败.{e}")
            self._dates = pl.Series([], dtype=pl.Date)

    def __str__(self) -> str:
        return f"{self._store_path.stem}[{self.start}-{self.end}]"

    def __len__(self) -> int:
        try:
            lf = self._scan_store(keep_partition_col=False)
            if lf is None:
                return 0
            return int(lf.select(pl.len()).collect().item())
        except Exception as e:
            logger.exception(e)
            logger.warning("ParquetStore读取{}失败", self._store_path)
            return 0

    def _scan_store(self, keep_partition_col: bool = False) -> pl.LazyFrame | None:
        """统一的 Parquet 扫描函数

        Args:
            keep_partition_col: 是否保留分区列 partition_key_*

        Returns:
            pl.LazyFrame | None: 懒加载的数据帧，如果无数据则返回 None
        """
        if self._partition_by is None:
            if not self._store_path.exists():
                return None
            lf = pl.scan_parquet(self._store_path)
        else:
            pattern = str(self._store_path / "**/*.parquet")
            if not glob.glob(pattern, recursive=True):
                return None
            lf = pl.scan_parquet(self._store_path / "**/*.parquet", hive_partitioning=True)
            if not keep_partition_col:
                lf = lf.select(pl.exclude(self._partition_by))
        return lf

    def rec_counts_per_date(
        self, start: datetime.date | None = None, end: datetime.date | None = None
    ) -> dict[datetime.date, int]:
        """Count records by trading date through one implementation for every bar store."""
        lazy = self._scan_store(keep_partition_col=False)
        if lazy is None:
            return {}
        lazy = lazy.with_columns(pl.col("date").cast(pl.Date))
        if start is not None:
            lazy = lazy.filter(pl.col("date") >= start)
        if end is not None:
            lazy = lazy.filter(pl.col("date") <= end)
        counts = lazy.group_by("date").agg(pl.len().alias("n")).collect()
        return {day: int(count) for day, count in counts.iter_rows()}

    def default_error_handler(self, errors: list[list[Any]]) -> None:
        """默认错误处理函数

        将抓取错误写入 failed_tasks 表，便于后续重试。
        # todo: 与 FailedTaskManager解耦
        """
        if isinstance(errors, Iterable):
            for error in errors:
                logger.error(error)

    def _dates_file_path(self) -> Path:
        """索引文件路径（每个分区存储独立，避免同一父目录下互相覆盖）。"""
        if self._partition_by is not None:
            return self._store_path.parent / f"{self._store_path.name}-dates.pq"
        else:
            return self._store_path.parent / f"{self.store_name}-dates.pq"

    def _update_dates(self, new_dates: pl.Series) -> None:
        """从文件中加载日期或更新日期范围

        Args:
            new_dates: 新的日期数据，用于更新日期范围
        """
        # 索引使用 Date 类型，便于与交易日历对齐
        dates = pl.Series(new_dates).cast(pl.Date)

        if len(self._dates) == 0:
            self._dates = dates.unique().sort()
        else:
            self._dates = pl.concat([self._dates, dates]).unique().sort()

        # 更新索引文件
        df = self._dates.to_frame("date")
        write_parquet(df, self._dates_file_path())

    def _storage_signature(self) -> str:
        """Fingerprint every committed partition; detect additions, changes and deletions."""
        paths = (
            sorted(self._store_path.rglob("*.parquet"))
            if self._partition_by is not None
            else [self._store_path]
        )
        digest = hashlib.sha256()
        for path in paths:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            digest.update(f"{path}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
        return digest.hexdigest()

    def _cached_dates(self, signature: str) -> bool:
        """Use the derived index only when it describes the current committed files."""
        try:
            marker = self._dates_file_path().with_suffix(".signature.json")
            if json.loads(marker.read_text(encoding="utf-8"))["sha256"] != signature:
                return False
            dates = pl.read_parquet(self._dates_file_path())["date"].cast(pl.Date)
            if dates.is_empty():
                return False
            self._dates = dates
            return True
        except (OSError, ValueError, KeyError, pl.exceptions.PolarsError):
            return False

    def _collect_dates(self) -> None:
        """Rebuild stale or damaged derived indexes from the durable Parquet data."""
        signature = self._storage_signature()
        if self._cached_dates(signature):
            return
        lf = self._scan_store(keep_partition_col=False)
        if lf is None:
            self._dates = pl.Series([], dtype=pl.Date)
        else:
            self._dates = (
                lf.select(pl.col("date").cast(pl.Date).alias("date"))
                .unique()
                .sort("date")
                .collect()
                .to_series()
            )
        # A concurrent writer must not give an old index a new fingerprint.
        if self._storage_signature() != signature:
            raise RuntimeError(
                "Storage changed while rebuilding date index; retry under store lock"
            )
        write_parquet(self._dates.to_frame("date"), self._dates_file_path())
        with atomic_path(self._dates_file_path().with_suffix(".signature.json")) as temporary:
            temporary.write_text(json.dumps({"sha256": signature}), encoding="utf-8")

    def _save_single(self, lf: pl.LazyFrame | pd.DataFrame) -> None:
        """保存非分区数据"""
        if isinstance(lf, pd.DataFrame):
            lf = pl.from_pandas(lf).lazy()

        group = []
        if not self._store_path.exists():
            group = [lf]
        else:
            base_lf = self._scan_store(keep_partition_col=False)
            if base_lf is None:
                group = [lf]
            else:
                group = [base_lf, lf]

        combined = pl.concat(group).unique(subset=self._id_cols, keep="last").sort(self._id_cols)
        # todo: this cause PanicException, need to check
        # combined.sink_parquet(self._store_path,compression=self._compression, mkdir = True)
        write_parquet(
            combined.collect(), self._store_path, compression=self._compression, mkdir=True
        )

    def fetch(
        self,
        start: datetime.date,
        end: datetime.date,
        use_calendar: bool = True,
        now: datetime.time = datetime.time(hour=16),
        force: bool = False,
    ) -> None:
        """下载数据并保存到本 store 中"""
        # 不使用交易日历时，一次性获取并写入
        if not use_calendar:
            assert self._fetch_data_func is not None
            df, errors = self._fetch_data_func(start, end)
            self._error_handler(errors)
            self.append_data(df)
            return

        start = self._calendar.ceiling(start, FrameType.DAY)
        end_tm = self._calendar.replace_date(now, end)
        end = self._calendar.floor(end_tm, FrameType.DAY)

        expected_dates = self._calendar.get_frames(start, end, FrameType.DAY)
        # 按升序准备缺失日期列表

        if force:
            missing_dates = sorted(expected_dates)
        else:
            missing_dates = sorted(set(expected_dates) - set(self._dates.to_list()))

        if len(missing_dates) == 0:
            try:
                msg_hub.publish(
                    topic="fetch_data_progress",
                    msg_content={"msg": "本地数据已最新，无需更新"},
                )
                msg_hub.publish(topic="fetch_data_progress", msg_content=None)
            except Exception:
                pass
            return

        if self._fetch_data_func is None:
            raise ValueError("缓存中没有足够的数据，且未提供fetch_data_func方法")

        # 根据分区策略分片
        chunks = self._group_dates(missing_dates)
        for i, chunk in enumerate(chunks, start=1):
            df, errors = self._fetch_data_func(chunk)
            self._error_handler(errors)
            # 分片获取完成后立即写盘，增强断点续传
            self.append_data(df)
            try:
                if isinstance(df, pd.DataFrame) and "date" in df.columns:
                    new_dates = pd.to_datetime(df["date"]).dt.date.unique().tolist()
                    self._update_dates(pl.Series(new_dates))
            except Exception:
                pass
            logger.info(
                "分片写入进度 {}/{}，日期范围 [{} ~ {}]",
                i,
                len(chunks),
                chunk[0],
                chunk[-1],
            )

        try:
            msg_hub.publish(topic="fetch_data_progress", msg_content=None)
        except Exception:
            pass

        # 重新收集日期缓存，确保 _dates 刷新到最新范围
        self._collect_dates()

    def fetch_with_daily_progress(
        self,
        start: datetime.date,
        end: datetime.date,
        progress_callback: Callable[..., None] | None = None,
        force: bool = False,
    ) -> int:
        """Download each requested session, raising on incomplete data."""
        from quantide.data.stores.daily_progress import download_days

        return download_days(self, start, end, progress_callback, force)

    def get_and_fetch(
        self,
        start: datetime.date,
        end: datetime.date,
        use_calendar: bool = True,
        eager_mode: bool = True,
    ) -> pl.DataFrame | pl.LazyFrame:
        """根据指定的日期范围加载数据。

        如果本地缓存中包含完整的数据，则从缓存中加载；
        如果数据不足，则调用fetch_data_func方法获取数据。

        Args:
            start: 开始日期
            end: 结束日期
            use_calendar: 是否使用交易日历

        Returns:
            pl.DataFrame: 包含指定日期范围内数据的polars DataFrame

        Raises:
            ValueError: 如果未提供fetch_data_func且缓存中没有足够数据
        """
        self.fetch(start, end, use_calendar)

        return self.get(start=start, end=end, eager_mode=eager_mode)

    def update(self) -> None:
        """更新数据到最新的交易日

        从当前存储的最后日期开始，更新到最近的交易日。
        如果存储为空，则从一个默认的起始日期开始。
        """
        start = self.end or self._calendar.epoch

        now = datetime.datetime.now(tz=get_timezone())
        end = self._calendar.floor(now, FrameType.DAY)

        logger.info("开始更新日线数据: {} 到 {}", start, end)

        # 如果当前已有数据的结束日晚于对齐的交易日，则无需更新
        if start is not None and end is not None and start > end:
            self._last_update_time = now
            logger.info("无需更新：start({}) > end({})", start, end)
            return

        self.fetch(start, end)

        self._last_update_time = now
        logger.info("日线数据更新完成")

    @locked_store
    def append_data(self, df: pd.DataFrame | pl.DataFrame | pl.LazyFrame) -> None:
        """追加数据到Parquet文件

        如果新数据与现有数据有重叠，会自动去重，保留最新的数据。
        数据在写入前会按 date 和 asset 排序，以优化查询性能。

        在分区模式下，会使用增量追加策略，避免读取整个文件。

        Args:
            df: 要追加的数据，支持 pandas DataFrame、polars DataFrame 或 LazyFrame
        """
        if df is None:
            return

        # 统一为 LazyFrame
        if isinstance(df, pd.DataFrame):
            if len(df) == 0:
                return
            lf = pl.from_pandas(df).lazy()
        elif isinstance(df, pl.DataFrame):
            if len(df) == 0:
                return
            lf = df.lazy()
        elif isinstance(df, pl.LazyFrame):
            lf = df
        else:
            raise TypeError("Unsupported data type for append_data")
        # 日期列统一为 pl.Date：不同 fetcher 可能产出 datetime64，
        # 与既有分区（Date）合并时会触发 schema 冲突。
        if self._date_as_date and "date" in lf.collect_schema().names():
            lf = lf.with_columns(pl.col("date").cast(pl.Date))
        if self._partition_by is None:
            # 非分区模式
            self._save_single(lf)
        else:
            # 分区模式
            self._save_as_partition(lf)

        new_dates = (
            lf.select(pl.col("date").cast(pl.Date).alias("date"))
            .unique()
            .collect()
            .get_column("date")
        )
        self._update_dates(new_dates)

    @property
    def start(self) -> datetime.date | None:
        """获取数据起始日期"""
        return self._dates[0] if len(self._dates) > 0 else None

    @property
    def end(self) -> datetime.date | None:
        """获取数据终止日期"""
        return self._dates[-1] if len(self._dates) > 0 else None

    @property
    def total_dates(self) -> int:
        return len(self._dates)

    @property
    def size(self) -> int:
        return len(self)

    @property
    def available_dates(self) -> list[datetime.date]:
        return self._dates.to_list()

    @property
    def last_update_time(self) -> datetime.datetime | None:
        """获取数据最后更新时间"""
        return self._last_update_time

    @overload
    def get(
        self,
        assets: list[str] | str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        cols: list[str] | None = None,
        eager_mode: Literal[True] = True,
    ) -> pl.DataFrame: ...

    @overload
    def get(
        self,
        assets: list[str] | str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        cols: list[str] | None = None,
        *,
        eager_mode: Literal[False],
    ) -> pl.LazyFrame: ...

    @overload
    def get(
        self,
        assets: list[str] | str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        cols: list[str] | None = None,
        eager_mode: bool = True,
    ) -> pl.LazyFrame | pl.DataFrame: ...

    def get(
        self,
        assets: list[str] | str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        cols: list[str] | None = None,
        eager_mode: bool = True,
    ) -> pl.LazyFrame | pl.DataFrame:
        """根据指定的日期范围加载数据

        Args:
            start: 开始日期，None表示从最早开始
            end: 结束日期，None表示到最晚
            columns: 要查询的列名，None表示所有列
            eager_mode: 是否立即执行查询，默认True

        Returns:
            polars DataFrame格式的数据

        Raises:
            ValueError: 如果文件不存在且没有提供fetch_data_func
        """
        lf = _scan_storage_range(end, self, start)

        if lf is None:
            if eager_mode:
                return pl.DataFrame()
            else:
                return pl.LazyFrame()

        filters = []
        if assets is not None:
            if isinstance(assets, str):
                assets = [assets]
            filters.append(pl.col("asset").is_in(assets))

        if start is not None:
            filters.append(pl.col("date") >= _as_datetime_bound(start))

        if end is not None:
            filters.append(pl.col("date") <= _as_datetime_bound(end))

        if filters:
            lf = lf.filter(pl.all_horizontal(filters))

        if cols:
            lf = lf.select(cols)

        if eager_mode:
            return lf.collect()
        else:
            return lf

    @overload
    def get_by_date(
        self, date: datetime.date, eager_mode: Literal[True] = True
    ) -> pl.DataFrame: ...

    @overload
    def get_by_date(self, date: datetime.date, *, eager_mode: Literal[False]) -> pl.LazyFrame: ...

    @overload
    def get_by_date(
        self, date: datetime.date, eager_mode: bool = True
    ) -> pl.DataFrame | pl.LazyFrame: ...

    def get_by_date(
        self, date: datetime.date, eager_mode: bool = True
    ) -> pl.DataFrame | pl.LazyFrame:
        """查询截面数据

        Args:
            date: 要查询的日期

        Returns:
            polars DataFrame格式的截面数据
        """
        if self._partition_by is None:
            lf = self._scan_store(keep_partition_col=False)
            if lf is not None:
                lf = lf.filter(pl.col("date") == _as_datetime_bound(date))
        else:
            lf = self._read_partition(
                start=self._to_partition_key(date),
                end=self._to_partition_key(date),
                keep_partition_col=False,
            )
            if lf is not None:
                lf = lf.filter(pl.col("date") == _as_datetime_bound(date))

        if lf is None:
            if eager_mode:
                return pl.DataFrame()
            else:
                return pl.LazyFrame()

        if eager_mode:
            return lf.collect()
        else:
            return lf

    def _group_dates(self, dates: list[datetime.date]) -> list[list[datetime.date]]:
        """根据分区策略对缺失日期进行分组

        - None/月分区：按月分组，避免批次过大
        - 年分区：按年分片
        - 日分区：按天分片（分钟线等细粒度）
        """

        # 内部 _partition_by 使用 partition_key_* 命名
        def key_fn(day: datetime.date) -> str:
            if self._partition_by == "partition_key_year":
                return day.strftime("%Y")
            if self._partition_by == "partition_key_day":
                return day.isoformat()
            return day.strftime("%Y-%m")

        groups: dict[str, list[datetime.date]] = {}
        for dt in dates:
            k = key_fn(dt)
            groups.setdefault(k, []).append(dt)
        return [groups[k] for k in sorted(groups.keys())]
