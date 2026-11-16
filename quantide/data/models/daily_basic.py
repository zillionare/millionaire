"""Daily market-cap data used by universe filters.

The daily bars store intentionally contains only OHLCV / adjustment data.
Market-cap based universe rules need point-in-time ``total_mv`` / ``circ_mv``
from Tushare ``daily_basic``; keeping it in a separate parquet file avoids
changing the daily-bar schema and keeps the join optional.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from filelock import FileLock
from loguru import logger

from quantide.config.output_paths import external_runtime_path
from quantide.config.settings import get_data_home, get_tushare_token
from quantide.core.atomic_files import write_parquet
from quantide.core.singleton import singleton
from quantide.data.coverage import require_date_coverage, trading_sessions

if TYPE_CHECKING:
    import pandas as pd


@singleton
class DailyBasic:
    """Point-in-time market-cap store.

    The file is a single parquet file with ``date, asset, total_mv, circ_mv``.
    ``total_mv`` is Tushare's unit (10k CNY); only relative ranking is used by
    the universe filter, so no unit conversion is applied.
    """

    def __init__(self) -> None:
        self._path: Path | None = None
        self._data: pl.DataFrame = pl.DataFrame()
        self._loaded = False

    @staticmethod
    def _default_path() -> Path:
        return Path(get_data_home()) / "data/daily_basic.parquet"

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else self._default_path()

    @property
    def is_available(self) -> bool:
        return self.path.exists()

    @property
    def data(self) -> pl.DataFrame:
        return self._data

    def connect(self, path: str | Path) -> DailyBasic:
        self._path = Path(path).expanduser()
        self._data = pl.DataFrame()
        self._loaded = False
        return self

    def load(self, path: str | Path | None = None) -> DailyBasic:
        if path is not None:
            self._path = Path(path).expanduser()
        self._loaded = False
        if not self.path.exists():
            logger.warning("daily basic store not found: {}", self.path)
            return self
        try:
            data = pl.read_parquet(self.path)
        except Exception as exc:  # pragma: no cover - corrupt file is an ops issue
            logger.exception("failed to load daily basic store: {}", exc)
            return self
        self._data = self._normalize(data)
        self._loaded = True
        return self

    def _normalize(self, data: pl.DataFrame) -> pl.DataFrame:
        if data.is_empty():
            return data
        exprs: list[pl.Expr] = []
        if "date" in data.columns:
            exprs.append(pl.col("date").cast(pl.Date))
        if "asset" in data.columns:
            exprs.append(pl.col("asset").cast(pl.Utf8))
        for col in ("total_mv", "circ_mv"):
            if col in data.columns:
                exprs.append(pl.col(col).cast(pl.Float64))
        if exprs:
            data = data.with_columns(exprs)
        required = {"date", "asset", "total_mv"}
        if not required.issubset(data.columns):
            logger.error(
                "daily basic store missing columns {}: {}",
                sorted(required - set(data.columns)),
                self.path,
            )
            return pl.DataFrame()
        return data.unique(subset=["date", "asset"], keep="last").sort(["date", "asset"])

    def get(
        self,
        date: datetime.date,
        assets: list[str] | None = None,
    ) -> pl.DataFrame:
        if not self._loaded:
            self.load()
        if self._data.is_empty():
            return pl.DataFrame()
        out = self._data.filter(pl.col("date") == date)
        if assets:
            out = out.filter(pl.col("asset").is_in(assets))
        return out

    def attach(
        self,
        frame: pl.DataFrame,
        date_col: str = "date",
        asset_col: str = "asset",
    ) -> pl.DataFrame:
        """Left-join point-in-time market cap on ``date, asset``."""
        if frame.is_empty():
            return frame
        if "total_mv" in frame.columns:
            return frame
        if not self._loaded:
            self.load()
        if self._data.is_empty():
            return frame
        right = self._data.select(
            [
                pl.col("date"),
                pl.col("asset"),
                pl.col("total_mv"),
                *([pl.col("circ_mv")] if "circ_mv" in self._data.columns else []),
            ]
        )
        left = frame.with_columns(
            pl.col(date_col).cast(pl.Date),
            pl.col(asset_col).cast(pl.Utf8),
        )
        return left.join(
            right,
            left_on=[date_col, asset_col],
            right_on=["date", "asset"],
            how="left",
        )

    def update(
        self,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        dates: list[datetime.date] | None = None,
        path: str | Path | None = None,
    ) -> int:
        """Fetch and persist daily market-cap data. Returns row count."""
        from quantide.data.fetchers.registry import get_data_fetcher
        from quantide.data.models.calendar import calendar

        if dates is None:
            if start is None or end is None:
                raise ValueError("start/end or dates must be provided")
            dates = list(trading_sessions(calendar, start, end))
        if not dates:
            return 0

        if not str(get_tushare_token() or "").strip():
            raise RuntimeError("tushare token is not configured; cannot fetch daily_basic")

        fetcher = get_data_fetcher()
        fetch = getattr(fetcher, "fetch_daily_basic", None)
        if fetch is None:
            raise RuntimeError("configured data fetcher does not support daily_basic")

        logger.info(
            "fetching daily_basic for {} trading days ({} ~ {})",
            len(dates),
            dates[0],
            dates[-1],
        )
        frame, errors = fetch(dates)
        if errors:
            raise RuntimeError(f"daily_basic source failed: {errors}")
        require_date_coverage(frame, dates, "daily_basic")
        return self._merge_and_save(frame, external_runtime_path(path or self.path))

    def _merge_and_save(self, frame: pd.DataFrame, target: Path) -> int:
        """Serialize read/merge/replace and retain the existing file on any failure."""
        new_data = pl.from_pandas(frame)
        target.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(target) + ".lock", timeout=30):
            existing = self._normalize(pl.read_parquet(target)) if target.exists() else None
            combined = pl.concat(
                [existing, new_data] if existing is not None else [new_data],
                how="diagonal_relaxed",
            )
            combined = self._normalize(combined)
            write_parquet(combined, target)
            self._path = target
            self._data = combined
            self._loaded = True
        logger.info("daily_basic store updated: {} rows", combined.height)
        return combined.height


daily_basic = DailyBasic()

__all__ = ["DailyBasic", "daily_basic"]
