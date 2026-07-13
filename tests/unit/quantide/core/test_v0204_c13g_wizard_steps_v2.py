"""v0.2-004-coverage-recovery C1.3g: quantide/core/wizard_steps_v2.py.

FR-0460 init-wizard v2 step metadata: the 10-step invariant table, per-kind
classifications, lookup boundaries, download-progress parent step, and the
reconfigurable-field allowlist (which excludes admin password and data_dir).

These tests target lines 106 (``return False`` in ``is_step_skippable`` for
non-OPTIONAL) and 121 (``return False`` for unknown step id) that were
previously uncovered.
"""

from __future__ import annotations

import dataclasses

import pytest

from quantide.core.wizard_steps_v2 import (
    WIZARD_STEPS_V2,
    WizardStep,
    WizardStepKind,
    get_download_progress_step,
    get_reconfigurable_fields,
    get_step_by_id,
    is_required_step,
    is_step_skippable,
)

EXPECTED_KINDS: dict[int, WizardStepKind] = {
    1: WizardStepKind.REQUIRED,
    2: WizardStepKind.REQUIRED,
    3: WizardStepKind.REQUIRED,
    4: WizardStepKind.REQUIRED,
    5: WizardStepKind.REQUIRED,
    6: WizardStepKind.OPTIONAL,
    7: WizardStepKind.REQUIRED,
    8: WizardStepKind.REQUIRED_PARENT,
    9: WizardStepKind.OPTIONAL,
    10: WizardStepKind.COMPLETION,
}

EXPECTED_NAMES: dict[int, str] = {
    1: "欢迎",
    2: "运行环境",
    3: "管理员账号",
    4: "数据目录",
    5: "Tushare 数据源",
    6: "交易网关",
    7: "首次下载范围",
    8: "下载进度",
    9: "通知配置",
    10: "完成",
}


def test_wizard_steps_v2_has_exactly_ten_steps() -> None:
    """AC-FR0700-37: WIZARD_STEPS_V2 contains exactly 10 entries."""
    assert len(WIZARD_STEPS_V2) == 10


def test_wizard_steps_v2_ids_are_one_through_ten_contiguous() -> None:
    """AC-FR0700-38: step ids are the contiguous range 1..10 with no gaps or duplicates."""
    ids = [s.step_id for s in WIZARD_STEPS_V2]
    assert ids == list(range(1, 11))


def test_wizard_steps_v2_each_step_kind_matches_expected_table() -> None:
    """AC-FR0700-39: every step's kind matches the FR-0460 AC-2 step table."""
    for step in WIZARD_STEPS_V2:
        assert step.kind == EXPECTED_KINDS[step.step_id], (
            f"step {step.step_id} kind mismatch"
        )


def test_wizard_steps_v2_each_step_name_matches_expected_table() -> None:
    """AC-FR0700-40: every step's display name matches the FR-0460 AC-2 step table."""
    for step in WIZARD_STEPS_V2:
        assert step.name == EXPECTED_NAMES[step.step_id], (
            f"step {step.step_id} name mismatch"
        )


def test_wizard_steps_v2_default_subtasks_deferrable_is_false() -> None:
    """AC-FR0700-41: only the REQUIRED_PARENT step (id 8) has subtasks_deferrable=True."""
    for step in WIZARD_STEPS_V2:
        if step.step_id == 8:
            assert step.subtasks_deferrable is True
        else:
            assert step.subtasks_deferrable is False


def test_wizard_step_is_frozen_dataclass() -> None:
    """AC-FR0700-42: WizardStep is frozen, so step instances are immutable."""
    step = WizardStep(step_id=1, name="x", kind=WizardStepKind.REQUIRED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.step_id = 999  # type: ignore[misc]


def test_wizard_step_kind_enum_values_are_lowercase_strings() -> None:
    """AC-FR0700-43: WizardStepKind enum string values match the documented lowercase tokens."""
    assert WizardStepKind.REQUIRED.value == "required"
    assert WizardStepKind.REQUIRED_PARENT.value == "required_parent"
    assert WizardStepKind.OPTIONAL.value == "optional"
    assert WizardStepKind.COMPLETION.value == "completion"


def test_get_step_by_id_returns_step_for_valid_ids() -> None:
    """AC-FR0700-44: get_step_by_id returns the correct step for ids 1 and 10."""
    first = get_step_by_id(1)
    last = get_step_by_id(10)
    assert first is not None and first.step_id == 1
    assert last is not None and last.step_id == 10


def test_get_step_by_id_returns_none_for_zero_and_above_range() -> None:
    """AC-FR0700-45: get_step_by_id returns None for id 0 and id 11 (out of range)."""
    assert get_step_by_id(0) is None
    assert get_step_by_id(11) is None


def test_get_step_by_id_returns_none_for_negative_id() -> None:
    """AC-FR0700-46: get_step_by_id returns None for a negative id."""
    assert get_step_by_id(-1) is None


def test_is_required_step_true_for_required_and_required_parent() -> None:
    """AC-FR0700-47: is_required_step returns True for REQUIRED (id 1) and REQUIRED_PARENT (id 8)."""
    assert is_required_step(1) is True
    assert is_required_step(8) is True


def test_is_required_step_false_for_optional_and_completion() -> None:
    """AC-FR0700-48: is_required_step returns False for OPTIONAL (id 6) and COMPLETION (id 10)."""
    assert is_required_step(6) is False
    assert is_required_step(10) is False


def test_is_required_step_false_for_unknown_id() -> None:
    """AC-FR0700-49: is_required_step returns False for an id that does not exist."""
    assert is_required_step(99) is False


def test_is_step_skippable_true_only_for_optional() -> None:
    """AC-FR0700-50: is_step_skippable returns True only for OPTIONAL steps (ids 6 and 9)."""
    assert is_step_skippable(6) is True
    assert is_step_skippable(9) is True


def test_is_step_skippable_false_for_required_required_parent_and_completion() -> None:
    """AC-FR0700-51: is_step_skippable returns False for REQUIRED, REQUIRED_PARENT, and COMPLETION."""
    assert is_step_skippable(1) is False
    assert is_step_skippable(8) is False
    assert is_step_skippable(10) is False


def test_is_step_skippable_false_for_unknown_id() -> None:
    """AC-FR0700-52: is_step_skippable returns False for an id that does not exist."""
    assert is_step_skippable(99) is False


def test_get_download_progress_step_returns_id_eight_deferrable() -> None:
    """AC-FR0700-53: get_download_progress_step returns step 8, REQUIRED_PARENT, deferrable."""
    step = get_download_progress_step()
    assert step is not None and step.step_id == 8
    assert step.kind == WizardStepKind.REQUIRED_PARENT
    assert step.subtasks_deferrable is True


def test_get_reconfigurable_fields_contains_all_documented_fields() -> None:
    """AC-FR0700-54: reconfigurable fields include all 11 documented allowlist entries."""
    fields = get_reconfigurable_fields()
    expected = {
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
    assert fields == expected
    assert len(fields) == 11


def test_get_reconfigurable_fields_excludes_admin_password_and_data_dir() -> None:
    """AC-FR0700-55: reconfigurable fields exclude admin password and data_dir."""
    fields = get_reconfigurable_fields()
    assert "admin_password" not in fields
    assert "password" not in fields
    assert "data_dir" not in fields
    assert "data_home" not in fields


def test_get_reconfigurable_fields_returns_frozenset() -> None:
    """AC-FR0700-56: reconfigurable fields are returned as a frozenset (immutable)."""
    fields = get_reconfigurable_fields()
    assert isinstance(fields, frozenset)
