"""FR-0460 init-wizard 步骤定义单元测试.

覆盖 acceptance.md AC-FR0460-2, AC-3, AC-5:
- 10 步流程 (欢迎 -> 运行环境 -> 管理员账号 -> 数据目录 -> Tushare -> 交易网关(可选) -> 首次下载范围 -> 下载进度(必选) -> 通知配置(可选) -> 完成)
- 必选步骤不允许跳过; 可选步骤可跳过标"待处理"
- 重新配置模式禁止改管理员密码与数据目录
- 下载进度是必选父步骤, 子任务失败可延后
"""
from __future__ import annotations

import pytest

from quantide.core.wizard_steps_v2 import (
    WizardStep,
    WizardStepKind,
    WIZARD_STEPS_V2,
    get_download_progress_step,
    get_reconfigurable_fields,
    get_step_by_id,
    is_required_step,
    is_step_skippable,
)


class TestWizardStepsV2Definition:
    """AC-2: 10 步流程定义."""

    def test_has_ten_steps(self):
        assert len(WIZARD_STEPS_V2) == 10

    def test_step_ids_sequential(self):
        ids = [s.step_id for s in WIZARD_STEPS_V2]
        assert ids == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    def test_step_names_match_spec(self):
        names = [s.name for s in WIZARD_STEPS_V2]
        assert names[0] == "欢迎"
        assert names[1] == "运行环境"
        assert names[2] == "管理员账号"
        assert names[3] == "数据目录"
        assert names[4] == "Tushare 数据源"
        assert names[5] == "交易网关"
        assert names[6] == "首次下载范围"
        assert names[7] == "下载进度"
        assert names[8] == "通知配置"
        assert names[9] == "完成"


class TestRequiredVsOptional:
    """AC-2: 必选/可选步骤标记."""

    @pytest.mark.parametrize("step_id", [1, 2, 3, 4, 5, 7, 8])
    def test_required_steps(self, step_id):
        """必选步骤: 欢迎/运行环境/管理员账号/数据目录/Tushare/首次下载范围/下载进度."""
        assert is_required_step(step_id) is True
        assert is_step_skippable(step_id) is False

    @pytest.mark.parametrize("step_id", [6, 9])
    def test_optional_steps(self, step_id):
        """可选步骤: 交易网关/通知配置 - 允许跳过."""
        assert is_required_step(step_id) is False
        assert is_step_skippable(step_id) is True

    def test_completion_step_not_skippable(self):
        """完成页不是可跳过步骤."""
        assert is_step_skippable(10) is False

    def test_completion_step_not_required(self):
        """完成页不是 required (它只是终态)."""
        assert is_required_step(10) is False


class TestDownloadProgressParentStep:
    """AC-2, AC-3: 下载进度是必选父步骤, 子任务失败可延后."""

    def test_download_progress_is_required_parent(self):
        step = get_download_progress_step()
        assert step is not None
        assert step.step_id == 8
        assert step.kind == WizardStepKind.REQUIRED_PARENT

    def test_download_progress_not_skippable(self):
        """父步骤不能跳过."""
        assert is_step_skippable(8) is False

    def test_download_progress_subtasks_can_defer(self):
        """AC-3: 子任务失败可延后, 标'待处理', 父步骤不阻断."""
        step = get_download_progress_step()
        assert step is not None
        assert step.subtasks_deferrable is True


class TestReconfigurableFields:
    """AC-5: 重新配置模式禁止改管理员密码与数据目录."""

    def test_password_not_reconfigurable(self):
        """AC-5: 重新配置时不允许修改管理员密码字段."""
        fields = get_reconfigurable_fields()
        assert "password" not in fields
        assert "admin_password" not in fields

    def test_data_dir_not_reconfigurable(self):
        """AC-5: 重新配置时不允许修改数据目录字段."""
        fields = get_reconfigurable_fields()
        assert "data_dir" not in fields
        assert "data_home" not in fields

    def test_gateway_reconfigurable(self):
        """交易网关可在重新配置时调整."""
        fields = get_reconfigurable_fields()
        assert "gateway" in fields or "gateway_server" in fields

    def test_tushare_reconfigurable(self):
        fields = get_reconfigurable_fields()
        assert "tushare_token" in fields


class TestGetStepById:
    def test_returns_step(self):
        step = get_step_by_id(5)
        assert step is not None
        assert step.name == "Tushare 数据源"

    def test_returns_none_for_invalid_id(self):
        assert get_step_by_id(99) is None


class TestStepModel:
    def test_step_carries_metadata(self):
        step = WizardStep(
            step_id=6,
            name="交易网关",
            kind=WizardStepKind.OPTIONAL,
            subtasks_deferrable=False,
        )
        assert step.kind == WizardStepKind.OPTIONAL
        assert step.subtasks_deferrable is False
