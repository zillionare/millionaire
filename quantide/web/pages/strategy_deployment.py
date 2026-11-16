"""Strategy deployment."""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
)
from monsterui.all import *
from starlette.requests import Request

from quantide.config.features import (
    live_trading_unavailable_message,
    supports_live_trading,
)
from quantide.core.enums import BrokerKind
from quantide.service.discovery import strategy_loader
from quantide.service.strategy_runtime import strategy_runtime_manager


def _get_runtime(req: Request) -> Any:
    if req is None:
        return None
    app = getattr(req, "app", None)
    state = getattr(app, "state", None)
    return getattr(state, "runtime", None)


def _get_registry(req: Request) -> Any:
    runtime = _get_runtime(req)
    if runtime is None:
        return None
    return runtime.registry


def _get_market_data(req: Request) -> Any:
    runtime = _get_runtime(req)
    if runtime is None:
        return None
    return runtime.market_data


def _get_paper_deploy_availability(req: Request) -> tuple[bool, str]:
    """返回转入仿真的可用性。"""
    runtime = _get_runtime(req)
    if runtime is None:
        return False, "运行时未初始化，无法转仿真"
    if runtime.market_data is None:
        return False, "行情源未初始化，无法转仿真"
    return True, ""


def _get_live_deploy_availability(req: Request) -> tuple[bool, str]:
    """返回转入实盘的可用性。"""
    if not supports_live_trading():
        return False, live_trading_unavailable_message()
    registry = _get_registry(req)
    if registry is None:
        return False, "运行时未初始化，无法转实盘"
    if registry.get(BrokerKind.QMT, "gateway") is None:
        return False, "请先配置交易网关，才能转实盘"
    return True, ""


def _get_backtest_deploy_capabilities(req: Request) -> dict[str, Any]:
    """返回回测投放按钮的可用性上下文。"""
    paper_available, paper_unavailable_reason = _get_paper_deploy_availability(req)
    live_available, live_unavailable_reason = _get_live_deploy_availability(req)
    return {
        "paper_available": paper_available,
        "paper_unavailable_reason": paper_unavailable_reason,
        "live_available": live_available,
        "live_unavailable_reason": live_unavailable_reason,
    }


def _get_live_accounts(req: Request) -> list[dict[str, Any]]:
    live_available, _ = _get_live_deploy_availability(req)
    if not live_available:
        return []
    return [{"id": "gateway:default", "name": "gateway:default"}]


def _render_deploy_result(message: str, is_error: bool = False) -> Any:
    """渲染策略投放结果提示。"""
    base_cls = "mt-3 rounded-lg px-3 py-2 text-sm"
    cls = (
        f"{base_cls} border border-red-200 bg-red-50 text-red-600"
        if is_error
        else f"{base_cls} border border-green-200 bg-green-50 text-green-600"
    )
    return Div(message, id="deploy-result", cls=cls, hx_swap_oob="true")


def _load_backtest_run_config(portfolio_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """从 BacktestRun 拿 config + 策略类 default_config (无 run 时回空).

    进程重启后 _backtest_history 为空, 必须回退 _resolve_backtest_run 从持久化
    specs 恢复, 否则 deploy modal 失去 config 表 + POST 传空 config 覆盖 run.config.
    """
    run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
    if run is None:
        return {}, None
    default_config: dict[str, Any] | None = None
    try:
        strategies = strategy_loader.load_from_cache()
        cls = strategies.get(run.strategy_name)
        if cls is not None and hasattr(cls, "default_config"):
            default_config = cls.default_config()
    except Exception:
        default_config = None
    return dict(run.config or {}), default_config
