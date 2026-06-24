"""FR-360 风控评估事件层.

按 spec-trading.md §FR-360 + interfaces.md §6:
- risk.triggered event: RiskStrategy 触发卖出时发出
- risk.excess_return.finalized event: N 日窗口结束时回填 excess_return
- activation_id 生命周期: RiskStrategy 启动时分配 UUID, 停止时关闭

事件 payload schema (interfaces.md §6):
  risk.triggered:
    - event_id: str (UUID)
    - activation_id: str (UUID, RiskStrategy 启动时分配)
    - risk_strategy_id: str
    - host_strategy_id: str
    - asset: str
    - trigger_price: float
    - cost_basis: float | None
    - reason: str (pullback/cost_stop/stop_loss/...)
    - trigger_ts: datetime
    - barrier_hit: up/down/expire (default expire, F-TB-1/2 触发时为 up/down)
  risk.excess_return.finalized:
    - event_id: str (UUID)
    - activation_id: str
    - event_id_triggered: str (关联 risk.triggered 的 event_id)
    - excess_return: float | None (N=0 立即算; N>0 N 日后回填)
    - finalized_at: datetime

使用 msg_hub 单例发送事件, 消费方 (e2e, UI, 持久化层) 通过 subscribe 接收.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from quantide.core.message import msg_hub


RISK_TRIGGERED_TOPIC = "risk.triggered"
RISK_EXCESS_FINALIZED_TOPIC = "risk.excess_return.finalized"


class BarrierHit(str, Enum):
    """屏障触发类型 (F-TB-1/2/3)."""

    UP = "up"
    DOWN = "down"
    EXPIRE = "expire"


@dataclass(frozen=True)
class RiskTriggeredEvent:
    """risk.triggered 事件 payload."""

    event_id: str
    activation_id: str
    risk_strategy_id: str
    host_strategy_id: str
    asset: str
    trigger_price: float
    cost_basis: float | None
    reason: str
    trigger_ts: datetime.datetime
    barrier_hit: BarrierHit = BarrierHit.EXPIRE
    tm: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["barrier_hit"] = self.barrier_hit.value
        d["trigger_ts"] = self.trigger_ts.isoformat()
        d["tm"] = self.tm.isoformat()
        return d


@dataclass(frozen=True)
class RiskExcessFinalizedEvent:
    """risk.excess_return.finalized 事件 payload."""

    event_id: str
    activation_id: str
    triggered_event_id: str
    excess_return: float | None
    finalized_at: datetime.datetime
    tm: datetime.datetime = field(default_factory=datetime.datetime.now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["finalized_at"] = self.finalized_at.isoformat()
        d["tm"] = self.tm.isoformat()
        return d


def emit_risk_triggered(
    activation_id: str,
    risk_strategy_id: str,
    host_strategy_id: str,
    asset: str,
    trigger_price: float,
    cost_basis: float | None,
    reason: str,
    trigger_ts: datetime.datetime,
    barrier_hit: BarrierHit = BarrierHit.EXPIRE,
) -> str:
    """发送 risk.triggered event, 返回 event_id."""
    event_id = str(uuid.uuid4())
    event = RiskTriggeredEvent(
        event_id=event_id,
        activation_id=activation_id,
        risk_strategy_id=risk_strategy_id,
        host_strategy_id=host_strategy_id,
        asset=asset,
        trigger_price=trigger_price,
        cost_basis=cost_basis,
        reason=reason,
        trigger_ts=trigger_ts,
        barrier_hit=barrier_hit,
    )
    msg_hub.publish(RISK_TRIGGERED_TOPIC, event.to_dict())
    return event_id


def emit_risk_excess_finalized(
    activation_id: str,
    triggered_event_id: str,
    excess_return: float | None,
    finalized_at: datetime.datetime,
) -> str:
    """发送 risk.excess_return.finalized event, 返回 event_id."""
    event_id = str(uuid.uuid4())
    event = RiskExcessFinalizedEvent(
        event_id=event_id,
        activation_id=activation_id,
        triggered_event_id=triggered_event_id,
        excess_return=excess_return,
        finalized_at=finalized_at,
    )
    msg_hub.publish(RISK_EXCESS_FINALIZED_TOPIC, event.to_dict())
    return event_id
