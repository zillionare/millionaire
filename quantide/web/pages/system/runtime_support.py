"""系统维护中运行保障相关的共享渲染逻辑。"""

from __future__ import annotations

import json
from typing import Any

from fasthtml.common import Div, Span, Table, Tbody, Td, Th, Thead, Tr
from monsterui.all import H2, Button

from quantide.service.strategy_runtime import strategy_runtime_manager

POLL_TRIGGER = "every 5s [document.visibilityState === 'visible' && document.hasFocus()]"


def _runtime_status_chip(status: str):
    """构建运行时状态标签。"""
    if status == "running":
        cls = "px-2 py-0.5 rounded text-xs bg-green-100 text-green-700"
    elif status == "blocked":
        cls = "px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-700"
    elif status == "failed":
        cls = "px-2 py-0.5 rounded text-xs bg-red-100 text-red-700"
    else:
        cls = "px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700"
    return Span(status, cls=cls)


def _risk_severity_chip(severity: str):
    """构建风险级别标签。"""
    if severity == "critical":
        cls = "px-2 py-0.5 rounded text-xs bg-red-100 text-red-700"
    elif severity == "warning":
        cls = "px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-700"
    else:
        cls = "px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700"
    return Span(severity, cls=cls)


def build_risk_event_center_content(limit: int = 8) -> Div:
    """构建风险事件中心内容。"""
    summary = strategy_runtime_manager.risk_summary()
    events = strategy_runtime_manager.list_risk_events(limit=limit)
    rows = _build_risk_event_rows(events)
    return Div(
        Div(
            Div(
                H2("风险事件中心", cls="text-lg font-semibold text-gray-900"),
                Span("展示封控、告警与重启恢复事件", cls="text-xs text-gray-500"),
                cls="flex flex-col",
            ),
            Div(
                Span(f"账户封控 {summary['blocked_accounts']}", cls="px-2 py-1 rounded bg-red-50 text-red-700 text-xs"),
                Span(f"策略封控 {summary['blocked_strategies']}", cls="px-2 py-1 rounded bg-amber-50 text-amber-700 text-xs"),
                Span(f"活动告警 {summary['open_events']}", cls="px-2 py-1 rounded bg-blue-50 text-blue-700 text-xs"),
                cls="flex items-center gap-2 flex-wrap",
            ),
            cls="p-6 border-b border-gray-200 flex items-center justify-between gap-4",
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        Th("级别", cls="px-4 py-2"),
                        Th("事件", cls="px-4 py-2"),
                        Th("范围", cls="px-4 py-2"),
                        Th("时间", cls="px-4 py-2"),
                        cls="text-left text-sm text-gray-600 border-b border-gray-200",
                    )
                ),
                Tbody(*rows, cls="text-sm"),
                cls="w-full",
            ),
            cls="overflow-x-auto",
        ),
    )


def _build_risk_event_rows(events: list[dict[str, Any]]) -> list[Any]:
    """构建风险事件表格行。"""
    rows: list[Any] = []
    for event in events:
        rows.append(
            Tr(
                Td(_risk_severity_chip(str(event.get("severity") or "info")), cls="px-4 py-3 align-top"),
                Td(
                    Div(
                        Div(str(event.get("title") or "风险事件"), cls="text-sm font-medium text-gray-900"),
                        Div(str(event.get("message") or ""), cls="text-sm text-gray-600 mt-1"),
                    ),
                    cls="px-4 py-3",
                ),
                Td(str(event.get("scope") or "-"), cls="px-4 py-3 text-xs text-gray-500 uppercase"),
                Td(str(event.get("created_at") or "-"), cls="px-4 py-3 text-xs text-gray-500 whitespace-nowrap"),
                cls="border-b border-gray-100",
            )
        )
    if rows:
        return rows
    return [Tr(Td("暂无风险事件", colspan="4", cls="px-4 py-6 text-center text-gray-400"))]


def build_risk_event_center_card(refresh_path: str, limit: int = 8) -> Div:
    """构建带自动刷新的风险事件卡片。"""
    return Div(
        build_risk_event_center_content(limit=limit),
        id="risk-event-center",
        hx_get=refresh_path,
        hx_trigger=POLL_TRIGGER,
        hx_swap="innerHTML",
        cls="bg-white rounded-lg shadow",
    )


def build_runtime_table_content(action_base_path: str, target_selector: str) -> Div:
    """构建运行时监控表格内容。"""
    return Div(
        Div(
            H2("运行时监控", cls="text-lg font-semibold text-gray-900"),
            Span("live/paper 常驻，backtest 按需创建", cls="text-xs text-gray-500"),
            cls="p-6 border-b border-gray-200 flex items-center justify-between",
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        Th("模式", cls="px-4 py-2"),
                        Th("账户", cls="px-4 py-2"),
                        Th("策略", cls="px-4 py-2"),
                        Th("策略ID", cls="px-4 py-2"),
                        Th("状态", cls="px-4 py-2"),
                        Th("告警 / 封控原因", cls="px-4 py-2"),
                        Th("总资产", cls="px-4 py-2"),
                        Th("持仓数", cls="px-4 py-2"),
                        Th("委托数", cls="px-4 py-2"),
                        Th("更新时间", cls="px-4 py-2"),
                        Th("操作", cls="px-4 py-2"),
                        cls="text-left text-sm text-gray-600 border-b border-gray-200",
                    )
                ),
                Tbody(*_build_runtime_rows(action_base_path, target_selector), cls="text-sm"),
                cls="w-full",
            ),
            cls="overflow-x-auto",
        ),
    )


