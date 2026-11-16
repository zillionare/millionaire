"""PartitionOperations implementation."""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import polars as pl

from quantide.core.atomic_files import write_parquet
from quantide.data.store_lock import locked_store


def _partition_key_bounds(
    level: str,
    value: str,
    start: datetime.date | None,
    end: datetime.date | None,
    year: int | None,
) -> tuple[Any, Any, Any]:
    """Compare years, months or days without duplicating range semantics."""
    if level == "partition_key_year":
        return int(value), start.year if start else None, end.year if end else None
    if level == "partition_key_month":
        if year is None:
            year, month = (int(part) for part in value.split("-"))
        else:
            month = int(value)
        return (
            (year, month),
            (start.year, start.month) if start else None,
            (end.year, end.month) if end else None,
        )
    if level == "partition_key_day":
        return datetime.date.fromisoformat(value), start, end
    raise ValueError("Unknown partition level")


class PartitionOperations:
    """PartitionOperations implementation."""

    if TYPE_CHECKING:
        _store_path: Path
        _partition_levels: tuple[str, ...]
        _partition_by: str | None
        _id_cols: list[str]
        _compression: str

        def _scan_store(self, keep_partition_col: bool = False) -> pl.LazyFrame | None: ...

    def _candidate_partition_files(
        self, start: datetime.date | None, end: datetime.date | None
    ) -> list[str]:
        """Visit only partition directories intersecting the requested date bounds."""
        if not self._store_path.exists():
            return []
        if not self._partition_levels:
            return sorted(str(path) for path in self._store_path.rglob("*.parquet"))
        return list(self._walk_partition_files(self._store_path, 0, None, start, end))

    def _walk_partition_files(
        self,
        path: Path,
        depth: int,
        year: int | None,
        start: datetime.date | None,
        end: datetime.date | None,
    ) -> Iterator[str]:
        if depth == len(self._partition_levels):
            yield from (str(file) for file in sorted(path.rglob("*.parquet")))
            return
        if not path.exists():
            return
        level = self._partition_levels[depth]
        for child in sorted(path.iterdir()):
            if not child.is_dir() or not child.name.startswith(f"{level}="):
                continue
            value = child.name[len(level) + 1 :]
            if not self._level_overlaps(level, value, start, end, year):
                continue
            next_year = year
            if level == "partition_key_year":
                try:
                    next_year = int(value)
                except ValueError:
                    next_year = None
            yield from self._walk_partition_files(child, depth + 1, next_year, start, end)

    def _level_overlaps(
        self,
        level: str,
        value: str,
        start: datetime.date | None,
        end: datetime.date | None,
        year: int | None = None,
    ) -> bool:
        """Keep unknown partitions; prune only when their parsed bounds prove exclusion."""
        try:
            key, lower, upper = _partition_key_bounds(level, value, start, end, year)
        except (TypeError, ValueError, AttributeError):
            return True
        return (lower is None or key >= lower) and (upper is None or key <= upper)

    def _scan_store_range(
        self,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        keep_partition_col: bool = False,
    ) -> pl.LazyFrame | None:
        """按日期范围扫描（多级分区下只打开命中的文件）。"""
        files = self._candidate_partition_files(start, end)
        if not files:
            return None
        lf = pl.scan_parquet(files, hive_partitioning=True)
        levels = self._partition_levels or ((self._partition_by,) if self._partition_by else ())
        if not keep_partition_col:
            for level in levels:
                if level in lf.collect_schema():
                    lf = lf.select(pl.exclude(level))
        return lf

    def _read_partition(
        self, start: Any = None, end: Any = None, keep_partition_col: bool = False
    ) -> pl.LazyFrame | None:
        lf = self._scan_store(keep_partition_col=True)
        if lf is None:
            return None
        assert self._partition_by is not None, "Partition column must be configured"

        filters = []
        if start is not None:
            filters.append(pl.col(self._partition_by) >= start)
        if end is not None:
            filters.append(pl.col(self._partition_by) <= end)
        if filters:
            lf = lf.filter(pl.all_horizontal(filters))

        if not keep_partition_col:
            lf = lf.select(pl.exclude(self._partition_by))
        return lf

    def _ensure_partition_col(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """补齐缺失的分区列（多级分区会补齐所有层级）。"""
        schema = lf.collect_schema()
        for level in self._partition_levels or (
            (self._partition_by,) if self._partition_by else ()
        ):
            if level in schema:
                continue
            if level == "partition_key_year":
                lf = lf.with_columns(pl.col("date").dt.year().cast(pl.Int64).alias(level))
            elif level == "partition_key_month":
                if self._partition_levels and len(self._partition_levels) > 1:
                    # 两级及以上：年已在上层目录，这里只放月份
                    lf = lf.with_columns(pl.col("date").dt.month().cast(pl.Int64).alias(level))
                else:
                    lf = lf.with_columns(pl.col("date").dt.strftime("%Y-%m").alias(level))
            elif level == "partition_key_day":
                lf = lf.with_columns(pl.col("date").dt.strftime("%Y-%m-%d").alias(level))
        return lf

    def _partition_value(self, level: str, v: datetime.date | datetime.datetime | None) -> Any:
        """单个分区层级对应的取值。"""
        if v is None:
            return None
        if level == "partition_key_year":
            return v.year
        if level == "partition_key_month":
            if self._partition_levels and len(self._partition_levels) > 1:
                return v.month
            return v.strftime("%Y-%m")
        if level == "partition_key_day":
            return v.strftime("%Y-%m-%d")
        return None

    def _to_partition_key(self, v: datetime.date | datetime.datetime | None) -> Any:
        if self._partition_by == "partition_key_year":
            return v.year if v is not None else None
        elif self._partition_by == "partition_key_month":
            if self._partition_levels and len(self._partition_levels) > 1:
                return v.month if v is not None else None
            return v.strftime("%Y-%m") if v is not None else None
        elif self._partition_by == "partition_key_day":
            return v.strftime("%Y-%m-%d") if v is not None else None

    def _partition_dirs(self, lf: pl.LazyFrame) -> list[tuple[tuple[str, ...], pl.LazyFrame]]:
        """按分区层级组合，把数据切分成 (目录键元组, 数据) 的列表。

        多级分区时目录形如 ``partition_key_year=2024/partition_key_month=03``。
        """
        if self._partition_levels:
            levels = self._partition_levels
        else:
            assert self._partition_by is not None, "Partition column must be configured"
            levels = (self._partition_by,)
        lf = self._ensure_partition_col(lf)
        keys = lf.select([pl.col(level) for level in levels]).unique().collect().rows()
        groups: list[tuple[tuple[str, ...], pl.LazyFrame]] = []
        for key in keys:
            mask = pl.all_horizontal(
                [pl.col(level) == value for level, value in zip(levels, key, strict=True)]
            )
            groups.append((tuple(str(v) for v in key), lf.filter(mask)))
        return groups

    def _partition_path(self, key: tuple[str, ...]) -> Path:
        """分区键元组对应的目录。"""
        if self._partition_levels:
            levels = self._partition_levels
        else:
            assert self._partition_by is not None, "Partition column must be configured"
            levels = (self._partition_by,)
        path = self._store_path
        for level, value in zip(levels, key, strict=True):
            path = path / f"{level}={self._format_partition_value(level, value)}"
        return path

    def _format_partition_value(self, level: str, value: str) -> str:
        """分区目录名的展示形式（月份补零便于排序）。"""
        if level == "partition_key_month":
            try:
                return f"{int(value):02d}"
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    def _read_partition_dir(self, path: Path) -> pl.LazyFrame | None:
        """读取一个分区目录下的全部 parquet。"""
        if not path.exists():
            return None
        files = sorted(path.rglob("*.parquet"))
        if not files:
            return None
        return pl.scan_parquet([str(f) for f in files], hive_partitioning=True)

    def _save_as_partition(self, lf: pl.LazyFrame | pd.DataFrame) -> None:
        if isinstance(lf, pd.DataFrame):
            lf = pl.from_pandas(lf).lazy()
        elif isinstance(lf, pl.DataFrame):
            lf = lf.lazy()

        levels = self._partition_levels or (self._partition_by,)
        for key, part_lf in self._partition_dirs(lf):
            partition_dir = self._partition_path(key)
            base_lf = self._read_partition_dir(partition_dir)
            if base_lf is None:
                group = [part_lf]
            else:
                group = [base_lf, part_lf]
            combined = (
                pl.concat(group).unique(subset=self._id_cols, keep="last").sort(self._id_cols)
            )
            partition_dir.mkdir(parents=True, exist_ok=True)
            output_file = partition_dir / "part-0.parquet"
            write_df = combined.collect()
            for level in levels:
                if level in write_df.columns:
                    write_df = write_df.drop(level)
            write_parquet(write_df, output_file, compression=self._compression)

    @locked_store
    def normalize_partition_schema(self, dry_run: bool = False) -> int:
        """把分区文件中类型不一致的 ``date`` 列统一为 pl.Date。

        历史数据可能由不同 fetcher 写入（``Date`` vs ``Datetime``），
        混用会导致读取时 concat 失败。此方法只重写需要修正的文件。

        Args:
            dry_run: 只统计不写盘。

        Returns:
            int: 修正的分区文件数量。
        """
        if self._partition_by is None or not self._store_path.exists():
            return 0
        fixed = 0
        for path in sorted(self._store_path.rglob("*.parquet")):
            try:
                schema = pl.read_parquet_schema(path)
            except Exception:  # pragma: no cover - 损坏文件跳过
                continue
            if "date" not in schema or schema["date"] == pl.Date:
                continue
            fixed += 1
            if dry_run:
                continue
            frame = pl.read_parquet(path).with_columns(pl.col("date").cast(pl.Date))
            write_parquet(frame, path, compression=self._compression)
        return fixed

    def repartition_to_levels(self, levels: tuple[str, ...], dry_run: bool = False) -> int:
        """把旧的单级分区数据一次性重写为多级分区。

        旧布局：``partition_key_year=2024/part-0.parquet``
        新布局：``partition_key_year=2024/partition_key_month=03/part-0.parquet``

        Args:
            levels: 目标分区层级（自粗到细）。
            dry_run: 只统计不写盘。

        Returns:
            int: 迁移的分区数量。
        """
        if not self._store_path.exists():
            return 0
        legacy_dirs = [
            path
            for path in sorted(self._store_path.iterdir())
            if path.is_dir()
            and path.name.startswith("partition_key_year=")
            and any(path.glob("*.parquet"))
        ]
        migrated = 0
        for legacy_dir in legacy_dirs:
            files = sorted(legacy_dir.glob("*.parquet"))
            if not files:
                continue
            frame = pl.read_parquet([str(f) for f in files])
            frame = frame.drop([c for c in frame.columns if c.startswith("partition_key_")])
            if dry_run:
                migrated += 1
                continue
            for (year, month), part in self._split_by_levels(frame, levels):
                target = (
                    self._store_path
                    / f"partition_key_year={year}"
                    / f"partition_key_month={month:02d}"
                )
                target.mkdir(parents=True, exist_ok=True)
                write_parquet(part, target / "part-0.parquet", compression=self._compression)
            for f in files:
                f.unlink()
            migrated += 1
        return migrated

    def _split_by_levels(
        self, frame: pl.DataFrame, levels: tuple[str, ...]
    ) -> list[tuple[tuple[int, int], pl.DataFrame]]:
        """按 (年, 月) 切分数据帧。"""
        work = frame.with_columns(pl.col("date").cast(pl.Date))
        keys = (
            work.select(
                [
                    pl.col("date").dt.year().alias("y"),
                    pl.col("date").dt.month().alias("m"),
                ]
            )
            .unique()
            .rows()
        )
        out: list[tuple[tuple[int, int], pl.DataFrame]] = []
        for year, month in sorted(keys):
            part = work.filter(
                (pl.col("date").dt.year() == year) & (pl.col("date").dt.month() == month)
            )
            out.append(((int(year), int(month)), part))
        return out
