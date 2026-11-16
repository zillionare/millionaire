"""Input controls for the legacy home and live trade panels."""

from fasthtml.common import *
from fasthtml.common import FT, Div
from fasthtml.common import Label as _Label
from monsterui.all import *
from monsterui.all import Button, Input, UkIcon


def LegacyTradeInputs(price_label: str, submit_class: str) -> FT:
    input_cls = (
        "mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 "
        "text-sm text-gray-900 outline-none transition focus:border-[#e41815] "
        "focus:ring-2 focus:ring-[#e41815]/10"
    )
    label_cls = "block text-xs font-medium text-gray-500"
    ratio_btn_cls = (
        "rounded-md border border-gray-200 px-2 py-1 text-[11px] text-gray-600 "
        "transition hover:border-[#e41815] hover:text-[#e41815]"
    )
    return Div(
        _Label("股票代码", cls=label_cls),
        Input(name="asset", placeholder="例如: 000001.SZ", cls=input_cls, required=True),
        _Label(price_label, cls=label_cls),
        Input(name="price", type="number", step="0.01", value="0.00", cls=input_cls),
        _Label("仓位选择", cls=label_cls),
        Div(
            Button("满仓", type="button", cls=ratio_btn_cls),
            Button("1/2", type="button", cls=ratio_btn_cls),
            Button("1/3", type="button", cls=ratio_btn_cls),
            Button("1/4", type="button", cls=ratio_btn_cls),
            Button("1/10", type="button", cls=ratio_btn_cls),
            cls="flex gap-1 mb-4 mt-1",
        ),
        _Label("交易数量 (股)", cls=label_cls),
        Input(name="shares", type="number", step="100", cls=input_cls, required=True),
        Button(UkIcon("shopping-cart", size=16), " 下单", type="submit", cls=submit_class),
    )
