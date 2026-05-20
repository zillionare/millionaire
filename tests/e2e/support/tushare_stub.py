"""Fixture-backed Tushare stub helpers for end-to-end tests."""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from quantide.core.ports import DataFetcherPort
from quantide.data.fetchers.registry import fetcher_registry, register_builtin_fetchers

TESTS_ROOT = Path(__file__).resolve().parents[2]
ASSETS_ROOT = TESTS_ROOT / "assets"
REPO_ROOT = TESTS_ROOT.parent
DEFAULT_STOCK_LIST_PATH = REPO_ROOT / "data" / "stock_list.parquet"


@dataclass(slots=True)
class TushareStubConfig:
    """Behavior switches for the fixture-backed Tushare stub."""

    empty_endpoints: set[str] = field(default_factory=set)
    rate_limited_endpoints: set[str] = field(default_factory=set)
    auth_failed_endpoints: set[str] = field(default_factory=set)
    network_failed_endpoints: set[str] = field(default_factory=set)
    missing_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _normalize_dates(
    dates: Iterable[datetime.date] | datetime.date,
) -> list[datetime.date]:
    if isinstance(dates, datetime.date):
        return [dates]
    return list(dates)


def _drop_missing_fields(
    frame: pd.DataFrame,
    endpoint: str,
    config: TushareStubConfig,
) -> pd.DataFrame:
    drop_columns = [
        column
        for column in config.missing_fields.get(endpoint, ())
        if column in frame.columns
    ]
    if not drop_columns:
        return frame
    return frame.drop(columns=drop_columns)


def _filter_frame_by_dates(
    frame: pd.DataFrame,
    dates: Iterable[datetime.date] | datetime.date,
    endpoint: str,
    config: TushareStubConfig,
) -> pd.DataFrame:
    if endpoint in config.empty_endpoints:
        return frame.iloc[0:0].copy()

    normalized_dates = {pd.Timestamp(date) for date in _normalize_dates(dates)}
    filtered = frame[frame["date"].isin(normalized_dates)].copy()
    return _drop_missing_fields(filtered, endpoint, config)


