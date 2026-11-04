"""交易页闪电单组件与接口。

本模块负责闪电单列表的渲染，以及创建、编辑、删除闪电买入单等交互。
"""

from __future__ import annotations

import re
from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
    Span,
    ft_hx,
    to_xml,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
)
from starlette.responses import HTMLResponse

from quantide.config.features import supports_live_trading
from quantide.core.enums import BrokerKind
from quantide.core.market_time import market_today
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import stock_list
from quantide.service.market_data_hub import market_data_hub
from quantide.service.reference_prices import historical_reference, positive_price
from quantide.service.trade_lightning import (
    TradeLightningEntry,
    add_trade_lightning_entry,
    clear_trade_lightning_entries,
    get_trade_lightning_entry,
    list_trade_lightning_entries,
    remove_trade_lightning_entry,
    update_trade_lightning_entry,
)
from quantide.web.components.asset_search import AssetSearchResults
from quantide.web.components.lightning_forms import (
    _clear_modal as _clear_modal,
)
from quantide.web.components.lightning_forms import (
    _close_circle_icon as _close_circle_icon,
)
from quantide.web.components.lightning_forms import (
    _close_modal_button as _close_modal_button,
)
from quantide.web.components.lightning_forms import (
    _create_modal as _create_modal,
)
from quantide.web.components.lightning_forms import (
    _delete_modal as _delete_modal,
)
from quantide.web.components.lightning_forms import (
    _detail_row as _detail_row,
)
from quantide.web.components.lightning_forms import (
    _dialog_modal as _dialog_modal,
)
from quantide.web.components.lightning_forms import (
    _edit_modal as _edit_modal,
)
from quantide.web.components.lightning_forms import (
    _entry_display_name as _entry_display_name,
)
from quantide.web.components.lightning_forms import (
    _lightning_asset_search_script as _lightning_asset_search_script,
)
from quantide.web.components.lightning_forms import (
    _minus_circle_icon as _minus_circle_icon,
)
from quantide.web.components.lightning_forms import (
    _modal_amount_input as _modal_amount_input,
)
from quantide.web.components.lightning_forms import (
    _modal_field_row as _modal_field_row,
)
from quantide.web.components.lightning_forms import (
    _modal_price_ref_select as _modal_price_ref_select,
)
from quantide.web.components.lightning_forms import (
    _modal_stock_input as _modal_stock_input,
)
from quantide.web.components.lightning_forms import (
    _pencil_icon as _pencil_icon,
)
from quantide.web.components.lightning_forms import (
    _plus_circle_icon as _plus_circle_icon,
)
from quantide.web.components.lightning_forms import (
    _search_icon as _search_icon,
)
from quantide.web.components.lightning_forms import (
    _upsert_modal as _upsert_modal,
)

# 现价+百分比 = 实际解析时按 ``current * (1 + pct)`` 计算。
from quantide.web.components.lightning_values import (
    PRICE_REFERENCE_CURRENT_PREMIUMS as PRICE_REFERENCE_CURRENT_PREMIUMS,
)
from quantide.web.components.lightning_values import (
    PRICE_REFERENCE_LABELS as PRICE_REFERENCE_LABELS,
)
from quantide.web.components.lightning_values import (
    PRICE_REFERENCE_OPTIONS as PRICE_REFERENCE_OPTIONS,
)
from quantide.web.components.lightning_values import (
    _asset_profile as _asset_profile,
)
from quantide.web.components.lightning_values import (
    _asset_symbol as _asset_symbol,
)
from quantide.web.components.lightning_values import (
    _format_amount_wan as _format_amount_wan,
)
from quantide.web.components.lightning_values import (
    _is_valid_price_ref as _is_valid_price_ref,
)
from quantide.web.components.lightning_values import (
    _price_reference_label as _price_reference_label,
)
from quantide.web.components.trade_toast import TradeToast

ASSET_CODE_PATTERN = re.compile(r"(\d{6}\.(?:SZ|SH|BJ))", re.IGNORECASE)


