"""腾讯行情数据源适配器（直连 HTTP，不依赖 akshare / a-stock-data 包）。

由 a-stock-data 的公开接口整理而来，作为我们自维护的补充源：

- **实时行情**：``qt.gtimg.cn``，一次最多约 800 支，含当日涨跌停价；
- **K 线**：``web.ifzq.gtimg.cn``，支持日/周/月与 1/5/15/30/60 分钟；
- **指数日线**：同一 K 线接口（``sh000300`` 等）。

能力边界（重要）：

* 分钟 K 线只保留**近期若干根**（历史 30 分钟请用 BaoStock 回补）；
* 不提供按日期批量日线、复权因子、ST 名单、指数成分 PIT；
  这些仍由 Tushare 主源提供，见 :class:`~quantide.data.fetchers.multi.MultiSourceDataFetcher`；
* 腾讯返回的 K 线字段顺序是 ``[日期, 开盘, 收盘, 最高, 最低, 成交量, ...]``，
  注意不是 OHLC，本模块已按正确顺序映射；
* 成交量单位：多数为手，科创板（688/689）为股（沿用源口径，未做统一换算）；
* 成交额：日线/分钟线由 ``成交量 × 收盘价`` 估算（千元），实时快照用源字段（万元→千元）。
"""

from __future__ import annotations

import datetime
import threading
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
from loguru import logger

if TYPE_CHECKING:
    import requests

from quantide.core.ports.data_fetcher import (
    STANDARD_INDEX_BAR_COLUMNS,
    STANDARD_MINUTE_BAR_COLUMNS,
    ErrorRecord,
)
from quantide.data.fetchers.budget import NoQuotaBudget

#: 实时行情批量上限（a-stock-data 实测约 800 支/次）
DEFAULT_QUOTE_BATCH = 100
_TENCENT_BUDGET = NoQuotaBudget("tencent")


def _kline_source_rows(
    self: TencentDataFetcher, asset: str, period: str, count: int, adjust: str
) -> list[list[object]] | None:
    """Kline source rows."""
    symbol = to_tencent_symbol(asset)
    period = self.PERIOD_MAP.get(str(period), str(period))
    if period.startswith("m"):
        param = f"{symbol},{period},,,{int(count)}"
        keys = (period, f"qfq{period}", f"hfq{period}")
    else:
        param = f"{symbol},{period},,,{int(count)},{adjust}"
        keys = (f"{adjust}{period}", period, f"qfq{period}")
    data = self._request_json(self.KLINE_URL, {"param": param})
    node = ((data.get("data") or {}).get(symbol) or {}) if data else {}
    rows = None
    for key in keys:
        value = node.get(key)
        if isinstance(value, list):
            rows = value
            break
    return rows


def to_tencent_symbol(asset: str) -> str:
    """``600519.SH`` -> ``sh600519``；``000001.SZ`` -> ``sz000001``。"""
    text = str(asset).strip().upper()
    if "." in text:
        code, market = text.split(".", 1)
        prefixes = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
        if market not in prefixes:
            raise ValueError(f"Unsupported market: {market}")
        return f"{prefixes[market]}{code}"
    if text.startswith(("4", "8", "92")):
        return f"bj{text}"
    return f"sh{text}" if text.startswith(("5", "6", "9")) else f"sz{text}"


def from_tencent_symbol(symbol: str) -> str:
    """``sh600519`` -> ``600519.SH``。"""
    text = str(symbol).strip().lower()
    return f"{text[2:]}.{text[:2].upper()}"


def _to_float(value: object) -> float | None:
    try:
        number = float(cast(float | int | str, value))
    except (TypeError, ValueError):
        return None
    return number


def _parse_quote_time(value: object) -> datetime.datetime | None:
    """解析腾讯行情时间（``20241022150000`` 或 ``2024/10/22 15:00:00``）。"""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


