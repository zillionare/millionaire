"""实时行情发布/订阅协议（发行版公开接口）。

设计目标
--------
发行版把"实时行情"定义为一个**发布/订阅**协议，而不是绑定某个行情 SDK：

* **发布者**（用户或官方示例）周期性拉取行情，把快照发布到消息总线；
* **订阅者**（Quantide 的 Paper 撮合、风控、UI）订阅所需标的的快照；
* 双方只通过 :class:`~quantide.core.domain.events.QuoteSnapshot` 这一份结构通信。

这样：
* 官方可以提供基于 AkShare 的**示例发布者**（50 支标的轮询）；
* 用户可以换成 pytdx / QMT / 自己的服务（全市场也不在话下），
  只要发布同样结构的快照即可，Quantide 侧无需改动。

用法（发布者）
--------------
```python
from quantide.core.enums import Topics
from quantide.core.message import msg_hub

msg_hub.publish(
    Topics.QUOTES_ALL.value,
    {
        "600519.SH": {
            "price": 1318.49, "open": 1303.21, "high": 1322.0, "low": 1296.0,
            "volume": 42491, "amount": 557622.0, "ts": "2026-10-22T15:00:00",
        }
    },
)
```

用法（订阅者）
--------------
```python
from quantide.service.market_data_hub import market_data_hub

market_data_hub.start()
market_data_hub.subscribe(["600519.SH"])
snapshot = market_data_hub.snapshot(["600519.SH"])
```

字段约定
--------
``price``       最新价（撮合用）
``open/high/low`` 当日开/高/低 —— 集合竞价期间 ``price`` 即为竞价价
``volume``      累计成交量（手，与 Tushare/日线存储一致）
``amount``      累计成交额（千元，与 Tushare/日线存储一致）
``ts``          行情时间戳（ISO 字符串或 datetime）
``prev_close``  交易所调整后的昨收价（除权除息日用于盘中复权对齐）
``name``        证券名称（可选；名称含 ``ST`` 时作为 ST 状态备份）
``up_limit``/``down_limit``  可选；涨跌停价缺失时回落到本地日线数据
"""

from __future__ import annotations

import datetime
import threading
from collections.abc import AsyncIterator
from typing import Any, cast

from loguru import logger

from quantide.core.domain.events import MarketEvent, QuoteSnapshot
from quantide.core.enums import Topics
from quantide.core.market_time import market_now
from quantide.core.market_values import float_or_none as _to_float
from quantide.core.message import msg_hub

#: 快照字段名（与 QuoteSnapshot 对应）
FIELD_PRICE = "price"
FIELD_OPEN = "open"
FIELD_HIGH = "high"
FIELD_LOW = "low"
FIELD_VOLUME = "volume"
FIELD_AMOUNT = "amount"
FIELD_TS = "ts"
FIELD_PREV_CLOSE = "prev_close"
FIELD_NAME = "name"
FIELD_UP_LIMIT = "up_limit"
FIELD_DOWN_LIMIT = "down_limit"


def parse_snapshot(symbol: str, payload: dict[str, Any]) -> QuoteSnapshot | None:
    """把发布者推送的原始字典转成 :class:`QuoteSnapshot`。

    Args:
        symbol: 标的代码。
        payload: 原始字段。

    Returns:
        QuoteSnapshot | None: 解析失败或无价格时返回 None。
    """
    price = _to_float(payload.get(FIELD_PRICE))
    if price is None or price <= 0:
        return None
    ts = _to_datetime(payload.get(FIELD_TS))
    return QuoteSnapshot(
        symbol=symbol,
        price=price,
        open=_to_float(payload.get(FIELD_OPEN)),
        high=_to_float(payload.get(FIELD_HIGH)),
        low=_to_float(payload.get(FIELD_LOW)),
        volume=_to_float(payload.get(FIELD_VOLUME)),
        amount=_to_float(payload.get(FIELD_AMOUNT)),
        ts=ts,
        prev_close=_to_float(payload.get(FIELD_PREV_CLOSE)),
        name=payload.get(FIELD_NAME),
    )


