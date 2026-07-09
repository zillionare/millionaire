"""FR-0180 功能降级状态机单元测试.

覆盖 acceptance.md AC-FR0180-1~23:
- A 类降级 (永久, 无网关): 入口禁用 / 503 / 回测仍可用 / 网关管理仍可用 / 配置后立即解除
- B 类降级 (临时, 网关偶发不可连): 黄色 banner / stale 可接受 / 恢复后 banner 消失
- A/B 转换规则: A 配置后立即变正常; B 永不升级为 A; B 期间后台行为非 UI 职责
"""
from __future__ import annotations

import pytest

from quantide.web.degradation import (
    DegradationClass,
    DegradationState,
    GatewayConfig,
    classify_degradation,
    entrance_disabled,
    is_backtest_available,
    is_gateway_management_available,
    is_trade_entrance_available,
    tooltip_message,
)


class TestDegradationClass:
    """AC-1~7, AC-17~19: A 类降级入口禁用规则."""

    def test_no_gateway_configured_is_class_a(self):
        """AC-1: 无网关配置 -> A 类降级."""
        state = DegradationState(gateway_configured=False, gateway_online=False)
        assert classify_degradation(state) == DegradationClass.A

    def test_gateway_configured_but_offline_is_class_b(self):
        """AC-9: 有网关但断线 -> B 类降级."""
        state = DegradationState(gateway_configured=True, gateway_online=False)
        assert classify_degradation(state) == DegradationClass.B

    def test_gateway_configured_and_online_is_normal(self):
        """正常状态: 配置 + 在线."""
        state = DegradationState(gateway_configured=True, gateway_online=True)
        assert classify_degradation(state) is None


class TestTradeEntranceDisabled:
    """AC-1, AC-3, AC-4, AC-6, AC-17: A 类降级时交易入口禁用."""

    @pytest.mark.parametrize(
        "entrance",
        ["trade_live", "trade_paper", "promote_to_live", "promote_to_paper", "live_order", "live_cancel"],
    )
    def test_class_a_disables_trade_entrances(self, entrance):
        """A 类降级禁用所有依赖 gateway 的入口."""
        assert entrance_disabled(entrance, DegradationClass.A) is True

    def test_class_a_disables_trade_nav(self):
        """AC-17: A 类降级时顶栏'交易'菜单禁用."""
        assert is_trade_entrance_available(DegradationClass.A) is False

    def test_class_b_keeps_trade_entrance_available(self):
        """B 类降级不禁用入口 (只显示 banner)."""
        assert is_trade_entrance_available(DegradationClass.B) is True

    def test_normal_keeps_trade_entrance_available(self):
        assert is_trade_entrance_available(None) is True


class TestBacktestStillAvailable:
    """AC-5, AC-19: A 类降级时回测仍可用."""

    def test_class_a_backtest_available(self):
        """AC-5: A 类降级时'启动回测'入口仍可用."""
        assert is_backtest_available(DegradationClass.A) is True

    def test_class_b_backtest_available(self):
        assert is_backtest_available(DegradationClass.B) is True

    def test_normal_backtest_available(self):
        assert is_backtest_available(None) is True


class TestGatewayManagementAvailable:
    """AC-7: A 类降级时网关管理仍可用 (用来配置 gateway)."""

    def test_class_a_gateway_management_available(self):
        assert is_gateway_management_available(DegradationClass.A) is True

    def test_normal_gateway_management_available(self):
        assert is_gateway_management_available(None) is True


class TestTooltipMessage:
    """AC-1, AC-18: A 类降级 hover tooltip 文案."""

    def test_class_a_tooltip_text(self):
        """AC-18: hover 显示 tooltip '此功能因交易网关未配置而无法使用'."""
        msg = tooltip_message(DegradationClass.A)
        assert "交易网关未配置" in msg
        assert "无法使用" in msg

    def test_class_b_no_tooltip(self):
        """B 类降级不显示入口 tooltip (用 banner)."""
        assert tooltip_message(DegradationClass.B) is None

    def test_normal_no_tooltip(self):
        assert tooltip_message(None) is None


