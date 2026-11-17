"""Application factory for Quantide."""

# Import order is intentional: local asset headers are configured before page
# modules load.
# ruff: noqa: E402

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fasthtml.common import Mount, Route
from fasthtml.core import FastHTML
from loguru import logger
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.staticfiles import StaticFiles

from quantide.config.branding import get_branding, get_runtime_edition
from quantide.config.dev_stubs import ensure_dev_stubs_started
from quantide.config.paths import (
    get_app_config_dir,
    get_app_db_path,
    get_pid_file_path,
    set_app_config_dir_override,
)
from quantide.config.settings import get_data_home
from quantide.core.errors import BaseTradeError
from quantide.core.runtime import RuntimeBootstrap
from quantide.data import init_data
from quantide.data.sqlite import db
from quantide.service.factor_tracking import factor_tracking_service
from quantide.service.lifecycle import application_lifespan, recover_interrupted_tasks
from quantide.service.registry import BrokerRegistry
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.apis.analysis import kline_router, search_router
from quantide.web.apis.broker import app as broker_api_app
from quantide.web.application import fast_app
from quantide.web.auth.guard import AuthGuard
from quantide.web.auth.manager import AuthManager
from quantide.web.middleware import BrokerRegistryMiddleware, exception_handler
from quantide.web.middleware_feature import FeatureCheckMiddleware
from quantide.web.middleware_init import InitCheckMiddleware
from quantide.web.pages.accounts import accounts_app
from quantide.web.pages.analysis import analysis_handler
from quantide.web.pages.attribution import attribution_app
from quantide.web.pages.data_calendar import data_calendar_app
from quantide.web.pages.data_db import data_db_app
from quantide.web.pages.data_market import data_market_app
from quantide.web.pages.data_stocks import data_stocks_app
from quantide.web.pages.factors import factor_app
from quantide.web.pages.history_orders import history_orders_list
from quantide.web.pages.history_positions import history_positions_list
from quantide.web.pages.history_trades import history_trades_list
from quantide.web.pages.home import home_app
from quantide.web.pages.init_wizard import init_wizard, init_wizard_app
from quantide.web.pages.live import live_app
from quantide.web.pages.optimize import (
    optimize_page as _optimize_page,  # noqa: E402,F401
)
from quantide.web.pages.paper import paper_app
from quantide.web.pages.strategy import strategy_app
from quantide.web.pages.system.calendar import system_calendar_app
from quantide.web.pages.system.datasource import system_datasource_app
from quantide.web.pages.system.directories import system_directories_app
from quantide.web.pages.system.gateway import system_gateway_app
from quantide.web.pages.system.jobs import _init_scheduler_jobs, system_jobs_app
from quantide.web.pages.system.market import system_market_app
from quantide.web.pages.system.network import system_network_app
from quantide.web.pages.system.realtime import system_realtime_app
from quantide.web.pages.system.risk_events import system_risk_events_app
from quantide.web.pages.system.runtime_monitor import system_runtime_monitor_app
from quantide.web.pages.system.stocks import system_stocks_app
from quantide.web.pages.tracking import toggle_tracking, tracking_page
from quantide.web.pages.trade_lightning import (
    trade_lightning_clear,
    trade_lightning_clear_modal,
    trade_lightning_create,
    trade_lightning_create_modal,
    trade_lightning_delete,
    trade_lightning_delete_modal,
    trade_lightning_edit_modal,
    trade_lightning_execute,
    trade_lightning_search,
    trade_lightning_update,
)
from quantide.web.pages.trade_main import (
    cancel_order_trade,
    place_order_trade,
    search_trade_assets,
    set_active_account,
    trade_asset_stats,
    trade_live_quote,
    trade_main_page,
    trade_orders_refresh,
    trade_positions_refresh,
)
from quantide.web.session_data import SessionData
from quantide.web.theme import AppTheme


def _check_single_instance() -> None:
    """Use an OS lock so stale/reused PIDs cannot block recovery after shutdown."""
    from quantide.core.instance_guard import acquire_instance_guard

    acquire_instance_guard(get_pid_file_path(), get_branding().product_name)


def _initialize_app_database() -> Path:
    """Initialize the fixed sqlite database in the config directory."""
    db_path = get_app_db_path()

    # Lock contention, failed migrations and disk/permission errors must never
    # turn a healthy account database into a new empty database. Corruption
    # requires explicit diagnosis and recovery, including its WAL sidecars.
    db.init(db_path)
    return db_path


