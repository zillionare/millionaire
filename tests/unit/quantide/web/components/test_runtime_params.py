"""FR-0020 运行时参数编辑单元测试.

覆盖 acceptance.md AC-FR0020-1~4:
- 字段: 本金/滑点/印花税比率/佣金比率/单笔最低佣金
- 默认值: 本金取上一次值, 滑点 0, 印花税 0.001, 佣金 0.0001, 最低佣金 5
- 校验: 本金 > 0; 滑点 0~0.1; 印花税 0~0.01; 佣金 0~0.01; 最低佣金 >= 0
- 不写入回测结果 (localStorage 缓存最近一次值)
"""
from __future__ import annotations

import pytest

from quantide.web.components.runtime_params import (
    DEFAULT_RUNTIME_PARAMS,
    RuntimeParams,
    RuntimeParamsError,
    validate_runtime_params,
)


class TestDefaults:
    """AC-1: 默认值."""

    def test_default_values(self):
        assert DEFAULT_RUNTIME_PARAMS.principal is None  # 取上一次值
        assert DEFAULT_RUNTIME_PARAMS.slippage_rate == 0
        assert DEFAULT_RUNTIME_PARAMS.stamp_tax_rate == 0.001
        assert DEFAULT_RUNTIME_PARAMS.commission_rate == 0.0001
        assert DEFAULT_RUNTIME_PARAMS.min_commission == 5


class TestPrincipalValidation:
    """AC-2: 本金 > 0."""

    def test_positive_principal_ok(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        assert validate_runtime_params(params) is True

    def test_zero_principal_rejected(self):
        params = RuntimeParams(principal=0, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "本金必须 > 0" in str(exc.value)

    def test_negative_principal_rejected(self):
        """AC-2: 本金 -100 -> 提交被阻止."""
        params = RuntimeParams(principal=-100, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "本金必须 > 0" in str(exc.value)


class TestSlippageValidation:
    """AC-2: 滑点 0~0.1."""

    def test_slippage_zero_ok(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        assert validate_runtime_params(params) is True

    def test_slippage_at_upper_bound_ok(self):
        params = RuntimeParams(principal=100000, slippage_rate=0.1, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        assert validate_runtime_params(params) is True

    def test_slippage_too_high_rejected(self):
        """AC-2: 滑点 0.2 -> 提交被阻止."""
        params = RuntimeParams(principal=100000, slippage_rate=0.2, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "滑点" in str(exc.value)

    def test_negative_slippage_rejected(self):
        params = RuntimeParams(principal=100000, slippage_rate=-0.01, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=5)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "滑点" in str(exc.value)


class TestStampTaxValidation:
    """AC: 印花税 0~0.01."""

    def test_stamp_tax_zero_ok(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0, commission_rate=0.0001, min_commission=5)
        assert validate_runtime_params(params) is True

    def test_stamp_tax_at_upper_bound_ok(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.01, commission_rate=0.0001, min_commission=5)
        assert validate_runtime_params(params) is True

    def test_stamp_tax_too_high_rejected(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.02, commission_rate=0.0001, min_commission=5)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "印花税" in str(exc.value)


class TestCommissionValidation:
    """AC: 佣金 0~0.01."""

    def test_commission_too_high_rejected(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.05, min_commission=5)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "佣金" in str(exc.value)


class TestMinCommissionValidation:
    """AC: 单笔最低佣金 >= 0."""

    def test_min_commission_zero_ok(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=0)
        assert validate_runtime_params(params) is True

    def test_negative_min_commission_rejected(self):
        params = RuntimeParams(principal=100000, slippage_rate=0, stamp_tax_rate=0.001, commission_rate=0.0001, min_commission=-1)
        with pytest.raises(RuntimeParamsError) as exc:
            validate_runtime_params(params)
        assert "最低佣金" in str(exc.value)
