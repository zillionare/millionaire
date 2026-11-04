"""交易主页面 - 符合 livetrade-default.html 原型。

包含：
1. 资产信息条
2. 闪电交易面板
3. 持仓明细
4. 当日委托
"""

import json
import urllib.error
import urllib.request

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    P,
    Span,
)
from fasthtml.common import to_xml as _to_xml
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H2,
    H3,
    H4,
    Button,
    Form,
    Input,
    UkIcon,
)
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)

from quantide.config.features import supports_live_trading
from quantide.config.settings import get_settings
from quantide.core.enums import BrokerKind
from quantide.data.models import Order, Position
from quantide.data.models.stocks import stock_list
from quantide.service.registry import BrokerRegistry
from quantide.web.components.asset_search import AssetSearchResults
from quantide.web.components.trade_order_entry import (
    AssetInfoBar as AssetInfoBar,
)
from quantide.web.components.trade_order_entry import (
    LightningTradePanel as LightningTradePanel,
)
from quantide.web.components.trade_order_entry import (
    _trade_toast as _trade_toast,
)
from quantide.web.components.trade_tables import (
    DEFAULT_POSITIONS_TAB as DEFAULT_POSITIONS_TAB,
)
from quantide.web.components.trade_tables import (
    POSITIONS_TABS as POSITIONS_TABS,
)
from quantide.web.components.trade_tables import (
    POSITIONS_TABS_PANEL_ID as POSITIONS_TABS_PANEL_ID,
)
from quantide.web.components.trade_tables import (
    PositionsOrdersTabs as PositionsOrdersTabs,
)
from quantide.web.components.trade_tables import (
    PositionTable as PositionTable,
)
from quantide.web.components.trade_tables import (
    TodayOrdersTable as TodayOrdersTable,
)
from quantide.web.components.trade_tables import (
    _normalize_positions_tab as _normalize_positions_tab,
)
from quantide.web.layouts.main import MainLayout
from quantide.web.semantic_styles import account_badge
from quantide.web.services.trade_accounts import (
    LiveAccountUnavailable,
    account_details,
    default_account,
    find_broker,
    is_live_kind,
    listed_account,
    resolve_active_account,
    resolve_order_account,
)
from quantide.web.services.trade_gateway_views import (
    _coerce_gateway_order as _coerce_gateway_order,
)
from quantide.web.services.trade_gateway_views import (
    _coerce_gateway_position as _coerce_gateway_position,
)
from quantide.web.services.trade_gateway_views import (
    _parse_order_time_text as _parse_order_time_text,
)
from quantide.web.services.trade_orders import parse_manual_order, submit_manual_order
from quantide.web.services.trade_quote_view import (
    _build_asset_stats as _build_asset_stats,
)
from quantide.web.services.trade_quote_view import (
    _build_live_quote_payload as _build_live_quote_payload,
)
from quantide.web.services.trade_quote_view import (
    _extract_recent_trade_dates as _extract_recent_trade_dates,
)
from quantide.web.services.trade_quote_view import (
    _format_trade_metric as _format_trade_metric,
)
from quantide.web.services.trade_quote_view import (
    _load_trade_reference_bars as _load_trade_reference_bars,
)
from quantide.web.services.trade_quote_view import (
    _maybe_start_live_quote as _maybe_start_live_quote,
)
from quantide.web.services.trade_quote_view import (
    _resolve_live_current_price as _resolve_live_current_price,
)
from quantide.web.services.trade_quote_view import (
    _resolve_local_trade_close as _resolve_local_trade_close,
)
from quantide.web.services.trade_quote_view import (
    _resolve_trade_reference_close as _resolve_trade_reference_close,
)
from quantide.web.services.trade_quote_view import (
    _resolve_trade_reference_dates as _resolve_trade_reference_dates,
)


def _get_registry(req) -> BrokerRegistry:
    return req.scope.get("registry")


def _get_all_accounts(reg: BrokerRegistry) -> list[dict]:
    """获取所有账号列表"""
    accounts = []
    kinds = [BrokerKind.SIMULATION]
    if supports_live_trading():
        kinds.insert(0, BrokerKind.QMT)
    for kind in kinds:
        for info in reg.list_by_kind(kind):
            accounts.append(listed_account(kind, info))
    return accounts


