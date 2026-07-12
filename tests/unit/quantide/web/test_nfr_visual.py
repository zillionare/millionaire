"""NFR-0040 视觉与组件规范单元测试.

覆盖 acceptance.md AC-NFR0040-1~8:
- 字体尺寸规范
- 按钮风格统一 (主操作中性深色, 危险操作红色描边+文字, 不使用红色背景)
- Modal 规范
- 语义色彩一致
- 8px 基准网格 / 统一圆角
- 禁止大面积红色背景
"""
from __future__ import annotations

import pytest

from quantide.web.nfr_visual import (
    BUTTON_RADIUS_PX,
    CARD_RADIUS_PX,
    MODAL_RADIUS_PX,
    SEMANTIC_COLORS,
    SPACING_GRID,
    TYPOGRAPHY,
    button_style,
    is_spacing_grid_compliant,
    is_valid_background_color,
    modal_spec,
)


class TestTypography:
    """AC-NFR0040-1: 字体尺寸规范."""

    def test_page_title_size(self):
        assert TYPOGRAPHY["page_title"] == "24px"

    def test_section_title_size(self):
        assert TYPOGRAPHY["section_title"] == "18px"

    def test_body_size(self):
        assert TYPOGRAPHY["body"] == "14px"

    def test_table_size(self):
        assert TYPOGRAPHY["table"] == "13px"

    def test_helper_size(self):
        assert TYPOGRAPHY["helper"] == "12px"


class TestButtonStyles:
    """AC-NFR0040-2: 按钮风格."""

    def test_primary_button_neutral_dark_background(self):
        style = button_style("primary")
        assert style["background"] == "neutral-dark"
        assert style["color"] == "white"
        assert style["border_radius_px"] == BUTTON_RADIUS_PX

    def test_secondary_button_outline(self):
        style = button_style("secondary")
        assert style["variant"] == "outline"

    def test_danger_button_no_red_background(self):
        """危险操作使用红色描边+文字, 不使用红色背景."""
        style = button_style("danger")
        assert style["background"] is None
        assert style["border_color"] == "red"
        assert style["color"] == "red"

    def test_unknown_variant_falls_back_to_secondary(self):
        style = button_style("ghost")
        assert style["variant"] == "outline"


class TestModalSpec:
    """AC-NFR0040-3: Modal 规范."""

    def test_modal_centered(self):
        spec = modal_spec()
        assert spec["position"] == "center"

    def test_modal_has_overlay(self):
        assert modal_spec()["overlay"] is True

    def test_modal_has_close_button(self):
        assert modal_spec()["close_button"] is True


class TestSemanticColors:
    """AC-NFR0040-4: 语义色彩一致."""

    def test_semantic_colors_defined(self):
        assert "success" in SEMANTIC_COLORS
        assert "error" in SEMANTIC_COLORS
        assert "warning" in SEMANTIC_COLORS
        assert "info" in SEMANTIC_COLORS
        assert "neutral" in SEMANTIC_COLORS


class TestSpacingGrid:
    """AC-NFR0040-5: 8px 基准网格."""

    def test_common_spacings(self):
        assert 4 in SPACING_GRID
        assert 8 in SPACING_GRID
        assert 16 in SPACING_GRID
        assert 24 in SPACING_GRID
        assert 32 in SPACING_GRID

    def test_compliant_spacing(self):
        assert is_spacing_grid_compliant(16) is True

    def test_non_compliant_spacing(self):
        assert is_spacing_grid_compliant(15) is False


class TestRadius:
    """AC-NFR0040-6: 统一圆角."""

    def test_button_radius(self):
        assert BUTTON_RADIUS_PX == 4

    def test_card_radius(self):
        assert CARD_RADIUS_PX == 8

    def test_modal_radius(self):
        assert MODAL_RADIUS_PX == 12


class TestNoLargeRedBackground:
    """AC-NFR0040-7: 不允许大面积红色背景."""

    def test_red_background_rejected(self):
        assert is_valid_background_color("red") is False

    def test_dark_background_acceptable(self):
        assert is_valid_background_color("neutral-dark") is True

    def test_white_background_acceptable(self):
        assert is_valid_background_color("white") is True

    def test_none_background_acceptable(self):
        assert is_valid_background_color(None) is True