class FixtureBackedTushareFetcher(DataFetcherPort):
    """Use repository fixtures as a no-network Tushare fetcher."""

    def __init__(self, config: TushareStubConfig | None = None):
        self._config = config or TushareStubConfig()
        self._calendar = pd.read_parquet(ASSETS_ROOT / "baseline_calendar.parquet")
        self._bars = pd.read_parquet(ASSETS_ROOT / "2024_bars.parquet")
        self._adjust = pd.read_parquet(ASSETS_ROOT / "2024_adjust_factor.parquet")
        self._limit = pd.read_parquet(ASSETS_ROOT / "2024_limit_price.parquet")
        self._st = pd.read_parquet(ASSETS_ROOT / "2024_st_info.parquet")
        self._stock_list = self._load_stock_list()

    def _load_stock_list(self) -> pd.DataFrame:
        """Load a realistic stock list for dev-stub search flows.

        Returns:
            A stock list frame filtered to the fixture asset universe when possible.
        """
        assets = sorted(self._bars["asset"].drop_duplicates().tolist())
        columns = ["asset", "name", "pinyin", "list_date", "delist_date"]

        if DEFAULT_STOCK_LIST_PATH.exists():
            frame = pd.read_parquet(DEFAULT_STOCK_LIST_PATH)
            available_columns = [column for column in columns if column in frame.columns]
            filtered = frame.loc[frame["asset"].isin(assets), available_columns].copy()
            if not filtered.empty:
                for missing_column in set(columns) - set(filtered.columns):
                    filtered[missing_column] = pd.NaT if "date" in missing_column else ""
                return filtered[columns]

        return pd.DataFrame(
            {
                "asset": assets,
                "name": assets,
                "pinyin": [asset.split(".")[0] for asset in assets],
                "list_date": [datetime.date(1990, 1, 1)] * len(assets),
                "delist_date": [pd.NaT] * len(assets),
            }
        )

    def _maybe_raise(self, endpoint: str) -> None:
        if endpoint in self._config.rate_limited_endpoints:
            raise RuntimeError(f"{endpoint} rate limited")
        if endpoint in self._config.auth_failed_endpoints:
            raise PermissionError(f"{endpoint} auth failed")
        if endpoint in self._config.network_failed_endpoints:
            raise ConnectionError(f"{endpoint} network unavailable")

    def fetch_calendar(self, epoch: datetime.date) -> pd.DataFrame:
        self._maybe_raise("trade_cal")
        if "trade_cal" in self._config.empty_endpoints:
            return self._calendar.iloc[0:0].copy()
        dates = pd.to_datetime(self._calendar.index)
        return self._calendar.loc[dates.date >= epoch].copy()

    def fetch_stock_list(self) -> pd.DataFrame | None:
        self._maybe_raise("stock_basic")
        columns = ["asset", "name", "pinyin", "list_date", "delist_date"]
        if "stock_basic" in self._config.empty_endpoints:
            return pd.DataFrame(columns=columns)
        frame = self._stock_list.copy()
        return _drop_missing_fields(frame, "stock_basic", self._config)

    def fetch_adjust_factor(
        self,
        dates: Iterable[datetime.date] | datetime.date,
    ) -> tuple[pd.DataFrame, list[list]]:
        self._maybe_raise("adj_factor")
        return _filter_frame_by_dates(self._adjust, dates, "adj_factor", self._config), []

    def fetch_bars(
        self,
        dates: Iterable[datetime.date] | datetime.date,
    ) -> tuple[pd.DataFrame, list[list]]:
        self._maybe_raise("daily")
        return _filter_frame_by_dates(self._bars, dates, "daily", self._config), []

    def fetch_limit_price(
        self,
        dates: Iterable[datetime.date] | datetime.date,
    ) -> tuple[pd.DataFrame, list[list]]:
        self._maybe_raise("stk_limit")
        return _filter_frame_by_dates(self._limit, dates, "stk_limit", self._config), []

    def fetch_st_info(
        self,
        dates: Iterable[datetime.date] | datetime.date,
    ) -> tuple[pd.DataFrame, list[list]]:
        self._maybe_raise("stock_st")
        return _filter_frame_by_dates(self._st, dates, "stock_st", self._config), []

    def fetch_bars_ext(
        self,
        dates: Iterable[datetime.date] | datetime.date,
        phase_callback: Callable[[str], None] | None = None,
    ) -> tuple[pd.DataFrame, list[list]]:
        if phase_callback is not None:
            phase_callback("bars")
        bars, errors1 = self.fetch_bars(dates)
        if phase_callback is not None:
            phase_callback("adjust")
        adjust, errors2 = self.fetch_adjust_factor(dates)
        if phase_callback is not None:
            phase_callback("limit")
        limit, errors3 = self.fetch_limit_price(dates)
        if phase_callback is not None:
            phase_callback("st")
        st, errors4 = self.fetch_st_info(dates)

        if bars.empty:
            columns = [
                "date",
                "asset",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "adjust",
                "is_st",
                "up_limit",
                "down_limit",
            ]
            return pd.DataFrame(columns=columns), errors1 + errors2 + errors3 + errors4

        frame = bars.merge(adjust, on=["date", "asset"], how="left")
        frame = frame.merge(st, on=["date", "asset"], how="left")
        frame = frame.merge(limit, on=["date", "asset"], how="left")
        frame["adjust"] = frame["adjust"].fillna(1.0)
        frame["is_st"] = frame["is_st"].astype("boolean").fillna(False)
        frame["up_limit"] = frame["up_limit"].fillna(0.0)
        frame["down_limit"] = frame["down_limit"].fillna(0.0)
        return frame, errors1 + errors2 + errors3 + errors4


@contextmanager
def patched_tushare_fetcher(
    config: TushareStubConfig | None = None,
) -> Iterator[FixtureBackedTushareFetcher]:
    """Temporarily replace the default `tushare` fetcher with fixture data."""
    register_builtin_fetchers()
    previous_fetcher = fetcher_registry.get("tushare") if fetcher_registry.has("tushare") else None
    previous_default = fetcher_registry.default_name
    stub = FixtureBackedTushareFetcher(config=config)
    fetcher_registry.register("tushare", stub, make_default=previous_default == "tushare")
    try:
        yield stub
    finally:
        if previous_fetcher is None:
            fetcher_registry._fetchers.pop("tushare", None)
        else:
            fetcher_registry.register(
                "tushare",
                previous_fetcher,
                make_default=previous_default == "tushare",
            )
        fetcher_registry._default_name = previous_default