def _get_active_account(reg, session, query_params=None):
    """Return the selected account after applying the edition's account policy."""
    selected = resolve_active_account(reg, session, query_params, supports_live_trading())
    return account_details(*selected) if selected else None


def _trade_result_has_order(result) -> bool:
    """Return whether a broker call produced an actual order.

    Args:
        result: Broker trade result object.

    Returns:
        True when an order id or trade rows are present.
    """
    if result is None:
        return False
    if getattr(result, "qt_oid", None):
        return True
    trades = getattr(result, "trades", None) or []
    return len(trades) > 0


# 持仓 / 委托 tab 配置 (Issue #30, #41).
# 与 09-backtest-report-tabs-and-logs.md 保持一致：tab 切换走 HTMX
# 局部刷新 + query 参数同步 URL，不再整页重载。
# HTMX 局部刷新的 swap 目标 id（同时用于 hx-select 过滤）


def NoAccountView():
    """无账号视图"""
    return Div(
        Div(
            UkIcon("alert-circle", size=48, cls="text-gray-400 mb-4"),
            H2("暂无交易账号", cls="text-2xl font-bold text-gray-900 mb-4"),
            P("您还没有配置任何交易账号。请先创建或配置账号。", cls="text-gray-600 mb-6"),
            Div(
                A(
                    UkIcon("plus", size=16),
                    " 创建仿真账号",
                    href="/trade/simulation",
                    cls="uk-button uk-button-primary mr-4",
                    style="background-color: #d32f2f;",
                ),
                A(
                    UkIcon("settings", size=16),
                    " 账号管理",
                    href="/system/accounts",
                    cls="uk-button uk-button-default",
                ),
                cls="flex justify-center gap-4",
            ),
            cls="text-center py-16",
        ),
        cls="max-w-2xl mx-auto bg-white rounded-xl shadow-sm border border-gray-100 p-8",
    )


def SelectAccountView(accounts: list[dict]):
    """选择账号视图"""
    live_accounts = [a for a in accounts if a["is_live"]]
    sim_accounts = [a for a in accounts if not a["is_live"]]

    def AccountCard(account: dict):
        return Div(
            Div(
                Div(
                    Span(
                        "实盘" if account["is_live"] else "仿真",
                        cls=(
                            "px-2 py-1 text-xs font-medium rounded-full "
                            f"{account_badge(account['is_live'])}"
                        ),
                    ),
                    Span(
                        "在线" if account["status"] else "离线",
                        cls=(
                            "ml-2 text-xs "
                            f"{('text-green-600' if account['status'] else 'text-gray-400')}"
                        ),
                    ),
                    cls="mb-2",
                ),
                H4(account["name"], cls="text-lg font-semibold text-gray-900"),
                P(f"ID: {account['id'][:16]}...", cls="text-xs text-gray-500"),
                cls="mb-4",
            ),
            Form(
                Input(type="hidden", name="kind", value=account["kind"]),
                Input(type="hidden", name="id", value=account["id"]),
                Button(
                    "设为活动账号",
                    type="submit",
                    cls="uk-button uk-button-primary w-full",
                    style="background-color: #d32f2f;",
                ),
                hx_post="/trade/set-active",
                hx_target="body",
                hx_swap="outerHTML",
            ),
            cls=(
                "bg-white rounded-xl shadow-sm border border-gray-100 p-6 "
                "hover:shadow-md transition-shadow"
            ),
        )

    return Div(
        Div(
            H2("选择活动账号", cls="text-2xl font-bold text-gray-900 mb-2"),
            P(
                "请选择一个账号作为当前活动账号，所有交易操作将与该账号关联。",
                cls="text-gray-600 mb-6",
            ),
            cls="mb-6",
        ),
        Div(
            Div(
                H3("实盘账号", cls="text-lg font-semibold text-gray-900 mb-4"),
                Div(
                    *[AccountCard(a) for a in live_accounts],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                )
                if live_accounts
                else P("暂无实盘账号", cls="text-gray-500 italic"),
                cls="mb-8",
            ),
            Div(
                H3("仿真账号", cls="text-lg font-semibold text-gray-900 mb-4"),
                Div(
                    *[AccountCard(a) for a in sim_accounts],
                    cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                )
                if sim_accounts
                else P("暂无仿真账号", cls="text-gray-500 italic"),
                cls="mb-8",
            ),
            Div(
                A(
                    UkIcon("settings", size=16),
                    " 管理账号",
                    href="/system/accounts",
                    cls="uk-button uk-button-default",
                ),
                cls="flex justify-center",
            ),
            cls="max-w-6xl mx-auto",
        ),
        cls="p-6",
    )


