"""Durable runtime specifications and restart restoration."""

from __future__ import annotations

import datetime
import json
import uuid
from _thread import RLock
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quantide.config.features import require_live_trading, supports_live_trading
from quantide.config.paths import get_strategy_runtime_state_path
from quantide.core.atomic_files import write_json
from quantide.core.enums import BrokerKind
from quantide.service.runtime_config import _optional_float
from quantide.service.runtime_models import StrategyRuntime

if TYPE_CHECKING:
    from quantide.service.registry import BrokerRegistry


def _resolve_runtime_account(
    self: RuntimeStatePersistence, spec: dict[str, Any]
) -> tuple[str, str, Any]:
    """Validate the edition and resolve the persisted runtime account."""
    if str(spec.get("mode") or "").lower() == "live":
        require_live_trading()
    if self._registry is None:
        raise RuntimeError("registry 未初始化")
    account_kind = str(spec.get("account_kind") or "")
    portfolio_id = str(spec.get("portfolio_id") or "")
    broker = None
    if account_kind == "gateway":
        broker = self._gateway_broker
    if broker is None:
        broker = self._registry.get(account_kind, portfolio_id)
    if broker is None:
        raise RuntimeError(f"账户不存在: {account_kind}:{portfolio_id}")
    if "interval" not in spec or not str(spec.get("interval") or "").strip():
        raise RuntimeError("持久化运行时缺少不可变策略周期")
    return account_kind, portfolio_id, broker


def _restore_paper_fees(account_kind: str, broker: Any, spec: dict[str, Any]) -> None:
    """Restore paper fees."""
    if account_kind == BrokerKind.SIMULATION.value:
        port = getattr(broker, "port", None)
        apply_fee_config = getattr(port, "apply_fee_config", None)
        if callable(apply_fee_config):
            config = dict(spec.get("config") or {})
            apply_fee_config(
                commission=_optional_float(config.get("commission")),
                stamp_tax=_optional_float(config.get("stamp_duty")),
                transfer_fee=_optional_float(config.get("transfer_fee")),
                min_commission=_optional_float(config.get("min_commission")),
                slippage=_optional_float(config.get("slippage_pct")),
            )


