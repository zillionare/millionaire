"""Wizard state."""

from fasthtml.common import *
from fasthtml.common import (
    Request,
)
from loguru import logger
from monsterui.all import *

from quantide.config.paths import DEFAULT_DATA_HOME
from quantide.web.application import fast_app
from quantide.web.theme import AppTheme

init_wizard_app, rt = fast_app(hdrs=AppTheme.headers())


_sync_status = {
    "is_running": False,
    "current_task": "",
    "progress": 0,
    "stage": "",
    "message": "",
    "completed": False,
    "error": None,
}


_download_error_message: str | None = None


_reconfigure_mode_active = False


def _set_download_error(message: str | None) -> None:
    global _download_error_message
    text = str(message or "").strip()
    _download_error_message = text or None


def _get_download_error(step: int, explicit_error: str | None = None) -> str | None:
    if explicit_error:
        return explicit_error
    if step == 6:
        return _download_error_message
    return None


def _set_reconfigure_mode(active: bool) -> None:
    global _reconfigure_mode_active
    _reconfigure_mode_active = bool(active)


def _request_in_force_mode(request: Request) -> bool:
    query_params = getattr(request, "query_params", {}) or {}
    return str(query_params.get("force", "false")).lower() == "true"


def _with_force_query(path: str) -> str:
    if not _reconfigure_mode_active:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}force=true"


def _update_sync_status(
    progress: int,
    stage: str,
    message: str | None = None,
    completed: bool = False,
    error: str | None = None,
) -> None:
    """更新同步状态"""
    _sync_status["progress"] = progress
    _sync_status["stage"] = stage
    _sync_status["message"] = message if message is not None else stage
    _sync_status["completed"] = completed
    _sync_status["error"] = error
    logger.info(f"同步进度: {progress}% - {stage} - {_sync_status['message']}")


ADMIN_FORM_FIELDS = {
    "password": "admin_password",
    "confirm": "admin_password_confirm",
}


RUNTIME_FORM_FIELDS = {
    "home": "app_home",
    "host": "app_host",
    "port": "app_port",
    "prefix": "app_prefix",
    "localhost_only": "localhost_only",
}


GATEWAY_FORM_FIELDS = {
    "enabled": "gateway_enabled",
    "server": "gateway_server",
    "port": "gateway_port",
    "api_key": "gateway_api_key",
    "prefix": "gateway_prefix",
    "state_prefix": "gateway_base_url",
}


DATA_INIT_FORM_FIELDS = {
    "epoch": "epoch",
    "data_source": "data_source",
    "tushare_token": "tushare_token",
    "history_years": "history_years",
}


RUNTIME_FIELD_ALIASES = {
    RUNTIME_FORM_FIELDS["home"]: (RUNTIME_FORM_FIELDS["home"], "home"),
    RUNTIME_FORM_FIELDS["host"]: (RUNTIME_FORM_FIELDS["host"], "host"),
    RUNTIME_FORM_FIELDS["port"]: (RUNTIME_FORM_FIELDS["port"], "port"),
    RUNTIME_FORM_FIELDS["prefix"]: (RUNTIME_FORM_FIELDS["prefix"], "prefix"),
}


GATEWAY_FIELD_ALIASES = {
    GATEWAY_FORM_FIELDS["enabled"]: (GATEWAY_FORM_FIELDS["enabled"],),
    GATEWAY_FORM_FIELDS["server"]: (GATEWAY_FORM_FIELDS["server"],),
    GATEWAY_FORM_FIELDS["port"]: (GATEWAY_FORM_FIELDS["port"],),
    GATEWAY_FORM_FIELDS["api_key"]: (GATEWAY_FORM_FIELDS["api_key"],),
    GATEWAY_FORM_FIELDS["prefix"]: (
        GATEWAY_FORM_FIELDS["prefix"],
        GATEWAY_FORM_FIELDS["state_prefix"],
    ),
}


DATA_INIT_FIELD_ALIASES = {
    DATA_INIT_FORM_FIELDS["epoch"]: (DATA_INIT_FORM_FIELDS["epoch"],),
    DATA_INIT_FORM_FIELDS["data_source"]: (DATA_INIT_FORM_FIELDS["data_source"],),
    DATA_INIT_FORM_FIELDS["tushare_token"]: (DATA_INIT_FORM_FIELDS["tushare_token"],),
    DATA_INIT_FORM_FIELDS["history_years"]: (DATA_INIT_FORM_FIELDS["history_years"],),
}


RUNTIME_DEFAULTS = {
    RUNTIME_FORM_FIELDS["home"]: DEFAULT_DATA_HOME,
    RUNTIME_FORM_FIELDS["host"]: "127.0.0.1",
    RUNTIME_FORM_FIELDS["port"]: 8130,
    RUNTIME_FORM_FIELDS["prefix"]: "/quantide",
}


GATEWAY_DEFAULTS = {
    GATEWAY_FORM_FIELDS["enabled"]: True,
    GATEWAY_FORM_FIELDS["server"]: "localhost",
    GATEWAY_FORM_FIELDS["port"]: 8000,
    GATEWAY_FORM_FIELDS["api_key"]: "",
    GATEWAY_FORM_FIELDS["prefix"]: "/",
}


DATA_INIT_DEFAULTS = {
    DATA_INIT_FORM_FIELDS["epoch"]: "2005-01-01",
    DATA_INIT_FORM_FIELDS["data_source"]: "tushare",
    DATA_INIT_FORM_FIELDS["tushare_token"]: "",
    DATA_INIT_FORM_FIELDS["history_years"]: 1,
}


PRIMARY_COLOR = "#D13527"


FONT_STYLES = {
    "title": "font-size: 20px; font-weight: 600;",
    "subtitle": "font-size: 16px; font-weight: 500;",
    "description": "font-size: 14px; font-weight: 400; color: #6b7280;",
    "label": "font-size: 13px; font-weight: 500; color: #374151;",
    "hint": "font-size: 12px; font-weight: 400; color: #9ca3af;",
    "required": "color: #dc2626; margin-left: 2px;",
}


WIZARD_PANEL_STYLE = (
    # "background: white; border-radius: 12px; min-height: 560px; "
    # "padding: 36px 44px 28px; display: flex; flex-direction: column; "
    # "box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);"
)


WIZARD_STEP_WRAPPER_STYLE = (
    "width: 88px; min-height: 420px; display: flex; align-items: flex-start; "
    "justify-content: center; overflow: visible;"
)


WIZARD_BODY_INNER_STYLE = "width: 100%; margin: 0 auto;"