def _health_response(request: Request) -> JSONResponse:
    failed = bool(getattr(request.app.state, "startup_error", ""))
    return JSONResponse(
        {
            "status": "degraded" if failed else "ok",
            "pid": os.getpid(),
            "edition": get_runtime_edition(),
        },
        status_code=503 if failed else 200,
    )


def _bind_session_key(app: FastHTML, secret: str, visited: set[int] | None = None) -> None:
    """Use the root profile's session key across its mounted page applications."""
    visited = set() if visited is None else visited
    if id(app) in visited:
        return
    visited.add(id(app))
    for middleware in getattr(app, "user_middleware", []):
        if middleware.cls is SessionMiddleware:
            middleware.kwargs["secret_key"] = secret
    if hasattr(app, "middleware_stack"):
        app.middleware_stack = None
    for route in getattr(app, "routes", []):
        if isinstance(route, Mount):
            _bind_session_key(route.app, secret, visited)


def _attach_runtime_to_app_states(runtime: RuntimeBootstrap) -> None:
    """Attach the effective runtime to all mounted app states."""
    for mounted_app in (
        broker_api_app,
        home_app,
        live_app,
        strategy_app,
        accounts_app,
        data_calendar_app,
        data_db_app,
        data_market_app,
        data_stocks_app,
        factor_app,
        init_wizard_app,
        system_calendar_app,
        system_datasource_app,
        system_directories_app,
        system_gateway_app,
        system_jobs_app,
        system_market_app,
        system_realtime_app,
        system_risk_events_app,
        system_runtime_monitor_app,
        system_stocks_app,
    ):
        mounted_app.state.runtime = runtime


def _attach_root_app_to_app_states(root_app: FastHTML) -> None:
    """Expose the root app to mounted sub-apps for post-init runtime refresh."""
    for mounted_app in (
        broker_api_app,
        home_app,
        live_app,
        strategy_app,
        accounts_app,
        data_calendar_app,
        data_db_app,
        data_market_app,
        data_stocks_app,
        factor_app,
        init_wizard_app,
        system_calendar_app,
        system_datasource_app,
        system_directories_app,
        system_gateway_app,
        system_jobs_app,
        system_market_app,
        system_realtime_app,
        system_risk_events_app,
        system_runtime_monitor_app,
        system_stocks_app,
    ):
        mounted_app.state.root_app = root_app


def _redirect_preserving_query(req: Request, target: str) -> RedirectResponse:
    """重定向并保留 query string（避免丢失 account_id）。"""
    query = getattr(getattr(req, "url", None), "query", "") or ""
    destination = f"{target}?{query}" if query else target
    return RedirectResponse(destination, status_code=303)


