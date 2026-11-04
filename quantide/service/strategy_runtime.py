import asyncio
import datetime
import threading
import uuid
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from quantide.config.features import require_live_trading
from quantide.config.paths import get_backtest_log_path
from quantide.config.settings import get_cheat_on_close_time
from quantide.core.enums import BrokerKind, FrameType
from quantide.core.market_time import market_now
from quantide.core.runtime import RuntimeContext
from quantide.core.runtime.registration import register_port_backed_broker
from quantide.core.strategy import BaseStrategy, RiskStrategy, Strategy
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.discovery import strategy_loader
from quantide.service.registry import BrokerRegistry
from quantide.service.risk_programs import build_live_risk_strategies
from quantide.service.runtime_config import _float_or
from quantide.service.runtime_intents import RuntimeIntentExecution
from quantide.service.runtime_models import BacktestRun, StrategyRuntime
from quantide.service.runtime_proxies import (
    NextOpenBarBrokerProxy,
    NextOpenBrokerProxy,
    StrategyBrokerProxy,
)
from quantide.service.runtime_risk import RuntimeRiskControls
from quantide.service.runtime_state import RuntimeStatePersistence
from quantide.service.sim_broker import PaperBroker
from quantide.service.strategy_tracking import TrackingStore, tracking_store

if TYPE_CHECKING:
    from quantide.service.strategy_session import StrategySession


def _independent_strategy(strategy_cls: type[Strategy]) -> type[BaseStrategy]:
    """Only independent strategies have the on-bar lifecycle used by a runtime."""
    if isinstance(strategy_cls, type) and issubclass(strategy_cls, RiskStrategy):
        raise ValueError("风控策略不能作为独立策略运行")
    # Discovery admits independent BaseStrategy classes and risk classes;
    # callable test/extension factories are also supported at this boundary.
    return cast(type[BaseStrategy], strategy_cls)


def _runtime_row_block(
    self: "StrategyRuntimeManager", account_key: str, runtime: StrategyRuntime
) -> tuple[str, str]:
    """Runtime row block."""
    account_block = self._blocked_accounts.get(account_key)
    strategy_block = (
        self._blocked_strategies.get(runtime.runtime_id) if runtime.strategy_id else None
    )
    blocked_scope = ""
    block_reason = ""
    block_reason, blocked_scope = _runtime_block_reason(
        account_block, block_reason, blocked_scope, strategy_block
    )
    return blocked_scope, block_reason


def _validate_runtime_start(
    self: "StrategyRuntimeManager",
    strategy_name: str,
    config: dict[str, Any],
    interval: str,
    mode: str,
    portfolio_id: str,
    runtime_id: str,
) -> None:
    """Validate runtime start."""
    strategy_cls = strategy_loader.load_from_cache().get(strategy_name)
    if strategy_cls is not None:
        from quantide.service.runner import BacktestRunner

        BacktestRunner.validate_strategy_interval(strategy_cls, config, interval)
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


def _runtime_block_reason(
    account_block: dict[str, Any] | None,
    block_reason: str,
    blocked_scope: str,
    strategy_block: dict[str, Any] | None,
) -> tuple[str, str]:
    """Runtime block reason."""
    if account_block is not None:
        blocked_scope = "account"
        block_reason = str(account_block.get("reason") or "")
    elif strategy_block is not None:
        blocked_scope = "strategy"
        block_reason = str(strategy_block.get("reason") or "")
    return block_reason, blocked_scope


