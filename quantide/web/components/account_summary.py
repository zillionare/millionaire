"""Account total cards shared by the dashboard and live account page."""

from fasthtml.common import *
from fasthtml.common import (
    Div,
)
from monsterui.all import *


def AssetSummary(asset_overview: dict | None = None, **kwargs):
    """Render totals with a single formatting rule and consistent profit colours."""
    values = asset_overview or {}
    pnl = values.get("pnl") or 0
    colour = "text-red-500" if pnl > 0 else ("text-green-600" if pnl < 0 else "text-gray-900")
    labels = (
        ("total", "总资产"),
        ("cash", "可用金额"),
        ("frozen_cash", "冻结金额"),
        ("market_value", "总市值"),
        ("pnl", "盈亏"),
        ("pnl_pct", "盈亏比例"),
    )
    return Div(
        Div(
            *[_account_stat(key, label, values, colour) for key, label in labels],
            cls="grid grid-cols-2 gap-px bg-gray-100 md:grid-cols-3 xl:grid-cols-6",
        ),
        id="asset-summary",
        cls="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm",
        **kwargs,
    )


def _account_stat(key, label, values, colour):
    value = values.get(key) or 0
    text = f"{value * 100:.2f}%" if key == "pnl_pct" else f"{value:,.2f}"
    colour = colour if key in {"pnl", "pnl_pct"} else "text-gray-900"
    return Div(
        P(label, cls="text-xs text-gray-500"),
        P(text, cls=f"mt-1 text-xl font-semibold tabular-nums {colour}"),
        cls="bg-white px-4 py-4",
    )


def build_asset_overview(asset) -> dict:
    pnl = asset.total - asset.principal
    ppnl = pnl / asset.principal if asset.principal else 0.0
    return {
        "total": asset.total,
        "cash": asset.cash,
        "frozen_cash": asset.frozen_cash,
        "market_value": asset.market_value,
        "pnl": pnl,
        "pnl_pct": ppnl,
    }
