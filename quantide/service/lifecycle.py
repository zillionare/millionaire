"""Application-owned task recovery and orderly component shutdown."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from types import ModuleType

from loguru import logger
from starlette.applications import Starlette

from quantide.data.sqlite import db


def _component_shutdown_callbacks(modes: ModuleType, app: Starlette) -> list[Callable[[], object]]:
    """Component shutdown callbacks."""
    from quantide.core.scheduler import scheduler
    from quantide.service.data_readiness import data_readiness_monitor
    from quantide.service.data_sync import data_sync_service
    from quantide.service.factor_tracking import factor_tracking_service
    from quantide.service.limit_price_refresher import limit_price_refresher
    from quantide.service.market_data_hub import market_data_hub
    from quantide.service.minute_bar_aggregator import minute_bar_aggregator
    from quantide.service.optimization_tasks import shutdown_optimizations
    from quantide.service.quote_monitor import quote_monitor

    publisher = modes._quote_publisher
    callbacks = [
        scheduler.pause,
        data_sync_service.cancel,
        shutdown_optimizations,
        app.state.strategy_runtime_manager.shutdown,
        data_readiness_monitor.stop,
        factor_tracking_service.stop,
        limit_price_refresher.stop,
        lambda: scheduler.stop(wait=True),
        quote_monitor.stop,
        minute_bar_aggregator.stop,
        market_data_hub.stop,
    ]
    if publisher is not None:
        callbacks.insert(0, publisher.stop)
    return callbacks


def recover_interrupted_tasks() -> None:
    """Retain progress and expose interrupted work instead of stale running badges."""
    tables = {
        "data_sync_tasks": "服务重启中断，可从已完成阶段继续",
        "optimization_runs": "服务重启中断，已保存完成结果",
    }
    for table, message in tables.items():
        if table not in db.table_names():
            continue
        with db.db.conn:
            db.db.conn.execute(
                f"UPDATE {table} SET status='interrupted', error=? "
                "WHERE status IN ('pending', 'running')",
                (message,),
            )


def shutdown_components(app: Starlette) -> None:
    """Attempt every cleanup even when an individual component fails."""
    from quantide.core.message import msg_hub
    from quantide.core.runtime import modes

    callbacks = _component_shutdown_callbacks(modes, app)
    runtime = app.state.runtime
    if runtime is not None:
        for item in runtime.registry.list():
            broker = runtime.registry.get(item["kind"], item["id"])
            close = getattr(broker, "close", None)
            if callable(close):
                callbacks.append(close)
    auth = getattr(app.state, "auth_manager", None)
    if auth is not None:
        callbacks.append(auth.close)
    callbacks.extend([msg_hub.stop, db.close])
    for callback in callbacks:
        try:
            callback()
        except Exception:
            logger.exception("服务组件停止失败: {}", callback)
    modes._quote_publisher = None


@asynccontextmanager
async def application_lifespan(app: Starlette) -> AsyncIterator[None]:
    """Wire process ownership to ASGI lifespan, including shutdown on SIGTERM."""
    from quantide.core.message import msg_hub

    msg_hub.start()
    try:
        auth = getattr(app.state, "auth_manager", None)
        if auth is not None:
            auth.reopen()
        yield
    finally:
        from quantide.service.background import stop_background
        from quantide.web.pages.wizard_sync import stop_wizard_sync

        await stop_wizard_sync()
        await stop_background()
        shutdown_components(app)