class RuntimeStatePersistence:
    """Durable runtime specifications and restart restoration."""

    if TYPE_CHECKING:
        _lock: RLock
        _registry: BrokerRegistry | None
        _gateway_broker: Any
        _market_data: Any
        _runtime_specs: dict[str, dict[str, Any]]
        _blocked_accounts: dict[str, dict[str, Any]]
        _blocked_strategies: dict[str, dict[str, Any]]
        _risk_events: list[dict[str, Any]]
        _data_missing_alarms: set[str]

        def record_system_event(
            self,
            *,
            title: str,
            message: str,
            severity: str = "warning",
            blocked: bool = True,
            target_id: str = "system",
        ) -> None: ...
        def _start_strategy_runtime(
            self,
            mode: str,
            strategy_name: str,
            config: dict[str, Any],
            broker: Any,
            portfolio_id: str,
            source_backtest_portfolio_id: str,
            account_kind: str,
            interval: str,
            market_data: Any,
            principal: float = 0.0,
            runtime_id: str | None = None,
            strategy_id: str | None = None,
            persist: bool = True,
        ) -> StrategyRuntime: ...

    def _state_file(self) -> Path:
        return get_strategy_runtime_state_path()

    def _save_specs(self) -> None:
        with self._lock:
            file_path = self._state_file()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "strategy_runtimes": list(self._runtime_specs.values()),
                "blocked_accounts": list(self._blocked_accounts.values()),
                "blocked_strategies": list(self._blocked_strategies.values()),
                "risk_events": self._risk_events[:100],
            }
            write_json(file_path, payload)

    def _load_specs(self) -> None:
        file_path = self._state_file()
        if not file_path.exists():
            return
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            items = payload.get("strategy_runtimes") or []
            mapping: dict[str, dict[str, Any]] = {}
            for item in items:
                runtime_id = str(item.get("runtime_id") or "")
                if runtime_id:
                    mapping[runtime_id] = item
            self._runtime_specs = mapping
            self._blocked_accounts = {
                str(item.get("target_id") or ""): item
                for item in payload.get("blocked_accounts") or []
                if str(item.get("target_id") or "")
            }
            self._blocked_strategies = {
                str(item.get("target_id") or ""): item
                for item in payload.get("blocked_strategies") or []
                if str(item.get("target_id") or "")
            }
            self._risk_events = [
                item for item in (payload.get("risk_events") or []) if isinstance(item, dict)
            ]
        except Exception as exc:
            raise RuntimeError(f"运行状态损坏，已阻止自动恢复；请检查并恢复 {file_path}") from exc

    def _restore_persisted_runtimes(self) -> None:
        for spec in list(self._runtime_specs.values()):
            if str(spec.get("status") or "").lower() == "running":
                self._restore_one_runtime(spec)

    def _refuse_restoration(
        self, spec: dict[str, Any], block_scope: str, reason: str, event: dict[str, str]
    ) -> None:
        spec.update(status="blocked", block_scope=block_scope, block_reason=reason)
        if event["severity"] == "critical":
            spec["error"] = reason
        self._save_specs()
        self._record_risk_event(**event, blocked=True)

    def _edition_prevents_restoration(self, spec: dict[str, Any], runtime_id: str) -> bool:
        if str(spec.get("mode") or "").lower() != "live" or supports_live_trading():
            return False
        reason = "CE edition 暂不支持实盘交易，未恢复该实盘运行时"
        self._refuse_restoration(
            spec,
            "edition",
            reason,
            {
                "scope": "system",
                "target_id": runtime_id,
                "title": "重启恢复阻止：实盘功能不可用",
                "message": reason,
                "severity": "critical",
            },
        )
        return True

    def _risk_prevents_restoration(self, spec: dict[str, Any], runtime_id: str) -> bool:
        from quantide.service.risk_programs import unavailable_risk_program_ids

        unavailable = unavailable_risk_program_ids(
            (spec.get("config") or {}).get("risk_programs") or [],
            frame_type=str(spec.get("interval") or "1d"),
        )
        if not unavailable:
            return False
        reason = "风险程序不可用/已阻止：" + ", ".join(unavailable)
        self._refuse_restoration(
            spec,
            "strategy",
            reason,
            {
                "scope": "strategy",
                "target_id": runtime_id,
                "title": "重启恢复阻止：风险程序不可用",
                "message": f"运行时 {runtime_id} 未恢复：{reason}",
                "severity": "critical",
            },
        )
        return True

    def _existing_block_prevents_restoration(self, spec: dict[str, Any], runtime_id: str) -> bool:
        account_key = self._account_key(
            str(spec.get("mode") or ""), str(spec.get("portfolio_id") or "")
        )
        account = self._blocked_accounts.get(account_key)
        strategy = self._blocked_strategies.get(runtime_id)
        if account is None and strategy is None:
            return False
        scope = "account" if account is not None else "strategy"
        reason = str((account if account is not None else strategy or {}).get("reason") or "")
        self._refuse_restoration(
            spec,
            scope,
            reason,
            {
                "scope": scope,
                "target_id": account_key if scope == "account" else runtime_id,
                "title": "重启恢复跳过封锁运行时",
                "message": (
                    f"重启恢复时跳过运行时 {runtime_id}，因为{scope}仍被封锁："
                    f"{reason or '待确认解除'}"
                ),
                "severity": "warning",
            },
        )
        return True

    def _restore_one_runtime(self, spec: dict[str, Any]) -> None:
        runtime_id = str(spec.get("runtime_id") or "")
        if spec.get("mode") == "backtest":
            if spec.get("status") in {"pending", "running", "stopping"}:
                spec.update(status="interrupted", error="服务重启中断回测，请重新运行")
                self._save_specs()
            return
        checks = (
            self._edition_prevents_restoration,
            self._risk_prevents_restoration,
            self._existing_block_prevents_restoration,
        )
        if any(check(spec, runtime_id) for check in checks):
            return
        try:
            self._start_from_spec(spec)
            self._record_risk_event(
                scope="system",
                target_id=runtime_id,
                title="重启恢复完成",
                message=f"重启恢复已重新启动运行时 {runtime_id}。",
                severity="info",
                blocked=False,
            )
        except Exception as exc:
            spec.update(status="failed", error=str(exc))
            self._save_specs()
            self._record_risk_event(
                scope="system",
                target_id=runtime_id,
                title="重启恢复失败",
                message=f"运行时 {runtime_id} 在重启恢复时失败：{exc}",
                severity="critical",
                blocked=False,
            )

    def _account_key(self, mode: str, portfolio_id: str) -> str:
        return f"{mode}:{portfolio_id}"

    def _account_key_for_runtime(self, runtime: StrategyRuntime) -> str:
        return self._account_key(runtime.mode, runtime.portfolio_id)

    def _apply_runtime_block(self, runtime: StrategyRuntime, reason: str) -> None:
        if runtime.stop_event is not None:
            runtime.stop_event.set()
        runtime.status = "blocked"
        runtime.error = reason
        runtime.updated_at = datetime.datetime.now()
        getattr(self, "_data_missing_alarms", set()).discard(f"strategy_data:{runtime.runtime_id}")
        try:
            from quantide.service.strategy_tasks import strategy_task_manager

            strategy_task_manager.detach(runtime.runtime_id)
        except Exception:
            pass

    def _sync_strategy_data_alarm(self, runtime: StrategyRuntime, missing: bool) -> None:
        """策略行情缺失/恢复时写系统风险事件（避免静默跳过选股）。"""
        target = f"strategy_data:{runtime.runtime_id}"
        if missing and target not in self._data_missing_alarms:
            self._data_missing_alarms.add(target)
            self.record_system_event(
                title="策略行情缺失",
                message=(
                    f"{runtime.strategy_name or runtime.runtime_id} 今日行情/覆盖不足，已跳过选股。"
                ),
                severity="critical",
                blocked=True,
                target_id=target,
            )
        elif not missing and target in self._data_missing_alarms:
            self._data_missing_alarms.discard(target)
            self.record_system_event(
                title="策略行情恢复",
                message=f"{runtime.strategy_name or runtime.runtime_id} 行情已恢复。",
                severity="info",
                blocked=False,
                target_id=target,
            )

    def _record_risk_event(
        self,
        *,
        scope: str,
        target_id: str,
        title: str,
        message: str,
        severity: str,
        blocked: bool,
    ) -> None:
        event = {
            "event_id": uuid.uuid4().hex[:8],
            "scope": scope,
            "target_id": target_id,
            "title": title,
            "message": message,
            "severity": severity,
            "blocked": blocked,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self._risk_events.insert(0, event)
        self._risk_events = self._risk_events[:100]
        self._save_specs()

    def _start_from_spec(self, spec: dict[str, Any]) -> StrategyRuntime:
        account_kind, portfolio_id, broker = _resolve_runtime_account(self, spec)
        interval = str(spec["interval"]).strip().lower()
        _restore_paper_fees(account_kind, broker, spec)
        return self._start_strategy_runtime(
            mode=str(spec.get("mode") or ""),
            strategy_name=str(spec.get("strategy_name") or ""),
            config=dict(spec.get("config") or {}),
            broker=broker,
            portfolio_id=portfolio_id,
            source_backtest_portfolio_id=str(spec.get("source_backtest_portfolio_id") or ""),
            account_kind=account_kind,
            interval=interval,
            market_data=self._market_data,
            principal=float(spec.get("principal") or 0),
            runtime_id=str(spec.get("runtime_id") or ""),
            strategy_id=str(spec.get("strategy_id") or ""),
            persist=False,
        )