def create_app(
    app_config_dir: str | Path | None = None,
    enforce_single_instance: bool = True,
) -> FastHTML:
    """Create a Quantide web application.

    Args:
        app_config_dir: 应用运行时配置目录，用于 sqlite、pid 等持久化文件。
        enforce_single_instance: 是否执行单实例检查。
    """
    set_app_config_dir_override(app_config_dir)
    # These singletons are imported before create_app() is called.  Rebind
    # them after the per-test/per-instance config directory is selected so
    # durable next-open intents and model artifacts use this app's database.
    from quantide.service.model_store import model_store
    from quantide.service.strategy_tracking import tracking_store

    tracking_store.rebind(get_app_db_path())
    model_store.rebind(get_app_config_dir() / "models")
    db_path = _initialize_app_database()
    recover_interrupted_tasks()
    # InitWizardService is also a singleton and caches AppState.  A new app
    # config directory must read its own state before the first worker-thread
    # request, rather than inheriting the previous app's cached object.
    init_wizard.reset_state_cache()
    ensure_dev_stubs_started()

    if enforce_single_instance:
        _check_single_instance()

    runtime = None
    startup_error = ""
    reg = BrokerRegistry()
    try:
        if init_wizard.is_initialized():
            init_data(get_data_home(), init_db=False)
            runtime = RuntimeBootstrap().bootstrap()
            reg = runtime.registry
            strategy_runtime_manager.bootstrap_from_runtime(runtime)
            from quantide.service.data_readiness import data_readiness_monitor

            data_readiness_monitor.start()
            try:
                _init_scheduler_jobs()
                factor_tracking_service.start(recover=enforce_single_instance)
            except Exception as exc:
                logger.warning(f"定时任务注册失败: {exc}")
    except Exception as exc:
        startup_error = str(exc)
        logger.warning(f"应用运行时初始化失败，将进入初始化向导模式: {exc}")

    auth = AuthManager(
        db_path=str(db_path),
        config={
            "login_path": "/auth/login",
            "public_paths": ["/init-wizard", r"/init-wizard/.*", "/api/health"],
        },
    )
    # AuthManager is a process singleton, while the factory supports isolated
    # app config directories (notably for tests and embedded app instances).
    # Rebind before registering middleware/routes so a request handled by an
    # ASGI worker cannot use the connection from an earlier app.
    auth_db_path = Path(auth.auth_db.db_path).expanduser()
    if auth_db_path != db_path.expanduser():
        auth.rebind_database(str(db_path))

    app, rt = fast_app(
        lifespan=application_lifespan,
        hdrs=AppTheme.headers(),
        before=auth.create_beforeware(),
        middleware=[
            Middleware(InitCheckMiddleware),
            Middleware(FeatureCheckMiddleware),
            Middleware(BrokerRegistryMiddleware, registry=reg),
        ],
        exception_handlers={
            Exception: exception_handler,
            BaseTradeError: exception_handler,
        },
        routes=[
            Route("/api/health", _health_response, methods=["GET"]),
            Mount(
                "/static",
                StaticFiles(directory=str(Path(__file__).resolve().parent / "web" / "static")),
                name="static",
            ),
            Route(
                "/init-wizard",
                lambda req: RedirectResponse(
                    f"/init-wizard/?{req.url.query}" if req.url.query else "/init-wizard/"
                ),
            ),
            Mount("/init-wizard", init_wizard_app),
            Route(
                "/login",
                lambda req: RedirectResponse("/auth/login", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/login/",
                lambda req: RedirectResponse("/auth/login", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/system",
                lambda req: RedirectResponse("/system/calendar", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/system/",
                lambda req: RedirectResponse("/system/calendar", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/live",
                lambda req: _redirect_preserving_query(req, "/trade/live/"),
                methods=["GET"],
            ),
            Route(
                "/live/",
                lambda req: _redirect_preserving_query(req, "/trade/live/"),
                methods=["GET"],
            ),
            Route(
                "/papertrade",
                lambda req: _redirect_preserving_query(req, "/trade/paper/"),
                methods=["GET"],
            ),
            Route(
                "/papertrade/",
                lambda req: _redirect_preserving_query(req, "/trade/paper/"),
                methods=["GET"],
            ),
            Route(
                "/trade/simulation",
                lambda req: _redirect_preserving_query(req, "/trade/paper/"),
                methods=["GET"],
            ),
            Route(
                "/trade/live",
                lambda req: _redirect_preserving_query(req, "/trade/live/"),
                methods=["GET"],
            ),
            Route(
                "/trade/paper",
                lambda req: _redirect_preserving_query(req, "/trade/paper/"),
                methods=["GET"],
            ),
            Mount("/home", home_app),
            Mount("/trade/live", live_app),
            Mount("/trade/paper", paper_app),
            Route("/trade/positions/history", history_positions_list, methods=["GET"]),
            Route("/trade/orders/history", history_orders_list, methods=["GET"]),
            Route("/trade/records/history", history_trades_list, methods=["GET"]),
            Route("/trade", trade_main_page),
            Route("/trade/", trade_main_page),
            Route("/trade/positions", trade_positions_refresh, methods=["GET"]),
            Route("/trade/orders", trade_orders_refresh, methods=["GET"]),
            Route("/trade/search", search_trade_assets, methods=["GET"]),
            Route("/trade/lightning/search", trade_lightning_search, methods=["GET"]),
            Route("/trade/asset-stats", trade_asset_stats, methods=["GET"]),
            Route("/trade/live-quote", trade_live_quote, methods=["GET"]),
            Route("/trade/order", place_order_trade, methods=["POST"]),
            Route("/tracking/{portfolio_id}", tracking_page, methods=["GET"]),
            Route("/tracking/{portfolio_id}/toggle", toggle_tracking, methods=["POST"]),
            Route("/trade/cancel/{qtoid}", cancel_order_trade, methods=["POST"]),
            Route(
                "/trade/lightning/{portfolio_id:str}/create-modal",
                trade_lightning_create_modal,
                methods=["GET"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/create",
                trade_lightning_create,
                methods=["POST"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/clear-modal",
                trade_lightning_clear_modal,
                methods=["GET"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/clear",
                trade_lightning_clear,
                methods=["POST"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/{asset:str}/edit-modal",
                trade_lightning_edit_modal,
                methods=["GET"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/{asset:str}/update",
                trade_lightning_update,
                methods=["POST"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/{asset:str}/delete-modal",
                trade_lightning_delete_modal,
                methods=["GET"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/{asset:str}/delete",
                trade_lightning_delete,
                methods=["POST"],
            ),
            Route(
                "/trade/lightning/{portfolio_id:str}/{asset:str}/execute",
                trade_lightning_execute,
                methods=["POST"],
            ),
            Route("/system/accounts", lambda req: RedirectResponse("/system/accounts/")),
            Mount("/system/accounts", accounts_app),
            Route("/strategy", lambda req: RedirectResponse("/strategy/")),
            Route(
                "/strategy/live",
                lambda req: RedirectResponse("/trade/live/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/strategy/live/",
                lambda req: RedirectResponse("/trade/live/", status_code=303),
                methods=["GET"],
            ),
            Mount("/strategy", strategy_app),
            Route(
                "/factors",
                lambda req: RedirectResponse("/factors/", status_code=303),
                methods=["GET"],
            ),
            Mount("/factors", factor_app),
            Mount("/attribution", attribution_app),
            Route("/analysis", analysis_handler, methods=["GET"]),
            Mount("/broker", broker_api_app),
            Mount("/api/v1/kline", kline_router),
            Mount("/api/v1/search", search_router),
            Route(
                "/data/calendar",
                lambda req: RedirectResponse("/data/calendar/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/data/market",
                lambda req: RedirectResponse("/data/market/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/data/stocks",
                lambda req: RedirectResponse("/data/stocks/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/data/db",
                lambda req: RedirectResponse("/data/db/", status_code=303),
                methods=["GET"],
            ),
            Mount("/data/calendar", data_calendar_app),
            Mount("/data/market", data_market_app),
            Mount("/data/stocks", data_stocks_app),
            Mount("/data/db", data_db_app),
            Route(
                "/system/calendar",
                lambda req: RedirectResponse("/system/calendar/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/system/stocks",
                lambda req: RedirectResponse("/system/stocks/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/system/market",
                lambda req: RedirectResponse("/system/market/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/calendar", system_calendar_app),
            Mount("/system/stocks", system_stocks_app),
            Mount("/system/market", system_market_app),
            Route(
                "/system/realtime",
                lambda req: RedirectResponse("/system/realtime/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/realtime", system_realtime_app),
            Route(
                "/system/jobs",
                lambda req: RedirectResponse("/system/jobs/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/jobs", system_jobs_app),
            Route(
                "/system/gateway",
                lambda req: RedirectResponse("/system/gateway/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/gateway", system_gateway_app),
            Route(
                "/system/datasource",
                lambda req: RedirectResponse("/system/datasource/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/datasource", system_datasource_app),
            Route(
                "/system/network",
                lambda req: RedirectResponse("/system/network/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/network", system_network_app),
            Route(
                "/system/directories",
                lambda req: RedirectResponse("/system/directories/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/directories", system_directories_app),
            Route(
                "/system/risk-events",
                lambda req: RedirectResponse("/system/risk-events/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/risk-events", system_risk_events_app),
            Route(
                "/system/runtime-monitor",
                lambda req: RedirectResponse("/system/runtime-monitor/", status_code=303),
                methods=["GET"],
            ),
            Mount("/system/runtime-monitor", system_runtime_monitor_app),
            Mount("/", home_app),
        ],
    )

    app.user_middleware.append(Middleware(AuthGuard, auth=auth))
    auth.initialize(app, prefix="/auth")
    _bind_session_key(app, app.secret_key)
    app.state.runtime = runtime
    app.state.startup_error = startup_error
    app.state.strategy_runtime_manager = strategy_runtime_manager
    app.state.app_config_dir = get_app_config_dir()
    app.state.auth_manager = auth
    _attach_root_app_to_app_states(app)
    _attach_runtime_to_app_states(runtime)

    @rt("/trade/set-active", methods=["POST"])
    async def trade_set_active(req: Request, session: SessionData) -> Any:
        return set_active_account(req)

    return app


__all__ = ["create_app"]