def _render_response(*nodes: Any) -> HTMLResponse:
    """将多个节点拼成 HTMX 片段响应。"""
    return HTMLResponse("".join(to_xml(node) for node in nodes))


def _resolve_asset_input(asset_query: str) -> str | None:
    """将用户输入解析成唯一股票代码。"""
    normalized = asset_query.strip().upper()
    if not normalized:
        return None
    code_match = ASSET_CODE_PATTERN.search(normalized)
    if code_match:
        normalized = code_match.group(1).upper()

    try:
        stock_list.get_name(normalized)
        return normalized
    except Exception:
        pass

    try:
        matches = stock_list.fuzzy_search(asset_query, id_only=True)
    except Exception:
        return None
    return matches[0] if len(matches) == 1 else None


def _parse_amount_wan(raw_value: str) -> float | None:
    """解析万元金额输入。"""
    text = raw_value.strip()
    if not text:
        return None
    try:
        amount_wan = float(text)
    except ValueError:
        return None
    return amount_wan if amount_wan > 0 else None


def _reference_price_panel() -> Any:
    """渲染参考价格按钮区。"""
    return Div(
        *[
            Button(
                Div(label, cls="text-[11px] text-gray-500 dark:text-gray-400 mb-1"),
                Div(
                    "",
                    cls="text-xs font-medium text-gray-700 dark:text-gray-300 min-h-4",
                    id=f"ref-{key}",
                ),
                type="button",
                cls=(
                    "reference-price-btn bg-gray-50 rounded-md py-1.5 px-1 "
                    "text-center flex flex-col items-center justify-center gap-1 flex-1 min-w-0 "
                    "disabled:opacity-40 disabled:cursor-not-allowed"
                ),
                data_ref_key=key,
                disabled=True,
            )
            for label, key in [
                ("昨收", "close"),
                ("MA5", "ma5"),
                ("MA10", "ma10"),
                ("MA20", "ma20"),
                ("MA30", "ma30"),
                ("MA60", "ma60"),
                ("现价", "current"),
            ]
        ],
        cls="flex gap-1 mb-2",
        id="reference-price-panel",
    )


def TradeReferencePanel() -> Any:
    """渲染交易页参考价格区，与闪电单控件保持独立。"""
    return _reference_price_panel()


def _header_icon_button(icon: Any, *, title: str, button_id: str, hx_get: str) -> Any:
    """渲染表头的纯图标按钮。"""
    return ft_hx(
        "button",
        icon,
        type="button",
        title=title,
        hx_get=hx_get,
        hx_target="#trade-lightning-modal-container",
        cls=(
            "inline-flex h-5 w-5 items-center justify-center bg-transparent p-0 text-gray-600 "
            "outline-none ring-0 transition-colors hover:text-gray-900 dark:text-gray-200 "
            "dark:hover:text-white"
        ),
        style="background:none;border:none;box-shadow:none;",
        id=button_id,
    )


def _empty_lightning_state() -> Any:
    """渲染闪电单空态。"""
    return Div(
        "尚未添加闪电单股票",
        cls="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400",
    )


