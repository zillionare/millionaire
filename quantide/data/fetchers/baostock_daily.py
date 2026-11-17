"""Token-free BaoStock daily history adapter normalized to SQEP conventions."""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable
from typing import Any

import pandas as pd
from loguru import logger

from quantide.core.bar_schema import OHLCV_COLUMNS
from quantide.core.ports.data_fetcher import ErrorRecord
from quantide.data.fetchers.baostock_minute import BaostockMinuteFetcher
from quantide.data.fetchers.capabilities import SOURCE_CAPABILITIES, require_source_asset

_DAILY_COLUMNS = (
    "date",
    "asset",
    *OHLCV_COLUMNS,
    "adjust",
    "is_st",
    "up_limit",
    "down_limit",
)
_BAR_COLUMNS = ("date", "asset", *OHLCV_COLUMNS, "is_st")


def _date_list(
    dates: Iterable[datetime.date] | datetime.date | str,
) -> list[datetime.date]:
    if isinstance(dates, datetime.date):
        return [dates]
    if isinstance(dates, str):
        return [datetime.date.fromisoformat(dates[:10])]
    return list(dates)


def _empty(columns: tuple[str, ...]) -> pd.DataFrame:
    dtypes = {
        "date": "datetime64[ms]",
        "asset": "object",
        "is_st": "boolean",
    }
    return pd.DataFrame({name: pd.Series(dtype=dtypes.get(name, "float64")) for name in columns})


