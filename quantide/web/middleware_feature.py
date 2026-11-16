"""功能可用性检查中间件."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from quantide.config.branding import get_branding
from quantide.config.features import (
    live_trading_unavailable_message,
    supports_live_trading,
)
from quantide.service.init_wizard import init_wizard


def _request_feature_key(request: Request) -> str | None:
    """Resolve the feature being requested, including HTMX target views."""
    feature_key = _match_feature_for_path(request.url.path)
    if feature_key is None and request.url.path.startswith("/broker"):
        requested_kind = str(request.query_params.get("kind", "")).lower()
        active_kind = str(
            (request.scope.get("session") or {}).get("active_account_kind", "")
        ).lower()
        if requested_kind in {"qmt", "live"} or active_kind in {"qmt", "live"}:
            feature_key = "live_trading"
    if feature_key is None and (
        request.url.path == "/trade/set-active" or request.url.path.startswith("/trade/cancel/")
    ):
        active_kind = str(
            (request.scope.get("session") or {}).get("active_account_kind", "")
        ).lower()
        if active_kind in {"qmt", "live"}:
            feature_key = "live_trading"
    return feature_key


FEATURE_ROUTE_PREFIXES = {
    "/live": "live_trading",
    "/trade/simulation": "simulation",
    "/trade/live": "live_trading",
    "/strategy/live": "live_trading",
    "/system/gateway": "live_settings",
    "/init-wizard/gateway-test": "live_settings",
    "/system/accounts/live": "live_trading",
}


def _edition_feature(feature_key: str) -> dict[str, Any]:
    """Edition feature."""
    if feature_key == "live_settings":
        if not supports_live_trading():
            feature = {
                "name": "实盘设置",
                "available": False,
            }
        else:
            # The settings page is how a private edition configures
            # the gateway, so it must remain reachable before setup.
            feature = {"name": "实盘设置", "available": True}
    else:
        feature = get_feature_status().get(feature_key, {})
    return feature


def _match_feature_for_path(path: str) -> str | None:
    for prefix, feature in FEATURE_ROUTE_PREFIXES.items():
        if path == prefix or path.startswith(f"{prefix}/"):
            return feature
    if "/deploy/live" in path:
        return "live_trading"
    return None


def _is_htmx_request(headers: Mapping[str, str]) -> bool:
    return str(headers.get("HX-Request", "")).lower() == "true"


def _disabled_fragment_html(feature_name: str) -> str:
    if not supports_live_trading() and feature_name in {"实盘交易", "live_trading", "实盘设置"}:
        return (
            '\n        <div class="max-w-xl mx-auto mt-10 p-6 bg-white rounded-lg shadow '
            'border border-gray-200 text-center">\n            <h3 class="text-lg '
            'font-semibold text-gray-700 mb-3">🔒 实盘交易暂不可用</h3>\n            <p '
            'class="text-gray-700 mb-2">'
            f"{live_trading_unavailable_message()}"
            '。</p>\n            <p class="text-gray-600">当前版本可继续使用回测、仿真账'
            "户和纸面运行。</p>\n        </div>\n        "
        )
    return (
        '\n    <div class="max-w-xl mx-auto mt-10 p-6 bg-white rounded-lg shadow border '
        'border-gray-200 text-center">\n        <h3 class="text-lg font-semibold '
        'text-red-700 mb-3">🔒 '
        f"{feature_name}"
        '功能已禁用</h3>\n        <p class="text-gray-700 mb-2">您当前未配置 '
        "gateway，因此无法使用"
        f"{feature_name}"
        '功能。</p>\n        <p class="text-gray-600 '
        'mb-4">如需启用，请先前往交易网关页面完成配置。</p>\n        <a '
        'href="/system/gateway/" class="btn btn-primary" style="background: #D13527; '
        "color: white; text-decoration: none; padding: 10px 20px; border-radius: 6px; "
        'display: inline-block;">前往交易网关</a>\n    </div>\n    '
    )


def _disabled_page_html(feature_name: str) -> str:
    fragment = _disabled_fragment_html(feature_name)
    product_name = get_branding().product_name
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>功能禁用 - {product_name}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
                padding: 40px;
            }}
            .btn:hover {{ background: #b52d20; }}
        </style>
    </head>
    <body>
        {fragment}
    </body>
    </html>
    """


def _feature_disabled_response(feature_name: str, *, htmx: bool = False) -> Response:
    """AC-2: A 类降级直接 URL 访问返回 503 + 提示页 (interfaces.md GATEWAY_NOT_CONFIGURED)."""
    if htmx:
        return HTMLResponse(content=_disabled_fragment_html(feature_name), status_code=503)
    return HTMLResponse(content=_disabled_page_html(feature_name), status_code=503)


class FeatureCheckMiddleware(BaseHTTPMiddleware):
    """功能可用性检查中间件

    根据初始化后的功能状态收紧交易入口。
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """处理请求"""
        feature_key = _request_feature_key(request)
        if feature_key is not None:
            feature = _edition_feature(feature_key)
            if not feature.get("available", False):
                feature_name = str(feature.get("name") or feature_key)
                if request.method == "GET":
                    return _feature_disabled_response(
                        feature_name,
                        htmx=_is_htmx_request(request.headers),
                    )
                return JSONResponse(
                    {
                        "error": (
                            live_trading_unavailable_message()
                            if not supports_live_trading()
                            and feature_key in {"live_trading", "live_settings"}
                            else f"{feature_name}功能已禁用，请先在交易网关页面配置 gateway"
                        )
                    },
                    status_code=503,
                )
        response = await call_next(request)
        return response


def require_qmt_configured(func: Any) -> Any:
    """装饰器：要求必须配置 gateway 才能访问

    用于在路由处理函数中手动检查 gateway 配置。

    Args:
        func: 被装饰的函数

    Returns:
        如果未配置 gateway，返回提示页面；否则执行原函数
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        feature = get_feature_status().get("live_trading", {})
        if not feature.get("available", False):
            feature_name = str(feature.get("name") or "实盘交易")
            return _feature_disabled_response(feature_name)
        return func(*args, **kwargs)

    return wrapper


def get_feature_status() -> dict[str, dict[str, Any]]:
    """获取功能状态信息

    Returns:
        功能状态字典，包含各功能的可用状态和提示信息
    """
    try:
        status = init_wizard.get_feature_status()

        features = {
            "backtest": {
                "name": "回测功能",
                "available": status["backtest"],
                "icon": "📊",
                "description": "使用历史数据进行策略回测",
                "required": "完成初始化并配置 Tushare",
            },
            "simulation": {
                "name": "仿真交易",
                "available": status["simulation"],
                "icon": "🎮",
                "description": "使用 gateway 进行仿真交易",
                "required": "完成初始化并启用 gateway",
            },
            "live_trading": {
                "name": "实盘交易",
                "available": supports_live_trading() and status["live_trading"],
                "icon": "💰",
                "description": "使用 gateway 进行实盘交易",
                "required": "完成初始化并启用 gateway",
            },
        }

        return features
    except Exception:
        # 如果检查失败，返回全部不可用
        return {
            "backtest": {
                "name": "回测功能",
                "available": False,
                "icon": "📊",
                "description": "使用历史数据进行策略回测",
                "required": "完成初始化",
            },
            "simulation": {
                "name": "仿真交易",
                "available": False,
                "icon": "🎮",
                "description": "使用 gateway 进行仿真交易",
                "required": "完成初始化",
            },
            "live_trading": {
                "name": "实盘交易",
                "available": False,
                "icon": "💰",
                "description": "使用 gateway 进行实盘交易",
                "required": "完成初始化",
            },
        }
