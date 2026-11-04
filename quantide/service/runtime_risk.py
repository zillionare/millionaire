"""Runtime risk blocks, events and status views."""

from __future__ import annotations

import datetime
from _thread import RLock
from typing import Any, Protocol

from quantide.service.runtime_models import BacktestRun, StrategyRuntime


class _RiskHost(Protocol):
    _lock: RLock
    _account_runtimes: dict[str, StrategyRuntime]
    _strategy_runtimes: dict[str, StrategyRuntime]
    _backtest_runtimes: dict[str, BacktestRun]
    _runtime_specs: dict[str, dict[str, Any]]
    _blocked_accounts: dict[str, dict[str, Any]]
    _blocked_strategies: dict[str, dict[str, Any]]
    _risk_events: list[dict[str, Any]]

    def _account_key(self, mode: str, portfolio_id: str) -> str: ...
    def _account_key_for_runtime(self, runtime: StrategyRuntime) -> str: ...
    def _apply_runtime_block(self, runtime: StrategyRuntime, reason: str) -> None: ...
    def _save_specs(self) -> None: ...
    def _runtime_to_row(self, runtime: StrategyRuntime) -> dict[str, Any]: ...
    def list_runtime_rows(self) -> list[dict[str, Any]]: ...
    def _record_risk_event(
        self, *, scope: str, target_id: str, title: str, message: str, severity: str, blocked: bool
    ) -> None: ...


def _unblock_account_strategies(account_runtime_id: str, self: _RiskHost) -> None:
    """Unblock account strategies."""
    for item in self._strategy_runtimes.values():
        if (
            self._account_key_for_runtime(item) == account_runtime_id
            and item.runtime_id not in self._blocked_strategies
        ):
            if item.status == "blocked":
                item.status = "stopped"
                item.error = ""
                item.updated_at = datetime.datetime.now()