def _lightning_row(portfolio_id: str, entry: TradeLightningEntry) -> Any:
    """渲染单个闪电单条目。"""
    name, _ = _asset_profile(entry.asset)
    label = _price_reference_label(entry.price_ref)
    if entry.cached_price > 0 and entry.price_ref != "current":
        summary = f"{_format_amount_wan(entry.amount_wan)} · {label}（{entry.cached_price:.2f}）"
    else:
        summary = f"{_format_amount_wan(entry.amount_wan)} · {label}"
    return Div(
        Span(
            _asset_symbol(entry.asset),
            cls="text-xs font-bold text-gray-900 dark:text-white w-20",
        ),
        Div(
            Span(name, cls="text-xs text-gray-600 dark:text-gray-400"),
            cls="flex items-center min-w-0",
        ),
        Span(
            summary,
            cls="text-[11px] text-gray-400 dark:text-gray-500 mr-2 truncate max-w-[120px]",
            title=summary,
        ),
        Div(
            Button(
                _pencil_icon(),
                type="button",
                title="修改闪电单",
                hx_get=f"/trade/lightning/{portfolio_id}/{entry.asset}/edit-modal",
                hx_target="#trade-lightning-modal-container",
                cls=(
                    "inline-flex h-4 w-4 items-center justify-center bg-transparent "
                    "p-0 text-gray-500 hover:text-gray-700 dark:text-gray-300 "
                    "dark:hover:text-white"
                ),
                style="background:none;border:none;box-shadow:none;",
            ),
            Button(
                _minus_circle_icon(),
                type="button",
                title="删除闪电单",
                hx_get=f"/trade/lightning/{portfolio_id}/{entry.asset}/delete-modal",
                hx_target="#trade-lightning-modal-container",
                cls=(
                    "inline-flex h-4 w-4 items-center justify-center bg-transparent "
                    "p-0 text-gray-500 hover:text-red-600 dark:text-gray-300 "
                    "dark:hover:text-red-400"
                ),
                style="background:none;border:none;box-shadow:none;",
            ),
            cls="flex items-center gap-2 text-xs",
        ),
        cls=(
            "grid grid-cols-[80px_1fr_auto_auto] items-center py-2.5 px-4 border-b "
            "border-gray-100 dark:border-gray-700 last:border-b-0 even:bg-[#f9fafb] "
            "dark:even:bg-gray-700/50 cursor-pointer select-none"
        ),
        data_lightning_asset=entry.asset,
        title="双击立即按预置金额与价格提交买入委托",
        hx_post=f"/trade/lightning/{portfolio_id}/{entry.asset}/execute",
        hx_trigger="dblclick",
        hx_target="#trade-toast-slot",
        hx_swap="outerHTML",
    )


def render_trade_lightning_panel(
    portfolio_id: str,
    *,
    hx_swap_oob: bool = False,
    extra_fragments: tuple[Any, ...] = (),
) -> Any:
    """渲染闪电单列表面板。

    Args:
        portfolio_id: 交易账户 ID。
        hx_swap_oob: 是否以 OOB 方式替换面板。
        extra_fragments: 额外附加到返回结果中的片段。

    Returns:
        闪电单面板。
    """
    entries = list_trade_lightning_entries(portfolio_id)
    attrs: dict[str, Any] = {"id": "trade-lightning-panel"}
    if hx_swap_oob:
        attrs["hx_swap_oob"] = "outerHTML"
    return Div(
        Div(
            H3("闪电单", cls="text-base font-semibold text-gray-900 dark:text-white m-0"),
            Div(
                _header_icon_button(
                    _plus_circle_icon(),
                    title="新建闪电单",
                    button_id="lightning-create-button",
                    hx_get=f"/trade/lightning/{portfolio_id}/create-modal",
                ),
                _header_icon_button(
                    _minus_circle_icon(),
                    title="清空闪电单",
                    button_id="lightning-clear-button",
                    hx_get=f"/trade/lightning/{portfolio_id}/clear-modal",
                ),
                cls="flex gap-1 text-[80%]",
            ),
            cls="flex items-center justify-between bg-gray-100 px-4 py-2.5 rounded-t-lg",
        ),
        Div(
            *(
                [_empty_lightning_state()]
                if not entries
                else [_lightning_row(portfolio_id, entry) for entry in entries]
            ),
            cls="bg-white dark:bg-gray-800 rounded-b-lg",
            id="trade-lightning-list",
        ),
        *extra_fragments,
        **attrs,
    )


def TradeLightningSidebar(portfolio_id: str) -> Any:
    """渲染交易页右侧闪电单区域。"""
    return Div(
        render_trade_lightning_panel(portfolio_id),
        Div(id="trade-lightning-modal-container"),
        cls="flex-[0.95] space-y-0",
    )


