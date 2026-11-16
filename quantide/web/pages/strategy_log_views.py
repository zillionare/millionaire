"""Strategy log views."""

from typing import Any

from fasthtml.common import *
from fasthtml.common import (
    Div,
    P,
    Pre,
    Span,
)
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
)

from quantide.service.backtest_logs import (
    list_backtest_logs,
    load_saved_backtest_logs,
    saved_backtest_log_exists,
    saved_backtest_log_path,
)
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.pages.strategy_metrics import (
    _resolve_backtest_status,
)
from quantide.web.pages.strategy_routes import (
    rt,
)


def _build_log_rows(portfolio_id: str, limit: int = 200) -> list[dict[str, str]]:
    """构建日志行。

    Args:
        portfolio_id: 组合 ID
        limit: 最大行数

    Returns:
        list[dict]: 日志行
    """
    return list_backtest_logs(portfolio_id, limit=limit)


def _build_log_meta(portfolio_id: str) -> dict[str, Any]:
    """构建回测日志状态元数据。"""
    saved_path = saved_backtest_log_path(portfolio_id)
    run = strategy_runtime_manager.get_backtest_run(portfolio_id)
    return {
        "save_requested": bool(getattr(run, "save_logs", False)),
        "saved": saved_backtest_log_exists(portfolio_id),
        "saved_path": str(saved_path),
    }


def _format_log_lines(rows: list[dict[str, Any]]) -> list[str]:
    """格式化回测日志展示文本。"""
    lines: list[str] = []
    for row in rows:
        base = (
            f"{row.get('dt', '')} | {row.get('level', 'INFO')} | "
            f"{row.get('source', 'system')} | {row.get('message', '')}"
        )
        extra = str(row.get("extra") or "").strip()
        lines.append(f"{base} | {extra}" if extra else base)
    return lines


def _build_log_panel(
    portfolio_id: str,
    status: str,
    rows: list[dict[str, Any]] | None = None,
    source_label: str = "实时日志",
    error_text: str = "",
) -> Div:
    """构建回测日志面板。"""
    log_rows = rows if rows is not None else _build_log_rows(portfolio_id, limit=200)
    meta = _build_log_meta(portfolio_id)
    log_lines = _format_log_lines(log_rows)
    save_status_text = "本次回测未启用文件保存"
    save_status_cls = "text-xs text-gray-500"
    if meta["save_requested"] and meta["saved"]:
        save_status_text = "已保存到文件，可重复加载"
        save_status_cls = "text-xs text-green-600"
    elif meta["save_requested"]:
        save_status_text = "已启用文件保存，日志生成后会写入本地文件"
        save_status_cls = "text-xs text-gray-500"

    load_button = (
        Button(
            "加载已保存日志",
            cls="btn btn-secondary btn-sm",
            type="button",
            hx_get=f"/strategy/backtest/{portfolio_id}/logs/saved",
            hx_target="#backtest-log-panel",
            hx_swap="outerHTML",
        )
        if meta["saved"]
        else Button(
            "暂无已保存日志",
            cls="btn btn-secondary btn-sm opacity-60 cursor-not-allowed",
            type="button",
            disabled=True,
        )
    )

    return Div(
        Div(
            Div(
                H3("日志输出", cls="text-xl font-bold"),
                P(
                    "运行中自动刷新；保存日志后可从文件重复加载。",
                    cls="text-sm text-gray-500 mt-1",
                ),
            ),
            Div(
                Span(
                    f"当前来源：{source_label}",
                    id="log_source_badge",
                    cls="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600",
                ),
                load_button,
                cls="flex flex-wrap items-center gap-2",
            ),
            cls="flex flex-col gap-3 md:flex-row md:items-start md:justify-between",
        ),
        Div(
            P(
                "回测进行中，日志会自动刷新。"
                if status == "running"
                else "回测已结束，可查看已采集日志。",
                cls="text-xs text-gray-500",
            ),
            P(
                save_status_text,
                id="log_save_status",
                cls=save_status_cls,
            ),
            P(
                meta["saved_path"],
                id="log_save_path",
                cls="text-xs text-gray-400 break-all",
            ),
            cls="space-y-1 mt-4",
        ),
        (
            Div(
                error_text,
                id="log_panel_error",
                cls=(
                    "mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
                ),
            )
            if error_text
            else Div(id="log_panel_error", cls="hidden")
        ),
        Pre(
            "\n".join(log_lines) if log_lines else "暂无回测日志",
            id="log_output",
            cls=(
                "mt-4 max-h-[560px] overflow-auto rounded-lg bg-gray-950 p-4 text-xs "
                "text-gray-100 whitespace-pre-wrap"
            ),
        ),
        id="backtest-log-panel",
        cls="bg-white p-6 rounded-lg shadow-sm border border-gray-100 mt-6",
    )


@rt("/backtest/{portfolio_id}/logs/saved")
def load_saved_backtest_log_panel(portfolio_id: str) -> Div:
    """加载已保存的回测日志面板。"""
    status, _ = _resolve_backtest_status(portfolio_id)
    try:
        rows = load_saved_backtest_logs(portfolio_id, limit=200)
        return _build_log_panel(
            portfolio_id=portfolio_id,
            status=status,
            rows=rows,
            source_label="已保存文件",
        )
    except Exception as exc:
        return _build_log_panel(
            portfolio_id=portfolio_id,
            status=status,
            rows=[],
            source_label="已保存文件",
            error_text=str(exc),
        )
