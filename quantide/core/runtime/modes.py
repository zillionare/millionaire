"""运行时模式装配."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from quantide.config.features import supports_live_trading
from quantide.config.settings import get_settings
from quantide.core.enums import BrokerKind
from quantide.core.ports import MarketDataPort
from quantide.core.ports.clock import ClockPort
from quantide.core.runtime.adapter_registry import AdapterRegistry
from quantide.core.runtime.clock_bridge import SystemClockAdapter
from quantide.core.runtime.gateway_broker import GatewayBrokerAdapter
from quantide.core.runtime.gateway_client import GatewayClient
from quantide.core.runtime.port_broker import PortBackedBroker
from quantide.core.runtime.registration import register_port_backed_broker
from quantide.core.scheduler import scheduler
from quantide.data import db
from quantide.service.market_data_hub import market_data_hub
from quantide.service.registry import BrokerRegistry
from quantide.service.sim_broker import PaperBroker

if TYPE_CHECKING:
    from quantide.providers.tencent_publisher import TencentPublisher

RuntimeMode = Literal["live", "paper", "backtest"]

_quote_publisher_lock = threading.Lock()
_quote_publisher: Any = None


@dataclass
class RuntimeContext:
    """运行时上下文."""

    mode: RuntimeMode
    registry: BrokerRegistry
    adapters: AdapterRegistry
    market_data: MarketDataPort
    clock: ClockPort

    def register_port_broker(
        self,
        port: Any,
        portfolio_id: str,
        kind: BrokerKind | str,
        *,
        adapter_name: str | None = None,
        portfolio_name: str = "",
        status: bool = True,
        is_connected: bool | None = None,
    ) -> PortBackedBroker:
        """将正式 broker port 注册到运行时。"""
        return register_port_backed_broker(
            registry=self.registry,
            adapters=self.adapters,
            port=port,
            portfolio_id=portfolio_id,
            kind=kind,
            adapter_name=adapter_name,
            portfolio_name=portfolio_name,
            status=status,
            is_connected=is_connected,
        )


class RuntimeBootstrap:
    """运行时装配器."""

    def __init__(self, mode: RuntimeMode | None = None, clock: ClockPort | None = None) -> None:
        """初始化装配器.

        Args:
            mode: 指定运行模式，不传则自动解析。
            clock: 时钟端口 (NFR-060), 不传则默认注入 `SystemClockAdapter` (生产语义: 返回墙钟).
                  测试侧可传入 `VirtualClock` (见 tests/e2e/support/virtual_clock.py) 替换时间.
        """
        requested_mode = mode or self._resolve_mode()
        self._mode = (
            "paper" if requested_mode == "live" and not supports_live_trading() else requested_mode
        )
        self._clock = clock if clock is not None else SystemClockAdapter()

    def bootstrap(self) -> RuntimeContext:
        """执行运行时装配."""
        scheduler.start()
        adapters = AdapterRegistry()
        market_data = self._build_market_data(adapters)
        registry = BrokerRegistry()
        self._registry_ref = registry
        self._load_accounts_from_db(registry, market_data=market_data)
        self._register_broker_adapters(registry, adapters)
        self._register_gateway_broker_adapter(adapters, market_data)
        return RuntimeContext(
            mode=self._mode,
            registry=registry,
            adapters=adapters,
            market_data=market_data,
            clock=self._clock,
        )

    def _resolve_mode(self) -> RuntimeMode:
        """解析运行模式."""
        runtime = get_settings()
        raw = runtime.runtime_mode
        if raw == "live" and not supports_live_trading():
            # Older CE state files used ``live`` as their default.  Coerce
            # those files to the safe paper runtime instead of allowing a
            # restart to create a live gateway runtime.
            return "paper"
        if raw in {"live", "paper", "backtest"}:
            return raw  # type: ignore
        if not runtime.gateway_enabled:
            return "backtest"
        return "live"

    def _build_market_data(self, adapters: AdapterRegistry) -> MarketDataPort:
        """构建行情适配器.

        行情来源是**发布/订阅**协议：任何发布者（官方 AkShare 示例、用户自带的
        pytdx/QMT 服务）把快照发布到消息总线 ``quotes.all``，
        这里统一由 :class:`MarketDataHub` 订阅并提供给 Paper 撮合与风控。

         所有实时消费者统一使用 ``MarketDataHub``。
        """
        market_data_hub.start()
        from quantide.service.limit_price_refresher import limit_price_refresher
        from quantide.service.minute_bar_aggregator import minute_bar_aggregator
        from quantide.service.quote_monitor import quote_monitor

        minute_bar_aggregator.ensure_started()
        limit_price_refresher.start()
        quote_monitor.start()
        self._start_embedded_publisher(adapters)
        adapters.register("market_data", "market_data_hub", market_data_hub)
        return market_data_hub

    def _start_embedded_publisher(self, adapters: AdapterRegistry) -> None:
        """按环境变量启动内置行情发布者（可选，默认关闭）。

        ``QUANTIDE_QUOTE_PUBLISHER=tencent`` 时启动腾讯发布者；可用
        ``QUANTIDE_QUOTE_SYMBOLS=600519.SH,000001.SZ`` 限制标的，
        ``QUANTIDE_QUOTE_INTERVAL`` 控制间隔（秒）。
        """
        global _quote_publisher
        from quantide.config.realtime_source import realtime_source
        from quantide.config.tencent_trial import trial_status
        from quantide.providers.extensions import load_quote_provider, quote_provider_enabled

        selected = realtime_source()
        use_extension = selected == "extension" or (not selected and quote_provider_enabled())
        use_tushare = selected == "tushare"
        if selected == "none" or not (use_tushare or use_extension or trial_status().enabled):
            return
        with _quote_publisher_lock:
            if _quote_publisher is None:
                if use_tushare:
                    from quantide.providers.tushare_publisher import TusharePublisher

                    _quote_publisher = TusharePublisher()
                else:
                    _quote_publisher = (
                        load_quote_provider() if use_extension else self._create_tencent_publisher()
                    )
            publisher = _quote_publisher
            publisher.start()
        name = "tushare" if use_tushare else ("user" if use_extension else "tencent")
        adapters.register("quote_publisher", name, publisher)

    @staticmethod
    def _create_tencent_publisher() -> TencentPublisher:
        from quantide.providers.tencent_publisher import TencentPublisher

        raw_symbols = os.environ.get("QUANTIDE_QUOTE_SYMBOLS", "")
        symbols = [part.strip() for part in raw_symbols.split(",") if part.strip()] or None
        try:
            interval = float(os.environ.get("QUANTIDE_QUOTE_INTERVAL", "5") or 5)
        except ValueError:
            interval = 5.0
        return TencentPublisher(symbols, interval=interval)

    def _register_broker_adapters(
        self, registry: BrokerRegistry, adapters: AdapterRegistry
    ) -> None:
        """注册已加载账户的 broker 适配器."""
        for item in registry.list():
            kind = item.get("kind")
            portfolio_id = item.get("id")
            if not kind or not portfolio_id:
                continue
            broker = registry.get(kind, portfolio_id)
            if broker is None:
                continue
            name = f"{kind}:{portfolio_id}"
            port = broker
            register_port_backed_broker(
                registry=registry,
                adapters=adapters,
                port=port,
                portfolio_id=portfolio_id,
                kind=kind,
                adapter_name=name,
                portfolio_name=getattr(broker, "portfolio_name", ""),
                status=getattr(broker, "status", True),
            )

    def _load_accounts_from_db(
        self,
        registry: BrokerRegistry,
        market_data: MarketDataPort | None = None,
    ) -> None:
        """从数据库加载账户."""
        try:
            portfolios = db.get_all_portfolios()
        except RuntimeError:
            return
        for portfolio in portfolios:
            if portfolio.kind != BrokerKind.SIMULATION:
                continue
            try:
                broker = PaperBroker.load(
                    portfolio.portfolio_id,
                    market_data=market_data,
                    clock=self._clock,
                )
                registry.register(BrokerKind.SIMULATION, portfolio.portfolio_id, broker)
            except Exception:
                continue

    def _register_gateway_broker_adapter(
        self,
        adapters: AdapterRegistry,
        market_data: MarketDataPort,
    ) -> None:
        """注册 gateway 交易适配器."""
        if not supports_live_trading():
            return
        runtime = get_settings()
        broker_name = runtime.runtime_broker_adapter
        mode_name = "gateway"
        gateway_url = str(getattr(runtime, "gateway_base_url", "") or "").strip()
        use_gateway = (
            runtime.gateway_enabled
            and bool(gateway_url)
            and (broker_name == "gateway" or mode_name == "gateway")
        )
        if not use_gateway:
            return
        client = GatewayClient.from_config()
        adapter = GatewayBrokerAdapter(client)
        registry = getattr(self, "_registry_ref", None)
        if registry:
            register_port_backed_broker(
                registry=registry,
                adapters=adapters,
                port=adapter,
                portfolio_id="gateway",
                kind=BrokerKind.QMT,
                adapter_name="gateway:default",
                portfolio_name="实盘网关",
                status=True,
                is_connected=True,
            )