def _panel_with_toast(
    portfolio_id: str,
    message: str,
    *,
    level: str = "error",
    hx_swap_oob: bool = False,
) -> Any:
    """同时返回面板与 toast 片段。"""
    return render_trade_lightning_panel(
        portfolio_id,
        hx_swap_oob=hx_swap_oob,
        extra_fragments=(_lightning_toast(message, level, hx_swap_oob=True),),
    )


async def trade_lightning_search(req):
    """搜索闪电买入单中的股票候选项。"""
    query = req.query_params.get("asset_query", "").strip()
    if not query:
        return HTMLResponse(to_xml(Div(id="lightning-asset-search-dropdown", cls="hidden")))

    try:
        result_df = stock_list.fuzzy_search(query, id_only=False)
    except Exception:
        return HTMLResponse(to_xml(Div(id="lightning-asset-search-dropdown", cls="hidden")))

    if result_df is None or len(result_df) == 0:
        return HTMLResponse(to_xml(Div(id="lightning-asset-search-dropdown", cls="hidden")))

    return AssetSearchResults(result_df, lightning=True)


async def trade_lightning_edit_modal(req):
    """返回编辑弹窗。"""
    portfolio_id = req.path_params["portfolio_id"]
    asset = req.path_params["asset"]
    entry = get_trade_lightning_entry(portfolio_id, asset)
    if entry is None:
        return _render_response(
            Div(id="trade-lightning-modal-container"),
            _lightning_toast("该闪电单条目不存在", hx_swap_oob=True),
        )
    return HTMLResponse(to_xml(_edit_modal(portfolio_id, entry)))


async def trade_lightning_delete_modal(req):
    """返回删除确认弹窗。"""
    portfolio_id = req.path_params["portfolio_id"]
    asset = req.path_params["asset"]
    entry = get_trade_lightning_entry(portfolio_id, asset)
    if entry is None:
        return _render_response(
            Div(id="trade-lightning-modal-container"),
            _lightning_toast("该闪电单条目不存在", hx_swap_oob=True),
        )
    return HTMLResponse(to_xml(_delete_modal(portfolio_id, entry)))


async def trade_lightning_create_modal(req):
    """返回新建弹窗。"""
    portfolio_id = req.path_params["portfolio_id"]
    return HTMLResponse(to_xml(_create_modal(portfolio_id)))


async def trade_lightning_create(req):
    """创建新的闪电单条目。"""
    portfolio_id = req.path_params["portfolio_id"]
    form = await req.form()
    asset_query = str(form.get("asset_query") or "").strip()
    amount_wan_raw = str(form.get("amount_wan") or "10").strip()
    price_ref = str(form.get("price_ref") or "current").strip()
    if not asset_query:
        return _lightning_create_error(
            portfolio_id,
            asset_query,
            amount_wan_raw,
            price_ref or "current",
            "请输入股票代码、拼音或者名称",
            "error",
        )
    asset = _resolve_asset_input(asset_query)
    if asset is None:
        return _lightning_create_error(
            portfolio_id,
            asset_query,
            amount_wan_raw,
            price_ref or "current",
            "未找到唯一匹配股票，请输入完整代码、拼音或名称",
            "error",
        )
    amount_wan = _parse_amount_wan(amount_wan_raw)
    if amount_wan is None:
        return _lightning_create_error(
            portfolio_id,
            asset_query,
            amount_wan_raw,
            price_ref or "current",
            "请输入有效的买入金额",
            "error",
        )
    if not _is_valid_price_ref(price_ref):
        return _lightning_create_error(
            portfolio_id, asset_query, amount_wan_raw, "current", "请选择有效的买入价格", "error"
        )

    _, created = add_trade_lightning_entry(portfolio_id, asset, amount_wan, price_ref)
    message = "已创建闪电买入单" if created else "该股票已存在于闪电买入单中"
    level = "success" if created else "error"
    if not created:
        return _lightning_create_error(
            portfolio_id, asset_query, amount_wan_raw, price_ref, message, level
        )
    return _render_response(
        Div(id="trade-lightning-modal-container"),
        _panel_with_toast(portfolio_id, message, level=level, hx_swap_oob=True),
    )


