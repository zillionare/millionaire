import asyncio
import datetime
import json
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Any

import polars as pl
import websockets
from loguru import logger

from quantide.config.settings import get_settings
from quantide.core.domain import MarketEvent, QuoteSnapshot
from quantide.core.enums import Topics
from quantide.core.message import msg_hub
from quantide.core.scheduler import scheduler
from quantide.data.fetchers.registry import get_data_fetcher


class LiveQuote:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._mode: str | None = None
        self._is_running = False
        self._quotes: dict[str, dict[str, Any]] = {}
        self._limits: dict[str, dict[str, float]] = {}
        self._minute_bars: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=480))
        self._daily_bars: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._ws_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # MarketDataPort stream state
        self._subscribed: set[str] = set()
        self._stream_queue: asyncio.Queue[MarketEvent] | None = None
        self._stream_loop: asyncio.AbstractEventLoop | None = None
        self._streaming = False

    def start(self):
        if self._is_running:
            return
        self._mode = "gateway"
        self._is_running = True
        self._stop_event.clear()
        self._start_limit_schedule()
        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True, name="livequote-ws")
        self._ws_thread.start()

    def stop(self):
        self._streaming = False
        self._is_running = False
        self._stop_event.set()
        # 注入 sentinel 唤醒可能阻塞在 queue.get() 的 stream() 消费者
        if self._stream_queue is not None and self._stream_loop is not None:
            self._stream_loop.call_soon_threadsafe(
                self._stream_queue.put_nowait, None,
            )

    def _run_ws(self):
        asyncio.run(self._ws_loop())

    async def _ws_loop(self):
        while not self._stop_event.is_set():
            ws_url = self._build_ws_url()
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    while not self._stop_event.is_set():
                        raw = await ws.recv()
                        payload = self._parse_ws_payload(raw)
                        if not payload:
                            continue
                        self._cache_and_broadcast(payload)
            except Exception as e:
                logger.warning(f"gateway ws disconnected: {e}")
                await asyncio.sleep(2)

    def _build_ws_url(self) -> str:
        base_url = get_settings().gateway_base_url.rstrip("/")
        if base_url.startswith("https://"):
            return "wss://" + base_url[len("https://") :] + "/ws/quotes"
        if base_url.startswith("http://"):
            return "ws://" + base_url[len("http://") :] + "/ws/quotes"
        return f"ws://{base_url}/ws/quotes"

    def _parse_ws_payload(self, raw: str | bytes) -> dict[str, dict[str, Any]]:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        symbol = str(data.get("symbol") or "")
        if not symbol:
            return {}
        ts = data.get("timestamp")
        ts_ms = int(float(ts or time.time()) * 1000)
        m1_raw = data.get("1m")
        d1_raw = data.get("1d")
        m1: dict[str, Any] = m1_raw if isinstance(m1_raw, dict) else {}
        d1: dict[str, Any] = d1_raw if isinstance(d1_raw, dict) else {}

        # Issue #20：forming daily bar 从首个 tick 起累积。后续 tick 缺字段时
        # 不可被 0/默认值覆盖；open 锁首日开盘、high/low 取 max/min、close 跟最新价、
        # volume/amount 跨 tick 累加。
        with self._lock:
            prev_raw = self._daily_bars.get(symbol) or {}
            new_dt = datetime.datetime.fromtimestamp(ts_ms / 1000).date()
            prev_dt = prev_raw.get("dt")
            # 跨日切换：丢掉旧日缓存，按新 tick 重建（LiveQuote 只跟踪当前交易
            # 日的 forming bar；旧日应该是已结算的 fixed bar，不应再被"累积"）。
            is_new_day = prev_dt is not None and prev_dt != new_dt
            prev = {} if is_new_day else prev_raw
            prev_open = self._to_float(prev.get("open"), 0.0)
            prev_high = self._to_float(prev.get("high"), 0.0)
            prev_low = self._to_float(prev.get("low"), 0.0)
            prev_close = self._to_float(prev.get("close"), 0.0)
            prev_volume = self._to_float(prev.get("volume"), 0.0)
            prev_amount = self._to_float(prev.get("amount"), 0.0)

        new_close = self._to_float(m1.get("close"), self._to_float(d1.get("close"), 0.0))
        new_open_d1 = self._to_float(d1.get("open"), 0.0)
        new_open_m1 = self._to_float(m1.get("open"), 0.0)
        new_high_m1 = self._to_float(m1.get("high"), 0.0)
        new_low_m1 = self._to_float(m1.get("low"), 0.0)
        new_high_d1 = self._to_float(d1.get("high"), 0.0)
        new_low_d1 = self._to_float(d1.get("low"), 0.0)
        # volume/amount 必须有 1d 字段才累加（1d 是日内累计；m1 是单分钟，
        # 不可与日内累计相加，否则一分钟一次推送会让成交量膨胀 240 倍）。
        if d1:
            new_volume = self._to_float(d1.get("vol"), 0.0)
            new_amount = self._to_float(d1.get("amount"), 0.0)
            has_d1_volume = True
        else:
            new_volume = 0.0
            new_amount = 0.0
            has_d1_volume = False

        if new_close <= 0:
            new_close = prev_close
        daily_open = new_open_d1 if new_open_d1 > 0 else (prev_open if prev_open > 0 else new_open_m1)
        # 1d 字段本身就是日内 running high/low（gateway 已聚合），
        # 直接用最新；只有当 1d 缺字段时才退化到与 m1 联合 max/min。
        if new_high_d1 > 0:
            daily_high = new_high_d1
        else:
            candidate_highs = [v for v in (prev_high, new_high_m1) if v > 0]
            daily_high = max(candidate_highs) if candidate_highs else new_close
        if new_low_d1 > 0:
            daily_low = new_low_d1
        else:
            candidate_lows = [v for v in (prev_low, new_low_m1) if v > 0]
            daily_low = min(candidate_lows) if candidate_lows else new_close
        daily_volume = prev_volume + new_volume if has_d1_volume else prev_volume
        daily_amount = prev_amount + new_amount if has_d1_volume else prev_amount
        daily_dt = new_dt

        quote = {
            "price": new_close,
            "lastPrice": new_close,
            "open": new_open_m1 if new_open_m1 > 0 else daily_open,
            "high": new_high_m1 if new_high_m1 > 0 else daily_high,
            "low": new_low_m1 if new_low_m1 > 0 else daily_low,
            "volume": daily_volume,
            "amount": daily_amount,
            "time": ts_ms,
        }
        minute_bar = {
            "asset": symbol,
            "frame": "1m",
            "dt": datetime.datetime.fromtimestamp(ts_ms / 1000),
            "open": new_open_m1 if new_open_m1 > 0 else daily_open,
            "high": new_high_m1 if new_high_m1 > 0 else daily_high,
            "low": new_low_m1 if new_low_m1 > 0 else daily_low,
            "close": new_close,
            "volume": self._to_float(m1.get("vol"), 0.0),
            "amount": self._to_float(m1.get("amount"), 0.0),
        }
        daily_bar = {
            "asset": symbol,
            "frame": "1d",
            "dt": daily_dt,
            "open": daily_open,
            "high": daily_high,
            "low": daily_low,
            "close": new_close,
            "volume": daily_volume,
            "amount": daily_amount,
        }
        with self._lock:
            self._minute_bars[symbol].append(minute_bar)
            self._daily_bars[symbol] = daily_bar
        return {symbol: quote}

    def _start_limit_schedule(self):
        scheduler.add_job(
            self._refresh_limits,
            "cron",
            hour=9,
            minute=0,
            name="livequote.limit.refresh",
        )
        self._refresh_limits()

    def _refresh_limits(self, dt: datetime.date | None = None):
        dt = dt or datetime.date.today()
        try:
            df, _ = get_data_fetcher().fetch_limit_price(dt)
        except Exception as e:
            logger.warning(f"refresh limits failed: {e}")
            return
        if df is None or df.empty:
            return
        symbol_col = "asset" if "asset" in df.columns else "ts_code" if "ts_code" in df.columns else None
        if symbol_col is None:
            return
        up_col = "up_limit" if "up_limit" in df.columns else None
        down_col = "down_limit" if "down_limit" in df.columns else None
        if up_col is None:
            df["up_limit"] = 0.0
            up_col = "up_limit"
        if down_col is None:
            df["down_limit"] = 0.0
            down_col = "down_limit"
        data = {
            str(row[symbol_col]): {
                "up_limit": float(row[up_col] or 0),
                "down_limit": float(row[down_col] or 0),
            }
            for _, row in df.iterrows()
        }
        self._cache_limits_and_broadcast(data)

    def _cache_and_broadcast(self, data: dict[str, Any]):
        with self._lock:
            self._quotes.update(data)
        msg_hub.publish(Topics.QUOTES_ALL.value, data)

    def _cache_limits(self, data: dict[str, Any] | None):
        if not data:
            return
        with self._lock:
            self._limits.update(data)

    def _cache_limits_and_broadcast(self, data: dict[str, Any]):
        self._cache_limits(data)
        msg_hub.publish(Topics.STOCK_LIMIT.value, data)

    def get_quote(self, asset: str) -> dict[str, Any] | None:
        with self._lock:
            return self._quotes.get(asset)

    def get_price_limits(self, asset: str) -> tuple[float, float]:
        with self._lock:
            data = self._limits.get(asset)
        if data is None:
            return 0.0, 0.0
        return float(data.get("down_limit", 0)), float(data.get("up_limit", 0))

    def get_limit(self, asset: str) -> dict[str, float] | None:
        with self._lock:
            return self._limits.get(asset)

    def get_minute_bars(self, symbol: str) -> pl.DataFrame:
        with self._lock:
            data = list(self._minute_bars.get(symbol, []))
        if not data:
            return pl.DataFrame(schema={"asset": pl.Utf8, "frame": pl.Utf8, "dt": pl.Datetime, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "volume": pl.Float64, "amount": pl.Float64})
        return pl.DataFrame(data)

    def get_daily_bar(self, symbol: str) -> dict[str, Any] | None:
        with self._lock:
            return self._daily_bars.get(symbol)

    @property
    def all_limits(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return dict(self._limits)

    @property
    def all_quotes(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._quotes)

    @property
    def all_minute_bars(self) -> pl.DataFrame:
        with self._lock:
            data: list[dict[str, Any]] = []
            for rows in self._minute_bars.values():
                data.extend(rows)
        if not data:
            return pl.DataFrame(schema={"asset": pl.Utf8, "frame": pl.Utf8, "dt": pl.Datetime, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "volume": pl.Float64, "amount": pl.Float64})
        return pl.DataFrame(data)

    @property
    def all_daily_bars(self) -> pl.DataFrame:
        with self._lock:
            values = list(self._daily_bars.values())
        if not values:
            return pl.DataFrame(schema={"asset": pl.Utf8, "frame": pl.Utf8, "dt": pl.Date, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "volume": pl.Float64, "amount": pl.Float64})
        return pl.DataFrame(values)

    @property
    def mode(self) -> str | None:
        return self._mode

    @property
    def is_running(self) -> bool:
        return self._is_running


    # ── MarketDataPort methods ──────────────────────────────────────────

    def subscribe(self, symbols: list[str]) -> None:
        """登记关注标的."""
        for symbol in symbols:
            if symbol:
                self._subscribed.add(symbol)

    def unsubscribe(self, symbols: list[str]) -> None:
        """移除关注标的."""
        for symbol in symbols:
            self._subscribed.discard(symbol)

    async def stream(self) -> AsyncIterator[MarketEvent]:
        """获取行情事件流 (async generator).

        使用 asyncio.Queue + call_soon_threadsafe 桥接
        msg_hub dispatch 线程与 asyncio 事件循环。
        """
        if self._stream_queue is not None:
            raise RuntimeError("stream already started")
        self._stream_queue = asyncio.Queue(maxsize=2000)
        self._stream_loop = asyncio.get_running_loop()
        self._streaming = True
        msg_hub.subscribe(Topics.QUOTES_ALL.value, self._on_quotes_all)
        try:
            while self._streaming:
                event = await self._stream_queue.get()
                if event is None:  # sentinel from stop()
                    break
                yield event
        finally:
            self._streaming = False
            msg_hub.unsubscribe(Topics.QUOTES_ALL.value, self._on_quotes_all)
            self._stream_queue = None
            self._stream_loop = None

    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        """获取行情快照."""
        result: dict[str, QuoteSnapshot] = {}
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote is None:
                continue
            ts_raw = quote.get("time")
            ts = None
            if isinstance(ts_raw, (int, float)) and ts_raw > 0:
                ts = datetime.datetime.fromtimestamp(ts_raw / 1000)
            result[symbol] = QuoteSnapshot(
                symbol=symbol,
                price=self._to_float_or_none(quote.get("price")),
                open=self._to_float_or_none(quote.get("open")),
                high=self._to_float_or_none(quote.get("high")),
                low=self._to_float_or_none(quote.get("low")),
                volume=self._to_float_or_none(quote.get("volume")),
                amount=self._to_float_or_none(quote.get("amount")),
                ts=ts,
            )
        return result

    def _on_quotes_all(self, payload: dict[str, dict[str, Any]]) -> None:
        """接收消息总线行情推送, 桥接到 async stream."""
        if self._stream_queue is None or self._stream_loop is None:
            return
        if not payload:
            return
        now = datetime.datetime.now()
        for symbol, quote in payload.items():
            if self._subscribed and symbol not in self._subscribed:
                continue
            event = MarketEvent(
                symbol=symbol,
                event_type="tick",
                ts=now,
                payload=dict(quote),
                source="live_quote",
            )
            self._stream_loop.call_soon_threadsafe(self._put_event_safe, event)

    def _put_event_safe(self, event: MarketEvent) -> None:
        """将事件写入队列 (从 event loop 线程调用)."""
        if self._stream_queue is None:
            return
        try:
            self._stream_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def _to_float_or_none(self, value: Any) -> float | None:
        """将任意值转换为浮点, 失败时返回 None."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default


live_quote = LiveQuote()