def trade_main_page(request):
    """交易主页面 - 符合 livetrade-default.html 原型"""
    session = request.scope.get("session", {})
    layout = MainLayout(title="交易", user=session.get("auth"))
    layout.header_active = "交易"
    layout.set_sidebar_active("/trade")

    reg = _get_registry(request)

    active_tab = _normalize_positions_tab(getattr(request, "query_params", {}).get("tab"))

    # 获取所有账号
    accounts = _get_all_accounts(reg) if reg else []

    # 如果没有配置任何账号
    if not accounts:

        def main_block():
            return Div(NoAccountView(), cls="p-6")

        layout.main_block = main_block
        return HTMLResponse(to_xml(layout.render()))

    # 获取活动账号
    active_account = _get_active_account(reg, session, request.query_params)

    # 如果没有活动账号，显示选择页面
    if not active_account:

        def main_block():
            return SelectAccountView(accounts)

        layout.main_block = main_block
        return HTMLResponse(to_xml(layout.render()))

    # 获取账号数据
    portfolio_id = active_account["id"]
    kind = active_account["kind"]

    broker = reg.get(BrokerKind(kind), portfolio_id) if reg else None

    # 获取资产信息
    capital = _trade_capital(broker)
    positions: list[Position] = []
    orders: list[Order] = []

    # 仿真账户直接读 broker（paper 的成交/委托在 broker 内），
    # 实盘仍走 gateway JSON API。错误一律吞掉，留空表 + log warning。
    try:
        positions, orders = _positions_orders_for_account(broker, kind)
    except Exception as e:
        logger.warning(f"加载持仓/委托失败: {e}")

    def main_block():
        return Div(
            Div(
                id="trade-toast-slot",
                cls=("pointer-events-none absolute inset-x-6 top-0 z-50"),
                aria_live="polite",
            ),
            # 账号信息
            Div(
                Div(
                    Span("★", cls="text-[#e41815] mr-1"),
                    Span(f"当前账号: {active_account['name']}", cls="font-medium"),
                    Span(f"({active_account['label']})", cls="ml-2 text-sm text-gray-500"),
                    A(
                        "对照 →",
                        href=f"/tracking/{portfolio_id}",
                        cls="ml-3 text-xs font-medium text-[#e41815] hover:text-[#c91412]",
                    ),
                    cls="flex items-center mb-4 px-6",
                ),
            ),
            # 资产信息条
            AssetInfoBar(**capital),
            # 闪电交易面板
            LightningTradePanel(
                portfolio_id,
                kind,
                capital["cash"],
                capital["total"],
                is_live=bool(active_account.get("is_live")),
            ),
            PositionsOrdersTabs(positions, orders, active_tab),
            cls="relative p-6",
        )

    layout.main_block = main_block
    return HTMLResponse(to_xml(layout.render()))


async def place_order_trade(req):
    """Validate the account and instruction before submitting a manual order."""
    form = await req.form()
    try:
        broker, kind = resolve_order_account(
            _get_registry(req), req.scope.get("session", {}), form, supports_live_trading()
        )
    except LiveAccountUnavailable as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    if not broker:
        return _render_order_toast("未找到可用的交易账号")
    try:
        order = parse_manual_order(form, _resolve_local_trade_close)
    except ValueError as exc:
        return _render_order_toast(str(exc))
    try:
        result = await submit_manual_order(broker, order)
        if not _trade_result_has_order(result):
            return _render_order_toast("未生成有效委托，请检查价格、数量和持仓后重试")
        return _submitted_order_response(broker, kind, order)
    except Exception as exc:
        return _render_order_toast(f"下单失败: {exc}")


