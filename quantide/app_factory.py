"""Application factory for Quantide."""

from __future__ import annotations

import atexit
import datetime
import os
import sys
from pathlib import Path

from fasthtml.common import Mount, Route, fast_app
from fasthtml import core as _fasthtml_core
from loguru import logger

# fasthtml 默认注入 htmx@2.0.7；AppTheme.headers() 又显式注入了 htmx@1.9.12。
# 两个版本同时加载会让同一份 hx-* 属性被两套监听器重复绑定，浏览器侧触发
# ``htmx:afterRequest``/``htmx:sendAbort`` 互相打断死循环（用户报告：点击
# “实盘”进入 /trade 后整页 frozen）。把 fasthtml 的默认 htmx URL 改到 1.9.12，
# 两份就是同源，浏览器会自动去重，冲突消失。
_fasthtml_core.htmxsrc = _fasthtml_core.Script(
    src="https://unpkg.com/htmx.org@1.9.12"
)
from starlette.middleware import Middleware
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from quantide.config.branding import get_branding
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
from quantide.service.registry import BrokerRegistry
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.apis.analysis import kline_router, search_router
from quantide.web.apis.broker import app as broker_api_app
from quantide.web.auth.manager import AuthManager
from quantide.web.middleware import BrokerRegistryMiddleware, exception_handler
from quantide.web.middleware_feature import FeatureCheckMiddleware
from quantide.web.middleware_init import InitCheckMiddleware
from quantide.web.pages.accounts import accounts_app, accounts_list
from quantide.web.pages.analysis import analysis_handler
from quantide.web.pages.data_calendar import data_calendar_app
from quantide.web.pages.data_db import data_db_app
from quantide.web.pages.data_market import data_market_app
from quantide.web.pages.data_stocks import data_stocks_app
from quantide.web.pages.history_orders import history_orders_list
from quantide.web.pages.history_positions import history_positions_list
from quantide.web.pages.history_trades import history_trades_list
from quantide.web.pages.home import home_app
from quantide.web.pages.init_wizard import init_wizard, init_wizard_app
from quantide.web.pages.live import live_app
from quantide.web.pages.paper import paper_app
from quantide.web.pages.strategy import strategy_app
from quantide.web.pages.system.calendar import system_calendar_app
from quantide.web.pages.system.datasource import system_datasource_app
from quantide.web.pages.system.gateway import system_gateway_app
from quantide.web.pages.system.jobs import system_jobs_app
from quantide.web.pages.system.market import system_market_app
from quantide.web.pages.system.risk_events import system_risk_events_app
from quantide.web.pages.system.runtime_monitor import system_runtime_monitor_app
from quantide.web.pages.system.stocks import system_stocks_app
from quantide.web.pages.trade_lightning import (
    trade_lightning_clear,
    trade_lightning_clear_modal,
    trade_lightning_create,
    trade_lightning_create_modal,
    trade_lightning_delete,
    trade_lightning_delete_modal,
    trade_lightning_edit_modal,
    trade_lightning_search,
    trade_lightning_update,
)
from quantide.web.pages.trade_main import (
    place_order_trade,
    search_trade_assets,
    set_active_account,
    trade_asset_stats,
    trade_live_quote,
    trade_main_page,
    trade_positions_refresh,
    trade_orders_refresh,
)
from quantide.web.theme import AppTheme


def _check_single_instance() -> None:
    """检查是否已有实例在运行，防止多实例启动。"""
    pid_file = get_pid_file_path()
    product_name = get_branding().product_name

    if pid_file.exists():
        try:
            with open(pid_file) as file_obj:
                pid = int(file_obj.read().strip())

            if sys.platform == "win32":
                import ctypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle != 0:
                    kernel32.CloseHandle(handle)
                    raise RuntimeError(
                        f"{product_name} 已经在运行 (PID: {pid})。"
                        f"请先停止现有实例，或删除 {pid_file} 后重试。"
                    )
            else:
                os.kill(pid, 0)
                raise RuntimeError(
                    f"{product_name} 已经在运行 (PID: {pid})。"
                    f"请先停止现有实例，或删除 {pid_file} 后重试。"
                )
        except (ValueError, OSError, ProcessLookupError):
            pid_file.unlink()

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    with open(pid_file, "w") as file_obj:
        file_obj.write(str(os.getpid()))

    def cleanup_pid() -> None:
        if pid_file.exists():
            pid_file.unlink()

    atexit.register(cleanup_pid)


