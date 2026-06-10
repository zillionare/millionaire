import asyncio
import datetime
import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from quantide.config.paths import get_backtest_log_path, get_strategy_runtime_state_path
from quantide.config.settings import get_cheat_on_close_time
from quantide.core.enums import BrokerKind, FrameType
from quantide.core.runtime import RuntimeContext
from quantide.data.sqlite import db
from quantide.service.discovery import strategy_loader
from quantide.service.registry import BrokerRegistry
from quantide.service.sim_broker import PaperBroker


@dataclass
class StrategyRuntime:
    runtime_id: str
    mode: str
    strategy_name: str
    strategy_id: str
    portfolio_id: str
    account_kind: str
    status: str
    config: dict[str, Any]
    source_backtest_portfolio_id: str = ""
    symbols: list[str] = field(default_factory=list)
    principal: float = 0.0
    started_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    error: str = ""
    stop_event: threading.Event | None = None
    thread: threading.Thread | None = None
    broker: Any = None


@dataclass
class BacktestRun:
    runtime_id: str
    portfolio_id: str
    strategy_name: str
    config: dict[str, Any]
    interval: str
    start_date: str
    end_date: str
    initial_cash: float
    status: str
    save_logs: bool = False
    log_path: str = ""
    cheat_on_close: bool = False
    cheat_on_close_time: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    error: str = ""


class StrategyBrokerProxy:
    def __init__(self, broker: Any, strategy_id: str):
        self._broker = broker
        self._strategy_id = strategy_id

    def __getattr__(self, item):
        return getattr(self._broker, item)

    async def buy(self, asset, shares, price=0, order_time=None, timeout=0.5):
        return await self._broker.buy(
            asset=asset,
            shares=shares,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )

    async def sell(self, asset, shares, price=0, order_time=None, timeout=0.5):
        return await self._broker.sell(
            asset=asset,
            shares=shares,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )

    async def buy_percent(self, asset, percent, price=0, order_time=None, timeout=0.5):
        return await self._broker.buy_percent(
            asset=asset,
            percent=percent,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )

    async def sell_percent(self, asset, percent, price=0, order_time=None, timeout=0.5):
        return await self._broker.sell_percent(
            asset=asset,
            percent=percent,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )

    async def buy_amount(self, asset, amount, price=0, order_time=None, timeout=0.5):
        return await self._broker.buy_amount(
            asset=asset,
            amount=amount,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )

    async def sell_amount(self, asset, amount, price=0, order_time=None, timeout=0.5):
        return await self._broker.sell_amount(
            asset=asset,
            amount=amount,
            price=price,
            order_time=order_time,
            timeout=timeout,
            strategy_id=self._strategy_id,
        )


class StrategyRuntimeManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._account_runtimes: dict[str, StrategyRuntime] = {}
        self._strategy_runtimes: dict[str, StrategyRuntime] = {}
        self._backtest_runtimes: dict[str, BacktestRun] = {}
        self._backtest_history: dict[str, BacktestRun] = {}
        self._runtime_specs: dict[str, dict[str, Any]] = {}
        self._blocked_accounts: dict[str, dict[str, Any]] = {}
        self._blocked_strategies: dict[str, dict[str, Any]] = {}
        self._risk_events: list[dict[str, Any]] = []
        self._runtime: RuntimeContext | None = None
        self._registry: BrokerRegistry | None = None
        self._adapters: Any = None
        self._market_data: Any = None
        self._gateway_broker: Any = None

    def bootstrap_from_runtime(self, runtime: RuntimeContext) -> None:
        """使用正式 RuntimeContext 初始化运行时管理器。"""
        self._runtime = runtime
        self._registry = runtime.registry
        self._adapters = runtime.adapters
        self._market_data = runtime.market_data
        self._gateway_broker = runtime.registry.get(BrokerKind.QMT, "gateway")
        registry = runtime.registry
        with self._lock:
            self._account_runtimes = {}
            for item in registry.list():
                kind = item["kind"]
                portfolio_id = item["id"]
                mode = "live" if kind == BrokerKind.QMT.value else "paper"
                runtime_id = f"{mode}:{portfolio_id}"
                self._account_runtimes[runtime_id] = StrategyRuntime(
                    runtime_id=runtime_id,
                    mode=mode,
                    strategy_name="",
                    strategy_id="",
                    portfolio_id=portfolio_id,
                    account_kind=kind,
                    status="idle",
                    config={},
                    broker=registry.get(kind, portfolio_id),
                )
        self._load_specs()
        self._restore_persisted_runtimes()

    def create_backtest_runtime(
        self,
        portfolio_id: str,
        strategy_name: str,
        config: dict[str, Any],
        interval: str,
        start_date: str,
        end_date: str,
        initial_cash: float,
        save_logs: bool = False,
    ) -> None:
        cheat = bool(config.get("cheat_on_close", False))
        cheat_tm = get_cheat_on_close_time() if cheat else ""
        run = BacktestRun(
            runtime_id=f"backtest:{portfolio_id}",
            portfolio_id=portfolio_id,
            strategy_name=strategy_name,
            config=config,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            status="running",
            save_logs=save_logs,
            log_path=str(get_backtest_log_path(portfolio_id)),
            cheat_on_close=cheat,
            cheat_on_close_time=cheat_tm,
        )
        with self._lock:
            self._backtest_runtimes[portfolio_id] = run
            self._backtest_history[portfolio_id] = run
            self._runtime_specs[run.runtime_id] = {
                "runtime_id": run.runtime_id,
                "mode": "backtest",
                "strategy_name": strategy_name,
                "strategy_id": "",
                "portfolio_id": portfolio_id,
                "source_backtest_portfolio_id": "",
                "account_kind": "bt",
                "status": run.status,
                "config": dict(config or {}),
                "symbols": [],
                "principal": initial_cash,
                "interval": interval,
                "cheat_on_close": cheat,
                "cheat_on_close_time": cheat_tm,
            }
            self._save_specs()

    def complete_backtest_runtime(self, portfolio_id: str, error: str = "") -> None:
        with self._lock:
            run = self._backtest_history.get(portfolio_id)
            if run is not None:
                run.status = "failed" if error else "finished"
                run.error = error
                run.updated_at = datetime.datetime.now()
                spec = self._runtime_specs.get(run.runtime_id)
                if spec is not None:
                    spec["status"] = run.status
                    spec["error"] = run.error
                    self._save_specs()
            if portfolio_id in self._backtest_runtimes:
                del self._backtest_runtimes[portfolio_id]

    def get_backtest_run(self, portfolio_id: str) -> BacktestRun | None:
        with self._lock:
            return self._backtest_history.get(portfolio_id)

    def get_backtest_run_or_resolve(self, portfolio_id: str) -> BacktestRun | None:
        """优先 in-memory history, 缺失时回退 _resolve_backtest_run (持久化恢复).

        #47/#49 followup2: 进程重启后 _backtest_history 为空, 报告页 / deploy modal
        仍需拿到恢复后的 run 才能正常渲染. 回退失败 (portfolio 不存在) 时返 None.
        """
        run = self.get_backtest_run(portfolio_id)
        if run is not None:
            return run
        try:
            return self._resolve_backtest_run(portfolio_id)
        except Exception:
            return None

    def remove_backtest_run(self, portfolio_id: str) -> None:
        """从内存中移除指定回测的运行记录。

        Args:
            portfolio_id: 组合 ID。
        """
        with self._lock:
            self._backtest_history.pop(portfolio_id, None)
            self._backtest_runtimes.pop(portfolio_id, None)

    def deploy_to_paper(
        self,
        portfolio_id: str,
        principal: float,
        registry: BrokerRegistry,
        market_data: Any,
        config: dict[str, Any] | None = None,
    ) -> StrategyRuntime:
        run = self._resolve_backtest_run(portfolio_id)
        existing = self.get_active_backtest_deployment(run.portfolio_id, "paper")
        if existing is not None:
            return existing
        effective_config = config if config is not None else run.config
        account_id = f"paper-{run.strategy_name}-{uuid.uuid4().hex[:8]}"
        broker = PaperBroker.create(
            portfolio_id=account_id,
            portfolio_name=f"{run.strategy_name}-paper",
            principal=principal,
            market_data=market_data,
        )
        runtime = self._runtime
        if runtime is None:
            raise RuntimeError("runtime 未初始化")
        handle = runtime.register_legacy_broker(
            broker=broker,
            portfolio_id=account_id,
            kind=BrokerKind.SIMULATION,
            portfolio_name=f"{run.strategy_name}-paper",
            status=True,
            is_connected=True,
        )
        return self._start_strategy_runtime(
            mode="paper",
            strategy_name=run.strategy_name,
            config=effective_config,
            broker=handle,
            portfolio_id=account_id,
            source_backtest_portfolio_id=run.portfolio_id,
            account_kind=BrokerKind.SIMULATION.value,
            interval=run.interval,
            market_data=market_data,
            principal=principal,
        )

    def deploy_to_live(
        self,
        portfolio_id: str,
        account_id: str,
        registry: BrokerRegistry,
        market_data: Any,
        config: dict[str, Any] | None = None,
    ) -> StrategyRuntime:
        run = self._resolve_backtest_run(portfolio_id)
        existing = self.get_active_backtest_deployment(run.portfolio_id, "live")
        if existing is not None:
            return existing
        effective_config = config if config is not None else run.config
        broker = self._gateway_broker
        account_kind = "gateway"
        account_id = "gateway"
        if broker is None:
            raise RuntimeError("gateway broker 未初始化")
        return self._start_strategy_runtime(
            mode="live",
            strategy_name=run.strategy_name,
            config=effective_config,
            broker=broker,
            portfolio_id=account_id,
            source_backtest_portfolio_id=run.portfolio_id,
            account_kind=account_kind,
            interval=run.interval,
            market_data=market_data,
            principal=0.0,
        )

    def stop_strategy_runtime(self, runtime_id: str) -> None:
        with self._lock:
            runtime = self._strategy_runtimes.get(runtime_id)
            if runtime is None:
                raise RuntimeError(f"策略运行时不存在: {runtime_id}")
            if runtime.stop_event is not None:
                runtime.stop_event.set()
            runtime.status = "stopping"
            runtime.updated_at = datetime.datetime.now()
            spec = self._runtime_specs.get(runtime_id)
            if spec is not None:
                spec["status"] = "stopped"
                self._save_specs()

    def start_strategy_runtime(self, runtime_id: str) -> StrategyRuntime:
        with self._lock:
            current = self._strategy_runtimes.get(runtime_id)
            if current is not None and current.status in {"running", "stopping"}:
                return current
            block = self._blocked_strategies.get(runtime_id)
            if block is not None:
                self._record_risk_event(
                    scope="strategy",
                    target_id=runtime_id,
                    title="策略启动被阻止",
                    message=f"策略运行时 {runtime_id} 仍处于风控封锁：{block.get('reason') or '待确认解除'}",
                    severity="critical",
                    blocked=True,
                )
                raise RuntimeError(f"策略运行时已被封锁: {runtime_id}")
            spec = self._runtime_specs.get(runtime_id)
            if spec is None:
                raise RuntimeError(f"策略运行时配置不存在: {runtime_id}")
            account_key = self._account_key(str(spec.get("mode") or ""), str(spec.get("portfolio_id") or ""))
            account_block = self._blocked_accounts.get(account_key)
            if account_block is not None:
                self._record_risk_event(
                    scope="account",
                    target_id=account_key,
                    title="账户启动被阻止",
                    message=(
                        f"账户 {account_key} 仍处于风控封锁，无法恢复策略 {runtime_id}："
                        f"{account_block.get('reason') or '待确认解除'}"
                    ),
                    severity="critical",
                    blocked=True,
                )
                raise RuntimeError(f"账户已被封锁: {account_key}")
            spec["status"] = "running"
            self._save_specs()
        return self._start_from_spec(spec)

    def block_account(self, account_runtime_id: str, reason: str = "手动账户封锁") -> None:
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

    def unblock_account(self, account_runtime_id: str) -> None:
        with self._lock:
            block = self._blocked_accounts.pop(account_runtime_id, None)
            if block is None:
                return
            reason = str(block.get("reason") or "手动解除")
            for item in self._strategy_runtimes.values():
                if self._account_key_for_runtime(item) == account_runtime_id and item.runtime_id not in self._blocked_strategies:
                    if item.status == "blocked":
                        item.status = "stopped"
                        item.error = ""
                        item.updated_at = datetime.datetime.now()
            for spec in self._runtime_specs.values():
                if self._account_key(str(spec.get("mode") or ""), str(spec.get("portfolio_id") or "")) != account_runtime_id:
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

    def block_strategy(self, runtime_id: str, reason: str = "手动策略封锁") -> None:
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

    def unblock_strategy(self, runtime_id: str) -> None:
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

    def list_risk_events(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._risk_events[:limit]]

    def risk_summary(self) -> dict[str, int]:
        with self._lock:
            return {
                "blocked_accounts": len(self._blocked_accounts),
                "blocked_strategies": len(self._blocked_strategies),
                "open_events": sum(1 for item in self._risk_events if item.get("blocked")),
                "event_count": len(self._risk_events),
            }

    def runtime_summary(self) -> dict[str, int]:
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

    def list_runtime_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._lock:
            for item in self._account_runtimes.values():
                rows.append(self._runtime_to_row(item))
            for item in self._backtest_runtimes.values():
                rows.append(
                    {
                        "runtime_id": item.runtime_id,
                        "mode": "backtest",
                        "portfolio_id": item.portfolio_id,
                        "strategy_name": item.strategy_name,
                        "strategy_id": "",
                        "status": item.status,
                        "principal": item.initial_cash,
                        "cash": 0.0,
                        "market_value": 0.0,
                        "total": 0.0,
                        "positions": 0,
                        "orders": 0,
                        "updated_at": item.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "error": item.error,
                    }
                )
            for item in self._strategy_runtimes.values():
                rows.append(self._runtime_to_row(item))
        rows.sort(key=lambda x: (x["mode"], x["portfolio_id"], x["strategy_id"]))
        return rows

    def backtest_deployment_modes(self, portfolio_id: str) -> dict[str, dict[str, Any]]:
        """返回某个回测当前活跃的投放模式。

        Args:
            portfolio_id: 回测组合 ID。

        Returns:
            以模式为键的运行时摘要，仅包含当前仍处于活跃状态的 paper/live 运行时。
        """
        active_statuses = {"running", "stopping", "blocked"}
        result: dict[str, dict[str, Any]] = {}
        for row in self.list_runtime_rows():
            if str(row.get("source_backtest_portfolio_id") or "") != portfolio_id:
                continue
            mode = str(row.get("mode") or "")
            if mode not in {"paper", "live"}:
                continue
            if str(row.get("status") or "") not in active_statuses:
                continue
            result[mode] = row
        return result

    def get_active_backtest_deployment(
        self,
        portfolio_id: str,
        mode: str,
    ) -> StrategyRuntime | None:
        """获取某个回测在指定模式下的活跃运行时。"""
        active_statuses = {"running", "stopping", "blocked"}
        with self._lock:
            for runtime in self._strategy_runtimes.values():
                if runtime.mode != mode:
                    continue
                if runtime.source_backtest_portfolio_id != portfolio_id:
                    continue
                if runtime.status not in active_statuses:
                    continue
                return runtime
        return None

    def _runtime_to_row(self, runtime: StrategyRuntime) -> dict[str, Any]:
        cash = 0.0
        mv = 0.0
        total = 0.0
        positions = 0
        orders = 0
        try:
            asset = db.get_asset(runtime.portfolio_id)
            if asset is not None:
                cash = float(asset.cash)
                mv = float(asset.market_value)
                total = float(asset.total)
        except Exception:
            pass
        try:
            pos_df = db.get_positions(runtime.portfolio_id)
            positions = pos_df.height
        except Exception:
            positions = 0
        try:
            ord_df = db.get_orders(runtime.portfolio_id)
            orders = ord_df.height
        except Exception:
            orders = 0
        account_key = self._account_key_for_runtime(runtime)
        account_block = self._blocked_accounts.get(account_key)
        strategy_block = self._blocked_strategies.get(runtime.runtime_id) if runtime.strategy_id else None
        blocked_scope = ""
        block_reason = ""
        if account_block is not None:
            blocked_scope = "account"
            block_reason = str(account_block.get("reason") or "")
        elif strategy_block is not None:
            blocked_scope = "strategy"
            block_reason = str(strategy_block.get("reason") or "")
        status = "blocked" if blocked_scope else runtime.status
        return {
            "runtime_id": runtime.runtime_id,
            "mode": runtime.mode,
            "portfolio_id": runtime.portfolio_id,
            "source_backtest_portfolio_id": runtime.source_backtest_portfolio_id,
            "strategy_name": runtime.strategy_name,
            "strategy_id": runtime.strategy_id,
            "status": status,
            "principal": runtime.principal,
            "cash": cash,
            "market_value": mv,
            "total": total,
            "positions": positions,
            "orders": orders,
            "updated_at": runtime.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "error": runtime.error,
            "alert_text": block_reason or runtime.error,
            "blocked_scope": blocked_scope,
            "block_target": account_key if blocked_scope == "account" else runtime.runtime_id,
            "can_stop": bool(runtime.strategy_id) and runtime.status in {"running", "stopping"} and not blocked_scope,
            "can_start": bool(runtime.strategy_id) and runtime.status in {"stopped", "failed"} and not blocked_scope,
            "can_block_account": not runtime.strategy_id and not blocked_scope,
            "can_unblock_account": not runtime.strategy_id and blocked_scope == "account",
            "can_block_strategy": bool(runtime.strategy_id) and not blocked_scope,
            "can_unblock_strategy": bool(runtime.strategy_id) and blocked_scope == "strategy",
        }

    def _resolve_backtest_run(self, portfolio_id: str) -> BacktestRun:
        run = self.get_backtest_run(portfolio_id)
        if run is not None:
            return run
        portfolio = db.get_portfolio(portfolio_id)
        if portfolio is None:
            raise RuntimeError(f"回测记录不存在: {portfolio_id}")
        strategy_name = portfolio.name or ""
        if not strategy_name:
            raise RuntimeError("无法识别回测策略名")
        runtime_id = f"backtest:{portfolio_id}"
        spec = self._runtime_specs.get(runtime_id)
        if spec is not None:
            config = dict(spec.get("config") or {})
            cheat = bool(spec.get("cheat_on_close", False))
            cheat_tm = str(spec.get("cheat_on_close_time") or "")
        else:
            strategies = strategy_loader.load_from_cache()
            strategy_cls = strategies.get(strategy_name)
            config = dict(getattr(strategy_cls, "PARAMS", {})) if strategy_cls else {}
            cheat = bool(config.get("cheat_on_close", False))
            cheat_tm = get_cheat_on_close_time() if cheat else ""
        return BacktestRun(
            runtime_id=runtime_id,
            portfolio_id=portfolio_id,
            strategy_name=strategy_name,
            config=config,
            interval="1m",
            start_date=str(portfolio.start),
            end_date=str(portfolio.end),
            initial_cash=0,
            status="finished",
            save_logs=get_backtest_log_path(portfolio_id).exists(),
            log_path=str(get_backtest_log_path(portfolio_id)),
            cheat_on_close=cheat,
            cheat_on_close_time=cheat_tm,
        )

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
    ) -> StrategyRuntime:
        strategy_id = strategy_id or f"{strategy_name}-{uuid.uuid4().hex[:8]}"
        runtime_id = runtime_id or f"{mode}:{portfolio_id}:{strategy_id}"
        account_key = self._account_key(mode, portfolio_id)
        account_block = self._blocked_accounts.get(account_key)
        if account_block is not None:
            self._record_risk_event(
                scope="account",
                target_id=account_key,
                title="运行时启动被阻止",
                message=f"账户 {account_key} 已被封锁，阻止启动运行时 {runtime_id}。",
                severity="critical",
                blocked=True,
            )
            raise RuntimeError(f"账户已被封锁: {account_key}")
        strategy_block = self._blocked_strategies.get(runtime_id)
        if strategy_block is not None:
            self._record_risk_event(
                scope="strategy",
                target_id=runtime_id,
                title="运行时启动被阻止",
                message=f"策略运行时 {runtime_id} 已被封锁，无法启动。",
                severity="critical",
                blocked=True,
            )
            raise RuntimeError(f"策略运行时已被封锁: {runtime_id}")
        symbols = self._extract_symbols(config)
        stop_event = threading.Event()
        runtime = StrategyRuntime(
            runtime_id=runtime_id,
            mode=mode,
            strategy_name=strategy_name,
            strategy_id=strategy_id,
            portfolio_id=portfolio_id,
            source_backtest_portfolio_id=source_backtest_portfolio_id,
            account_kind=account_kind,
            status="running",
            config=config,
            symbols=symbols,
            principal=principal,
            stop_event=stop_event,
            broker=broker,
        )
        runtime.thread = threading.Thread(
            target=self._run_strategy_loop,
            args=(runtime, interval, market_data),
            daemon=True,
            name=f"strategy-{strategy_id}",
        )
        with self._lock:
            self._strategy_runtimes[runtime_id] = runtime
            if persist:
                self._runtime_specs[runtime_id] = {
                    "runtime_id": runtime_id,
                    "mode": mode,
                    "strategy_name": strategy_name,
                    "strategy_id": strategy_id,
                    "portfolio_id": portfolio_id,
                    "source_backtest_portfolio_id": source_backtest_portfolio_id,
                    "account_kind": account_kind,
                    "status": "running",
                    "config": config,
                    "symbols": symbols,
                    "principal": principal,
                    "interval": interval,
                }
                self._save_specs()
        runtime.thread.start()
        return runtime

    def _run_strategy_loop(self, runtime: StrategyRuntime, interval: str, market_data: Any) -> None:
        asyncio.run(self._strategy_loop(runtime, interval, market_data))

    def _apply_live_broker_config(self, runtime: StrategyRuntime) -> None:
        """把 strategy config / 类属性中的 cheat_on_close / execution_window / slippage 注入 broker wrapper.

        #45 followup: 原 set_strategy_runtime_config 从未被调用,
        GatewayBrokerWrapper._strategy_cheat_on_close 永远默认 True,
        导致 cheat_on_close=False 路径上的 DeferredOrderQueue 实际是死代码.
        #45 followup2: config 缺 cheat_on_close 时, 读策略类属性 (与 BacktestRunner._resolve_cheat_on_close 对齐),
        否则把 cheat_on_close=True 类属性策略强制改成 deferred-order 路径, 违反 #46 契约.
        """
        config = runtime.config or {}
        if "cheat_on_close" in config:
            cheat_on_close = bool(config["cheat_on_close"])
        else:
            try:
                strategy_cls = strategy_loader.load_from_cache().get(runtime.strategy_name)
            except Exception:
                strategy_cls = None
            cheat_on_close = bool(getattr(strategy_cls, "cheat_on_close", False))
        live_execution_window = str(config.get("live_execution_window", "auction"))
        live_execution_slippage = float(config.get("live_execution_slippage", 0.001))
        setter = getattr(runtime.broker, "set_strategy_runtime_config", None)
        if not callable(setter):
            return
        setter(
            cheat_on_close=cheat_on_close,
            live_execution_window=live_execution_window,
            live_execution_slippage=live_execution_slippage,
        )

    async def _strategy_loop(self, runtime: StrategyRuntime, interval: str, market_data: Any) -> None:
        strategies = strategy_loader.load_from_cache()
        strategy_cls = strategies.get(runtime.strategy_name)
        if strategy_cls is None:
            runtime.status = "failed"
            runtime.error = f"策略不存在: {runtime.strategy_name}"
            runtime.updated_at = datetime.datetime.now()
            return
        if runtime.mode == "live":
            self._apply_live_broker_config(runtime)
        broker = runtime.broker
        if runtime.mode == "live":
            broker = StrategyBrokerProxy(runtime.broker, runtime.strategy_id)
        strategy = strategy_cls(broker, runtime.config)
        frame = FrameType.MIN1 if interval == "1m" else FrameType.DAY
        strategy.interval = frame.value
        try:
            await strategy.init()
            await strategy.on_start(datetime.datetime.now())
            while runtime.stop_event is not None and not runtime.stop_event.is_set():
                now = datetime.datetime.now()
                if hasattr(runtime.broker, "set_clock"):
                    runtime.broker.set_clock(now)
                quotes = self._build_quotes(runtime.symbols, market_data)
                await strategy.on_bar(now, quotes, frame)
                runtime.updated_at = datetime.datetime.now()
                await asyncio.sleep(2)
            if runtime.status in {"running", "stopping"}:
                runtime.status = "stopped"
        except Exception as exc:
            runtime.status = "failed"
            runtime.error = str(exc)
            logger.exception("strategy runtime failed: {}", exc)
            self._record_risk_event(
                scope="strategy",
                target_id=runtime.runtime_id,
                title="策略运行失败",
                message=f"策略运行时 {runtime.runtime_id} 失败：{runtime.error}",
                severity="critical",
                blocked=False,
            )
        finally:
            runtime.updated_at = datetime.datetime.now()
            with self._lock:
                spec = self._runtime_specs.get(runtime.runtime_id)
                if spec is not None:
                    spec["status"] = runtime.status
                    self._save_specs()
            try:
                await strategy.on_stop(datetime.datetime.now())
            except Exception:
                pass

    def _build_quotes(self, symbols: list[str], market_data: Any) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not symbols:
            symbols = ["000001.SZ"]
        if market_data is None:
            return result
        snaps = market_data.snapshot(symbols)
        for symbol in symbols:
            snap = snaps.get(symbol)
            if snap is None:
                continue
            result[symbol] = {
                "lastPrice": float(snap.price or 0),
                "open": float(snap.open or 0),
                "high": float(snap.high or 0),
                "low": float(snap.low or 0),
                "volume": float(snap.volume or 0),
                "amount": float(snap.amount or 0),
            }
        return result

    def _extract_symbols(self, config: dict[str, Any]) -> list[str]:
        for key in ("symbol", "asset", "security"):
            value = config.get(key)
            if isinstance(value, str) and value:
                return [value]
        for key in ("symbols", "assets", "securities"):
            value = config.get(key)
            if isinstance(value, list):
                symbols = [str(item) for item in value if item]
                if symbols:
                    return symbols
        return []

    def _state_file(self) -> Path:
        return get_strategy_runtime_state_path()

    def _save_specs(self) -> None:
        file_path = self._state_file()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "strategy_runtimes": list(self._runtime_specs.values()),
            "blocked_accounts": list(self._blocked_accounts.values()),
            "blocked_strategies": list(self._blocked_strategies.values()),
            "risk_events": self._risk_events[:100],
        }
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

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
        except Exception:
            self._runtime_specs = {}
            self._blocked_accounts = {}
            self._blocked_strategies = {}
            self._risk_events = []

    def _restore_persisted_runtimes(self) -> None:
        specs = list(self._runtime_specs.values())
        for spec in specs:
            if str(spec.get("status") or "").lower() != "running":
                continue
            runtime_id = str(spec.get("runtime_id") or "")
            account_key = self._account_key(str(spec.get("mode") or ""), str(spec.get("portfolio_id") or ""))
            account_block = self._blocked_accounts.get(account_key)
            strategy_block = self._blocked_strategies.get(runtime_id)
            if account_block is not None or strategy_block is not None:
                reason = ""
                scope = "account"
                if account_block is not None:
                    reason = str(account_block.get("reason") or "")
                elif strategy_block is not None:
                    scope = "strategy"
                    reason = str(strategy_block.get("reason") or "")
                spec["status"] = "blocked"
                spec["block_scope"] = scope
                spec["block_reason"] = reason
                self._save_specs()
                self._record_risk_event(
                    scope=scope,
                    target_id=account_key if scope == "account" else runtime_id,
                    title="重启恢复跳过封锁运行时",
                    message=(
                        f"重启恢复时跳过运行时 {runtime_id}，因为{scope}仍被封锁：{reason or '待确认解除'}"
                    ),
                    severity="warning",
                    blocked=True,
                )
                continue
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
                spec["status"] = "failed"
                spec["error"] = str(exc)
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
        return self._start_strategy_runtime(
            mode=str(spec.get("mode") or ""),
            strategy_name=str(spec.get("strategy_name") or ""),
            config=dict(spec.get("config") or {}),
            broker=broker,
            portfolio_id=portfolio_id,
            source_backtest_portfolio_id=str(spec.get("source_backtest_portfolio_id") or ""),
            account_kind=account_kind,
            interval=str(spec.get("interval") or "1m"),
            market_data=self._market_data,
            principal=float(spec.get("principal") or 0),
            runtime_id=str(spec.get("runtime_id") or ""),
            strategy_id=str(spec.get("strategy_id") or ""),
            persist=False,
        )


strategy_runtime_manager = StrategyRuntimeManager()
