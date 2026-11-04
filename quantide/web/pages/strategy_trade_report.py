"""Strategy trade report."""

from typing import Any
from urllib.parse import quote, urlencode

from fasthtml.common import *
from fasthtml.common import (
    A,
    Div,
    P,
    Span,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
)

from quantide.service.trade_pairs import build_trade_pairs
from quantide.web.components.analysis.trade_kline import (
    build_trade_kline_payload,
    render_trade_kline_chart,
)
from quantide.web.pages.strategy_format import (
    _strategy_dialog_modal,
)
from quantide.web.pages.strategy_routes import (
    STRATEGY_MODAL_CLOSE_JS,
    TRADE_PAIRS_PAGE_SIZE,
    TRADE_SORT_RETURN,
    rt,
)


def _trade_pair_detail_table(_sort_header, portfolio_id, rows):
    """Render trade pair values and links using the selected sort header."""
    table = Table(
        Thead(
            Tr(
                Th("标的"),
                Th("买入时间"),
                Th("卖出时间"),
                Th("金额(买入)"),
                Th("PnL"),
                Th(_sort_header("收益率", TRADE_SORT_RETURN)),
                Th("费用"),
            )
        ),
        Tbody(
            *[
                Tr(
                    Td(row["asset"]),
                    Td(row["buy_tm"]),
                    Td(row["sell_tm"] or "持仓中"),
                    Td(f"{row['buy_amount']:.2f}"),
                    Td(
                        f"{row['pnl']:.2f}"
                        if row["pnl"] is not None
                        else (
                            f"{row['unrealized_pnl']:.2f}（浮盈）"
                            if row["unrealized_pnl"] is not None
                            else "—"
                        ),
                        cls="text-red-500"
                        if (row["pnl"] or row["unrealized_pnl"] or 0) > 0
                        else "text-green-500",
                    ),
                    Td("—" if row["return_rate"] is None else f"{row['return_rate'] * 100:.2f}%"),
                    Td(f"{row['fee']:.2f}"),
                    hx_get=(
                        f"/strategy/backtest/{portfolio_id}/trade/kline/modal"
                        f"?buy_tid={quote(row['buy_tid'])}"
                        f"&sell_tid={quote(row['sell_tid'])}"
                    ),
                    hx_target="#modal-container",
                    title="点击查看该成交对的 K 线与买卖点",
                    cls="cursor-pointer hover:bg-gray-50 transition-colors",
                )
                for row in rows
            ],
            id="trade_pairs_body",
        ),
        cls=TableT.striped + " text-xs",
    )
    return table


def _ordered_trade_pairs(portfolio_id: str) -> list[Any]:
    """按买入时间倒序返回成交对（与交易明细表顺序一致）。

    Args:
        portfolio_id: 组合 ID。

    Returns:
        list: 成交对列表。
    """
    return list(reversed(build_trade_pairs(portfolio_id)))


def _build_trade_pair_rows(portfolio_id: str) -> list[dict]:
    """构建成交对明细行（按买入时间倒序）。

    Args:
        portfolio_id: 组合 ID。

    Returns:
        list[dict]: 成交对明细。
    """
    pairs = _ordered_trade_pairs(portfolio_id)
    rows = []
    for pair in pairs:
        rows.append(
            {
                "asset": pair.asset,
                "buy_tm": str(pair.buy_tm)[:19],
                "sell_tm": str(pair.sell_tm)[:19] if pair.sell_tm else "",
                "buy_amount": pair.buy_amount,
                "sell_amount": pair.sell_amount,
                "pnl": pair.pnl,
                "unrealized_pnl": pair.unrealized_pnl,
                "return_rate": pair.return_rate,
                "fee": pair.fee,
                "status": pair.status,
                "buy_tid": pair.buy_tid,
                "sell_tid": pair.sell_tid or "",
            }
        )
    return rows


