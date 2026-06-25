"""运行时 broker 注册助手。"""

from typing import Any

from quantide.core.enums import BrokerKind
from quantide.core.ports import BrokerPort
from quantide.core.runtime.port_broker import PortBackedBroker
from quantide.service.registry import BrokerRegistry


def register_port_backed_broker(
    registry: BrokerRegistry,
    port: BrokerPort,
    portfolio_id: str,
    kind: BrokerKind | str,
    *,
    adapters: Any | None = None,
    adapter_name: str | None = None,
    portfolio_name: str = "",
    status: bool = True,
    is_connected: bool | None = None,
) -> PortBackedBroker:
    """注册正式 broker port，并暴露统一 handle。"""
    if isinstance(kind, BrokerKind):
        kind_value = kind.value
        broker_kind = kind
    else:
        kind_value = kind
        broker_kind = BrokerKind(kind)

    name = adapter_name or f"{kind_value}:{portfolio_id}"
    if adapters is not None:
        adapters.register("broker", name, port)

    handle = PortBackedBroker(
        port=port,
        portfolio_id=portfolio_id,
        kind=broker_kind,
        portfolio_name=portfolio_name or portfolio_id,
        status=status,
        is_connected=is_connected,
    )
    registry.register(broker_kind, portfolio_id, handle)
    return handle