class RuntimeRiskControls:
    """Runtime risk blocks, events and status views."""

    def block_account(
        self: _RiskHost, account_runtime_id: str, reason: str = "手动账户封锁"
    ) -> None:
        with self._lock:
            runtime = self._account_runtimes.get(account_runtime_id)
            account_key = runtime.runtime_id if runtime is not None else account_runtime_id
            payload = {
                "target_id": account_key,
                "reason": reason,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            self._blocked_accounts[account_key] = payload
            for item in self._strategy_runtimes.values():
                if self._account_key_for_runtime(item) == account_key:
                    self._apply_runtime_block(item, reason)
                    spec = self._runtime_specs.get(item.runtime_id)
                    if spec is not None:
                        spec["status"] = "blocked"
                        spec["block_scope"] = "account"
                        spec["block_reason"] = reason
            self._save_specs()
            self._record_risk_event(
                scope="account",
                target_id=account_key,
                title="账户已封锁",
                message=f"账户 {account_key} 已被风控封锁：{reason}",
                severity="critical",
                blocked=True,
            )

    def unblock_account(self: _RiskHost, account_runtime_id: str) -> None:
        with self._lock:
            block = self._blocked_accounts.pop(account_runtime_id, None)
            if block is None:
                return
            reason = str(block.get("reason") or "手动解除")
            _unblock_account_strategies(account_runtime_id, self)
            for spec in self._runtime_specs.values():
                if (
                    self._account_key(
                        str(spec.get("mode") or ""), str(spec.get("portfolio_id") or "")
                    )
                    != account_runtime_id
                ):
                    continue
                if str(spec.get("block_scope") or "") == "account":
                    spec["status"] = "stopped"
                    spec.pop("block_scope", None)
                    spec.pop("block_reason", None)
            self._save_specs()
            self._record_risk_event(
                scope="account",
                target_id=account_runtime_id,
                title="账户已解除封锁",
                message=f"账户 {account_runtime_id} 已确认解除封锁（原因为：{reason}）。",
                severity="info",
                blocked=False,
            )

    def block_strategy(self: _RiskHost, runtime_id: str, reason: str = "手动策略封锁") -> None:
        with self._lock:
            payload = {
                "target_id": runtime_id,
                "reason": reason,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            self._blocked_strategies[runtime_id] = payload
            runtime = self._strategy_runtimes.get(runtime_id)
            if runtime is not None:
                self._apply_runtime_block(runtime, reason)
            spec = self._runtime_specs.get(runtime_id)
            if spec is not None:
                spec["status"] = "blocked"
                spec["block_scope"] = "strategy"
                spec["block_reason"] = reason
            self._save_specs()
            self._record_risk_event(
                scope="strategy",
                target_id=runtime_id,
                title="策略已封锁",
                message=f"策略运行时 {runtime_id} 已被风控封锁：{reason}",
                severity="warning",
                blocked=True,
            )

    def unblock_strategy(self: _RiskHost, runtime_id: str) -> None:
        with self._lock:
            block = self._blocked_strategies.pop(runtime_id, None)
            if block is None:
                return
            reason = str(block.get("reason") or "手动解除")
            runtime = self._strategy_runtimes.get(runtime_id)
            if runtime is not None and runtime.status == "blocked":
                runtime.status = "stopped"
                runtime.error = ""
                runtime.updated_at = datetime.datetime.now()
            spec = self._runtime_specs.get(runtime_id)
            if spec is not None:
                spec["status"] = "stopped"
                spec.pop("block_scope", None)
                spec.pop("block_reason", None)
            self._save_specs()
            self._record_risk_event(
                scope="strategy",
                target_id=runtime_id,
                title="策略已解除封锁",
                message=f"策略运行时 {runtime_id} 已确认解除封锁（原因为：{reason}）。",
                severity="info",
                blocked=False,
            )

    def record_system_event(
        self: _RiskHost,
        *,
        title: str,
        message: str,
        severity: str = "warning",
        blocked: bool = True,
        target_id: str = "system",
    ) -> None:
        """记录系统级事件（数据就绪、行情中断等）。

        ``blocked=True`` 会进入 header 告警计数；恢复事件使用 ``blocked=False``，
        并同时把同一 ``target_id`` 的未恢复告警标记为已解决。
        """
        if not blocked and target_id:
            with self._lock:
                resolved_at = datetime.datetime.now().isoformat(timespec="seconds")
                for event in self._risk_events:
                    if str(event.get("target_id") or "") == target_id and event.get("blocked"):
                        event["blocked"] = False
                        event["resolved_at"] = resolved_at
        self._record_risk_event(
            scope="system",
            target_id=target_id,
            title=title,
            message=message,
            severity=severity,
            blocked=blocked,
        )

    def list_risk_events(self: _RiskHost, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._risk_events[:limit]]

    def risk_summary(self: _RiskHost) -> dict[str, int]:
        with self._lock:
            return {
                "blocked_accounts": len(self._blocked_accounts),
                "blocked_strategies": len(self._blocked_strategies),
                "open_events": sum(bool(item.get("blocked")) for item in self._risk_events),
                "event_count": len(self._risk_events),
            }

    def runtime_summary(self: _RiskHost) -> dict[str, int]:
        """汇总当前运行时状态。"""
        summary = {
            "total": 0,
            "running": 0,
            "blocked": 0,
            "failed": 0,
            "idle": 0,
        }
        for row in self.list_runtime_rows():
            summary["total"] += 1
            status = str(row.get("status") or "idle")
            if status in summary:
                summary[status] += 1
            else:
                summary["idle"] += 1
        return summary

    def list_runtime_rows(self: _RiskHost) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._lock:
            for item in self._account_runtimes.values():
                rows.append(self._runtime_to_row(item))
            for backtest in self._backtest_runtimes.values():
                rows.append(
                    {
                        "runtime_id": backtest.runtime_id,
                        "mode": "backtest",
                        "portfolio_id": backtest.portfolio_id,
                        "strategy_name": backtest.strategy_name,
                        "strategy_id": "",
                        "status": backtest.status,
                        "principal": backtest.initial_cash,
                        "cash": 0.0,
                        "market_value": 0.0,
                        "total": 0.0,
                        "positions": 0,
                        "orders": 0,
                        "updated_at": backtest.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "error": backtest.error,
                    }
                )
            for item in self._strategy_runtimes.values():
                rows.append(self._runtime_to_row(item))
        rows.sort(key=lambda x: (x["mode"], x["portfolio_id"], x["strategy_id"]))
        return rows

    def get_runtime(self: _RiskHost, runtime_id: str) -> StrategyRuntime | None:
        """按 runtime_id 获取运行时实例。"""
        with self._lock:
            return self._strategy_runtimes.get(runtime_id)