def _sort_trade_pair_rows(rows: list[dict], sort: str = "", direction: str = "asc") -> list[dict]:
    """按指定字段排序成交对。

    Args:
        rows: 成交对明细。
        sort: 排序字段（``return`` 表示按收益率，其余按买入时间）。
        direction: ``asc`` 升序 / ``desc`` 降序。

    Returns:
        list[dict]: 排序后的成交对。
    """
    if sort != TRADE_SORT_RETURN:
        return list(rows)
    with_value = [row for row in rows if row.get("return_rate") is not None]
    without_value = [row for row in rows if row.get("return_rate") is None]
    with_value.sort(
        key=lambda row: float(row["return_rate"]),
        reverse=direction == "desc",
    )
    return with_value + without_value


def _paginate_trade_pairs(
    rows: list[dict], page: int, page_size: int = TRADE_PAIRS_PAGE_SIZE
) -> tuple[list[dict], int, int, int]:
    """对成交对分页。

    Args:
        rows: 成交对明细。
        page: 目标页码（从 1 开始）。
        page_size: 每页行数。

    Returns:
        tuple: (当前页数据, 当前页码, 总页数, 总行数)。
    """
    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current = max(1, min(int(page or 1), total_pages))
    start = (current - 1) * page_size
    return rows[start : start + page_size], current, total_pages, total


def _build_trade_pair_table(
    portfolio_id: str,
    rows: list[dict],
    page: int,
    total_pages: int,
    total: int,
    sort: str = "",
    direction: str = "asc",
) -> Any:
    """构建成交对表格与分页控件。"""

    def _query(**extra: Any) -> str:
        params = {"tab": "trades", **extra}
        return f"/strategy/backtest/{portfolio_id}?{urlencode(params)}"

    def _sort_header(label: str, field: str) -> Any:
        if sort == field:
            next_dir = "desc" if direction == "asc" else "asc"
            arrow = " ↑" if direction == "asc" else " ↓"
            return A(
                label + arrow,
                href=_query(sort=field, dir=next_dir, page=1),
                cls="cursor-pointer select-none hover:text-[#e41815]",
            )
        return A(
            label,
            href=_query(sort=field, dir="asc", page=1),
            cls="cursor-pointer select-none hover:text-[#e41815]",
        )

    table = _trade_pair_detail_table(_sort_header, portfolio_id, rows)

    def _page_link(target: int, label: str, *, disabled: bool = False) -> Any:
        if disabled:
            return Span(label, cls="px-2 py-1 text-xs text-gray-300")
        extra: dict[str, Any] = {"page": target}
        if sort:
            extra["sort"] = sort
            extra["dir"] = direction
        return A(
            label,
            href=_query(**extra),
            cls="px-2 py-1 text-xs text-[#e41815] hover:underline",
        )

    pagination = _trade_pair_pagination(page, total_pages, _page_link, sort, direction, total)

    return Div(table, pagination, cls="mt-2")


def _trade_kline_modal_footer() -> Any:
    """构建 K 线弹窗底部按钮。"""
    return Div(
        Button(
            "关闭",
            type="button",
            cls="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50",
            onclick=STRATEGY_MODAL_CLOSE_JS,
        ),
        cls="flex justify-end gap-2",
    )


def _trade_kline_modal_url(
    portfolio_id: str,
    buy_tid: str,
    sell_tid: str | None,
    panel: str = "",
) -> str:
    """构建成交对 K 线弹窗链接（可带右侧面板页签）。"""
    url = (
        f"/strategy/backtest/{portfolio_id}/trade/kline/modal"
        f"?buy_tid={quote(buy_tid)}&sell_tid={quote(sell_tid or '')}"
    )
    if panel:
        url += f"&panel={quote(panel)}"
    return url


def _trade_pair_nav_url(portfolio_id: str, pair: Any, panel: str = "") -> str:
    """构建成交对 K 线弹窗的跳转链接。"""
    return _trade_kline_modal_url(portfolio_id, pair.buy_tid, pair.sell_tid, panel)