class TencentDataFetcher:
    """腾讯行情适配器（符合 DataFetcherPort 实时/分钟扩展）。"""

    source_name = "tencent"

    def budget(self) -> NoQuotaBudget:
        return _TENCENT_BUDGET

    QUOTE_URL = "https://qt.gtimg.cn/q={}"
    KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    PERIOD_MAP = {
        "1": "m1",
        "5": "m5",
        "15": "m15",
        "30": "m30",
        "60": "m60",
        "m1": "m1",
        "m5": "m5",
        "m15": "m15",
        "m30": "m30",
        "m60": "m60",
        "day": "day",
        "week": "week",
        "month": "month",
    }

    def __init__(
        self,
        timeout: float = 3.0,
        max_retries: int = 2,
        quote_batch: int = DEFAULT_QUOTE_BATCH,
        min_interval: float = 5.0,
        session: requests.Session | None = None,
        access_check: Callable[[], None] | None = None,
    ) -> None:
        """初始化适配器。

        Args:
            timeout: 单次 HTTP 超时（秒）；实时扫描要求 <5 秒，默认 3 秒。
            max_retries: 失败重试次数。
            quote_batch: 实时行情单次请求标的数（演示上限 100）。
            min_interval: 同一适配器连续请求的最小间隔（秒）。
            session: 可注入的 requests.Session（测试用）。
        """
        self._timeout = float(timeout)
        self._max_retries = max(0, int(max_retries))
        self._quote_batch = min(100, max(1, int(quote_batch)))
        self._min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last_request = 0.0
        from quantide.config.tencent_trial import require_tencent_access

        self._access_check = access_check or require_tencent_access
        self._session = session

    # ------------------------------------------------------------------
    # HTTP 基础
    # ------------------------------------------------------------------
    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        import requests

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Millionaire/0.3 (+https://github.com/zillionare/millionaire)",
            }
        )
        return self._session

    def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            wait = self._last_request + self._min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def _request_bytes(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """GET 请求并返回原始字节（腾讯行情为 GBK 编码）。"""
        self._access_check()
        session = self._get_session()
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._access_check()
            self._throttle()
            try:
                response = session.get(url, params=params, timeout=self._timeout)
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                content = getattr(response, "content", None)
                if content is not None:
                    return cast(bytes, content)
                return str(getattr(response, "text", "")).encode("utf-8")
            except Exception as exc:  # pragma: no cover - 网络异常
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {401, 403, 429}:
                    raise
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"腾讯请求失败: {last_error}")

    def _request_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = self._request_bytes(url, params)
        import json

        text = raw.decode("utf-8", errors="ignore")
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            return cast(dict[str, Any], json.loads(text[start : end + 1]))
        except ValueError:
            return {}

    # ------------------------------------------------------------------
    # 实时快照
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_quote_line(line: str) -> tuple[str, dict[str, Any]] | None:
        """解析一行 ``v_sh600519="..."``。"""
        if "=" not in line or '"' not in line:
            return None
        head, payload = line.split("=", 1)
        symbol = head.strip().lower()
        if not symbol.startswith("v_") or len(symbol) <= 2:
            return None
        fields = payload.strip().strip(";").strip('"').split("~")
        if len(fields) < 35:
            return None
        price = _to_float(fields[3])
        if price is None or price <= 0:
            return None
        amount_wan = _to_float(fields[37]) if len(fields) > 37 else None
        return (
            from_tencent_symbol(symbol[2:]),
            {
                "name": fields[1].strip() if len(fields) > 1 else None,
                "price": price,
                "prev_close": _to_float(fields[4]),
                "open": _to_float(fields[5]),
                "high": _to_float(fields[33]),
                "low": _to_float(fields[34]),
                "volume": _to_float(fields[6]),
                "amount": (amount_wan * 10.0) if amount_wan is not None else None,
                "up_limit": _to_float(fields[47]) if len(fields) > 47 else None,
                "down_limit": _to_float(fields[48]) if len(fields) > 48 else None,
                "ts": _parse_quote_time(fields[30]) if len(fields) > 30 else None,
            },
        )

    def fetch_quote_snapshot(self, symbols: Iterable[str] | str) -> dict[str, dict[str, Any]]:
        """获取实时快照（演示范围最多 100 个标的）。"""
        if isinstance(symbols, str):
            symbols = [symbols]
        result: dict[str, dict[str, Any]] = {}
        unique = list(dict.fromkeys(str(s).strip().upper() for s in symbols if s))[:100]
        for start in range(0, len(unique), self._quote_batch):
            batch = unique[start : start + self._quote_batch]
            query = ",".join(to_tencent_symbol(symbol) for symbol in batch)
            try:
                raw = self._request_bytes(self.QUOTE_URL.format(query))
            except Exception as exc:
                logger.warning("腾讯实时行情请求失败: {}", exc)
                continue
            text = raw.decode("gbk", errors="ignore")
            for line in text.split(";"):
                parsed = self._parse_quote_line(line)
                if parsed is None:
                    continue
                symbol, payload = parsed
                result[symbol] = payload
        return result

    # ------------------------------------------------------------------
    # K 线
    # ------------------------------------------------------------------
    def _fetch_kline(
        self,
        asset: str,
        period: str,
        count: int,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """拉取腾讯 K 线并映射为标准列。

        注意腾讯行的字段顺序为 ``[日期, 开盘, 收盘, 最高, 最低, 成交量, ...]``。
        """
        rows = _kline_source_rows(self, asset, period, count, adjust)
        if not rows:
            return pd.DataFrame()
        records = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            records.append(
                {
                    "date": str(row[0]).strip(),
                    "open": _to_float(row[1]),
                    "close": _to_float(row[2]),
                    "high": _to_float(row[3]),
                    "low": _to_float(row[4]),
                    "volume": _to_float(row[5]),
                }
            )
        frame = pd.DataFrame.from_records(records)
        if frame.empty:
            return pd.DataFrame()
        frame["asset"] = asset
        return frame

    def fetch_minute_bars(
        self,
        asset: str,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
        period: str = "30",
        count: int = 320,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        """获取近期分钟线（腾讯只保留有限根数，历史回补用 BaoStock）。"""
        errors: ErrorRecord = []
        try:
            frame = self._fetch_kline(asset, period, count)
        except Exception as exc:
            return (
                pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS),
                [["fetch_minute_bars", asset, str(exc)]],
            )
        if frame.empty:
            return pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS), errors
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").astype("datetime64[ms]")
        frame = frame.dropna(subset=["date"])
        # 腾讯 K 线返回 bar 起点，统一加一个周期，改为收盘时刻（项目口径）。
        frame["date"] = (frame["date"] + pd.Timedelta(minutes=int(period))).astype("datetime64[ms]")
        if start_date is not None:
            frame = frame[frame["date"].dt.date >= start_date]
        if end_date is not None:
            frame = frame[frame["date"].dt.date <= end_date]
        if frame.empty:
            return pd.DataFrame(columns=STANDARD_MINUTE_BAR_COLUMNS), errors
        # 成交额估算：volume(手) * 100 * close(元) / 1000 = 千元
        frame["amount"] = frame["volume"].fillna(0.0) * frame["close"].fillna(0.0) / 10.0
        frame = frame.sort_values("date").tail(int(count))
        return frame[STANDARD_MINUTE_BAR_COLUMNS].reset_index(drop=True), errors

    # ------------------------------------------------------------------
    # DataFetcherPort（其余能力交给 Tushare 主源）
    # ------------------------------------------------------------------
    def fetch_calendar(self, epoch: datetime.date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ms]"),
                "is_open": pd.Series(dtype="int64"),
            }
        )

    def fetch_stock_list(self) -> pd.DataFrame | None:
        return None

    def fetch_adjust_factor(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(
                {
                    "date": pd.Series(dtype="datetime64[ms]"),
                    "asset": pd.Series(dtype="object"),
                    "adjust": pd.Series(dtype="float64"),
                }
            ),
            [["fetch_adjust_factor", "tencent", "腾讯不提供复权因子，请用 Tushare"]],
        )

    def fetch_bars(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(),
            [["fetch_bars", "tencent", "腾讯不提供按日期批量日线，请用 Tushare"]],
        )

    def fetch_limit_price(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(),
            [["fetch_limit_price", "tencent", "腾讯只提供当日涨跌停（见实时快照）"]],
        )

    def fetch_st_info(
        self, dates: Iterable[datetime.date] | datetime.date
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(),
            [["fetch_st_info", "tencent", "腾讯不提供 ST 名单，请用 Tushare"]],
        )

    def fetch_bars_ext(
        self,
        dates: Iterable[datetime.date] | datetime.date,
        phase_callback: Callable[[str], None] | None = None,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(),
            [["fetch_bars_ext", "tencent", "腾讯不提供扩展日线，请用 Tushare"]],
        )

    def fetch_daily_basic(
        self,
        dates: Iterable[datetime.date] | datetime.date,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(),
            [["fetch_daily_basic", "tencent", "腾讯不提供历史市值，请用 Tushare"]],
        )

    def fetch_index_bars(
        self,
        index_codes: Iterable[str] | str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        """用腾讯日 K 线获取指数日线（基准/超额分析用）。"""
        if isinstance(index_codes, str):
            index_codes = [index_codes]
        frames: list[pd.DataFrame] = []
        errors: ErrorRecord = []
        count = max(120, (end_date - start_date).days + 40)
        for code in index_codes:
            try:
                frame = self._fetch_kline(code, "day", count)
            except Exception as exc:
                errors.append(["fetch_index_bars", code, str(exc)])
                continue
            if frame is None or frame.empty:
                continue
            frame = frame.copy()
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce").astype("datetime64[ms]")
            frame = frame.dropna(subset=["date"])
            frame = frame[
                (frame["date"].dt.date >= start_date) & (frame["date"].dt.date <= end_date)
            ]
            if frame.empty:
                continue
            frame["index_code"] = code
            frame["amount"] = 0.0
            frames.append(frame)
        if not frames:
            return pd.DataFrame(columns=STANDARD_INDEX_BAR_COLUMNS), errors
        out = pd.concat(frames, ignore_index=True)
        return out[STANDARD_INDEX_BAR_COLUMNS].sort_values(["date", "index_code"]).reset_index(
            drop=True
        ), errors

    def fetch_index_weights(
        self,
        index_codes: Iterable[str] | str,
        snapshot_dates: Iterable[datetime.date],
    ) -> tuple[pd.DataFrame, ErrorRecord]:
        return (
            pd.DataFrame(),
            [["fetch_index_weights", "tencent", "腾讯不提供指数成分 PIT，请用 Tushare"]],
        )
