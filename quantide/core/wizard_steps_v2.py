"""FR-0460 init-wizard 步骤定义 (v2).

v0.2-002-ui spec FR-0460 AC-2 定义的 10 步流程, 与现有
``quantide/core/init_wizard_steps.py`` 的 6 步定义并存.

本模块是 v0.2-002-ui 的步骤元数据单一来源, 不修改旧常量以避免破坏现有 wizard 页面.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WizardStepKind(str, Enum):
    """步骤类别.

    REQUIRED: 必选步骤, 不允许跳过, 必须填写并通过校验.
    REQUIRED_PARENT: 必选父步骤 (如下载进度), 不可跳过; 子任务失败可延后.
    OPTIONAL: 可选步骤, 允许跳过, 跳过后标"待处理".
    COMPLETION: 完成页 (终态).
    """

    REQUIRED = "required"
    REQUIRED_PARENT = "required_parent"
    OPTIONAL = "optional"
    COMPLETION = "completion"


@dataclass(frozen=True)
class WizardStep:
    """wizard 步骤元数据.

    Attributes:
        step_id: 步骤序号 (1-10).
        name: 步骤显示名.
        kind: 步骤类别.
        subtasks_deferrable: 子任务失败时是否可延后 (仅 REQUIRED_PARENT 有效).
    """

    step_id: int
    name: str
    kind: WizardStepKind
    subtasks_deferrable: bool = False


_WIZARD_STEPS_V2: tuple[WizardStep, ...] = (
    WizardStep(1, "欢迎", WizardStepKind.REQUIRED),
    WizardStep(2, "运行环境", WizardStepKind.REQUIRED),
    WizardStep(3, "管理员账号", WizardStepKind.REQUIRED),
    WizardStep(4, "数据目录", WizardStepKind.REQUIRED),
    WizardStep(5, "Tushare 数据源", WizardStepKind.REQUIRED),
    WizardStep(6, "交易网关", WizardStepKind.OPTIONAL),
    WizardStep(7, "首次下载范围", WizardStepKind.REQUIRED),
    WizardStep(8, "下载进度", WizardStepKind.REQUIRED_PARENT, subtasks_deferrable=True),
    WizardStep(9, "通知配置", WizardStepKind.OPTIONAL),
    WizardStep(10, "完成", WizardStepKind.COMPLETION),
)

# Public alias for tests and consumers; keeps internal tuple immutable.
WIZARD_STEPS_V2: tuple[WizardStep, ...] = _WIZARD_STEPS_V2

_RECONFIGURABLE_FIELDS: frozenset[str] = frozenset(
    {
        "app_host",
        "app_port",
        "app_prefix",
        "tushare_token",
        "gateway",
        "gateway_server",
        "gateway_port",
        "gateway_prefix",
        "gateway_api_key",
        "download_range",
        "notification_config",
    }
)


def get_step_by_id(step_id: int) -> WizardStep | None:
    """按 ID 查找步骤.

    Args:
        step_id: 步骤序号.

    Returns:
        步骤元数据; 无效 ID 返回 None.
    """
    for step in _WIZARD_STEPS_V2:
        if step.step_id == step_id:
            return step
    return None


def is_required_step(step_id: int) -> bool:
    """AC-2: 判定步骤是否必选.

    Args:
        step_id: 步骤序号.

    Returns:
        True 当步骤为 REQUIRED 或 REQUIRED_PARENT.
    """
    step = get_step_by_id(step_id)
    if step is None:
        return False
    return step.kind in (WizardStepKind.REQUIRED, WizardStepKind.REQUIRED_PARENT)


def is_step_skippable(step_id: int) -> bool:
    """AC-2: 判定步骤是否可跳过.

    Args:
        step_id: 步骤序号.

    Returns:
        True 当且仅当步骤为 OPTIONAL.
    """
    step = get_step_by_id(step_id)
    if step is None:
        return False
    return step.kind == WizardStepKind.OPTIONAL


def get_download_progress_step() -> WizardStep | None:
    """AC-2, AC-3: 获取下载进度父步骤.

    下载进度是必选父步骤, 子任务失败可延后.

    Returns:
        下载进度步骤元数据.
    """
    return get_step_by_id(8)


def get_reconfigurable_fields() -> frozenset[str]:
    """AC-5: 重新配置模式允许修改的字段.

    禁止修改: 管理员密码 (password / admin_password), 数据目录 (data_dir / data_home).

    Returns:
        可重新配置的字段名集合.
    """
    return _RECONFIGURABLE_FIELDS


__all__ = [
    "WIZARD_STEPS_V2",
    "WizardStep",
    "WizardStepKind",
    "get_download_progress_step",
    "get_reconfigurable_fields",
    "get_step_by_id",
    "is_required_step",
    "is_step_skippable",
]
