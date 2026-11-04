"""Compatibility helpers for historical bar views."""

import datetime
from typing import TYPE_CHECKING, Any, cast

import polars as pl

from quantide.data.helper import qfq_adjustment
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.service.bar_access import (
    empty_history,
    history_end,
    history_source,
    previous_session,
    provider_history,
)
from quantide.service.market_data_hub import market_data_hub


def _cast_forming_column(col: str, forming_df: pl.DataFrame, hist: pl.DataFrame) -> pl.DataFrame:
    """Cast forming column."""
    if col in forming_df.columns and hist.schema[col] != forming_df.schema[col]:
        try:
            forming_df = forming_df.with_columns(pl.col(col).cast(hist.schema[col]).alias(col))
        except Exception:
            forming_df = forming_df.drop(col)
    return forming_df


def _forming_row_fields(forming: dict[str, Any], date_column: str) -> dict[str, Any]:
    clean = dict(forming)
    if "frame" in clean and not isinstance(clean["frame"], (datetime.date, datetime.datetime)):
        clean.pop("frame")
    if "dt" in clean and date_column != "dt":
        value = clean.pop("dt")
        if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
            value = datetime.datetime.combine(value, datetime.time.min)
        clean[date_column] = value
    return clean


def _fill_forming_auxiliary(history: pl.DataFrame, forming: dict[str, Any]) -> None:
    down, up = market_data_hub.get_limits(forming.get("asset", ""))
    auxiliary = {
        "adjust": history["adjust"][-1] if "adjust" in history.columns else 1.0,
        "is_st": bool(history["is_st"][-1]) if "is_st" in history.columns else False,
        "up_limit": up or None,
        "down_limit": down or None,
    }
    for column, value in auxiliary.items():
        if column in history.columns and column not in forming:
            forming[column] = value


class PaperHistory:
    """Compatibility helpers for historical bar views."""

    if TYPE_CHECKING:
        _market_data: Any

        def _get_today(self) -> datetime.date: ...

    def _previous_trade_date(self, today: datetime.date) -> datetime.date:
        return previous_session(calendar, today)

    def _get_history_bars(
        self, asset: str, count: int, end_date: datetime.date | None, frame_type: str
    ) -> pl.DataFrame | None:
        provider = history_source(
            self._market_data, daily_bars, getattr(daily_bars, "_store", None) is not None
        )
        if provider is None:
            return self._empty_history_frame()
        return cast(
            pl.DataFrame | None,
            provider_history(provider, asset, count, end_date, frame_type, eager=True),
        )

    def _should_attach_forming_bar(
        self,
        end_date: datetime.date,
        end_dt: datetime.datetime | None,
    ) -> bool:
        """end_date 落在今日且不是凌晨 9:30 之前才挂 forming bar。"""
        if end_date != self._get_today():
            return False
        if isinstance(end_dt, datetime.datetime) and end_dt.time() <= datetime.time(9, 30):
            return False
        return True

    def _extract_forming_bar(self, asset: str, end_date: datetime.date) -> dict[str, Any] | None:
        """从 MarketDataHub 拿今日 forming bar（若没有则返回 None）。"""
        bar = market_data_hub.get_daily_bar(asset)
        if bar is None:
            return None
        bar_dt = bar.get("dt")
        if bar_dt is not None and hasattr(bar_dt, "date"):
            bar_dt = bar_dt.date()
        if bar_dt != end_date:
            return None
        return bar

    @staticmethod
    def _concat_with_forming(
        hist: pl.DataFrame, forming: dict[str, Any], count: int
    ) -> pl.DataFrame:
        """Merge a forming row with the historical schema, then adjust and trim the window."""
        date_column = (
            "frame" if "frame" in hist.columns else ("date" if "date" in hist.columns else None)
        )
        if date_column is None or hist.is_empty():
            return hist
        clean = _forming_row_fields(forming, date_column)
        _fill_forming_auxiliary(hist, clean)
        clean = {column: clean.get(column) for column in hist.columns}
        current = pl.DataFrame([clean])
        for column in hist.columns:
            current = _cast_forming_column(column, current, hist)
        merged = pl.concat([hist, current.select(hist.columns)], how="vertical")
        identity = [date_column, "asset"] if "asset" in merged.columns else [date_column]
        merged = merged.unique(subset=identity, keep="last").sort(date_column).tail(count)
        if "adjust" in merged.columns:
            merged = cast(
                pl.DataFrame, qfq_adjustment(merged, adj_factor_col="adjust", eager_mode=True)
            )
        return merged

    def _resolve_history_end_date(self, end_dt: datetime.datetime | None) -> datetime.date | None:
        return history_end(end_dt, self._get_today(), calendar)

    def _empty_history_frame(self) -> pl.DataFrame:
        return empty_history()
