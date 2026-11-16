"""腾讯行情发布者（公开版）。

把腾讯实时快照发布到消息总线，供 Paper 撮合、风控与 UI 消费：

- ``Topics.QUOTES_ALL``：价格/开高低/成交量额；
- ``Topics.STOCK_LIMIT``：当日涨停/跌停价（Paper 撮合的前置校验用）。

用法::

    # 需先在 wizard 显式启用演示；默认取当前订阅，最多 100 个标的
    python -m quantide.providers.tencent_publisher
    python -m quantide.providers.tencent_publisher --symbols 600519.SH,000001.SZ

也可以在自己的服务里::

    from quantide.providers.tencent_publisher import TencentPublisher

    TencentPublisher(symbols=["600519.SH"], interval=5.0).start()

默认关闭。首次启用后固定 30 天，到期停止所有请求；之后请通过用户扩展接入行情。
默认最短轮询间隔 5 秒，最多请求 100 个订阅标的。
"""

from __future__ import annotations

import argparse
import datetime
import threading
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from quantide.core.enums import Topics
from quantide.core.market_time import market_now
from quantide.core.message import msg_hub
from quantide.data.fetchers.tencent import TencentDataFetcher

#: 默认轮询间隔（秒）
DEFAULT_INTERVAL = 5.0

#: 行情请求时段（含集合竞价与收盘后 30 秒，确保拿到收盘快照）
SESSION_WINDOWS = (
    (datetime.time(9, 15), datetime.time(11, 30)),
    (datetime.time(13, 0), datetime.time(15, 0, 30)),
)


def _resolve_symbols(symbols: list[str] | None) -> list[str]:
    """未显式给定时，取当前订阅标的和演示基准，最多 100 个。"""
    if symbols:
        return list(dict.fromkeys(str(s).strip().upper() for s in symbols if str(s).strip()))[:100]
    from quantide.service.market_data_hub import market_data_hub

    subscribed = market_data_hub.subscribed_symbols()
    indices = ["000001.SH", "000300.SH", "399001.SZ", "399006.SZ"]
    return list(dict.fromkeys([*subscribed, *indices, "000001.SZ"]))[:100]


class TencentPublisher:
    """腾讯实时行情发布者。"""

    source_name = "tencent"

    def __init__(
        self,
        symbols: list[str] | None = None,
        interval: float = DEFAULT_INTERVAL,
        fetcher: TencentDataFetcher | None = None,
        calendar: Any | None = None,
        clock: Any | None = None,
        access_check: Callable[[], None] | None = None,
    ) -> None:
        """初始化。

        Args:
            symbols: 标的列表；None 表示使用当前订阅和演示基准（最多 100 个）。
            interval: 轮询间隔（秒）。
            fetcher: 可注入的腾讯适配器（测试用）。
            calendar: 交易日历（测试可注入）。
            clock: 时钟函数（测试可注入）。
        """
        from quantide.config.tencent_trial import require_tencent_access

        self._access_check = access_check or require_tencent_access
        self.symbols = list(symbols) if symbols else None
        self.interval = max(5.0, float(interval))
        self._fetcher = fetcher or TencentDataFetcher()
        self._calendar = calendar
        self._clock = clock or market_now
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _calendar_obj(self) -> Any:
        if self._calendar is not None:
            return self._calendar
        from quantide.data.models.calendar import calendar

        return calendar

    def _in_session(self, now: datetime.datetime | None = None) -> bool:
        """当前是否处于需要请求行情的交易时段。"""
        now = now or self._clock()
        try:
            if not self._calendar_obj().is_trade_day(now):
                return False
        except Exception:
            # 日历未加载时至少避开周末；节假日由运行时日历兜底。
            if now.weekday() >= 5:
                return False
        tm = now.time()
        return any(start <= tm <= end for start, end in SESSION_WINDOWS)

    def _tick(self, now: datetime.datetime | None = None) -> int:
        """交易时段内发布一轮；休市/午休直接跳过。"""
        if not self._in_session(now):
            return 0
        return self.publish_once()

    def publish_once(self) -> int:
        """拉取并发布一轮，返回成功发布的标的数。"""
        try:
            self._access_check()
        except PermissionError:
            self._stop.set()
            return 0
        symbols = _resolve_symbols(self.symbols)
        if not symbols:
            logger.warning("TencentPublisher 没有可发布的标的（股票列表为空？）")
            return 0
        try:
            snapshot = self._fetcher.fetch_quote_snapshot(symbols)
        except Exception as exc:
            logger.warning("腾讯行情拉取失败: {}", exc)
            return 0
        if not snapshot:
            return 0
        now = market_now()
        payload: dict[str, dict[str, Any]] = {}
        limits: dict[str, dict[str, float]] = {}
        for symbol, quote in snapshot.items():
            price = quote.get("price")
            if price is None or price <= 0:
                continue
            payload[symbol] = {
                "name": quote.get("name"),
                "price": price,
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "volume": quote.get("volume"),
                "amount": quote.get("amount"),
                "prev_close": quote.get("prev_close"),
                "ts": quote.get("ts") or now,
            }
            up = quote.get("up_limit")
            down = quote.get("down_limit")
            if up and down:
                # 同时提供 PaperBroker（up/down）与 Hub（up_limit/down_limit）的键名
                limits[symbol] = {
                    "up": float(up),
                    "down": float(down),
                    "up_limit": float(up),
                    "down_limit": float(down),
                }
        if payload:
            msg_hub.publish(Topics.QUOTES_ALL.value, payload)
        if limits:
            msg_hub.publish(Topics.STOCK_LIMIT.value, limits)
        return len(payload)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        """启动后台发布线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._access_check()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="tencent-publisher")
        self._thread.start()
        logger.info(
            "腾讯行情发布者已启动，标的数 {}，间隔 {}s",
            len(self.symbols) if self.symbols else "当前订阅（最多 100）",
            self.interval,
        )

    def stop(self) -> None:
        """停止发布线程。"""
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._access_check()
            except PermissionError:
                self._stop.set()
                break
            count = self._tick()
            if count:
                logger.debug("已发布 {} 个标的的行情", count)
            self._stop.wait(self.interval)


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="腾讯行情发布者")
    parser.add_argument(
        "--symbols", default="", help="逗号分隔的标的代码；为空=当前订阅（最多 100）"
    )
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    publisher = TencentPublisher(symbols or None, interval=args.interval)
    publisher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        publisher.stop()


if __name__ == "__main__":
    main()