async def trade_lightning_clear_modal(req):
    """返回清空确认弹窗。"""
    portfolio_id = req.path_params["portfolio_id"]
    return HTMLResponse(to_xml(_clear_modal(portfolio_id)))


async def trade_lightning_clear(req):
    """清空当前账户下的全部闪电单。"""
    portfolio_id = req.path_params["portfolio_id"]
    removed_count = clear_trade_lightning_entries(portfolio_id)
    if removed_count == 0:
        return _render_response(
            Div(id="trade-lightning-modal-container"),
            _panel_with_toast(portfolio_id, "当前没有可清空的闪电买入单", hx_swap_oob=True),
        )
    return _render_response(
        Div(id="trade-lightning-modal-container"),
        _panel_with_toast(
            portfolio_id,
            f"已清空 {removed_count} 条闪电买入单",
            level="success",
            hx_swap_oob=True,
        ),
    )


async def trade_lightning_update(req):
    """更新闪电买入单。"""
    portfolio_id = req.path_params["portfolio_id"]
    asset = req.path_params["asset"]
    entry = get_trade_lightning_entry(portfolio_id, asset)
    if entry is None:
        return _render_response(
            Div(id="trade-lightning-modal-container"),
            _lightning_toast("该闪电买入单不存在", hx_swap_oob=True),
        )
    form = await req.form()
    amount_wan_raw = str(form.get("amount_wan") or f"{entry.amount_wan:g}").strip()
    price_ref = str(form.get("price_ref") or entry.price_ref).strip()
    amount_wan = _parse_amount_wan(amount_wan_raw)
    if amount_wan is None:
        return _render_response(
            _edit_modal(
                portfolio_id,
                entry,
                amount_wan=amount_wan_raw or f"{entry.amount_wan:g}",
                price_ref=price_ref,
            ),
            _lightning_toast("请输入有效的买入金额", hx_swap_oob=True),
        )
    if not _is_valid_price_ref(price_ref):
        return _render_response(
            _edit_modal(
                portfolio_id,
                entry,
                amount_wan=amount_wan_raw or f"{entry.amount_wan:g}",
                price_ref=entry.price_ref,
            ),
            _lightning_toast("请选择有效的买入价格", hx_swap_oob=True),
        )
    updated = update_trade_lightning_entry(portfolio_id, asset, amount_wan, price_ref)
    message = "闪电买入单已更新" if updated is not None else "该闪电买入单不存在"
    level = "success" if updated is not None else "error"
    return _render_response(
        Div(id="trade-lightning-modal-container"),
        _panel_with_toast(portfolio_id, message, level=level, hx_swap_oob=True),
    )


async def trade_lightning_delete(req):
    """删除闪电单条目。"""
    portfolio_id = req.path_params["portfolio_id"]
    asset = req.path_params["asset"]
    removed = remove_trade_lightning_entry(portfolio_id, asset)
    message = "已删除闪电买入单" if removed else "该闪电买入单不存在"
    level = "success" if removed else "error"
    return _render_response(
        Div(id="trade-lightning-modal-container"),
        _panel_with_toast(portfolio_id, message, level=level, hx_swap_oob=True),
    )


def _resolve_lightning_price(asset: str, price_ref: str) -> float:
    """Resolve execution references using live quotes and unadjusted daily bars."""
    if price_ref in PRICE_REFERENCE_CURRENT_PREMIUMS:
        current = _resolve_lightning_price(asset, "current")
        return round(current * (1 + PRICE_REFERENCE_CURRENT_PREMIUMS[price_ref]), 2)
    if price_ref == "current":
        quote = market_data_hub.get_quote(asset) if market_data_hub.is_running else None
        for key in ("price", "lastPrice", "close"):
            price = positive_price((quote or {}).get(key))
            if price:
                return price
        price_ref = "close"
    return historical_reference(daily_bars, asset, price_ref, end=market_today(), adjust=None)


