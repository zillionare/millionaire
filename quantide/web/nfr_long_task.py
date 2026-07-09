"""NFR-0060 长任务交互.

定义长任务进度展示文案、SSE 断线提示与断点恢复语义.

AC-NFR0060-1/AC-5: init-wizard 步骤式进度 (百分比 + 当前步骤名 + current/total).
AC-NFR0060-5b: 数据同步任务列表进度 (百分比 + 当前任务名).
AC-NFR0060-2: 中断后从失败步骤继续, 已完成步骤不丢失.
AC-NFR0060-3: SSE 断线 -> "连接中断, 正在重连...".
AC-NFR0060-4: 页面重入恢复到当前步骤.
"""

from __future__ import annotations


def format_step_progress(
    percent: int,
    step_name: str,
    current_step: int,
    total_steps: int,
) -> str:
    """格式化步骤式进度文案.

    Args:
        percent: 百分比整数 (0-100).
        step_name: 当前步骤名.
        current_step: 当前步骤序号.
        total_steps: 总步骤数.

    Returns:
        "{percent}% · {step_name} ({current_step}/{total_steps})".
    """
    return f"{percent}% · {step_name} ({current_step}/{total_steps})"


def format_task_progress(percent: int, task_name: str) -> str:
    """格式化数据同步任务列表进度文案.

    Args:
        percent: 百分比整数.
        task_name: 当前任务名.

    Returns:
        "{percent}% · {task_name}".
    """
    return f"{percent}% · {task_name}"


def sse_reconnect_message() -> str:
    """AC-NFR0060-3: SSE 断线重连提示."""
    return "连接中断, 正在重连..."


def resume_from_checkpoint(failed_step: int) -> dict[str, object]:
    """AC-NFR0060-2: 从失败步骤恢复, 保留已完成步骤.

    Args:
        failed_step: 失败步骤序号 (从该步骤继续).

    Returns:
        恢复信息字典.
    """
    return {
        "resume_from_step": failed_step,
        "preserve_completed_steps": True,
    }


def is_progress_page_reentry_valid(current_step: int, total_steps: int) -> bool:
    """AC-NFR0060-4: 判断进度页面重入状态是否合法.

    Args:
        current_step: 当前步骤序号.
        total_steps: 总步骤数.

    Returns:
        True 当 current_step 在 [1, total_steps] 范围内.
    """
    return 1 <= current_step <= total_steps


__all__ = [
    "format_step_progress",
    "format_task_progress",
    "is_progress_page_reentry_valid",
    "resume_from_checkpoint",
    "sse_reconnect_message",
]