def _trade_kline_modal_title(
    portfolio_id: str,
    payload: dict[str, Any],
    buy_tid: str,
    sell_tid: str | None,
    panel: str = "",
) -> Any:
    """构建带前后翻箭头的弹窗标题。"""
    pairs = _ordered_trade_pairs(portfolio_id)
    current = next(
        (
            index
            for index, pair in enumerate(pairs)
            if pair.buy_tid == buy_tid and (sell_tid is None or pair.sell_tid == sell_tid)
        ),
        None,
    )

    def _arrow(index: int | None, label: str, hint: str) -> Any:
        if index is None or index < 0 or index >= len(pairs):
            return Span(
                label,
                cls="w-7 h-7 inline-flex items-center justify-center rounded text-gray-300",
            )
        return Button(
            label,
            type="button",
            title=hint,
            hx_get=_trade_pair_nav_url(portfolio_id, pairs[index], panel),
            hx_target="#modal-container",
            cls=(
                "w-7 h-7 inline-flex items-center justify-center rounded border "
                "border-gray-300 text-gray-600 hover:bg-gray-100"
            ),
        )

    prev_arrow = _arrow(current - 1 if current is not None else None, "‹", "上一笔成交对")
    next_arrow = _arrow(current + 1 if current is not None else None, "›", "下一笔成交对")
    return Div(
        H3(
            f"{payload.get('name', '')} {payload.get('asset', '')} K 线",
            cls="text-lg font-medium leading-6 text-gray-900",
        ),
        Div(prev_arrow, next_arrow, cls="flex items-center gap-1"),
        cls="flex items-center justify-between gap-3",
    )


@rt("/backtest/{portfolio_id}/trade/kline/modal")
def trade_kline_modal(req, portfolio_id: str):
    """成交对 K 线弹窗路由：展示个股 K 线、买卖点与交易信息。"""
    query = getattr(req, "query_params", {}) or {}
    buy_tid = str(query.get("buy_tid") or "").strip()
    sell_tid = str(query.get("sell_tid") or "").strip() or None
    panel = str(query.get("panel") or "").strip()
    payload = build_trade_kline_payload(portfolio_id, buy_tid, sell_tid, panel)
    if payload is None:
        return _strategy_dialog_modal(
            "K 线",
            P("未找到该笔成交记录。", cls="text-sm text-red-600"),
            _trade_kline_modal_footer(),
            modal_id="trade-kline-modal",
            width_cls="max-w-6xl",
        )
    active_panel = payload.get("active_panel") or ""
    tab_urls = {
        key: _trade_kline_modal_url(portfolio_id, buy_tid, sell_tid, key)
        for key in payload.get("available_panels") or []
        if key != active_panel
    }
    return _strategy_dialog_modal(
        _trade_kline_modal_title(portfolio_id, payload, buy_tid, sell_tid, active_panel),
        render_trade_kline_chart(payload, tab_urls),
        _trade_kline_modal_footer(),
        modal_id="trade-kline-modal",
        width_cls="max-w-6xl",
    )


def _trade_pair_pagination(page, total_pages, page_link, sort, direction, total):
    """Render a five-page window and a jump control with the current sorting."""
    page_links = []
    start_page = max(1, page - 2)
    end_page = min(total_pages, start_page + 4)
    start_page = max(1, end_page - 4)
    for number in range(start_page, end_page + 1):
        if number == page:
            page_links.append(
                Span(str(number), cls="px-2 py-1 text-xs font-semibold text-gray-900")
            )
        else:
            page_links.append(page_link(number, str(number)))

    jump_form = Form(
        Input(type="hidden", name="tab", value="trades"),
        *(
            [
                Input(type="hidden", name="sort", value=sort),
                Input(type="hidden", name="dir", value=direction),
            ]
            if sort
            else []
        ),
        Input(
            type="number",
            name="page",
            value=str(page),
            min="1",
            max=str(total_pages),
            cls="input input-bordered input-xs w-16 text-center",
        ),
        Button("跳转", type="submit", cls="btn btn-xs ml-1"),
        cls="flex items-center",
    )

    pagination = Div(
        jump_form,
        Div(
            page_link(page - 1, "上一页", disabled=page <= 1),
            *page_links,
            page_link(page + 1, "下一页", disabled=page >= total_pages),
            cls="flex items-center gap-1",
        ),
        Span(
            f"第 {page}/{total_pages} 页 · 共 {total} 笔成交对",
            cls="text-xs text-gray-500 ml-2",
        ),
        cls="flex items-center justify-end gap-2 mt-3",
    )
    return pagination