def _initialize_app_database() -> Path:
    """Initialize the fixed sqlite database in the config directory."""
    db_path = get_app_db_path()

    try:
        db.init(db_path)
        return db_path
    except Exception as exc:
        if not db_path.exists():
            raise

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = db_path.with_name(
            f"{db_path.stem}.corrupt.{timestamp}{db_path.suffix}"
        )
        logger.warning(f"配置数据库无法读取，已备份到 {backup_path}: {exc}")
        try:
            db_path.rename(backup_path)
        except Exception:
            logger.exception("备份损坏配置数据库失败")
            raise

        db._initialized = False
        db.init(db_path)
        return db_path

def _attach_runtime_to_app_states(runtime) -> None:
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
        init_wizard_app,
        system_calendar_app,
        system_datasource_app,
        system_gateway_app,
        system_jobs_app,
        system_market_app,
        system_risk_events_app,
        system_runtime_monitor_app,
        system_stocks_app,
    ):
        mounted_app.state.runtime = runtime


def _attach_root_app_to_app_states(root_app) -> None:
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
        init_wizard_app,
        system_calendar_app,
        system_datasource_app,
        system_gateway_app,
        system_jobs_app,
        system_market_app,
        system_risk_events_app,
        system_runtime_monitor_app,
        system_stocks_app,
    ):
        mounted_app.state.root_app = root_app


def create_app(
    app_config_dir: str | Path | None = None,
    enforce_single_instance: bool = True,
):
    """Create a Quantide web application.

    Args:
        app_config_dir: 应用运行时配置目录，用于 sqlite、pid 等持久化文件。
        enforce_single_instance: 是否执行单实例检查。
    """
    set_app_config_dir_override(app_config_dir)
    db_path = _initialize_app_database()
    ensure_dev_stubs_started()

    if enforce_single_instance:
        _check_single_instance()

    runtime = None
    reg = BrokerRegistry()
    try:
        if init_wizard.is_initialized():
            init_data(get_data_home(), init_db=False)
            runtime = RuntimeBootstrap().bootstrap()
            reg = runtime.registry
            strategy_runtime_manager.bootstrap_from_runtime(runtime)
    except Exception as exc:
        logger.warning(f"应用运行时初始化失败，将进入初始化向导模式: {exc}")

    auth = AuthManager(
        db_path=str(db_path),
        config={
            "login_path": "/auth/login",
            "public_paths": ["/init-wizard", r"/init-wizard/.*"],
        },
    )

    app, rt = fast_app(
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
            Mount(
                "/static",
                StaticFiles(
                    directory=str(
                        Path(__file__).resolve().parent / "web" / "static"
                    )
                ),
                name="static",
            ),
            Route(
                "/init-wizard",
                lambda req: RedirectResponse(
                    f"/init-wizard/?{req.url.query}"
                    if req.url.query
                    else "/init-wizard/"
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
                lambda req: RedirectResponse("/trade/live/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/live/",
                lambda req: RedirectResponse("/trade/live/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/papertrade",
                lambda req: RedirectResponse("/trade/paper/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/papertrade/",
                lambda req: RedirectResponse("/trade/paper/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/trade/simulation",
                lambda req: RedirectResponse("/trade/paper/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/trade/live",
                lambda req: RedirectResponse("/trade/live/", status_code=303),
                methods=["GET"],
            ),
            Route(
                "/trade/paper",
                lambda req: RedirectResponse("/trade/paper/", status_code=303),
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
            Route("/system/accounts", accounts_list, methods=["GET"]),
            Route("/system/accounts/", accounts_list, methods=["GET"]),
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

    auth.initialize(app, prefix="/auth")
    app.state.runtime = runtime
    app.state.strategy_runtime_manager = strategy_runtime_manager
    app.state.app_config_dir = get_app_config_dir()
    _attach_root_app_to_app_states(app)
    _attach_runtime_to_app_states(runtime)

    @rt("/trade/set-active", methods=["POST"])
    async def trade_set_active(req, session):
        return await set_active_account(req, session)

    return app


__all__ = ["create_app"]
