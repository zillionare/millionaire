"""NFR-0020 可访问性单元测试.

覆盖 acceptance.md AC-NFR0020-1:
- 主要文字与背景对比度 >= 4.5:1 (WCAG AA).
"""
from __future__ import annotations

import pytest

from quantide.web.nfr_accessibility import (
    MIN_CONTRAST_RATIO,
    contrast_ratio,
    hex_to_rgb,
    is_contrast_acceptable,
)


class TestHexToRgb:
    def test_short_hex(self):
        assert hex_to_rgb("#fff") == (255, 255, 255)

    def test_full_hex(self):
        assert hex_to_rgb("#ffffff") == (255, 255, 255)

    def test_black_hex(self):
        assert hex_to_rgb("#000000") == (0, 0, 0)


class TestRelativeLuminance:
    def test_white_luminance_is_one(self):
        from quantide.web.nfr_accessibility import relative_luminance

        assert relative_luminance((255, 255, 255)) == pytest.approx(1.0, abs=0.01)

    def test_black_luminance_is_zero(self):
        from quantide.web.nfr_accessibility import relative_luminance

        assert relative_luminance((0, 0, 0)) == pytest.approx(0.0, abs=0.01)


class TestContrastRatio:
    def test_black_on_white(self):
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)

    def test_white_on_white(self):
        assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)


class TestAcceptableContrast:
    """AC-NFR0020-1: 对比度 >= 4.5:1."""

    def test_dark_text_on_light_background_acceptable(self):
        assert is_contrast_acceptable("#333333", "#ffffff") is True

    def test_light_text_on_dark_background_acceptable(self):
        assert is_contrast_acceptable("#ffffff", "#333333") is True

    def test_low_contrast_rejected(self):
        assert is_contrast_acceptable("#888888", "#999999") is False
