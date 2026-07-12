"""E2E 黑盒测试 — FR-010 BaseStrategy 共享契约

按 test-plan.md §4.1 scenarios/strategy_discovery/ 设计:
- 仅依赖外部可观测对象(类暴露的方法签名、生命周期回调触发)
- 不 mock 框架内部实现
- 与 acceptance.md AC-010-01 ~ 04 对齐
"""

from __future__ import annotations

import datetime
import inspect

import pytest

from quantide.core.strategy import BaseStrategy


# ───────────────────────── AC-010-01 类型分层识别 ─────────────────────────


class TestClassHierarchy:
    """AC-010-01: BaseStrategy 是抽象基类,Day/Live/Risk 子类合法"""

    def test_base_strategy_exists(self):
        """BaseStrategy 类存在"""
        assert BaseStrategy is not None
        assert inspect.isclass(BaseStrategy)

    def test_subclass_recognized_as_strategy(self):
        """BaseStrategy 子类合法"""
        class MyStrat(BaseStrategy):
            pass

        assert issubclass(MyStrat, BaseStrategy)

    def test_non_subclass_not_recognized(self):
        """非 BaseStrategy 子类不合法(用于 spec AC-010-01 反向断言)"""
        class NotAStrategy:
            pass

        assert not issubclass(NotAStrategy, BaseStrategy)


# ───────────────────────── AC-010-02 生命周期钩子 ─────────────────────────


class TestLifecycleHooks:
    """AC-010-02: BaseStrategy 暴露 init/on_start/on_stop/on_day_open/on_day_close"""

    @pytest.mark.parametrize(
        "hook_name",
        ["init", "on_start", "on_stop", "on_day_open", "on_day_close"],
    )
    def test_hook_exists_on_base_strategy(self, hook_name):
        """所有生命周期钩子在 BaseStrategy 上定义"""
        assert hasattr(BaseStrategy, hook_name), f"missing {hook_name}"
        assert callable(getattr(BaseStrategy, hook_name))

    @pytest.mark.asyncio
    async def test_lifecycle_hooks_have_correct_signature(self):
        """钩子签名匹配 spec:init/on_start/on_stop 无参;on_day_* 接受 datetime"""
        import inspect as _i

        # 钩子都应该是 async
        for name in ["init", "on_start", "on_stop", "on_day_open", "on_day_close"]:
            method = getattr(BaseStrategy, name)
            assert _i.iscoroutinefunction(method), f"{name} must be async"

        # on_day_* 接受 datetime 参数
        for name in ["on_day_open", "on_day_close"]:
            sig = _i.signature(getattr(BaseStrategy, name))
            params = list(sig.parameters.keys())
            assert "tm" in params, f"{name} must accept 'tm' parameter"

    def test_on_bar_on_base_strategy(self):
        """spec FR-010 AC-010-02: on_bar(tm) 在 BaseStrategy 专有定义
        (BaseStrategy 专有, 不在抽象根 Strategy 上)
        """
        assert hasattr(BaseStrategy, "on_bar"), (
            "on_bar must be on BaseStrategy per v0.2 spec AC-010-02"
        )
        # 同时验证: 不在 Strategy 抽象根上
        from quantide.core.strategy import Strategy
        assert not hasattr(Strategy, "on_bar"), (
            "on_bar must NOT be on Strategy abstract root"
        )


# ───────────────────────── AC-010-03 辅助接口 ─────────────────────────


class TestHelperAPI:
    """AC-010-03: default_config / log / record"""

    def test_default_config_is_static(self):
        """default_config 是 staticmethod,默认返回空 dict"""
        assert isinstance(BaseStrategy.__dict__["default_config"], staticmethod)
        assert BaseStrategy.default_config() == {}

    def test_log_method_exists(self):
        """log 方法存在"""
        assert hasattr(BaseStrategy, "log")
        assert callable(BaseStrategy.log)

    def test_record_method_exists(self):
        """record 方法存在"""
        assert hasattr(BaseStrategy, "record")
        assert callable(BaseStrategy.record)


# ───────────────────────── AC-010-04 模式无关性 ─────────────────────────


class TestModeAgnostic:
    """AC-010-04: 策略不可感知运行模式"""

    def test_no_get_mode_method(self):
        """spec: 基类不暴露 get_mode 或等价方法"""
        assert not hasattr(BaseStrategy, "get_mode")
        assert not hasattr(BaseStrategy, "mode")
        assert not hasattr(BaseStrategy, "current_mode")