def _resolve_lightning_broker(req, portfolio_id: str):
    """从 request scope 中拿到闪电单对应账号的 broker.

    Args:
        req: HTTP 请求。
        portfolio_id: 闪电单账户 ID。

    Returns:
        broker 实例，找不到时返回 ``None``。
    """
    reg = req.scope.get("registry")
    if reg is None:
        return None
    session = req.scope.get("session", {})
    active_kind = session.get("active_account_kind")
    active_id = session.get("active_account_id")
    if active_kind and active_id and active_id == portfolio_id:
        try:
            return reg.get(BrokerKind(active_kind), active_id)
        except Exception:
            return None
    try:
        kinds = (BrokerKind.SIMULATION,)
        if supports_live_trading():
            kinds = (BrokerKind.QMT, BrokerKind.SIMULATION)
        for kind in kinds:
            for info in reg.list_by_kind(kind):
                if info.get("id") == portfolio_id:
                    return reg.get(kind, portfolio_id)
    except Exception:
        return None
    return None


async def trade_lightning_execute(req):
    """双击闪电单：按预存的金额/价格立即提交买入委托（Issue #38）.

    Args:
        req: HTTP 请求，路径参数 ``portfolio_id`` 和 ``asset``。

    Returns:
        toast 片段响应，包含执行结果。
    """
    portfolio_id = req.path_params["portfolio_id"]
    asset = req.path_params["asset"]
    entry = get_trade_lightning_entry(portfolio_id, asset)
    if entry is None:
        return _render_response(
            _lightning_toast("该闪电买入单不存在", hx_swap_oob=True),
        )

    broker = _resolve_lightning_broker(req, portfolio_id)
    if broker is None:
        return _render_response(
            _lightning_toast("未找到可用的交易账号", hx_swap_oob=True),
        )

    # Issue #38 followup: 非 current 的 price_ref 一律用创建/更新时锁定的
    # cached_price，确保「看到的数 = 下单的数」。current 系列走实时行情。
    if entry.price_ref == "current":
        price = _resolve_lightning_price(asset, entry.price_ref)
    else:
        price = entry.cached_price
    if price <= 0:
        return _render_response(
            _lightning_toast(
                f"无法解析 {asset} 的价格参考 {_price_reference_label(entry.price_ref)}",
                hx_swap_oob=True,
            ),
        )

    try:
        if hasattr(broker, "buy_amount"):
            result = await broker.buy_amount(asset, entry.amount_wan * 10000, price)
        else:
            shares = int(entry.amount_wan * 10000 / price // 100 * 100)
            if shares <= 0:
                return _render_response(
                    _lightning_toast(
                        f"按当前价格 {price:.2f} 算出的可买股数为 0，请增加买入金额",
                        hx_swap_oob=True,
                    ),
                )
            result = await broker.buy(asset, shares, price)
    except Exception as e:
        return _render_response(
            _lightning_toast(f"闪电买入失败: {e}", hx_swap_oob=True),
        )

    if result is None or not getattr(result, "qt_oid", None):
        return _render_response(
            _lightning_toast("闪电买入未生成有效委托，请检查账户和价格", hx_swap_oob=True),
        )

    name, _ = _asset_profile(asset)
    label = name if name != asset else _asset_symbol(asset)
    return _render_response(
        _lightning_toast(
            f"闪电买入已提交: {label} {_format_amount_wan(entry.amount_wan)}",
            level="success",
            hx_swap_oob=True,
        ),
    )


def _lightning_create_error(
    portfolio_id, asset_query, amount_raw, price_ref, message, level="error"
):
    return _render_response(
        _create_modal(
            portfolio_id,
            asset_query=asset_query,
            amount_wan=amount_raw or "10",
            price_ref=price_ref,
        ),
        _lightning_toast(message, level=level, hx_swap_oob=True),
    )


def _lightning_toast(message, level="error", *, hx_swap_oob=False):
    return TradeToast(message, level, hx_swap_oob=hx_swap_oob, container=True)
