"""BaoStock minute backfill, capability checks and evidence-based memory eviction."""

from __future__ import annotations

import datetime
import threading
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
from loguru import logger

from quantide.core.enums import FrameType
from quantide.core.market_time import market_now
from quantide.data.fetchers.capabilities import SOURCE_CAPABILITIES, require_source_asset

if TYPE_CHECKING:
    from quantide.data.fetchers.multi import BaostockMinuteAdapter

MINUTE_HISTORY_START = datetime.date(2020, 1, 2)
MINUTE_HISTORY_READY_TIME = datetime.time(17, 30)


class _BackfillParams(Protocol):
    start_date: datetime.date
    end_date: datetime.date
    minute_frequency: str
    minute_assets: list[str]


def _minute_history_end(
    end_date: datetime.date, now: datetime.datetime | None = None
) -> datetime.date | None:
    """Return the last closed session eligible for historical download."""
    from quantide.data.models.calendar import calendar

    now = now or market_now()
    today = now.date()
    if end_date < today:
        return end_date
    if calendar.is_trade_day(today) and now.time() >= MINUTE_HISTORY_READY_TIME:
        return today
    try:
        return calendar.day_shift(today, -1)
    except Exception:
        return None


def resolve_minute_assets(explicit: Iterable[str] | None) -> list[str]:
    """Default to supported Shanghai/Shenzhen assets; explicitly reject other markets."""
    from quantide.data.models.stocks import stock_list

    if explicit:
        assets = list(dict.fromkeys(str(asset).strip().upper() for asset in explicit))
        for asset in assets:
            require_source_asset("baostock", asset)
        return assets
    if stock_list.size == 0:
        raise RuntimeError("分钟同步需要证券列表，当前为空")
    supported = SOURCE_CAPABILITIES["baostock"].supports
    assets = [str(asset) for asset in stock_list.data["asset"].to_list() if supported(str(asset))]
    logger.info("BaoStock 分钟源只覆盖沪深；北交所需由扩展提供。此次 {} 个标的", len(assets))
    return assets


def _asset_lifespans() -> dict[str, dict[str, Any]]:
    from quantide.data.models.stocks import stock_list

    return {str(row["asset"]): row for row in stock_list.data.to_dicts()}


def _date_value(value: Any) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    return value if isinstance(value, datetime.date) else None


def asset_interval(
    metadata: dict[str, Any], start: datetime.date, end: datetime.date
) -> tuple[datetime.date, datetime.date]:
    """Clip a source request to the security's documented listing lifetime."""
    return (
        max(start, _date_value(metadata.get("list_date")) or start),
        min(end, _date_value(metadata.get("delist_date")) or end),
    )


def pending_ranges(
    assets: Iterable[str],
    last_dates: dict[str, datetime.date],
    start: datetime.date,
    end: datetime.date,
    coverage: dict[str, datetime.date | None] | None = None,
) -> list[tuple[str, datetime.date, datetime.date]]:
    """Build incremental ranges per security, retaining older in-memory coverage."""
    from quantide.data.models.calendar import calendar

    pending = []
    lifespans = _asset_lifespans()
    for asset in assets:
        first, last_day = asset_interval(lifespans.get(asset, {}), start, end)
        if coverage is not None:
            gap = coverage.get(asset)
            if gap is None:
                continue
            first = max(first, gap)
        else:
            last = last_dates.get(asset)
            if last is not None and last >= first:
                first = calendar.shift(last, 1, FrameType.DAY)
        if first <= last_day:
            pending.append((asset, first, last_day))
    return pending


def _inactive_session_evidence(
    adapter: BaostockMinuteAdapter,
    asset: str,
    frame: pd.DataFrame,
    start: datetime.date,
    end: datetime.date,
    period: str,
) -> set[datetime.date]:
    """Resolve missing sessions only from explicit source suspension status."""
    from quantide.data.models.calendar import calendar
    from quantide.service.minute_coverage import missing_minute_sessions

    if not missing_minute_sessions(frame, start, end, period, calendar):
        return set()
    status = adapter.fetch_trading_status(asset, start, end)
    return {row["date"] for row in status.to_dict("records") if str(row["tradestatus"]) == "0"}


