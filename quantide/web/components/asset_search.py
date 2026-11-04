"""Fast asset search results; no per-row quote requests."""

from __future__ import annotations

from typing import Any

import pandas as pd
from fasthtml.common import FT, Div, to_xml
from starlette.responses import HTMLResponse


def AssetSearchResults(frame: pd.DataFrame, *, lightning: bool = False) -> HTMLResponse:
    items = [
        _asset_search_item(row, lightning)
        for _, row in frame.sort_values("asset").head(20).iterrows()
    ]
    prefix = "lightning-" if lightning else ""
    theme = "" if lightning else "dark:bg-gray-800 dark:border-gray-600 "
    return HTMLResponse(
        to_xml(
            Div(
                *items,
                id=f"{prefix}asset-search-dropdown",
                cls=(
                    "absolute z-50 mt-1 w-full rounded-lg border border-gray-300 bg-white "
                    + theme
                    + "shadow-lg max-h-48 overflow-y-auto"
                ),
            )
        )
    )


def _asset_search_item(row: pd.Series[Any], lightning: bool) -> FT:
    asset, name, pinyin = (row.get(key, "") for key in ("asset", "name", "pinyin"))
    attrs = {} if lightning else {"data_name": name, "data_price": ""}
    title_theme, detail_theme = (
        ("", "") if lightning else (" dark:text-white", " dark:text-gray-400")
    )
    cls = (
        "lightning-asset-search-item cursor-pointer px-3 py-2 hover:bg-gray-100"
        if lightning
        else "asset-search-item px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700"
    )
    return Div(
        Div(name, cls="text-sm font-medium text-gray-900" + title_theme),
        Div(f"{asset} · {pinyin}", cls="text-xs text-gray-500" + detail_theme),
        cls=cls,
        data_asset=asset,
        data_display=f"{name}（{asset}）",
        tabindex="0",
        role="button",
        **attrs,
    )
