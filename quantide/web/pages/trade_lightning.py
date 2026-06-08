"""交易页闪电单组件与接口。

本模块负责闪电单列表的渲染，以及创建、编辑、删除闪电买入单等交互。
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from fasthtml.common import *
from monsterui.all import *
from starlette.responses import HTMLResponse

from quantide.config.branding import get_branding
from quantide.core.enums import BrokerKind
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.stocks import stock_list
from quantide.service.livequote import live_quote
from quantide.service.trade_lightning import (
    TradeLightningEntry,
    add_trade_lightning_entry,
    clear_trade_lightning_entries,
    get_trade_lightning_entry,
    list_trade_lightning_entries,
    remove_trade_lightning_entry,
    update_trade_lightning_entry,
)

PRICE_REFERENCE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("最新价", "current"),
    ("昨收价", "close"),
    ("5日均线", "ma5"),
    ("10日均线", "ma10"),
    ("20日均线", "ma20"),
    ("30日均线", "ma30"),
    ("60日均线", "ma60"),
)
PRICE_REFERENCE_LABELS = {key: label for label, key in PRICE_REFERENCE_OPTIONS}
ASSET_CODE_PATTERN = re.compile(r"(\d{6}\.(?:SZ|SH|BJ))", re.IGNORECASE)


def _lightning_toast(message: str, level: str = "error", *, hx_swap_oob: bool = False):
    """构建交易页 toast 容器。

    Args:
        message: 提示文案。
        level: 提示级别。
        hx_swap_oob: 是否作为 OOB 片段返回。

    Returns:
        toast 容器节点。
    """
    tone_classes = {
        "error": "border-red-200 bg-red-50 text-red-700",
        "success": "border-green-200 bg-green-50 text-green-700",
    }
    dismiss_js = (
        "const slot=document.getElementById('trade-toast-slot');"
        "if(slot){slot.innerHTML='';delete slot.dataset.toastToken;}"
    )
    attrs: dict[str, Any] = {
        "id": "trade-toast-slot",
        "cls": "pointer-events-none absolute inset-x-6 top-0 z-50",
        "aria_live": "polite",
    }
    if hx_swap_oob:
        attrs["hx_swap_oob"] = "outerHTML"
    return Div(
        Div(
            Span(message, cls="pr-4"),
            Button(
                "x",
                type="button",
                cls=(
                    "ml-auto text-base font-semibold leading-none opacity-70 hover:opacity-100 "
                    "pointer-events-auto cursor-pointer"
                ),
                aria_label="关闭提示",
                onclick=dismiss_js,
            ),
            cls=(
                "pointer-events-auto flex min-h-8 items-start rounded-xl border px-4 py-3 text-sm "
                "font-medium shadow-sm " + tone_classes.get(level, tone_classes["error"])
            ),
            role="alert" if level == "error" else "status",
        ),
        Script(
            """
            (() => {
                const slot = document.getElementById('trade-toast-slot');
                if (!slot) {
                    return;
                }
                const token = String(Date.now());
                slot.dataset.toastToken = token;
                window.setTimeout(function() {
                    const currentSlot = document.getElementById('trade-toast-slot');
                    if (currentSlot && currentSlot.dataset.toastToken === token) {
                        currentSlot.innerHTML = '';
                        delete currentSlot.dataset.toastToken;
                    }
                }, 7000);
            })();
            """
        ),
        **attrs,
    )


def _render_response(*nodes: Any) -> HTMLResponse:
    """将多个节点拼成 HTMX 片段响应。"""
    return HTMLResponse("".join(to_xml(node) for node in nodes))


def _asset_symbol(asset: str) -> str:
    """返回不带市场后缀的股票代码。"""
    return asset.split(".")[0]


def _asset_profile(asset: str) -> tuple[str, str]:
    """解析股票名称与拼音。

    Args:
        asset: 股票代码。

    Returns:
        ``(name, pinyin)``。
    """
    try:
        return stock_list.get_name(asset), stock_list.get_pinyin(asset)
    except Exception:
        return asset, ""


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


def _format_amount_wan(amount_wan: float) -> str:
    """格式化万元金额显示。"""
    return f"{amount_wan:g}万"


def _price_reference_label(price_ref: str) -> str:
    """返回价格参考的展示名称。"""
    return PRICE_REFERENCE_LABELS.get(price_ref, PRICE_REFERENCE_LABELS["current"])


def _is_valid_price_ref(price_ref: str) -> bool:
    """判断价格参考键是否合法。"""
    return price_ref in PRICE_REFERENCE_LABELS


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
                    "reference-price-btn bg-[#f9fafb] dark:bg-gray-700 rounded-md py-1.5 px-1 "
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


def _plus_circle_icon() -> Any:
    return NotStr(
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"></circle>'
        '<line x1="12" y1="8" x2="12" y2="16"></line>'
        '<line x1="8" y1="12" x2="16" y2="12"></line>'
        "</svg>"
    )


def _minus_circle_icon() -> Any:
    return NotStr(
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"></circle>'
        '<line x1="8" y1="12" x2="16" y2="12"></line>'
        "</svg>"
    )


def _pencil_icon() -> Any:
    return NotStr(
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 20h9"></path>'
        '<path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4Z"></path>'
        "</svg>"
    )


def _search_icon() -> Any:
    return NotStr(
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="11" cy="11" r="7"></circle>'
        '<path d="m20 20-3.5-3.5"></path>'
        "</svg>"
    )


def _close_circle_icon() -> Any:
    return NotStr(
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"></circle>'
        '<path d="m9 9 6 6"></path>'
        '<path d="m15 9-6 6"></path>'
        "</svg>"
    )


def _lightning_asset_search_script() -> Any:
    """渲染创建弹窗股票搜索交互脚本。"""
    return Script(
        """
        (() => {
            if (window.__lightningAssetSearchBound) {
                return;
            }
            window.__lightningAssetSearchBound = true;

            function getInput() {
                return document.getElementById('lightning-asset-query');
            }

            function getDropdown() {
                return document.getElementById('lightning-asset-search-dropdown');
            }

            function hideDropdown() {
                const dropdown = getDropdown();
                if (!dropdown) {
                    return;
                }
                dropdown.innerHTML = '';
                dropdown.className = 'hidden';
            }

            document.body.addEventListener('click', function(evt) {
                const item = evt.target.closest('.lightning-asset-search-item');
                if (item) {
                    const input = getInput();
                    if (input) {
                        input.value = item.dataset.display || item.dataset.asset || '';
                    }
                    hideDropdown();
                    return;
                }

                if (!evt.target.closest('#lightning-asset-search-wrapper')) {
                    hideDropdown();
                }
            });

            document.body.addEventListener('keydown', function(evt) {
                const input = getInput();
                if (!input || evt.target !== input || evt.key !== 'Enter') {
                    return;
                }
                const firstItem = document.querySelector('.lightning-asset-search-item');
                if (!firstItem) {
                    return;
                }
                evt.preventDefault();
                input.value = firstItem.dataset.display || firstItem.dataset.asset || '';
                hideDropdown();
            });
        })();
        """
    )


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
    summary = (
        f"{_format_amount_wan(entry.amount_wan)} · "
        f"{_price_reference_label(entry.price_ref)}"
    )
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
                    "inline-flex h-4 w-4 items-center justify-center bg-transparent p-0 text-gray-500 "
                    "hover:text-gray-700 dark:text-gray-300 dark:hover:text-white"
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
                    "inline-flex h-4 w-4 items-center justify-center bg-transparent p-0 text-gray-500 "
                    "hover:text-red-600 dark:text-gray-300 dark:hover:text-red-400"
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
            cls="flex items-center justify-between bg-[#e0e0e0] dark:bg-gray-600 px-4 py-2.5 rounded-t-lg",
        ),
        Div(
            *([_empty_lightning_state()] if not entries else [_lightning_row(portfolio_id, entry) for entry in entries]),
            cls="bg-white dark:bg-gray-800 rounded-b-lg",
            id="trade-lightning-list",
        ),
        *extra_fragments,
        **attrs,
    )


def TradeLightningSidebar(portfolio_id: str) -> Any:
    """渲染交易页右侧闪电单区域。"""
    return Div(
        _reference_price_panel(),
        render_trade_lightning_panel(portfolio_id),
        Div(id="trade-lightning-modal-container"),
        cls="flex-[0.95] space-y-0",
    )


def _close_modal_button() -> str:
    return "document.getElementById('trade-lightning-modal-container').innerHTML='';"


def _dialog_modal(title: str, body: Any, *, modal_id: str) -> Any:
    """渲染带红色标题栏的闪电单弹窗。"""
    branding = get_branding()
    return Div(
        Div(
            cls="fixed inset-0 bg-black/50 transition-opacity",
            onclick=_close_modal_button(),
        ),
        Div(
            Div(
                Div(
                    Div(
                        Div(
                            branding.product_name,
                            cls="whitespace-pre-line text-left text-sm font-semibold leading-4 text-white",
                        ),
                        H3(
                            title,
                            cls="m-0 text-center text-[24px] font-medium tracking-wide text-white",
                        ),
                        Button(
                            _close_circle_icon(),
                            type="button",
                            title="关闭弹窗",
                            aria_label="关闭弹窗",
                            onclick=_close_modal_button(),
                            cls=(
                                "inline-flex h-8 w-8 items-center justify-center bg-transparent p-0 "
                                "text-white hover:opacity-90"
                            ),
                            style="background:none;border:none;box-shadow:none;",
                        ),
                        cls="grid grid-cols-[auto_1fr_auto] items-center gap-4 bg-[#d00000] px-5 py-4",
                    ),
                    Div(body, cls="bg-[#f7f7f7]"),
                    cls=(
                        "inline-block w-full max-w-[640px] overflow-hidden rounded-xl bg-white "
                        "text-left align-middle shadow-2xl"
                    ),
                ),
                cls="flex min-h-full items-center justify-center p-4 text-center",
            ),
            cls="fixed inset-0 z-10 overflow-y-auto",
        ),
        id=modal_id,
    )


def _modal_field_row(label: str, control: Any) -> Any:
    """渲染设计稿风格的表单行。"""
    return Div(
        Div(
            label,
            cls=(
                "flex items-center justify-start bg-[#d9d9d9] px-4 text-left text-[15px] "
                "font-medium text-gray-800"
            ),
        ),
        control,
        cls="grid grid-cols-[110px_1fr] overflow-hidden rounded-md border border-[#cfcfcf] bg-white",
    )


def _modal_stock_input(asset_query: str, *, readonly: bool = False) -> Any:
    """渲染股票输入框。"""
    input_attrs: dict[str, Any] = {
        "type": "text",
        "value": asset_query,
        "placeholder": "请输入股票代码、拼音或者名称",
        "id": "lightning-asset-query",
        "cls": (
            "w-full border-0 bg-transparent px-4 py-3 pr-11 text-base text-gray-900 "
            "placeholder:text-gray-500 focus:outline-none"
        ),
    }
    if readonly:
        input_attrs["readonly"] = True
        search_dropdown = ""
    else:
        input_attrs["name"] = "asset_query"
        input_attrs["autocomplete"] = "off"
        input_attrs["hx_get"] = "/trade/lightning/search"
        input_attrs["hx_target"] = "#lightning-asset-search-dropdown"
        input_attrs["hx_trigger"] = "focus, input changed delay:200ms"
        search_dropdown = Div(id="lightning-asset-search-dropdown", cls="hidden")
    return Div(
        Div(
            Input(**input_attrs),
            Span(
                _search_icon(),
                cls="pointer-events-none absolute inset-y-0 right-3 flex items-center text-gray-400",
            ),
            cls="relative bg-white",
        ),
        search_dropdown,
        id="lightning-asset-search-wrapper",
        cls="relative",
    )


def _modal_amount_input(amount_wan: str) -> Any:
    """渲染金额输入框。"""
    return Div(
        Input(
            type="number",
            name="amount_wan",
            value=amount_wan,
            min="0.1",
            step="0.1",
            placeholder="10",
            cls=(
                "w-full border-0 bg-transparent px-4 py-3 pr-10 text-right text-base text-gray-900 "
                "focus:outline-none"
            ),
        ),
        Span(
            "万",
            cls="pointer-events-none absolute inset-y-0 right-4 flex items-center text-base text-gray-700",
        ),
        cls="relative bg-white",
    )


def _modal_price_ref_select(price_ref: str) -> Any:
    """渲染价格参考下拉框。"""
    options = [
        ft_hx(
            "option",
            label,
            value=key,
            selected="selected" if key == price_ref else None,
        )
        for label, key in PRICE_REFERENCE_OPTIONS
    ]
    return ft_hx(
        "select",
        *options,
        name="price_ref",
        cls=(
            "w-full border-0 bg-white px-4 py-3 text-base text-gray-900 focus:outline-none "
            "focus:ring-0"
        ),
    )


def _detail_row(label: str, value: str) -> Any:
    """渲染确认弹窗中的信息行。"""
    return Div(
        Span(label, cls="text-[15px] text-gray-500"),
        Span(value, cls="text-[15px] font-medium text-gray-900"),
        cls="grid grid-cols-[96px_1fr] gap-4",
    )


def _entry_display_name(entry: TradeLightningEntry) -> str:
    """返回闪电单的展示股票名。"""
    name, _ = _asset_profile(entry.asset)
    symbol = _asset_symbol(entry.asset)
    return f"{name}（{symbol}）" if name != entry.asset else symbol


def _upsert_modal(
    portfolio_id: str,
    *,
    modal_id: str,
    title: str,
    submit_label: str,
    submit_path: str,
    asset_query: str,
    amount_wan: str,
    price_ref: str,
    readonly_asset: bool = False,
    intro: str,
) -> Any:
    """渲染创建或编辑闪电买入单弹窗。"""
    form = Form(
        Div(
            P(
                intro,
                cls="text-left text-sm leading-7 text-gray-500",
            ),
            Div(
                _modal_field_row(
                    "股票代码",
                    _modal_stock_input(asset_query, readonly=readonly_asset),
                ),
                _modal_field_row("买入金额", _modal_amount_input(amount_wan)),
                _modal_field_row("买入价格", _modal_price_ref_select(price_ref)),
                cls="space-y-5",
            ),
            Div(cls="border-t border-[#e5e5e5]"),
            Div(
                Button(
                    submit_label,
                    type="submit",
                    cls=(
                        "inline-flex min-w-[264px] items-center justify-center rounded-md border "
                        "border-[#c5c5c5] bg-white px-6 py-3 text-[15px] font-medium text-gray-900 "
                        "transition-colors hover:bg-gray-50"
                    ),
                ),
                cls="flex justify-center pt-2",
            ),
            _lightning_asset_search_script(),
            cls="space-y-8 px-8 py-8",
        ),
        hx_post=submit_path,
        hx_target="#trade-lightning-modal-container",
        cls="min-h-[404px]",
    )
    body = Div(form, cls="bg-[#f7f7f7]")
    return _dialog_modal(title, body, modal_id=modal_id)


def _edit_modal(
    portfolio_id: str,
    entry: TradeLightningEntry,
    *,
    amount_wan: str | None = None,
    price_ref: str | None = None,
) -> Any:
    """渲染编辑闪电买入单弹窗。"""
    return _upsert_modal(
        portfolio_id,
        modal_id="trade-lightning-edit-modal",
        title="修改闪电买入单",
        submit_label="确定",
        submit_path=f"/trade/lightning/{portfolio_id}/{entry.asset}/update",
        asset_query=_entry_display_name(entry),
        amount_wan=amount_wan or f"{entry.amount_wan:g}",
        price_ref=price_ref or entry.price_ref,
        readonly_asset=True,
        intro="请调整预先设置的买入金额和价格参考，保存后可直接用于闪电买入。",
    )


def _create_modal(
    portfolio_id: str,
    *,
    asset_query: str = "",
    amount_wan: str = "10",
    price_ref: str = "current",
) -> Any:
    """渲染创建闪电买入单弹窗。"""
    return _upsert_modal(
        portfolio_id,
        modal_id="trade-lightning-create-modal",
        title="创建闪电买入单",
        submit_label="确定",
        submit_path=f"/trade/lightning/{portfolio_id}/create",
        asset_query=asset_query,
        amount_wan=amount_wan,
        price_ref=price_ref,
        intro="闪电单是一种预先确定买入标的、金额和价格的预埋单。执行时可双击买入，无须再走填单流程。",
    )


def _delete_modal(portfolio_id: str, entry: TradeLightningEntry) -> Any:
    """渲染删除确认弹窗。"""
    body = Div(
        Div(
            P("确定删除以下闪电买入单吗？", cls="text-center text-[15px] text-gray-500"),
            Div(
                _detail_row("股票名", _entry_display_name(entry)),
                _detail_row("买入金额", _format_amount_wan(entry.amount_wan)),
                _detail_row("买入价格", _price_reference_label(entry.price_ref)),
                cls="mx-auto max-w-[280px] space-y-4",
            ),
            cls="space-y-8 px-8 py-12",
        ),
        Div(cls="border-t border-[#e5e5e5]"),
        Div(
            Button(
                "确定",
                type="button",
                hx_post=f"/trade/lightning/{portfolio_id}/{entry.asset}/delete",
                hx_target="#trade-lightning-modal-container",
                cls=(
                    "inline-flex min-w-[180px] items-center justify-center rounded-md border "
                    "border-[#c5c5c5] bg-white px-6 py-3 text-[15px] font-medium text-gray-900 "
                    "transition-colors hover:bg-gray-50"
                ),
            ),
            cls="flex justify-center px-8 py-8",
        ),
        cls="bg-[#f7f7f7]",
    )
    return _dialog_modal("删除闪电买入单", body, modal_id="trade-lightning-delete-modal")


def _clear_modal(portfolio_id: str) -> Any:
    """渲染清空确认弹窗。"""
    body = Div(
        Div(
            P(
                "确定清空当前账户下的全部闪电买入单吗？",
                cls="px-8 py-12 text-center text-[15px] text-gray-500",
            ),
        ),
        Div(cls="border-t border-[#e5e5e5]"),
        Div(
            Button(
                "确定",
                type="button",
                hx_post=f"/trade/lightning/{portfolio_id}/clear",
                hx_target="#trade-lightning-modal-container",
                cls=(
                    "inline-flex min-w-[180px] items-center justify-center rounded-md border "
                    "border-[#c5c5c5] bg-white px-6 py-3 text-[15px] font-medium text-gray-900 "
                    "transition-colors hover:bg-gray-50"
                ),
            ),
            cls="flex justify-center px-8 py-8",
        ),
        cls="bg-[#f7f7f7]",
    )
    return _dialog_modal("清空闪电买入单", body, modal_id="trade-lightning-clear-modal")


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
        return HTMLResponse(
            to_xml(
                Div(
                    Div("无匹配结果", cls="px-3 py-2 text-sm text-gray-500"),
                    id="lightning-asset-search-dropdown",
                    cls=(
                        "absolute z-50 mt-1 w-full rounded-lg border border-gray-300 bg-white "
                        "shadow-lg max-h-48 overflow-y-auto"
                    ),
                )
            )
        )

    items = []
    for _, row in result_df.iterrows():
        asset = row.get("asset", "")
        name = row.get("name", "")
        pinyin = row.get("pinyin", "")
        display = f"{name}（{asset}）"
        items.append(
            Div(
                Div(name, cls="text-sm font-medium text-gray-900"),
                Div(f"{asset} · {pinyin}", cls="text-xs text-gray-500"),
                cls="lightning-asset-search-item cursor-pointer px-3 py-2 hover:bg-gray-100",
                data_asset=asset,
                data_display=display,
                tabindex="0",
                role="button",
            )
        )

    return HTMLResponse(
        to_xml(
            Div(
                *items,
                id="lightning-asset-search-dropdown",
                cls=(
                    "absolute z-50 mt-1 w-full rounded-lg border border-gray-300 bg-white "
                    "shadow-lg max-h-48 overflow-y-auto"
                ),
            )
        )
    )


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
        return _render_response(
            _create_modal(
                portfolio_id,
                asset_query=asset_query,
                amount_wan=amount_wan_raw or "10",
                price_ref=price_ref or "current",
            ),
            _lightning_toast("请输入股票代码、拼音或者名称", hx_swap_oob=True),
        )
    asset = _resolve_asset_input(asset_query)
    if asset is None:
        return _render_response(
            _create_modal(
                portfolio_id,
                asset_query=asset_query,
                amount_wan=amount_wan_raw or "10",
                price_ref=price_ref or "current",
            ),
            _lightning_toast("未找到唯一匹配股票，请输入完整代码、拼音或名称", hx_swap_oob=True),
        )
    amount_wan = _parse_amount_wan(amount_wan_raw)
    if amount_wan is None:
        return _render_response(
            _create_modal(
                portfolio_id,
                asset_query=asset_query,
                amount_wan=amount_wan_raw or "10",
                price_ref=price_ref or "current",
            ),
            _lightning_toast("请输入有效的买入金额", hx_swap_oob=True),
        )
    if not _is_valid_price_ref(price_ref):
        return _render_response(
            _create_modal(
                portfolio_id,
                asset_query=asset_query,
                amount_wan=amount_wan_raw or "10",
                price_ref="current",
            ),
            _lightning_toast("请选择有效的买入价格", hx_swap_oob=True),
        )

    _, created = add_trade_lightning_entry(portfolio_id, asset, amount_wan, price_ref)
    message = "已创建闪电买入单" if created else "该股票已存在于闪电买入单中"
    level = "success" if created else "error"
    if not created:
        return _render_response(
            _create_modal(
                portfolio_id,
                asset_query=asset_query,
                amount_wan=amount_wan_raw or "10",
                price_ref=price_ref,
            ),
            _lightning_toast(message, level=level, hx_swap_oob=True),
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
    """把闪电单的 price_ref 解析为具体价格.

    复用了 trade_main 的语义：``current`` 走实时行情，其余走本地日线。
    Args:
        asset: 股票代码。
        price_ref: 价格参考 key（``current`` / ``close`` / ``ma5`` 等）。

    Returns:
        解析到的价格。``current`` 拿不到时回退到昨收，``close`` 拿不到时回退 0。
    """
    if price_ref == "current":
        quote = live_quote.get_quote(asset) if live_quote.is_running else None
        if quote:
            for key in ("price", "lastPrice", "close"):
                try:
                    value = float(quote.get(key) or 0)
                except (TypeError, ValueError):
                    value = 0.0
                if value > 0:
                    return value
        return _resolve_lightning_price(asset, "close")

    if price_ref == "close":
        try:
            bars = daily_bars.get_bars(
                1, end=datetime.date.today(), assets=[asset], eager_mode=True, adjust=None
            )
        except Exception:
            return 0.0
        if bars.is_empty():
            return 0.0
        try:
            close_value = float(bars.sort("date").row(-1, named=True).get("close") or 0)
        except Exception:
            return 0.0
        return close_value if close_value > 0 else 0.0

    if price_ref.startswith("ma"):
        try:
            period = int(price_ref[2:])
        except ValueError:
            return 0.0
        try:
            bars = daily_bars.get_bars(
                period, end=datetime.date.today(), assets=[asset], eager_mode=True, adjust=None
            )
        except Exception:
            return 0.0
        if bars.is_empty() or len(bars) < period:
            return 0.0
        closes = [float(value) for value in bars.sort("date").get_column("close").to_list()]
        if len(closes) < period:
            return 0.0
        return sum(closes[-period:]) / period

    return 0.0


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
        for kind in (BrokerKind.QMT, BrokerKind.SIMULATION):
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

    price = _resolve_lightning_price(asset, entry.price_ref)
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