class MinuteBackfill:
    """Commit and evict one verified asset interval at a time."""

    def __init__(
        self,
        params: _BackfillParams,
        cancel: threading.Event,
        publish: Callable[[dict[str, Any]], None],
    ) -> None:
        from quantide.data import get_minute_bars_store

        self.params = params
        self.cancel = cancel
        self.publish = publish
        self.store = get_minute_bars_store()
        self.end = _minute_history_end(params.end_date)
        self.period = str(params.minute_frequency or "30")
        if self.period not in {"5", "15", "30", "60"}:
            raise ValueError("BaoStock 分钟周期仅支持 5/15/30/60")

    def run(self) -> None:
        """Close the source on all exits and fail the task for any incomplete asset."""
        from quantide.data.fetchers.baostock_minute import BaostockMinuteFetcher
        from quantide.data.fetchers.multi import BaostockMinuteAdapter

        assets = resolve_minute_assets(self.params.minute_assets)
        if self.end is None:
            raise RuntimeError("无法确定已收盘的分钟回补日期，请检查交易日历")
        from quantide.service.minute_gaps import coverage_starts

        start = max(self.params.start_date, MINUTE_HISTORY_START)
        pending = pending_ranges(
            assets,
            {},
            start,
            self.end,
            coverage=coverage_starts(self.store, assets, start, self.end, self.period),
        )
        if not pending:
            return
        fetcher = BaostockMinuteFetcher()
        failures = 0
        try:
            adapter = BaostockMinuteAdapter(fetcher)
            for index, (asset, start, end) in enumerate(pending, start=1):
                if self.cancel.is_set():
                    return
                if not self._commit_asset(adapter, asset, start, end):
                    failures += 1
                self._progress(index, len(pending))
        finally:
            fetcher.close()
        if failures:
            raise RuntimeError(f"分钟回补有 {failures} 只标的失败，未覆盖的内存数据予以保留")

    def _commit_asset(
        self, adapter: BaostockMinuteAdapter, asset: str, start: datetime.date, end: datetime.date
    ) -> bool:
        from quantide.data.fetchers.baostock_minute import BaostockThrottledError
        from quantide.data.models.calendar import calendar
        from quantide.service.data_sync import _to_minute_bars_frame
        from quantide.service.minute_bar_aggregator import minute_bar_aggregator
        from quantide.service.minute_coverage import require_minute_coverage

        try:
            frame, errors = adapter.fetch_minute_bars(
                asset, start, end, period=self.period, count=100000
            )
            if errors:
                raise RuntimeError(str(errors))
            inactive = _inactive_session_evidence(adapter, asset, frame, start, end, self.period)
            require_minute_coverage(frame, start, end, self.period, calendar, inactive)
            if not frame.empty and set(frame["asset"]) != {asset}:
                raise RuntimeError(f"分钟源返回了不匹配的标的: {asset}")
            if not frame.empty:
                self.store.append_data(_to_minute_bars_frame(frame))
            from quantide.service.minute_gaps import record_suspensions

            record_suspensions(self.store, asset, start, end, inactive)
        except BaostockThrottledError:
            raise
        except Exception as exc:
            logger.warning("BaoStock 分钟回补失败 {}: {}", asset, exc)
            return False
        minute_bar_aggregator.clear_between(start, end, assets=[asset])
        return True

    def _progress(self, index: int, total: int) -> None:
        if index % 50 == 0 or index == total:
            self.publish(
                {
                    "task_id": "",
                    "stage": "minute_bars",
                    "progress": min(50 + int(index * 50 / total), 100),
                    "message": f"分钟回补 {index}/{total}",
                }
            )
