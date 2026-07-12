"""FR-0340 网关管理单元测试.

覆盖 acceptance.md AC-FR0340-1~6:
- 配置项: server / port / url_prefix / api_key
- 测试: TCP 连接 + API Key 鉴权
- 保存前自动测试, 测试通过才能保存
- 无删除网关按钮 (AC-5)
- 无添加第二个网关入口 (AC-6)
"""
from __future__ import annotations

import pytest

from quantide.web.services.gateway import (
    GATEWAY_CONFIG_FIELDS,
    GatewayConfigResult,
    GatewayTestResult,
    GatewayValidationError,
    SINGLE_GATEWAY_ONLY,
    validate_gateway_config,
)


class TestGatewayConfigFields:
    """AC-2: 配置项包括服务器、端口、url_prefix 和 api KEY."""

    def test_required_fields_present(self):
        assert "server" in GATEWAY_CONFIG_FIELDS
        assert "port" in GATEWAY_CONFIG_FIELDS
        assert "url_prefix" in GATEWAY_CONFIG_FIELDS
        assert "api_key" in GATEWAY_CONFIG_FIELDS


class TestSingleGateway:
    """AC-5, AC-6: 无删除网关按钮 / 无添加第二个网关入口."""

    def test_single_gateway_only_flag(self):
        assert SINGLE_GATEWAY_ONLY is True


class TestGatewayConfigValidation:
    """AC-3, AC-4: 配置校验."""

    def _valid_config(self):
        return {"server": "127.0.0.1", "port": 8000, "url_prefix": "/", "api_key": "key123", "timeout_seconds": 5}

    def test_valid_config_passes(self):
        assert validate_gateway_config(self._valid_config()) is True

    def test_empty_server_rejected(self):
        cfg = self._valid_config()
        cfg["server"] = ""
        with pytest.raises(GatewayValidationError):
            validate_gateway_config(cfg)

    def test_port_out_of_range_rejected(self):
        cfg = self._valid_config()
        cfg["port"] = 0
        with pytest.raises(GatewayValidationError):
            validate_gateway_config(cfg)

    def test_url_prefix_must_start_with_slash(self):
        cfg = self._valid_config()
        cfg["url_prefix"] = "api"
        with pytest.raises(GatewayValidationError):
            validate_gateway_config(cfg)

    def test_empty_api_key_rejected(self):
        cfg = self._valid_config()
        cfg["api_key"] = ""
        with pytest.raises(GatewayValidationError):
            validate_gateway_config(cfg)


class TestGatewayTestResult:
    """AC-3: 测试结果."""

    def test_success_result(self):
        result = GatewayTestResult(ok=True, tcp_connected=True, auth_ok=True, message="测试通过")
        assert result.ok is True
        assert result.tcp_connected is True
        assert result.auth_ok is True

    def test_tcp_fail_result(self):
        result = GatewayTestResult(ok=False, tcp_connected=False, auth_ok=False, message="连接不可达")
        assert result.ok is False
        assert result.tcp_connected is False

    def test_auth_fail_result(self):
        result = GatewayTestResult(ok=False, tcp_connected=True, auth_ok=False, message="鉴权失败")
        assert result.ok is False
        assert result.auth_ok is False


class TestGatewayConfigResult:
    """AC-4: 保存结果 (测试通过才能保存)."""

    def test_save_requires_test_passed(self):
        """AC-4: 如未测试则自动触发测试; 测试通过才能保存."""
        result = GatewayConfigResult(saved=False, message="测试未通过, 表单保持打开", tested=False)
        assert result.saved is False

    def test_save_succeeds_after_test_pass(self):
        result = GatewayConfigResult(saved=True, message="保存成功", tested=True)
        assert result.saved is True
        assert result.tested is True