def _rows(result: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    while result.next():
        rows.append(result.get_row_data())
    return rows


class BaostockDailyFetcher(BaostockMinuteFetcher):
    """BaoStock anonymous daily adapter for SH/SZ equities.

    BaoStock does not publish an authoritative daily up/down-limit field and
    does not provide market-cap fields. Those datasets return typed empty
    frames instead of fabricated zeros; the sync pipeline skips them.
    """

    source_name = "baostock"
    datasets = SOURCE_CAPABILITIES["baostock"].datasets

    @staticmethod
    def _asset_from_code(code: Any) -> str | None:
        text = str(code or "").strip().lower()
        if "." not in text:
            return None
        market, number = text.split(".", 1)
        if market not in {"sh", "sz"} or not number.isdigit():
            return None
        asset = f"{number}.{market.upper()}"
        try:
            require_source_asset("baostock", asset)
        except ValueError:
            return None
        return asset

    def fetch_calendar(self, epoch: datetime.date) -> pd.DataFrame:
        import baostock as bs

        end = datetime.date.today()
        with self._session():
            self._consume()
            result = bs.query_trade_dates(start_date=epoch.isoformat(), end_date=end.isoformat())
            if result.error_code != "0":
                self._handle_error(result.error_msg)
            rows = _rows(result)
        if not rows:
            return pd.DataFrame()
        frame = pd.DataFrame(rows, columns=result.fields)
        frame["date"] = pd.to_datetime(frame["calendar_date"], errors="raise").dt.date
        frame["is_open"] = pd.to_numeric(frame["is_trading_day"], errors="coerce").fillna(0)
        frame = frame.sort_values("date")
        opened = frame["date"].where(frame["is_open"] == 1).ffill()
        frame["prev"] = opened.shift(1)
        return frame.sort_values("date").set_index("date")[["is_open", "prev"]]

    def fetch_stock_list(self) -> pd.DataFrame | None:
        import baostock as bs

        with self._session():
            self._consume()
            result = bs.query_stock_basic()
            if result.error_code != "0":
                self._handle_error(result.error_msg)
            rows = _rows(result)
        if not rows:
            return None
        frame = pd.DataFrame(rows, columns=result.fields)
        if "type" in frame.columns:
            frame = frame[frame["type"].astype(str) == "1"]
        frame["asset"] = frame["code"].map(self._asset_from_code)
        frame = frame[frame["asset"].notna()].copy()
        if frame.empty:
            return None
        frame["name"] = frame["code_name"].fillna("").astype(str)
        frame["pinyin"] = ""
        frame["list_date"] = pd.to_datetime(frame["ipoDate"], errors="coerce").dt.date
        frame["delist_date"] = pd.to_datetime(frame["outDate"], errors="coerce").dt.date
        return frame[["asset", "name", "pinyin", "list_date", "delist_date"]]

    def _daily_rows(
        self,
        dates: list[datetime.date],
        query: Callable[[str], Any],
        label: str,
        *,
        empty_is_error: bool = True,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        frames: list[pd.DataFrame] = []
        errors: ErrorRecord = []
        with self._session():
            for day in dates:
                self._consume()
                result = query(day.isoformat())
                if result.error_code != "0":
                    self._handle_error(result.error_msg)
                rows = _rows(result)
                if not rows:
                    logger.warning("{} returned no rows for {}", label, day)
                    if empty_is_error:
                        errors.append([label, day, f"{label} 无数据"])
                    continue
                frame = pd.DataFrame(rows, columns=result.fields)
                frame["asset"] = frame.get("code", pd.Series(dtype=object)).map(
                    self._asset_from_code
                )
                frame = frame[frame["asset"].notna()].copy()
                if not frame.empty:
                    frames.append(frame)
        return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), errors

    def fetch_bars(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        import baostock as bs

        requested = _date_list(dates)
        frame, errors = self._daily_rows(
            requested, lambda day: bs.query_daily_history_k_AStock(date=day), "daily"
        )
        if frame.empty:
            columns = ("date", "asset", "open", "high", "low", "close", "volume", "amount")
            return _empty(columns), errors
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        for column in OHLCV_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["date", "asset", "open", "high", "low", "close"])
        frame["volume"] = frame["volume"].fillna(0.0) / 100.0
        frame["amount"] = frame["amount"].fillna(0.0) / 1000.0
        frame["is_st"] = frame.get("isST", pd.Series(False, index=frame.index)).astype(str).eq("1")
        frame["date"] = pd.to_datetime(frame["date"]).astype("datetime64[ms]")
        return (
            frame[list(_BAR_COLUMNS)].sort_values(["date", "asset"]),
            errors,
        )

    def fetch_adjust_factor(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        import baostock as bs

        frame, errors = self._daily_rows(
            _date_list(dates),
            lambda day: bs.query_daily_adjust_factor(date=day),
            "adjust_factor",
            empty_is_error=False,
        )
        columns = ("asset", "date", "adjust")
        if frame.empty:
            return _empty(columns), errors
        date_column = "date" if "date" in frame.columns else "dividOperateDate"
        frame["date"] = pd.to_datetime(frame[date_column], errors="coerce").dt.date
        factor_column = (
            "backAdjustFactor" if "backAdjustFactor" in frame.columns else "adjustFactor"
        )
        frame["adjust"] = pd.to_numeric(frame[factor_column], errors="coerce").fillna(1.0)
        frame["date"] = pd.to_datetime(frame["date"]).astype("datetime64[ms]")
        return frame[list(columns)].dropna(subset=["date", "asset"]), errors

    def fetch_st_info(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        frame, errors = self.fetch_bars(dates)
        columns = ("asset", "date", "is_st")
        if frame.empty or "is_st" not in frame.columns:
            return _empty(columns), errors
        st = frame[frame["is_st"]][["asset", "date", "is_st"]].copy()
        return st, errors

    def fetch_bars_ext(
        self,
        dates: Iterable[datetime.date] | datetime.date,
        phase_callback: Callable[[str], None] | None = None,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        if phase_callback:
            phase_callback("bars")
        bars, errors = self.fetch_bars(dates)
        if bars.empty:
            return _empty(_DAILY_COLUMNS), errors
        if phase_callback:
            phase_callback("adjust")
        adjust, adjust_errors = self.fetch_adjust_factor(dates)
        errors.extend(adjust_errors)
        merged = bars.merge(adjust, on=["date", "asset"], how="left")
        merged["adjust"] = merged["adjust"].fillna(1.0)
        merged["is_st"] = merged.get("is_st", False)
        merged["up_limit"] = pd.NA
        merged["down_limit"] = pd.NA
        for column in ("up_limit", "down_limit"):
            merged[column] = pd.to_numeric(merged[column], errors="coerce")
        merged["adjust"] = pd.to_numeric(merged["adjust"], errors="coerce")
        return merged[list(_DAILY_COLUMNS)], errors

    def fetch_limit_price(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return _empty(("date", "asset", "up_limit", "down_limit")), []

    def fetch_daily_basic(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return _empty(("date", "asset", "total_mv", "circ_mv")), []

    def fetch_index_bars(
        self,
        index_codes: Iterable[str] | str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        columns = ("date", "index_code", "open", "high", "low", "close", "volume", "amount")
        return _empty(columns), []

    def fetch_index_weights(
        self, index_codes: Iterable[str] | str, snapshot_dates: Iterable[datetime.date]
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return _empty(("date", "index_code", "con_code", "weight")), []


__all__ = ["BaostockDailyFetcher"]