def _to_datetime(value: Any) -> datetime.datetime | None:
    """任意值转 datetime，失败返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(float(value))
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


class MarketDataHub:
    """行情订阅中心（订阅者侧）。

    订阅消息总线上的 ``quotes.all`` 主题，维护最新快照缓存；
    对外提供 :class:`~quantide.core.ports.market_data.MarketDataPort` 需要的接口。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[str, QuoteSnapshot] = {}
        self._limits: dict[str, tuple[float, float]] = {}
        self._subscribed: set[str] = set()
        self._running = False
        self._stream_queue: Any = None
        self._stream_loop: Any = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        """启动订阅。"""
        if self._running:
            return
        msg_hub.subscribe(Topics.QUOTES_ALL.value, self._on_quotes)
        msg_hub.subscribe(Topics.STOCK_LIMIT.value, self._on_limits)
        self._running = True
        logger.info("行情订阅中心已启动")

    def stop(self) -> None:
        """停止订阅。"""
        if self._running:
            try:
                msg_hub.unsubscribe(Topics.QUOTES_ALL.value, self._on_quotes)
                msg_hub.unsubscribe(Topics.STOCK_LIMIT.value, self._on_limits)
            except Exception:  # pragma: no cover - 退订失败忽略
                pass
        self._running = False
        if self._stream_queue is not None:
            try:
                self._stream_queue.put_nowait(_STREAM_STOP)
            except Exception:  # pragma: no cover - queue teardown race
                pass

    @property
    def is_running(self) -> bool:
        """Whether the hub is subscribed to the quote bus."""
        return self._running

    # ------------------------------------------------------------------
    # 订阅
    # ------------------------------------------------------------------
    def subscribed_symbols(self) -> list[str]:
        """Expose the active universe to opt-in quote publishers."""
        with self._lock:
            return sorted(self._subscribed)

    def subscribe(self, symbols: list[str]) -> None:
        """订阅标的（仅用于过滤，收到全量推送时按此过滤）。"""
        with self._lock:
            self._subscribed.update(str(s) for s in symbols)

    def unsubscribe(self, symbols: list[str]) -> None:
        """取消订阅。"""
        with self._lock:
            for symbol in symbols:
                self._subscribed.discard(str(symbol))

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _on_quotes(self, payload: dict[str, Any]) -> None:
        """处理行情推送。"""
        if not payload:
            return
        updates: dict[str, QuoteSnapshot] = {}
        with self._lock:
            for symbol, raw in payload.items():
                if self._subscribed and symbol not in self._subscribed:
                    continue
                if not isinstance(raw, dict):
                    continue
                snapshot = parse_snapshot(str(symbol), raw)
                if snapshot is None:
                    continue
                self._snapshots[str(symbol)] = snapshot
                updates[str(symbol)] = snapshot
        if updates:
            self._push_events(updates)

    def _on_limits(self, payload: dict[str, Any]) -> None:
        """处理涨跌停价推送。"""
        if not payload:
            return
        with self._lock:
            for symbol, raw in payload.items():
                if not isinstance(raw, dict):
                    continue
                self._limits[str(symbol)] = (
                    float(raw.get("down_limit", raw.get("down", 0)) or 0.0),
                    float(raw.get("up_limit", raw.get("up", 0)) or 0.0),
                )

    def _push_events(self, snapshots: dict[str, QuoteSnapshot]) -> None:
        """把快照转成事件推入流队列。"""
        if self._stream_queue is None or self._stream_loop is None:
            return
        now = market_now()
        for symbol, snapshot in snapshots.items():
            event = MarketEvent(
                symbol=symbol,
                event_type="tick",
                ts=snapshot.ts or now,
                payload={
                    FIELD_PRICE: snapshot.price,
                    FIELD_OPEN: snapshot.open,
                    FIELD_HIGH: snapshot.high,
                    FIELD_LOW: snapshot.low,
                    FIELD_VOLUME: snapshot.volume,
                    FIELD_AMOUNT: snapshot.amount,
                },
                source="market_data_hub",
            )
            self._stream_loop.call_soon_threadsafe(self._put_event_safe, event)

    def _put_event_safe(self, event: MarketEvent) -> None:
        """线程安全地写入队列。"""
        if self._stream_queue is None:
            return
        try:
            self._stream_queue.put_nowait(event)
        except Exception:  # pragma: no cover - 队列满忽略
            pass

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        """返回指定标的的最新快照。"""
        with self._lock:
            return {str(s): self._snapshots[str(s)] for s in symbols if str(s) in self._snapshots}

    def get_limits(self, symbol: str) -> tuple[float, float]:
        """返回标的的涨跌停价（未推送时返回 (0, 0)）。"""
        with self._lock:
            return self._limits.get(str(symbol), (0.0, 0.0))

    def get_price_limits(self, symbol: str) -> tuple[float, float]:
        """Compatibility spelling used by the bars and broker ports."""
        return self.get_limits(symbol)

    def get_quote(self, symbol: str) -> dict[str, Any] | None:
        """Return a quote-shaped view of the latest hub snapshot.

        This is a direct MarketDataHub view for older consumers; it does not
        maintain a second quote cache or source.
        """
        snapshot = self.snapshot([symbol]).get(str(symbol))
        if snapshot is None:
            return None
        return {
            "price": snapshot.price,
            "lastPrice": snapshot.price,
            "open": snapshot.open,
            "high": snapshot.high,
            "low": snapshot.low,
            "volume": snapshot.volume,
            "amount": snapshot.amount,
            "time": snapshot.ts.timestamp() * 1000 if snapshot.ts else None,
        }

    def get_daily_bar(self, symbol: str) -> dict[str, Any] | None:
        """Return the latest snapshot in the bar-shaped compatibility format."""
        snapshot = self.snapshot([symbol]).get(str(symbol))
        if snapshot is None:
            return None
        return {
            "asset": str(symbol),
            "frame": "1d",
            "dt": (snapshot.ts or market_now()).date(),
            "open": snapshot.open,
            "high": snapshot.high,
            "low": snapshot.low,
            "close": snapshot.price,
            "volume": snapshot.volume,
            "amount": snapshot.amount,
        }

    def is_st(self, symbol: str) -> bool:
        """按发布者提供的证券名称识别 ST（Tushare 数据缺失时的备份）。"""
        with self._lock:
            snapshot = self._snapshots.get(str(symbol))
        name = (snapshot.name if snapshot else None) or ""
        return "ST" in name.upper()

    def prev_close(self, symbol: str) -> float:
        """返回标的的交易所调整后昨收价（缺失返回 0）。"""
        with self._lock:
            snapshot = self._snapshots.get(str(symbol))
        return float(snapshot.prev_close) if snapshot and snapshot.prev_close else 0.0

    def last_price(self, symbol: str) -> float:
        """返回标的最新价（无数据返回 0）。"""
        with self._lock:
            snapshot = self._snapshots.get(str(symbol))
        return float(snapshot.price) if snapshot and snapshot.price else 0.0

    async def stream(self) -> AsyncIterator[MarketEvent]:
        """行情事件流（异步迭代）。"""
        import asyncio

        queue: asyncio.Queue[object] = asyncio.Queue()
        self._stream_queue = queue
        self._stream_loop = asyncio.get_running_loop()
        try:
            while True:
                event = await queue.get()
                if event is _STREAM_STOP:
                    return
                yield cast(MarketEvent, event)
        finally:
            self._stream_queue = None
            self._stream_loop = None


#: 全局单例
_STREAM_STOP = object()
market_data_hub = MarketDataHub()
