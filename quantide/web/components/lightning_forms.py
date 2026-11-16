"""Lightning order modal forms, independent of request routing."""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
    NotStr,
    P,
    Script,
    Span,
    ft_hx,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
    Form,
    Input,
)

from quantide.config.branding import get_branding
from quantide.service.trade_lightning import TradeLightningEntry
from quantide.web.components.lightning_values import (
    PRICE_REFERENCE_OPTIONS,
    _asset_profile,
    _asset_symbol,
    _format_amount_wan,
    _price_reference_label,
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
    return Script(src="/static/lightning-search.js")


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
                            cls=(
                                "whitespace-pre-line text-left text-sm font-semibold "
                                "leading-4 text-white"
                            ),
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
                                "inline-flex h-8 w-8 items-center justify-center "
                                "bg-transparent p-0 text-white hover:opacity-90"
                            ),
                            style="background:none;border:none;box-shadow:none;",
                        ),
                        cls=(
                            "grid grid-cols-[auto_1fr_auto] items-center gap-4 "
                            "bg-[#e41815] px-5 py-4"
                        ),
                    ),
                    Div(body, cls="bg-gray-50"),
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
                "flex items-center justify-start bg-gray-200 px-4 text-left text-[15px] "
                "font-medium text-gray-800"
            ),
        ),
        control,
        cls=(
            "grid grid-cols-[110px_1fr] overflow-hidden rounded-md border border-[#cfcfcf] bg-white"
        ),
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
                cls=(
                    "pointer-events-none absolute inset-y-0 right-3 flex items-center text-gray-400"
                ),
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
            cls=(
                "pointer-events-none absolute inset-y-0 right-4 flex items-center "
                "text-base text-gray-700"
            ),
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
    body = Div(form, cls="bg-gray-50")
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
        intro=(
            "请设置买入金额和价格以创建闪电单。保存后，在下单界面双击即可"
            "立即发出委托，适合提前埋伏多支个股，在接近触发条件时快速下单。"
        ),
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
        cls="bg-gray-50",
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
        cls="bg-gray-50",
    )
    return _dialog_modal("清空闪电买入单", body, modal_id="trade-lightning-clear-modal")
