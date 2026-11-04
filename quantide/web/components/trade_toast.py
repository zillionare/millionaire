"""Shared manual-order toast with automatic dismissal."""

from fasthtml.common import *
from fasthtml.common import (
    FT,
    Button,
    Div,
    Script,
    Span,
)


def TradeToast(
    message: str, level: str = "error", *, hx_swap_oob: bool = False, container: bool = False
) -> FT:
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
    attrs = {"cls": "contents"}
    if container:
        attrs.update(
            id="trade-toast-slot",
            cls="pointer-events-none absolute inset-x-6 top-0 z-50",
            aria_live="polite",
        )
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