async def cancel_order_trade(req):
    """撤销委托（模拟盘走 broker，实盘走 gateway）。"""
    qtoid = str(req.path_params.get("qtoid") or "").strip()
    if not qtoid:
        return HTMLResponse(to_xml(_trade_toast("缺少委托 ID")))
    reg = _get_registry(req)
    session = req.scope.get("session", {})
    kind = session.get("active_account_kind")
    account_id = session.get("active_account_id")
    if str(kind or "").lower() in {"qmt", "live"} and not supports_live_trading():
        return JSONResponse(
            {"error": "CE edition 暂不支持实盘交易"},
            status_code=503,
        )
    broker = None
    if reg and kind and account_id:
        try:
            broker = reg.get(BrokerKind(kind), account_id)
        except Exception:
            broker = None
    if broker is None:
        return HTMLResponse(to_xml(_trade_toast("未找到可用的交易账号")))
    try:
        await broker.cancel_order(qtoid)
    except Exception as e:
        return HTMLResponse(to_xml(_trade_toast(f"撤单失败: {e}")))
    try:
        _, orders = _positions_orders_for_account(broker, kind)
    except Exception:
        orders = []
    return HTMLResponse(
        to_xml(
            Div(
                _trade_toast("撤单已提交", level="success"),
                TodayOrdersTable(orders, hx_swap_oob=True),
            )
        )
    )


async def search_trade_assets(req):
    """搜索股票代码/名称/拼音，返回 HTMX 下拉列表 HTML。

    Args:
        req: HTTP 请求对象，包含查询参数 q

    Returns:
        HTMLResponse: 搜索结果下拉列表 HTML
    """
    query = req.query_params.get("q", "").strip()

    if not query:
        return HTMLResponse(to_xml(Div(id="asset-search-dropdown", cls="hidden")))

    try:
        result_df = stock_list.fuzzy_search(query, id_only=False)
    except Exception:
        return HTMLResponse(to_xml(Div(id="asset-search-dropdown", cls="hidden")))

    if result_df is None or len(result_df) == 0:
        return HTMLResponse(to_xml(Div(id="asset-search-dropdown", cls="hidden")))

    # 只返回代码/名称/拼音，避免逐条查询行情阻塞事件循环。
    return AssetSearchResults(result_df, lightning=False)


async def trade_asset_stats(req):
    """Return reference price stats for the selected asset.

    Args:
        req: HTTP request carrying the asset query parameter.

    Returns:
        JSONResponse: Compact stats payload for the trade panel.
    """
    asset = req.query_params.get("asset", "").strip()
    return JSONResponse(_build_asset_stats(asset) if asset else _build_asset_stats(""))


async def trade_live_quote(req):
    """Return a lightweight live quote payload for trade-page polling.

    Args:
        req: HTTP request carrying the asset query parameter.

    Returns:
        JSONResponse: Current quote payload for the selected asset.
    """
    asset = req.query_params.get("asset", "").strip()
    return JSONResponse(
        _build_live_quote_payload(asset) if asset else _build_live_quote_payload("")
    )


async def set_active_account(req, session: dict | None = None):
    """设置活动账号。

    Args:
        req: HTTP 请求。
        session: 可选的 session dict（未提供时从 ``req.scope["session"]`` 读）。
    """
    session = session if session is not None else req.scope.get("session", {})
    # 测试里可能传 dict 作为 req.scope，与 req 分离
    if not isinstance(req.scope, dict):
        req.scope = {}
    form = await req.form()
    kind = form.get("kind")
    account_id = form.get("id") or form.get("account_id")
    if not account_id and hasattr(req, "query_params"):
        account_id = req.query_params.get("account_id")

    if not kind or not account_id:
        return Div("参数错误", cls="text-red-500 p-4")
    if str(kind).lower() in {"qmt", "live"} and not supports_live_trading():
        return JSONResponse(
            {"error": "CE edition 暂不支持实盘交易"},
            status_code=503,
        )

    session["active_account_kind"] = kind
    session["active_account_id"] = account_id

    return RedirectResponse(url="/trade", status_code=303)


