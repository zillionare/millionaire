"""多数据源聚合器（主源 + 补充源）。

现实中单一数据源无法覆盖全部需求：

======== ================================================== ==========================
数据     主源                                                补充源
======== ================================================== ==========================
日线     Tushare（复权因子/涨跌停/ST/指数成分 PIT 一并提供）  腾讯（日线兜底）
指数日线 Tushare                                            腾讯
30 分钟  BaoStock（历史 + 每日回补，唯一历史来源）            —
实时行情 腾讯（``qt.gtimg.cn``，含当日涨跌停）                —
======== ================================================== ==========================

上层统一通过 :class:`MultiSourceDataFetcher` 取数；每类数据可配置自己的
fetcher 优先级，首选失败时自动降级到下一个。
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable
from typing import Any, cast

import pandas as pd

from quantide.core.ports.data_fetcher import (
    STANDARD_MINUTE_BAR_COLUMNS,
    ErrorRecord,
)

#: 默认的数据类型 -> fetcher 优先级
DEFAULT_STAGES: dict[str, list[str]] = {
    "calendar": ["tushare"],
    "stock_list": ["tushare"],
    "daily_bars": ["tushare", "tencent"],
    "adjust_factor": ["tushare"],
    "limit_price": ["tushare"],
    "st_info": ["tushare"],
    "daily_basic": ["tushare"],
    "index_bars": ["tushare", "tencent"],
    "index_weights": ["tushare"],
    "minute_bars": ["baostock"],
    "quote_snapshot": ["tencent"],
}


class BaostockMinuteAdapter:
    """把 :class:`BaostockMinuteFetcher` 适配成端口风格的分钟线接口。"""

    source_name = "baostock"

    def __init__(self, fetcher: Any) -> None:
        self._fetcher = fetcher

    def fetch_trading_status(
        self, asset: str, start: datetime.date, end: datetime.date
    ) -> pd.DataFrame:
        """Expose daily suspension evidence without inventing bars for missing sessions."""
        return cast(pd.DataFrame, self._fetcher.fetch_trading_status(asset, start, end))

    def fetch_minute_bars(
        self,
        asset: str,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
        period: str = "30",
        count: int = 320,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        if start_date is None or end_date is None:
            return (
                pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS),
                [["fetch_minute_bars", asset, "BaoStock 需要 start_date/end_date"]],
            )
        try:
            frame = self._fetcher.fetch_minute_bars(
                asset, start_date, end_date, frequency=str(period)
            )
        except Exception as exc:
            from quantide.data.fetchers.baostock_minute import BaostockThrottledError

            if isinstance(exc, (BaostockThrottledError, ImportError)):
                raise
            return (
                pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS),
                [["fetch_minute_bars", asset, str(exc)]],
            )
        if frame is None or frame.empty:
            return pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS), []
        frame = frame.copy()
        if "dt" in frame.columns:
            frame["date"] = pd.to_datetime(frame["dt"], errors="coerce")
        elif "date" in frame.columns and "time" in frame.columns:
            frame["date"] = pd.to_datetime(
                frame["date"].astype(str) + " " + frame["time"].astype(str),
                format="%Y-%m-%d %H%M%S%f",
                errors="coerce",
            )
        else:
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
        # BaoStock 的时间已经是 bar 收盘时刻（如 10:00 表示 09:30-10:00），
        # 与项目 Calendar 一致，直接保留。
        for col in ("volume", "amount"):
            if col not in frame.columns:
                frame[col] = 0.0
        # 单位统一为 Tushare/腾讯口径：成交量「手」、成交额「千元」。
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0) / 100.0
        frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0) / 1000.0
        frame = frame.tail(int(count))
        return frame[STANDARD_MINUTE_BAR_COLUMNS].reset_index(drop=True), []


def _append_source_errors(result: Any, errors: ErrorRecord) -> Any:
    if isinstance(result, tuple) and len(result) > 1 and errors:
        return result[0], [*errors, *(result[1] or [])]
    return result


def _empty_source_result(empty: Any, errors: ErrorRecord) -> Any:
    if isinstance(empty, tuple):
        return empty[0], [*errors, *(empty[1] or [])]
    return empty if empty is not None else pd.DataFrame()


def _minute_source_call(
    function: Callable[..., Any],
    asset: str,
    start: datetime.date | None,
    end: datetime.date | None,
    period: str,
    count: int,
) -> Any:
    try:
        return function(asset, start_date=start, end_date=end, period=str(period), count=int(count))
    except TypeError:
        return function(asset, start, end, frequency=str(period))


def _normalized_minute_result(result: Any) -> tuple[pd.DataFrame | None, ErrorRecord]:
    if isinstance(result, pd.DataFrame):
        return result, []
    return result[0], result[1] if len(result) > 1 else []


class MultiSourceDataFetcher:
    """按数据类型路由到不同 fetcher，失败自动降级。"""

    source_name = "multi"

    def __init__(
        self,
        fetchers: dict[str, Any] | None = None,
        stages: dict[str, list[str]] | None = None,
    ) -> None:
        """初始化。

        Args:
            fetchers: ``{name: fetcher}``；未提供时从注册表延迟解析。
            stages: 覆盖默认的 ``DEFAULT_STAGES``。
        """
        self._fetchers: dict[str, Any] = dict(fetchers or {})
        self._stages = {**DEFAULT_STAGES, **(stages or {})}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _resolve(self, name: str) -> Any | None:
        if name in self._fetchers:
            return self._fetchers[name]
        try:
            from quantide.data.fetchers.registry import get_data_fetcher

            fetcher = get_data_fetcher(name)
        except Exception:
            return None
        self._fetchers[name] = fetcher
        return fetcher

    def _fetchers_for(self, stage: str) -> list[tuple[str, Any]]:
        resolved: list[tuple[str, Any]] = []
        for name in self._stages.get(stage, []):
            fetcher = self._resolve(name)
            if fetcher is not None:
                resolved.append((name, fetcher))
        return resolved

    @staticmethod
    def _has_data(result: Any) -> bool:
        if result is None:
            return False
        if isinstance(result, tuple):
            frame = result[0]
            errors = result[1] if len(result) > 1 else []
            if frame is None:
                return False
            if isinstance(frame, pd.DataFrame):
                return not frame.empty or not errors
            return True
        if isinstance(result, pd.DataFrame):
            return not result.empty
        return bool(result)

    def _call(
        self,
        stage: str,
        method: str,
        *args: Any,
        empty: Any = None,
        **kwargs: Any,
    ) -> Any:
        errors: ErrorRecord = []
        sources = self._fetchers_for(stage)
        attempted = False
        for name, fetcher in sources:
            func = getattr(fetcher, method, None)
            if func is None:
                continue
            attempted = True
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                errors.append([name, method, str(exc)])
                continue
            if self._has_data(result):
                return _append_source_errors(result, errors)
            if isinstance(result, tuple) and len(result) > 1 and result[1]:
                errors.extend(result[1])
        if not attempted and isinstance(empty, tuple):
            errors.append([stage, method, "no available data source"])
        return _empty_source_result(empty, errors)

    def _call_frame(
        self, stage: str, method: str, *args: Any, **kwargs: Any
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        result = self._call(stage, method, *args, empty=(pd.DataFrame(), []), **kwargs)
        if isinstance(result, pd.DataFrame):
            return result, []
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], pd.DataFrame):
            return result[0], result[1]
        raise TypeError(f"{stage}.{method} returned an invalid historical data result")

    # ------------------------------------------------------------------
    # 日线与辅助字段
    # ------------------------------------------------------------------
    def fetch_calendar(self, epoch: datetime.date) -> pd.DataFrame:
        return cast(
            pd.DataFrame,
            self._call(
                "calendar",
                "fetch_calendar",
                epoch,
                empty=pd.DataFrame(
                    {
                        "date": pd.Series(dtype="datetime64[ms]"),
                        "is_open": pd.Series(dtype="int64"),
                    }
                ),
            ),
        )

    def fetch_stock_list(self) -> pd.DataFrame | None:
        return cast(pd.DataFrame | None, self._call("stock_list", "fetch_stock_list", empty=None))

    def fetch_adjust_factor(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("adjust_factor", "fetch_adjust_factor", dates)

    def fetch_bars(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("daily_bars", "fetch_bars", dates)

    def fetch_limit_price(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("limit_price", "fetch_limit_price", dates)

    def fetch_st_info(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("st_info", "fetch_st_info", dates)

    def fetch_bars_ext(
        self,
        dates: Iterable[datetime.date] | datetime.date,
        phase_callback: Any = None,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame(
            "daily_bars", "fetch_bars_ext", dates, phase_callback=phase_callback
        )

    def fetch_daily_basic(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("daily_basic", "fetch_daily_basic", dates)

    # ------------------------------------------------------------------
    # 指数
    # ------------------------------------------------------------------
    def fetch_index_bars(
        self,
        index_codes: Iterable[str] | str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("index_bars", "fetch_index_bars", index_codes, start_date, end_date)

    def fetch_index_weights(
        self,
        index_codes: Iterable[str] | str,
        snapshot_dates: Iterable[datetime.date],
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return self._call_frame("index_weights", "fetch_index_weights", index_codes, snapshot_dates)

    # ------------------------------------------------------------------
    # 分钟线 / 实时
    # ------------------------------------------------------------------
    def fetch_minute_bars(
        self,
        asset: str,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
        period: str = "30",
        count: int = 320,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        errors: ErrorRecord = []
        for name, fetcher in self._fetchers_for("minute_bars"):
            func = getattr(fetcher, "fetch_minute_bars", None)
            if func is None:
                continue
            try:
                result = _minute_source_call(func, asset, start_date, end_date, period, count)
            except Exception as exc:
                errors.append([name, "fetch_minute_bars", str(exc)])
                continue
            frame, item_errors = _normalized_minute_result(result)
            if frame is not None and not frame.empty:
                frame = frame.copy()
                if "date" not in frame.columns and "dt" in frame.columns:
                    frame = frame.rename(columns={"dt": "date"})
                return frame, [*errors, *(item_errors or [])]
            errors.extend(item_errors or [])
        return pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS), errors

    def fetch_quote_snapshot(self, symbols: Iterable[str] | str) -> dict[str, dict[str, Any]]:
        for _name, fetcher in self._fetchers_for("quote_snapshot"):
            func = getattr(fetcher, "fetch_quote_snapshot", None)
            if func is None:
                continue
            try:
                result = func(symbols)
            except Exception:
                continue
            if result:
                return cast(dict[str, dict[str, Any]], result)
        return {}

    # ------------------------------------------------------------------
    # 便捷构造
    # ------------------------------------------------------------------
    @classmethod
    def with_baostock(
        cls,
        baostock_fetcher: Any,
        stages: dict[str, list[str]] | None = None,
    ) -> MultiSourceDataFetcher:
        """构造带 BaoStock 历史分钟线补充的聚合器。"""
        adapter = BaostockMinuteAdapter(baostock_fetcher)
        return cls(fetchers={"baostock": adapter}, stages=stages)
