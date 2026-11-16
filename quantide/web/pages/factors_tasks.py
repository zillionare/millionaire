"""Background custom-study task status rendering."""

from __future__ import annotations

from typing import Any

from fasthtml.common import Button as ActionButton
from fasthtml.common import Div, Form, P

from quantide.factors.metadata import FactorDefinition

TASK_LABELS = {
    "pending": "已排队",
    "running": "计算中",
    "succeeded": "已完成",
    "failed": "失败",
    "insufficient": "样本不足",
    "cancelled": "已取消",
    "interrupted": "已中断",
    "superseded": "已被替代",
}


def study_task_block(meta: FactorDefinition, task: Any) -> Any:
    if task is None:
        return None
    label = TASK_LABELS.get(str(task.status), str(task.status))
    detail = P(
        f"任务 {task.run_id[:12]} · 状态 {label} · 阶段 {task.phase or '等待'}",
        cls="mt-1 text-xs text-gray-600",
    )
    cancel = (
        Form(
            ActionButton("取消检验", type="submit", cls="q-btn q-btn--sm mt-2"),
            method="post",
            action=f"/factors/{meta.factor_id}/study/{task.run_id}/cancel",
        )
        if task.status in {"pending", "running"}
        else None
    )
    error = P(task.error, cls="mt-1 text-xs text-red-700") if task.error else None
    return Div(
        P("自定义检验任务", cls="text-sm font-semibold text-gray-900"),
        detail,
        error,
        cancel,
        cls="rounded-xl border border-sky-200 bg-sky-50/50 p-4",
    )