class TestClassATransition:
    """AC-8, AC-13, AC-14: A 类配置 gateway 后立即解除."""

    def test_class_a_resolves_immediately_after_config(self):
        """AC-8, AC-13: A 类降级时配置 gateway -> 立即变正常 (不需测试通过)."""
        state = DegradationState(gateway_configured=False, gateway_online=False)
        assert classify_degradation(state) == DegradationClass.A

        state.gateway_configured = True
        state.gateway_online = True
        assert classify_degradation(state) is None

    def test_class_a_configured_but_untested_goes_to_b(self):
        """AC-14: A 类期间提交无效 gateway (配置了但连不上) -> B 类."""
        state = DegradationState(gateway_configured=False, gateway_online=False)
        state.gateway_configured = True
        state.gateway_online = False
        assert classify_degradation(state) == DegradationClass.B


class TestClassBNeverUpgradesToA:
    """AC-15: B 类永不升级为 A 类."""

    def test_class_b_stays_b_when_offline(self):
        """B 类临时降级不会变永久."""
        state = DegradationState(gateway_configured=True, gateway_online=False)
        assert classify_degradation(state) == DegradationClass.B

    def test_class_b_recovers_to_normal_when_online(self):
        """B 类恢复后变正常 (不经过 A)."""
        state = DegradationState(gateway_configured=True, gateway_online=False)
        state.gateway_online = True
        assert classify_degradation(state) is None


class TestBannerContent:
    """AC-9, AC-20, AC-21, AC-22: B 类降级 banner 内容."""

    def test_class_b_banner_has_warning_color(self):
        """AC-20: banner 背景黄色, 文字/图标红色 (非大面积红色背景)."""
        from quantide.web.degradation import banner_colors

        colors = banner_colors(DegradationClass.B)
        assert colors["background"] == "yellow"
        assert colors["text"] == "red"
        assert colors["icon"] == "red"

    def test_class_a_no_banner(self):
        """A 类降级用入口禁用, 不用 banner."""
        from quantide.web.degradation import banner_colors

        assert banner_colors(DegradationClass.A) is None

    def test_normal_no_banner(self):
        from quantide.web.degradation import banner_colors

        assert banner_colors(None) is None


class TestGatewayConfigValidation:
    """AC-8: gateway 配置字段校验 (用于 A 类解除判定)."""

    def test_valid_config(self):
        cfg = GatewayConfig(server="127.0.0.1", port=8000, url_prefix="/", api_key="key123", timeout_seconds=5)
        assert cfg.is_valid() is True

    def test_empty_server_invalid(self):
        cfg = GatewayConfig(server="", port=8000, url_prefix="/", api_key="key", timeout_seconds=5)
        assert cfg.is_valid() is False

    def test_port_out_of_range_invalid(self):
        cfg = GatewayConfig(server="127.0.0.1", port=0, url_prefix="/", api_key="key", timeout_seconds=5)
        assert cfg.is_valid() is False
        cfg2 = GatewayConfig(server="127.0.0.1", port=70000, url_prefix="/", api_key="key", timeout_seconds=5)
        assert cfg2.is_valid() is False

    def test_url_prefix_must_start_with_slash(self):
        cfg = GatewayConfig(server="127.0.0.1", port=8000, url_prefix="api", api_key="key", timeout_seconds=5)
        assert cfg.is_valid() is False

    def test_empty_api_key_invalid(self):
        cfg = GatewayConfig(server="127.0.0.1", port=8000, url_prefix="/", api_key="", timeout_seconds=5)
        assert cfg.is_valid() is False

    def test_timeout_must_be_positive(self):
        cfg = GatewayConfig(server="127.0.0.1", port=8000, url_prefix="/", api_key="key", timeout_seconds=0)
        assert cfg.is_valid() is False
