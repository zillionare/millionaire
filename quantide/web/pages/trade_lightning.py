"""交易页闪电单组件与接口。

本模块负责闪电单列表的渲染，以及新增、编辑标签和删除等交互。
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import *
from monsterui.all import *
from starlette.responses import HTMLResponse

from quantide.data.models.stocks import stock_list
from quantide.service.trade_lightning import (
    TradeLightningEntry,
    add_trade_lightning_entry,
    get_trade_lightning_entry,
    list_trade_lightning_entries,
    remove_trade_lightning_entry,
    update_trade_lightning_tags,
)


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
                cls="ml-auto text-base font-semibold leading-none opacity-70 hover:opacity-100",
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


def _icon_svg(path: str, *, size: int = 14, extra_cls: str = "") -> Any:
    """生成统一尺寸的 SVG 图标。"""
    return NotStr(
        f'<svg class="{extra_cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round"><path d="{path}"></path></svg>'
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


def _empty_lightning_state() -> Any:
    """渲染闪电单空态。"""
    return Div(
        "尚未添加闪电单股票",
        cls="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400",
    )


def _lightning_row(portfolio_id: str, entry: TradeLightningEntry) -> Any:
    """渲染单个闪电单条目。"""
    name, _ = _asset_profile(entry.asset)
    tags = entry.tags.strip()
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
            tags,
            cls="text-[11px] text-gray-400 dark:text-gray-500 mr-2 truncate max-w-[120px]",
        )
        if tags
        else Span("", cls="text-[11px] mr-2"),
        Div(
            Button(
                _pencil_icon(),
                type="button",
                title="修改标签",
                hx_get=f"/trade/lightning/{portfolio_id}/{entry.asset}/edit-modal",
                hx_target="#trade-lightning-modal-container",
                cls=(
                    "inline-flex h-6 w-6 items-center justify-center rounded text-gray-500 "
                    "hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-700"
                ),
            ),
            Button(
                _minus_circle_icon(),
                type="button",
                title="删除闪电单",
                hx_get=f"/trade/lightning/{portfolio_id}/{entry.asset}/delete-modal",
                hx_target="#trade-lightning-modal-container",
                cls=(
                    "inline-flex h-6 w-6 items-center justify-center rounded text-gray-500 "
                    "hover:bg-gray-100 hover:text-red-600 dark:hover:bg-gray-700"
                ),
            ),
            cls="flex items-center gap-1 text-xs",
        ),
        cls=(
            "grid grid-cols-[80px_1fr_auto_auto] items-center py-2.5 px-4 border-b "
            "border-gray-100 dark:border-gray-700 last:border-b-0 even:bg-[#f9fafb] "
            "dark:even:bg-gray-700/50"
        ),
        data_lightning_asset=entry.asset,
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
                Button(
                    _plus_circle_icon(),
                    type="button",
                    title="添加当前股票到闪电单",
                    hx_post=f"/trade/lightning/{portfolio_id}/add",
                    hx_include="#trade-form",
                    hx_target="#trade-lightning-panel",
                    hx_swap="outerHTML",
                    cls=(
                        "inline-flex h-5 w-5 items-center justify-center rounded text-gray-500 "
                        "hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-700"
                    ),
                    id="lightning-add-button",
                ),
                Button(
                    _minus_circle_icon(),
                    type="button",
                    title="从闪电单移除当前股票",
                    hx_post=f"/trade/lightning/{portfolio_id}/remove-current",
                    hx_include="#trade-form",
                    hx_target="#trade-lightning-panel",
                    hx_swap="outerHTML",
                    cls=(
                        "inline-flex h-5 w-5 items-center justify-center rounded text-gray-500 "
                        "hover:bg-gray-100 hover:text-red-600 dark:hover:bg-gray-700"
                    ),
                    id="lightning-remove-button",
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


def _dialog_modal(title: str, body: Any, footer: Any, *, modal_id: str) -> Any:
    """渲染闪电单弹窗。"""
    return Div(
        Div(cls="fixed inset-0 bg-black/50 transition-opacity"),
        Div(
            Div(
                Div(
                    Div(H3(title, cls="text-lg font-medium leading-6 text-gray-900"), cls="px-6 py-5 border-b border-gray-200"),
                    Div(body, cls="px-6 py-5"),
                    Div(footer, cls="px-6 py-4 border-t border-gray-100"),
                    cls="inline-block w-full max-w-md overflow-hidden rounded-lg bg-white text-left align-middle shadow-xl",
                ),
                cls="flex min-h-full items-center justify-center p-4 text-center",
            ),
            cls="fixed inset-0 z-10 overflow-y-auto",
        ),
        id=modal_id,
    )


def _edit_modal(portfolio_id: str, entry: TradeLightningEntry) -> Any:
    """渲染编辑标签弹窗。"""
    name, _ = _asset_profile(entry.asset)
    body = Form(
        Div(
            Div(f"{_asset_symbol(entry.asset)} · {name}", cls="mb-3 text-sm font-medium text-gray-900"),
            Label("标签", cls="mb-2 block text-sm font-medium text-gray-700"),
            Input(
                type="text",
                name="tags",
                value=entry.tags,
                placeholder="请输入标签，如：天然气、地产",
                cls="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm",
            ),
            cls="space-y-2",
        ),
        Div(
            Button("取消", type="button", cls="rounded-lg border border-gray-300 px-4 py-2 text-sm", onclick=_close_modal_button()),
            Button(
                "保存",
                type="submit",
                cls="rounded-lg bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700",
            ),
            cls="flex justify-end gap-2",
        ),
        hx_post=f"/trade/lightning/{portfolio_id}/{entry.asset}/update",
        hx_target="#trade-lightning-modal-container",
        cls="space-y-4",
    )
    return _dialog_modal("编辑闪电单", body, "", modal_id="trade-lightning-edit-modal")


def _delete_modal(portfolio_id: str, entry: TradeLightningEntry) -> Any:
    """渲染删除确认弹窗。"""
    name, _ = _asset_profile(entry.asset)
    footer = Div(
        Button("取消", type="button", cls="rounded-lg border border-gray-300 px-4 py-2 text-sm", onclick=_close_modal_button()),
        Button(
            "删除",
            type="button",
            cls="rounded-lg bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700",
            hx_post=f"/trade/lightning/{portfolio_id}/{entry.asset}/delete",
            hx_target="#trade-lightning-modal-container",
        ),
        cls="flex justify-end gap-2",
    )
    body = P(f"确定删除 {_asset_symbol(entry.asset)} · {name} 吗？", cls="text-sm text-gray-700")
    return _dialog_modal("删除闪电单", body, footer, modal_id="trade-lightning-delete-modal")


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


async def trade_lightning_add(req):
    """将当前股票加入闪电单。"""
    portfolio_id = req.path_params["portfolio_id"]
    form = await req.form()
    asset = str(form.get("asset") or "").strip()
    if not asset:
        return HTMLResponse(
            to_xml(_panel_with_toast(portfolio_id, "请先选择股票后再添加"))
        )

    try:
        stock_list.get_name(asset)
    except Exception:
        return HTMLResponse(to_xml(_panel_with_toast(portfolio_id, "股票代码无效，无法加入闪电单")))

    _, created = add_trade_lightning_entry(portfolio_id, asset)
    message = "已加入闪电单" if created else "该股票已在闪电单中"
    level = "success" if created else "error"
    return HTMLResponse(to_xml(_panel_with_toast(portfolio_id, message, level=level)))


async def trade_lightning_remove_current(req):
    """从闪电单移除当前股票。"""
    portfolio_id = req.path_params["portfolio_id"]
    form = await req.form()
    asset = str(form.get("asset") or "").strip()
    if not asset:
        return HTMLResponse(
            to_xml(_panel_with_toast(portfolio_id, "请先选择股票后再移除"))
        )

    removed = remove_trade_lightning_entry(portfolio_id, asset)
    message = "已从闪电单移除" if removed else "当前股票不在闪电单中"
    level = "success" if removed else "error"
    return HTMLResponse(to_xml(_panel_with_toast(portfolio_id, message, level=level)))


async def trade_lightning_update(req):
    """更新闪电单标签。"""
    portfolio_id = req.path_params["portfolio_id"]
    asset = req.path_params["asset"]
    form = await req.form()
    tags = str(form.get("tags") or "")
    updated = update_trade_lightning_tags(portfolio_id, asset, tags)
    message = "闪电单标签已更新" if updated is not None else "该闪电单条目不存在"
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
    message = "已删除闪电单条目" if removed else "该闪电单条目不存在"
    level = "success" if removed else "error"
    return _render_response(
        Div(id="trade-lightning-modal-container"),
        _panel_with_toast(portfolio_id, message, level=level, hx_swap_oob=True),
    )