def _build_runtime_rows(action_base_path: str, target_selector: str) -> list[Any]:
    """构建运行时表格行。"""
    rows: list[Any] = []
    for item in strategy_runtime_manager.list_runtime_rows():
        action_items = _build_runtime_actions(item, action_base_path, target_selector)
        actions = Td(
            Div(*action_items, cls="flex items-center gap-2 flex-wrap") if action_items else Span("-", cls="text-xs text-gray-400"),
            cls="px-4 py-2",
        )
        rows.append(
            Tr(
                Td(item["mode"], cls="px-4 py-2"),
                Td(item["portfolio_id"], cls="px-4 py-2 font-mono text-xs"),
                Td(item["strategy_name"] or "-", cls="px-4 py-2"),
                Td(item["strategy_id"] or "-", cls="px-4 py-2 font-mono text-xs"),
                Td(_runtime_status_chip(item["status"]), cls="px-4 py-2"),
                Td(item.get("alert_text") or "-", cls="px-4 py-2 text-sm text-gray-600"),
                Td(f"{item['total']:.2f}", cls="px-4 py-2"),
                Td(str(item["positions"]), cls="px-4 py-2"),
                Td(str(item["orders"]), cls="px-4 py-2"),
                Td(item["updated_at"], cls="px-4 py-2 text-xs text-gray-500"),
                actions,
                cls="border-b border-gray-100",
            )
        )
    if rows:
        return rows
    return [Tr(Td("暂无运行时实例", colspan="11", cls="px-4 py-6 text-center text-gray-400"))]


def _build_runtime_actions(item: dict[str, Any], action_base_path: str, target_selector: str) -> list[Any]:
    """构建运行时操作按钮。"""
    action_items: list[Any] = []
    if item.get("can_stop"):
        action_items.append(_runtime_action_button("停止", f"{action_base_path}/stop", {"runtime_id": item["runtime_id"]}, target_selector, "text-red-600"))
    if item.get("can_start"):
        action_items.append(_runtime_action_button("启动", f"{action_base_path}/start", {"runtime_id": item["runtime_id"]}, target_selector, "text-green-600"))
    if item.get("can_block_account"):
        action_items.append(_runtime_action_button("封锁账户", f"{action_base_path}/block", {"target_kind": "account", "target_id": item["runtime_id"]}, target_selector, "text-amber-700"))
    if item.get("can_unblock_account"):
        action_items.append(_runtime_action_button("解除账户封锁", f"{action_base_path}/unblock", {"target_kind": "account", "target_id": item["runtime_id"]}, target_selector, "text-blue-700", "确认解除账户风控封锁吗？"))
    if item.get("can_block_strategy"):
        action_items.append(_runtime_action_button("封锁策略", f"{action_base_path}/block", {"target_kind": "strategy", "target_id": item["runtime_id"]}, target_selector, "text-amber-700"))
    if item.get("can_unblock_strategy"):
        action_items.append(_runtime_action_button("解除策略封锁", f"{action_base_path}/unblock", {"target_kind": "strategy", "target_id": item["runtime_id"]}, target_selector, "text-blue-700", "确认解除策略风控封锁吗？"))
    if item.get("blocked_scope") == "account" and item.get("strategy_id"):
        action_items.append(Span("请在账户行解除封控", cls="text-xs text-amber-700"))
    return action_items


def _runtime_action_button(
    label: str,
    path: str,
    values: dict[str, Any],
    target_selector: str,
    text_cls: str,
    confirm: str | None = None,
) -> Button:
    """构建运行时操作按钮。"""
    attrs: dict[str, Any] = {
        "cls": f"btn btn-ghost btn-xs {text_cls}",
        "type": "button",
        "hx_post": path,
        "hx_target": target_selector,
        "hx_swap": "innerHTML",
        "hx_vals": json.dumps(values),
    }
    if confirm:
        attrs["hx_confirm"] = confirm
    return Button(label, **attrs)


def build_runtime_table_card(refresh_path: str, action_base_path: str, target_selector: str) -> Div:
    """构建带自动刷新的运行时监控卡片。"""
    return Div(
        build_runtime_table_content(action_base_path=action_base_path, target_selector=target_selector),
        id=target_selector.lstrip("#"),
        hx_get=refresh_path,
        hx_trigger=POLL_TRIGGER,
        hx_swap="innerHTML",
        cls="bg-white rounded-lg shadow",
    )