def _resolve_broker_for_refresh(req):
    """Resolve a remembered account or a usable default for HTMX refresh."""
    reg = _get_registry(req)
    session = req.scope.get("session", {}) or {}
    kind, account_id = session.get("active_account_kind"), session.get("active_account_id")
    if is_live_kind(kind) and not supports_live_trading():
        return None
    if kind and account_id:
        return find_broker(reg, kind, account_id)
    default = default_account(reg, supports_live_trading())
    return find_broker(reg, *default) if default else None


def _safe_orders(broker) -> list[Order]:
    """Try to fetch today's orders, returning ``[]`` on any failure."""
    if broker is None or not hasattr(broker, "orders"):
        return []
    try:
        orders_dict = broker.orders
    except Exception as e:
        logger.warning(f"刷新委托失败: {e}")
        return []
    if isinstance(orders_dict, dict):
        return list(orders_dict.values())
    return list(orders_dict) if orders_dict else []


def _safe_positions(broker) -> list[Position]:
    """Try to fetch current positions, returning ``[]`` on any failure."""
    if broker is None or not hasattr(broker, "positions"):
        return []
    try:
        positions_dict = broker.positions
    except Exception as e:
        logger.warning(f"刷新持仓失败: {e}")
        return []
    if isinstance(positions_dict, dict):
        return list(positions_dict.values())
    return list(positions_dict) if positions_dict else []


def _positions_orders_for_account(broker, kind: str | None) -> tuple[list[Position], list[Order]]:
    """按账号类型加载持仓/委托：仿真走 broker，实盘走 gateway."""
    if broker is not None and str(kind) == BrokerKind.SIMULATION.value:
        return _safe_positions(broker), _safe_orders(broker)
    return _resolve_positions_orders_from_settings()


def _fetch_positions_orders_via_gateway(
    base_url: str = "",
    api_key: str = "",
    timeout: float = 5.0,
) -> tuple[list[dict], list[dict]]:
    """直接通过 gateway JSON API 拉取持仓和委托.

    Issue #31 复盘 + 用户架构要求：让 /trade 页面成为「gateway htmx 渲染层」，
    解耦 broker 抽象（broker 包装、OrderView/PositionView 中间表示）。

    与 ``broker.positions`` / ``broker.orders`` 走的同一条数据通道（都是 GET
    /api/trade/{positions,orders}），但本函数直接发 HTTP，绕开
    ``GatewayClient`` 的 session-cookie 登录流程——带 ``X-API-Key`` 就够。

    任何错误（500、超时、鉴权失败、空配置）都返回 ``([], [])`` 并 log
    warning，绝不抛异常影响页面渲染。qmt-gateway#45 修好后，
    ``/api/trade/{positions,orders}`` 会正常返回 JSON（不再 500），本函数
    在 dev-stub / production 两种模式下表现完全一致。
    """
    empty: tuple[list[dict], list[dict]] = ([], [])
    if not base_url or not api_key:
        return empty

    positions: list[dict] = []
    orders: list[dict] = []

    positions = _gateway_json_collection(
        base_url, "/api/trade/positions", api_key, timeout, "positions"
    )
    orders = _gateway_json_collection(base_url, "/api/trade/orders", api_key, timeout, "orders")

    return positions, orders


def _resolve_positions_orders_from_settings() -> tuple[list[Position], list[Order]]:
    """从持久化 settings 拉取 gateway base_url/api_key，调 helper 转 dataclass."""
    settings = get_settings()
    if not settings.gateway_enabled:
        return [], []
    raw_positions, raw_orders = _fetch_positions_orders_via_gateway(
        base_url=settings.gateway_base_url,
        api_key=settings.gateway_api_key,
        timeout=float(settings.gateway_timeout or 5),
    )
    portfolio_id = "gateway"
    positions = [_coerce_gateway_position(p, portfolio_id) for p in raw_positions]
    orders = [_coerce_gateway_order(o, portfolio_id) for o in raw_orders]
    return positions, orders


