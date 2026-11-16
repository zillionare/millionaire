import datetime
from types import SimpleNamespace

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import BrokerKind
from quantide.core.runtime import modes as runtime_modes
from quantide.data.models import Asset, Portfolio
from quantide.data.sqlite import db


class DummyGatewayMarketData:
    def __init__(self, client):
        self.client = client
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def subscribe(self, symbols: list[str]) -> None:
        _ = symbols

    def unsubscribe(self, symbols: list[str]) -> None:
        _ = symbols

    async def stream(self):
        if False:
            yield None

    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        symbol = symbols[0]
        return {
            symbol: QuoteSnapshot(
                symbol=symbol,
                price=10.0,
                open=10.0,
                high=10.0,
                low=10.0,
                volume=1000,
                amount=10000.0,
                ts=datetime.datetime.now(),
            )
        }


def test_runtime_bootstrap_paper_uses_live_quote_market_data(monkeypatch):
    """#48: 数据源统一后, 任意配置 (gateway 开关 / 适配器名) 都走 LiveQuote."""
    db.init(":memory:")
    db.insert_portfolio(
        Portfolio(
            portfolio_id="paper-account",
            kind=BrokerKind.SIMULATION,
            start=datetime.date(2024, 1, 2),
            name="paper-account",
            status=True,
        )
    )
    db.upsert_asset(
        Asset(
            portfolio_id="paper-account",
            dt=datetime.date(2024, 1, 2),
            principal=100000,
            cash=100000,
            frozen_cash=0,
            market_value=0,
            total=100000,
        )
    )

    runtime_cfg = SimpleNamespace(
        runtime_mode="paper",
        gateway_enabled=True,
        gateway_base_url="http://gateway.local",
        runtime_broker_adapter="",
        livequote_mode="none",
    )

    monkeypatch.setattr(runtime_modes, "get_settings", lambda: runtime_cfg)
    monkeypatch.setattr(runtime_modes.scheduler, "start", lambda: None)

    runtime = runtime_modes.RuntimeBootstrap(mode="paper").bootstrap()

    assert runtime.mode == "paper"
    assert runtime.market_data is runtime_modes.market_data_hub

    handle = runtime.registry.get(BrokerKind.SIMULATION, "paper-account")
    assert handle is not None
    assert handle.portfolio_id == "paper-account"
    assert handle.portfolio_name == "paper-account"


def test_embedded_tencent_publisher_starts_when_enabled(monkeypatch):
    """QUANTIDE_QUOTE_PUBLISHER=tencent 时在服务进程内启动发布者。"""
    from quantide.core.runtime.adapter_registry import AdapterRegistry

    from types import SimpleNamespace
    monkeypatch.setattr("quantide.config.tencent_trial.trial_status",
                        lambda: SimpleNamespace(enabled=True))
    started: dict = {}

    class _FakePublisher:
        def __init__(self, symbols=None, interval=3.0):
            started["symbols"] = symbols
            started["interval"] = interval

        def start(self):
            started["started"] = True

    monkeypatch.setenv("QUANTIDE_QUOTE_PUBLISHER", "tencent")
    monkeypatch.setenv("QUANTIDE_QUOTE_SYMBOLS", "600519.SH,000001.SZ")
    monkeypatch.setenv("QUANTIDE_QUOTE_INTERVAL", "2")
    monkeypatch.setattr(
        "quantide.providers.tencent_publisher.TencentPublisher", _FakePublisher
    )
    monkeypatch.setattr(runtime_modes, "_quote_publisher", None)

    bootstrap = runtime_modes.RuntimeBootstrap(mode="paper")
    bootstrap._start_embedded_publisher(AdapterRegistry())
    assert started["started"] is True
    assert started["symbols"] == ["600519.SH", "000001.SZ"]
    assert started["interval"] == 2.0


def test_register_broker_adapters_preserves_portfolio_name(monkeypatch):
    """注册 adapter 时保留账户名称，避免侧边栏显示账户 ID。"""
    from types import SimpleNamespace

    from quantide.core.runtime.adapter_registry import AdapterRegistry
    from quantide.service.registry import BrokerRegistry

    registry = BrokerRegistry()
    broker = SimpleNamespace(portfolio_name="Paper 100万", status=True)
    registry.register(BrokerKind.SIMULATION, "sim_test", broker)

    bootstrap = runtime_modes.RuntimeBootstrap(mode="paper")
    bootstrap._register_broker_adapters(registry, AdapterRegistry())
    items = {item["id"]: item for item in registry.list_by_kind(BrokerKind.SIMULATION)}
    assert items["sim_test"]["name"] == "Paper 100万"


def test_runtime_bootstrap_uses_hub_when_gateway_url_empty(monkeypatch):
    """网关已开启但地址为空时，不应启动 live_quote，行情回落到 Hub。"""
    db.init(":memory:")
    db.insert_portfolio(
        Portfolio(
            portfolio_id="paper-hub-account",
            kind=BrokerKind.SIMULATION,
            start=datetime.date(2024, 1, 2),
            name="paper-hub-account",
            status=True,
        )
    )
    db.upsert_asset(
        Asset(
            portfolio_id="paper-hub-account",
            dt=datetime.date(2024, 1, 2),
            principal=100000,
            cash=100000,
            frozen_cash=0,
            market_value=0,
            total=100000,
        )
    )
    runtime_cfg = SimpleNamespace(
        runtime_mode="paper",
        gateway_enabled=True,
        gateway_base_url="",
        runtime_broker_adapter="",
        livequote_mode="none",
    )
    monkeypatch.setattr(runtime_modes, "get_settings", lambda: runtime_cfg)
    monkeypatch.setattr(runtime_modes.scheduler, "start", lambda: None)
    runtime = runtime_modes.RuntimeBootstrap(mode="paper").bootstrap()
    assert runtime.market_data is runtime_modes.market_data_hub