class StrategyRuntimeManager(RuntimeRiskControls, RuntimeStatePersistence, RuntimeIntentExecution):
    def __init__(self, tracking: TrackingStore | None = None) -> None:
        self._tracking_store = tracking or tracking_store
        self._lock = threading.RLock()
        self._shutting_down = False
        self._account_runtimes: dict[str, StrategyRuntime] = {}
        self._strategy_runtimes: dict[str, StrategyRuntime] = {}
        self._backtest_runtimes: dict[str, BacktestRun] = {}
        self._backtest_history: dict[str, BacktestRun] = {}
        self._runtime_specs: dict[str, dict[str, Any]] = {}
        self._blocked_accounts: dict[str, dict[str, Any]] = {}
        self._blocked_strategies: dict[str, dict[str, Any]] = {}
        self._risk_events: list[dict[str, Any]] = []
        #: 已发出“策略行情缺失”告警的 runtime，用于恢复时消警
        self._data_missing_alarms: set[str] = set()
        self._runtime: RuntimeContext | None = None
        self._registry: BrokerRegistry | None = None
        self._adapters: Any = None
        self._market_data: Any = None
        self._gateway_broker: Any = None

    @property
    def tracking_store(self) -> TrackingStore:
        """Durable signal repository, injectable by SDK users and deterministic tests."""
        return getattr(self, "_tracking_store", tracking_store)

    def bootstrap_from_runtime(self, runtime: RuntimeContext) -> None:
        """使用正式 RuntimeContext 初始化运行时管理器。"""
        self._shutting_down = False
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

    def shutdown(self) -> None:
        """Quiesce workers while retaining running specifications for restart."""
        self._shutting_down = True
        workers = list(self._strategy_runtimes.values())
        for runtime in workers:
            if runtime.stop_event is not None:
                runtime.stop_event.set()
        for runtime in workers:
            if runtime.thread is not None and runtime.thread is not threading.current_thread():
                runtime.thread.join()
        self._save_specs()

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
        if interval not in {"1d", "30m"}:
            raise ValueError(f"不支持的策略周期: {interval!r}")
        strategy_cls = strategy_loader.load_from_cache().get(strategy_name)
        if strategy_cls is not None:
            strategy_cls = _independent_strategy(strategy_cls)
        config = dict(config or {})
        if "risk_programs" in config:
            from quantide.service.risk_programs import normalize_risk_programs

            config["risk_programs"] = normalize_risk_programs(
                config["risk_programs"],
                host_strategy_cls=strategy_cls,
                frame_type=interval,
            )
        if strategy_cls is not None:
            from quantide.service.runner import BacktestRunner

            BacktestRunner.validate_strategy_interval(strategy_cls, config, interval)
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
        if error:
            self.record_system_event(
                title="回测运行失败",
                message=f"回测 {portfolio_id} 失败：{error}",
                severity="critical",
                blocked=True,
                target_id=f"backtest:{portfolio_id}",
            )

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
        if run.status == "failed":
            raise RuntimeError(f"回测不可投放：{run.error or '回测已失败'}")
        existing = self.get_active_backtest_deployment(run.portfolio_id, "paper")
        if existing is not None:
            return existing
        effective_config = config if config is not None else run.config
        self._validate_config_interval(effective_config, run.interval)
        account_id = f"paper-{run.strategy_name}-{uuid.uuid4().hex[:8]}"
        config = effective_config or {}
        broker = PaperBroker.create(
            portfolio_id=account_id,
            portfolio_name=f"{run.strategy_name}-paper",
            principal=principal,
            commission=_float_or(config.get("commission"), 1e-4),
            stamp_tax=_float_or(config.get("stamp_duty"), 5e-4),
            transfer_fee=_float_or(config.get("transfer_fee"), 1e-5),
            min_commission=_float_or(config.get("min_commission"), 5.0),
            slippage=_float_or(config.get("slippage_pct"), 0.001),
            market_data=market_data,
        )
        runtime = self._runtime
        if runtime is None:
            raise RuntimeError("runtime 未初始化")
        port = broker
        handle = register_port_backed_broker(
            registry=runtime.registry,
            adapters=runtime.adapters,
            port=port,
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
        require_live_trading()
        run = self._resolve_backtest_run(portfolio_id)
        if run.status == "failed":
            raise RuntimeError(f"回测不可投放：{run.error or '回测已失败'}")
        existing = self.get_active_backtest_deployment(run.portfolio_id, "live")
        if existing is not None:
            return existing
        effective_config = config if config is not None else run.config
        self._validate_config_interval(effective_config, run.interval)
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
        self._data_missing_alarms.discard(f"strategy_data:{runtime_id}")
        try:
            from quantide.service.strategy_tasks import strategy_task_manager

            strategy_task_manager.detach(runtime_id)
        except Exception as exc:
            logger.warning("策略任务卸载失败 {}: {}", runtime_id, exc)

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
                    message=(
                        "策略运行时 "
                        f"{runtime_id}"
                        " 仍处于风控封锁："
                        f"{block.get('reason') or '待确认解除'}"
                    ),
                    severity="critical",
                    blocked=True,
                )
                raise RuntimeError(f"策略运行时已被封锁: {runtime_id}")
            spec = self._runtime_specs.get(runtime_id)
            if spec is None:
                raise RuntimeError(f"策略运行时配置不存在: {runtime_id}")
            account_key = self._account_key(
                str(spec.get("mode") or ""), str(spec.get("portfolio_id") or "")
            )
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
            asset = db.get_asset(portfolio_id=runtime.portfolio_id)
            if asset is not None:
                cash = float(asset.cash)
                mv = float(asset.market_value)
                total = float(asset.total)
        except Exception:
            pass
        try:
            pos_df = db.get_positions(portfolio_id=runtime.portfolio_id)
            positions = pos_df.height
        except Exception:
            positions = 0
        try:
            ord_df = db.get_orders(portfolio_id=runtime.portfolio_id)
            orders = ord_df.height
        except Exception:
            orders = 0
        account_key = self._account_key_for_runtime(runtime)
        blocked_scope, block_reason = _runtime_row_block(self, account_key, runtime)
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
            "can_stop": bool(runtime.strategy_id)
            and runtime.status in {"running", "stopping"}
            and not blocked_scope,
            "can_start": bool(runtime.strategy_id)
            and runtime.status in {"stopped", "failed"}
            and not blocked_scope,
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
        config, cheat, cheat_tm, strategy_cls = _restored_backtest_config(spec, strategy_name)
        resolved_interval = _persisted_backtest_interval(strategy_name, spec, strategy_cls)
        return BacktestRun(
            runtime_id=runtime_id,
            portfolio_id=portfolio_id,
            strategy_name=strategy_name,
            config=config,
            interval=resolved_interval,
            start_date=str(portfolio.start),
            end_date=str(portfolio.end),
            initial_cash=0,
            status=str(spec.get("status") or "finished") if spec is not None else "finished",
            error=str(spec.get("error") or "") if spec is not None else "",
            save_logs=get_backtest_log_path(portfolio_id).exists(),
            log_path=str(get_backtest_log_path(portfolio_id)),
            cheat_on_close=cheat,
            cheat_on_close_time=cheat_tm,
        )

    @staticmethod
    def _validate_config_interval(config: dict[str, Any] | None, interval: str) -> None:
        configured = (config or {}).get("bar_interval")
        if configured is not None and str(configured).strip().lower() != interval:
            raise ValueError(
                "bar_interval override "
                f"{configured!r}"
                " conflicts with persisted strategy interval "
                f"{interval!r}"
            )

    def validate_runtime_interval(
        self, spec: dict[str, Any], strategy_cls: Any | None = None
    ) -> str:
        persisted = str(spec.get("interval") or "").strip().lower()
        if persisted not in {"1d", "30m"}:
            raise ValueError(f"无法验证持久化策略周期: {persisted!r}")
        self._validate_config_interval(spec.get("config") or {}, persisted)
        if strategy_cls is not None:
            from quantide.service.runner import BacktestRunner

            declared = BacktestRunner.strategy_interval(strategy_cls)
            if declared != persisted:
                raise ValueError(
                    "persisted interval "
                    f"{persisted!r}"
                    " conflicts with strategy declaration "
                    f"{declared!r}"
                )
        return persisted

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
        if mode == "live":
            require_live_trading()
        strategy_id = strategy_id or f"{strategy_name}-{uuid.uuid4().hex[:8]}"
        runtime_id = runtime_id or f"{mode}:{portfolio_id}:{strategy_id}"
        _validate_runtime_start(
            self, strategy_name, config, interval, mode, portfolio_id, runtime_id
        )
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
            interval=interval,
            symbols=self._extract_symbols(config),
            principal=principal,
            stop_event=threading.Event(),
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
                    "symbols": runtime.symbols,
                    "principal": principal,
                    "interval": interval,
                }
                self._save_specs()
        _attach_runtime_tasks(runtime)
        runtime.thread.start()
        return runtime

    def _run_strategy_loop(self, runtime: StrategyRuntime, interval: str, market_data: Any) -> None:
        asyncio.run(self._strategy_loop(runtime, interval, market_data))

    def _apply_live_broker_config(self, runtime: StrategyRuntime) -> None:
        """把 strategy config / 类属性中的 cheat_on_close / execution_window / slippage 注入

        broker wrapper.

        #45 followup: 原 set_strategy_runtime_config 从未被调用,
        GatewayBrokerWrapper._strategy_cheat_on_close 永远默认 True,
        导致 cheat_on_close=False 路径上的 DeferredOrderQueue 实际是死代码.
        #45 followup2: config 缺 cheat_on_close 时, 读策略类属性 (与
        BacktestRunner._resolve_cheat_on_close 对齐),
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
        if str(config.get("fill_timing", "")).strip().lower() in {
            "next_open",
            "open",
        }:
            # The runtime-owned durable queue already controls the delay.  The
            # gateway must submit when the queue is drained rather than put
            # the same order into its legacy in-memory deferred queue again.
            cheat_on_close = True
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

    def _prepare_session(self, runtime: StrategyRuntime, interval: str) -> "StrategySession":
        from quantide.service.strategy_session import StrategySession, fill_timing

        strategy_cls = strategy_loader.load_from_cache().get(runtime.strategy_name)
        if strategy_cls is None:
            raise RuntimeError(f"策略不存在: {runtime.strategy_name}")
        strategy_cls = _independent_strategy(strategy_cls)
        if interval in {"1d", "30m"} or isinstance(strategy_cls, type):
            self.validate_runtime_interval(
                {"interval": interval, "config": runtime.config}, strategy_cls
            )
        if runtime.mode == "live":
            self._apply_live_broker_config(runtime)
        broker = runtime.broker
        if runtime.mode == "live":
            broker = StrategyBrokerProxy(broker, runtime.strategy_id)
        strategy = strategy_cls(broker, runtime.config)
        frame = FrameType.MIN30 if interval == "30m" else FrameType.DAY
        strategy.interval = frame.value
        risks = self._build_live_risk_strategies(
            strategy_cls, broker, runtime.config, frame_type=frame
        )
        return StrategySession(
            self,
            runtime,
            strategy,
            risks,
            broker,
            interval,
            fill_timing(strategy_cls, runtime.config),
            (NextOpenBrokerProxy, NextOpenBarBrokerProxy),
        )

    def _finish_session(self, runtime: StrategyRuntime) -> None:
        from quantide.service.strategy_tasks import strategy_task_manager

        runtime.updated_at = datetime.datetime.now()
        strategy_task_manager.detach(runtime.runtime_id)
        with self._lock:
            spec = self._runtime_specs.get(runtime.runtime_id)
            if spec is not None and not getattr(self, "_shutting_down", False):
                spec["status"] = runtime.status
                self._save_specs()

    async def _strategy_loop(
        self, runtime: StrategyRuntime, interval: str, market_data: Any
    ) -> None:
        try:
            session = self._prepare_session(runtime, interval)
        except Exception as exc:
            self._mark_runtime_failed(runtime, exc)
            logger.exception("策略启动检查失败")
            return
        try:
            await session.start()
            while runtime.stop_event is not None and not runtime.stop_event.is_set():
                self._build_quotes(runtime.symbols, market_data)
                await session.tick(market_now())
                runtime.updated_at = datetime.datetime.now()
                await asyncio.sleep(2)
            if runtime.status in {"running", "stopping"}:
                runtime.status = "stopped"
        except Exception as exc:
            self._mark_runtime_failed(runtime, exc)
            logger.exception("策略运行失败")
        finally:
            try:
                self._finish_session(runtime)
            finally:
                await session.stop()

    def _mark_runtime_failed(self, runtime: StrategyRuntime, exc: Exception) -> None:
        """Persist a runtime failure and expose it through the risk event path."""
        runtime.status = "failed"
        runtime.error = str(exc)
        runtime.updated_at = datetime.datetime.now()
        with self._lock:
            spec = self._runtime_specs.get(runtime.runtime_id)
            if spec is not None:
                spec["status"] = "failed"
                spec["error"] = runtime.error
                self._save_specs()
        missing_dependency = "requires the lightgbm package" in runtime.error
        self.record_system_event(
            title="策略运行失败",
            message=f"策略运行时 {runtime.runtime_id} 失败：{runtime.error}",
            severity="critical",
            blocked=missing_dependency,
            target_id=runtime.runtime_id,
        )

    def _next_open_decision_day(self, now: datetime.datetime) -> datetime.date | None:
        """Find today's persisted, ready daily signal day.

        A restart before the next open may process an already-persisted intent,
        but it must not recreate yesterday's signal after the next open.  The
        candidate therefore has to be today's bar and pass the post-close
        persistence gate.
        """
        from quantide.service.data_readiness import data_readiness_monitor

        try:
            candidate = daily_bars.end
        except Exception:
            candidate = None
        if not isinstance(candidate, datetime.date) or candidate != now.date():
            return None
        if not data_readiness_monitor.is_daily_ready(now, day=candidate):
            return None
        return candidate

    @staticmethod
    def _latest_completed_30m_bar(now: datetime.datetime) -> datetime.datetime | None:
        """Return the latest session bar boundary that is fully closed.

        Calendar ticks encode the split morning/afternoon sessions, so flooring
        through this API never manufactures a lunch or overnight bar.  Before
        10:00 there is no completed 30m bar for today's session.
        """
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        tm = now.time()
        if tm < datetime.time(10, 0):
            return None
        try:
            if not calendar.is_trade_day(now):
                return None
            candidate = calendar.floor(now, FrameType.MIN30)
        except Exception:
            return None
        if not isinstance(candidate, datetime.datetime):
            return None
        candidate = candidate.replace(tzinfo=None)
        if candidate.date() != now.date():
            return None
        return candidate if candidate <= now else None

    @staticmethod
    def _next_eligible_30m_bar(signal_bar: datetime.datetime) -> datetime.datetime:
        """Return the next real 30m boundary, crossing session gaps safely."""
        try:
            next_completed = calendar.shift(signal_bar, 1, FrameType.MIN30)
        except Exception as exc:
            raise RuntimeError("无法确定 30m next_open 的目标 bar") from exc
        if not isinstance(next_completed, datetime.datetime):
            raise RuntimeError("30m next_open 的目标 bar 无效")
        return (next_completed - datetime.timedelta(minutes=30)).replace(tzinfo=None)

    def _build_live_risk_strategy(
        self, strategy_cls: Any, broker: Any, config: dict[str, Any]
    ) -> Any:
        """Backward-compatible singular wrapper for callers outside the loop."""
        strategies = self._build_live_risk_strategies(strategy_cls, broker, config)
        return strategies[0] if strategies else None

    def _build_live_risk_strategies(
        self,
        strategy_cls: Any,
        broker: Any,
        config: dict[str, Any],
        frame_type: FrameType | str = FrameType.DAY,
    ) -> list[Any]:
        """Build only explicitly adapted selected risk programs."""
        return build_live_risk_strategies(strategy_cls, broker, config, frame_type=frame_type)

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


strategy_runtime_manager = StrategyRuntimeManager()


def _persisted_backtest_interval(
    strategy_name: str, spec: dict[str, Any] | None, strategy_cls: type[Strategy] | None
) -> str:
    """Validate period declarations before restoring a saved backtest."""
    if spec is not None:
        if "interval" not in spec or not str(spec.get("interval") or "").strip():
            raise RuntimeError("无法验证持久化策略周期：记录缺少 interval")
        resolved_interval = str(spec["interval"]).strip().lower()
    elif strategy_cls is not None:
        try:
            from quantide.service.runner import BacktestRunner

            resolved_interval = BacktestRunner.strategy_interval(strategy_cls)
        except Exception as exc:
            raise RuntimeError(f"无法验证策略 {strategy_name!r} 的周期声明") from exc
    else:
        raise RuntimeError(f"无法验证策略 {strategy_name!r} 的周期声明")
    if resolved_interval not in {"1d", "30m"}:
        raise RuntimeError(f"无法验证持久化策略周期: {resolved_interval!r}")
    return resolved_interval


def _restored_backtest_config(
    spec: dict[str, Any] | None, strategy_name: str
) -> tuple[dict[str, Any], bool, str, type[Strategy] | None]:
    """Restore persisted parameters or the strategy defaults for a legacy record."""
    strategy_cls = None
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
    return config, cheat, cheat_tm, strategy_cls


def _attach_runtime_tasks(runtime: StrategyRuntime) -> None:
    """Attach scheduled tracking work without preventing runtime startup on failure."""
    try:
        from quantide.service.strategy_tasks import strategy_task_manager

        strategy_task_manager.attach(runtime)
    except Exception as exc:
        logger.warning("策略任务挂载失败 {}: {}", runtime.runtime_id, exc)