async def trade_positions_refresh(req):
    """Htmx 刷新按钮的 handler：仅返回 ``PositionTable`` 片段.

    Issue #29 复盘：原页面 ``hx_get="/trade/positions"`` 按钮没有对应路由，
    点击会 404。现在补齐，返回与主页面里同一份 ``PositionTable`` 组件
    以便 ``hx-swap="outerHTML"`` 替换 ``#position-table``。

    Issue #31 + 用户架构要求：数据从 broker 包装层切到直接 gateway JSON API。
    """
    reg = _get_registry(req)
    session = req.scope.get("session", {}) or {}
    account = _get_active_account(reg, session, req.query_params) if reg else None
    broker = None
    if reg and account:
        try:
            broker = reg.get(BrokerKind(account["kind"]), account["id"])
        except Exception:
            broker = None
    positions, _ = _positions_orders_for_account(broker, account["kind"] if account else None)
    return HTMLResponse(_to_xml(PositionTable(positions)))


async def trade_orders_refresh(req):
    """Htmx 刷新按钮的 handler：仅返回 ``TodayOrdersTable`` 片段.

    Issue #29 复盘：原页面 ``hx_get="/trade/orders"`` 按钮没有对应路由。

    Issue #31 + 用户架构要求：数据从 broker 包装层切到直接 gateway JSON API。
    """
    reg = _get_registry(req)
    session = req.scope.get("session", {}) or {}
    account = _get_active_account(reg, session, req.query_params) if reg else None
    broker = None
    if reg and account:
        try:
            broker = reg.get(BrokerKind(account["kind"]), account["id"])
        except Exception:
            broker = None
    _, orders = _positions_orders_for_account(broker, account["kind"] if account else None)
    return HTMLResponse(_to_xml(TodayOrdersTable(orders)))


def _render_order_toast(message):
    return HTMLResponse(to_xml(_trade_toast(message)))


def _submitted_order_response(broker, kind, order):
    try:
        positions, orders = _positions_orders_for_account(broker, kind)
    except Exception:
        positions, orders = [], []
    side_text = "买入" if order.side == "BUY" else "卖出"
    return HTMLResponse(
        to_xml(
            Div(
                _trade_toast(f"{side_text}委托已提交: {order.asset}", level="success"),
                TodayOrdersTable(orders, hx_swap_oob=True),
                PositionTable(positions, hx_swap_oob=True),
            )
        )
    )


def _gateway_json_collection(base_url, path, api_key, timeout, sink):
    """Read one gateway JSON collection; protocol and transport failures return empty."""
    url = base_url.rstrip("/") + path
    req_obj = urllib.request.Request(
        url=url,
        method="GET",
        headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req_obj, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            content_type_lower = content_type.lower().split(";")[0].strip()
            if "html" in content_type_lower:
                logger.warning(
                    f"通过 gateway 拉取 {sink} 收到 htmx 响应（违反 spec 12 协议契约）："
                    f"url={url} Content-Type={content_type!r}。回退到 empty。"
                )
                return []
            body = resp.read().decode("utf-8")
        if not body:
            return []
        data = json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logger.warning(f"通过 gateway JSON API 拉取 {sink} 失败: {e}")
        return []
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"通过 gateway JSON API 拉取 {sink} 解析失败: {e}")
        return []
    except Exception as e:  # noqa: BLE001  (defensive: 任何 IO 错误都不破页面)
        logger.warning(f"通过 gateway JSON API 拉取 {sink} 出现未预期异常: {e}")
        return []
    if not isinstance(data, list):
        return []
    return data


def _trade_capital(broker):
    """Read account balances without allowing a failed gateway to break the page."""
    total = cash = market_value = principal = 0
    if broker:
        # Issue #29 复盘：每条 gateway 调用都包 try/except，
        # 避免网关 500 把整页渲染炸掉、留下空表让人摸不着头脑。
        # 资产/持仓/委托里任何一条失败都不应影响其它两条的展示。
        try:
            if hasattr(broker, "asset") and broker.asset:
                total = broker.asset.total
                cash = broker.asset.cash
                market_value = broker.asset.market_value
                principal = broker.asset.principal
            elif hasattr(broker, "total_assets"):
                # SimulationBroker 等没有 asset 属性
                total = broker.total_assets
                cash = broker.cash if hasattr(broker, "cash") else 0
                market_value = total - cash
                principal = getattr(broker, "principal", 0)
        except Exception as e:
            logger.warning(f"获取资产信息失败: {e}")
    return {"total": total, "cash": cash, "market_value": market_value, "principal": principal}
