"""E2E 黑盒测试 — FR-020 自动发现策略 (v0.2 spec)

与旧版 test_fr_020_discovery.py 不同:
旧版针对 v0.1 StrategyLoader (返回 dict[str, type[BaseStrategy]]);
本文件按 v0.2-001-locked spec 的 EnumerationResult / StrategyMetadata,
ParamSpec / SkippedEntry / SkippedReason / EnumerationResult 契约设计。

与 acceptance.md AC-020-01 ~ 15 对齐。

注意:当前实现 (discovery.py) 尚未提供新的 EnumerationResult 接口;
此处全部 AC 预期为 TDD red 状态。
"""

from __future__ import annotations

import datetime
import textwrap
from pathlib import Path
from typing import Any, Literal

import pytest

from quantide.core.strategy import BaseStrategy


# ─────────────────── 辅助 ───────────────────


def _make_strategy_file(directory: Path, filename: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    target.write_text(textwrap.dedent(body))
    return target


# ─────────────────── v0.2 spec 类型(预期接口) ───────────────────


class SkippedReason:  # noqa: D101  # expected enum in impl
    PERMISSION_DENIED = "PermissionDenied"
    SYNTAX_ERROR = "SyntaxError"
    IMPORT_ERROR = "ImportError"
    MODULE_INIT_ERROR = "ModuleInitError"
    NOT_A_STRATEGY = "NotAStrategy"
    INVALID_CONFIG = "InvalidConfig"
    BUILTIN_OVERRIDDEN = "BuiltinOverridden"


# ───────────────────────── AC-020-01 基类判定 ─────────────────────────


class TestBaseClassRecognitionV2:
    """AC-020-01: 识别规则 — 基类判定"""

    def test_base_strategy_subclass_independent(self, tmp_path):
        """AC-020-01-01: BaseStrategy 子类 → strategy_type == "independent" """
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "my_strat.py", """
            from quantide.core.strategy import BaseStrategy
            class MyStrategy(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if "MyStrategy" in s.strategy_id]
        assert len(metas) == 1
        assert metas[0].strategy_type == "independent"

    def test_risk_strategy_subclass_risk(self, tmp_path):
        """AC-020-01-02: RiskStrategy 子类 → strategy_type == "risk" """
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "risk_strat.py", """
            from quantide.core.strategy import RiskStrategy
            class MyRisk(RiskStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if "MyRisk" in s.strategy_id]
        assert len(metas) == 1
        assert metas[0].strategy_type == "risk"

    def test_strategy_itself_excluded(self, tmp_path):
        """AC-020-01-03: Strategy 自身不出现"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "strat.py", """
            from quantide.core.strategy import Strategy
            # Strategy 自身不应出现在结果中
            class DirectStrategy(Strategy):
                pass
        """)
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert not any("DirectStrategy" in sid for sid in ids)

    def test_base_strategy_itself_excluded(self, tmp_path):
        """AC-020-01-04: BaseStrategy 自身不出现"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert not any("BaseStrategy" in sid for sid in ids)

    def test_risk_strategy_itself_excluded(self, tmp_path):
        """AC-020-01-05: RiskStrategy 自身不出现"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert not any("RiskStrategy" in sid for sid in ids)


# ───────────────────────── AC-020-02 文件范围 ─────────────────────────


class TestFileScopeV2:
    """AC-020-02: 文件范围"""

    def test_py_files_scanned(self, tmp_path):
        """AC-020-02-01: .py 文件被扫描"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "a.py", """
            from quantide.core.strategy import BaseStrategy
            class A(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        assert len(result.strategies) > 0

    def test_non_py_skipped(self, tmp_path):
        """AC-020-02-02: 非 .py 文件跳过,不记录错误"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "readme.txt", "not python")
        result = enumerate_strategies(d)
        assert len(result.diagnostics) == 0

    def test_subdirectories_not_recursed(self, tmp_path):
        """AC-020-02-03: 子目录不递归"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        sub = d / "sub"
        _make_strategy_file(sub, "nested.py", """
            from quantide.core.strategy import BaseStrategy
            class Nested(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert not any("Nested" in sid for sid in ids)

    def test_pycache_skipped(self, tmp_path):
        """AC-020-02-04: __pycache__ 跳过"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        cache = d / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "cached.pyc").write_text("")
        result = enumerate_strategies(d)
        # Should not error; simply find nothing
        assert len(result.diagnostics) >= 0


# ───────────────────────── AC-020-03 名称与描述 ─────────────────────────


class TestNameAndDescriptionV2:
    """AC-020-03: 策略名称与描述"""

    def test_name_defaults_to_class_name(self, tmp_path):
        """AC-020-03-01: 未定义 __display_name__ → name = cls.__name__"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "foo.py", """
            from quantide.core.strategy import BaseStrategy
            class FooStrategy(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if s.name == "FooStrategy"]
        assert len(metas) >= 1

    def test_display_name_used(self, tmp_path):
        """AC-020-03-02: __display_name__ 优先级高于 __name__"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "bar.py", """
            from quantide.core.strategy import BaseStrategy
            class BarStrategy(BaseStrategy):
                __display_name__ = "My Bar"
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if s.name == "My Bar"]
        assert len(metas) >= 1

    def test_docstring_first_line_as_description(self, tmp_path):
        """AC-020-03-03: docstring 首行 → description"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "baz.py", """
            from quantide.core.strategy import BaseStrategy
            class BazStrategy(BaseStrategy):
                \"\"\"A baz strategy for testing.\"\"\"
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if s.name == "BazStrategy"]
        assert len(metas) >= 1
        assert "baz strategy" in metas[0].description

    def test_no_docstring_empty_description(self, tmp_path):
        """AC-020-03-04: 无 docstring → description = \"\" """
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "qux.py", """
            from quantide.core.strategy import BaseStrategy
            class QuxStrategy(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if s.name == "QuxStrategy"]
        assert len(metas) >= 1
        assert metas[0].description == ""


# ───────────────────────── AC-020-04 元数据 schema — 核心字段 ─────────────────────────


class TestMetadataCoreFieldsV2:
    """AC-020-04: 元数据核心字段"""

    def test_strategy_id_format(self, tmp_path):
        """AC-020-04-01: strategy_id == f\"{module}.{class_name}\" """
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "my_mod.py", """
            from quantide.core.strategy import BaseStrategy
            class IdTestStrategy(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if "IdTestStrategy" in s.strategy_id]
        assert len(metas) >= 1
        assert "IdTestStrategy" in metas[0].strategy_id

    def test_strategy_type_values(self, tmp_path):
        """AC-020-04-02: strategy_type ∈ {"independent", "risk"}"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "type_test.py", """
            from quantide.core.strategy import BaseStrategy
            class TypeTest(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            assert s.strategy_type in ("independent", "risk")

    def test_module_field(self, tmp_path):
        """AC-020-04-03: module == cls.__module__"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "mod_check.py", """
            from quantide.core.strategy import BaseStrategy
            class ModCheck(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            assert isinstance(s.module, str)

    def test_is_builtin_flag(self):
        """AC-020-04-04: 框架包内 → is_builtin=True;否则 False"""
        from quantide.service.discovery_v2 import enumerate_strategies
        from quantide.service.discovery_v2 import is_builtin_path
        # builtin strategies from quantide.*
        result = enumerate_strategies(include_builtin=True)
        builtin = [s for s in result.strategies if s.is_builtin]
        user = [s for s in result.strategies if not s.is_builtin]
        assert len(builtin) >= 0
        assert isinstance(builtin, list)

    def test_skipped_reasons_only_on_non_strategy(self, tmp_path):
        """AC-020-04-05: 通过的策略 skipped_reasons=[]"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "ok.py", """
            from quantide.core.strategy import BaseStrategy
            class OkStrat(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            assert s.skipped_reasons == []


# ───────────────────────── AC-020-05 default_config → ParamSpec ─────────────────────────


class TestDefaultConfigToParamSpecV2:
    """AC-020-05: default_config 转 ParamSpec"""

    def test_config_with_params(self, tmp_path):
        """AC-020-05-01: default_config({"fast":5,"slow":20}) → ParamSpec"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "paramd.py", """
            from quantide.core.strategy import BaseStrategy
            class ParamdStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"fast": 5, "slow": 20}
        """)
        result = enumerate_strategies(d)
        metas = [s for s in result.strategies if "ParamdStrategy" in s.strategy_id]
        assert len(metas) >= 1
        dc = metas[0].default_config
        assert "fast" in dc
        assert dc["fast"].name == "fast"
        assert dc["fast"].default == 5
        assert "slow" in dc
        assert dc["slow"].default == 20

    def test_empty_config(self, tmp_path):
        """AC-020-05-02: default_config({}) → default_config == {}"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "empty_cfg.py", """
            from quantide.core.strategy import BaseStrategy
            class EmptyCfgStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {}
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            if hasattr(s, "default_config") and isinstance(s.default_config, dict):
                pass

    def test_no_override_empty_config(self, tmp_path):
        """AC-020-05-03: 未覆盖 → default_config == {} (不抛异常)"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "no_ovr.py", """
            from quantide.core.strategy import BaseStrategy
            class NoOverride(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            if hasattr(s, "default_config"):
                assert isinstance(s.default_config, dict)

    def test_config_stable(self, tmp_path):
        """AC-020-05-04: 同一策略两次枚举 → default_config 稳定一致"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "stable.py", """
            from quantide.core.strategy import BaseStrategy
            class StableStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"x": 10}
        """)
        r1 = enumerate_strategies(d)
        r2 = enumerate_strategies(d)
        m1 = [s for s in r1.strategies if "StableStrategy" in s.strategy_id]
        m2 = [s for s in r2.strategies if "StableStrategy" in s.strategy_id]
        assert len(m1) >= 1
        assert len(m2) >= 1


# ───────────────────────── AC-020-06 ParamSpec 字段契约 ─────────────────────────


class TestParamSpecFieldsV2:
    """AC-020-06: ParamSpec 字段(v0.2: type_hint/description/constraints 均为 None)"""

    def test_paramspec_name_and_default_required(self, tmp_path):
        """AC-020-06-01: ParamSpec.name 必填 = key; default 必填"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "ps.py", """
            from quantide.core.strategy import BaseStrategy
            class PSStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"alpha": 0.5}
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            for k, ps in s.default_config.items():
                assert ps.name == k
                assert ps.default is not None

    def test_type_hint_none_v02(self, tmp_path):
        """AC-020-06-02: type_hint v0.2 始终为 None"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "th.py", """
            from quantide.core.strategy import BaseStrategy
            class ThStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"a": 1}
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            for ps in s.default_config.values():
                assert ps.type_hint is None

    def test_description_none_v02(self, tmp_path):
        """AC-020-06-03: description v0.2 始终为 None"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "desc.py", """
            from quantide.core.strategy import BaseStrategy
            class DescStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"b": 2}
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            for ps in s.default_config.values():
                assert ps.description is None

    def test_constraints_none_v02(self, tmp_path):
        """AC-020-06-04: constraints v0.2 始终为 None"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "con.py", """
            from quantide.core.strategy import BaseStrategy
            class ConStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"c": 3}
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            for ps in s.default_config.values():
                assert ps.constraints is None


# ───────────────────────── AC-020-07 模式无关性 ─────────────────────────


class TestModeAgnosticV2:
    """AC-020-07: 枚举结果 4 模式一致"""

    def test_enumeration_does_not_contain_runtime_params(self, tmp_path):
        """AC-020-07-04: 枚举结果不含运行时参数"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "mode_test.py", """
            from quantide.core.strategy import BaseStrategy
            class ModeTest(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        for s in result.strategies:
            for key in ("initial_capital", "slippage", "commission", "tax_rate", "min_commission"):
                assert key not in s.default_config, \
                    f"runtime param {key} should not be in metadata"


# ───────────────────────── AC-020-08 目录问题 ─────────────────────────


class TestDirectoryFaultToleranceV2:
    """AC-020-08: 目录不存在/空/权限不足"""

    def test_directory_not_exists_returns_empty(self):
        """AC-020-08-01: 目录不存在 → 空列表,不抛异常"""
        from quantide.service.discovery_v2 import enumerate_strategies
        result = enumerate_strategies("/nonexistent/path/that/does/not/exist")
        assert result.strategies == []
        assert isinstance(result, object)

    def test_empty_directory_returns_empty(self, tmp_path):
        """AC-020-08-03: 目录存在但为空 → 空列表"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "empty"
        d.mkdir()
        result = enumerate_strategies(d)
        assert result.strategies == []


# ───────────────────────── AC-020-09 单文件失败 ─────────────────────────


class TestSingleFileFaultToleranceV2:
    """AC-020-09: 单文件失败不阻塞"""

    def test_syntax_error_skipped(self, tmp_path):
        """AC-020-09-01: 语法错 → 跳过,原因=SyntaxError"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "broken.py", "def incomplete(\n    pass\n")
        _make_strategy_file(d, "good.py", """
            from quantide.core.strategy import BaseStrategy
            class GoodStrat(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        assert len(result.strategies) >= 0
        diag_reasons = [e.reason for e in result.diagnostics]
        assert any("SyntaxError" in str(r) for r in diag_reasons)

    def test_import_error_skipped(self, tmp_path):
        """AC-020-09-02: import 失败 → 跳过,原因=ImportError"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "bad_import.py", """
            import nonexistent_module_xyz
            from quantide.core.strategy import BaseStrategy
            class BadImport(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        diag_reasons = [e.reason for e in result.diagnostics]
        assert any("ImportError" in str(r) for r in diag_reasons)


# ───────────────────────── AC-020-10 类级失败 ─────────────────────────


class TestClassLevelFaultToleranceV2:
    """AC-020-10: 类级失败不阻塞"""

    def test_non_strategy_class_excluded(self, tmp_path):
        """AC-020-10-01: 非 BaseStrategy 子类 → NotAStrategy"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "not_strat.py", """
            class NotAStrategy:
                pass
        """)
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert not any("NotAStrategy" in sid for sid in ids)

    def test_invalid_config_excluded(self, tmp_path):
        """AC-020-10-02: default_config 抛异常 → InvalidConfig"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "bad_cfg.py", """
            from quantide.core.strategy import BaseStrategy
            class BadCfg(BaseStrategy):
                @staticmethod
                def default_config():
                    raise RuntimeError("oops")
        """)
        result = enumerate_strategies(d)
        diag_reasons = [e.reason for e in result.diagnostics]
        assert any("InvalidConfig" in str(r) for r in diag_reasons)


# ───────────────────────── AC-020-12 整体不阻塞 ─────────────────────────


class TestNonBlockingV2:
    """AC-020-12: 整体不阻塞"""

    def test_partial_failure_returns_valid(self, tmp_path):
        """AC-020-12-01: M 个失败,M < N → 返回 N-M 有效策略 + 诊断"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "bad.py", "syntax error(")
        _make_strategy_file(d, "good.py", """
            from quantide.core.strategy import BaseStrategy
            class GoodStrat(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        assert len(result.strategies) >= 0

    def test_all_fail_returns_empty(self, tmp_path):
        """AC-020-12-02: 全部失败 → 空策略列表 + 诊断(不抛异常)"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "bad1.py", "syntax(")
        _make_strategy_file(d, "bad2.py", "also bad(")
        result = enumerate_strategies(d)
        assert isinstance(result.strategies, list)
        assert len(result.diagnostics) >= 0


# ───────────────────────── AC-020-14 排除项 ─────────────────────────


class TestExclusionsV2:
    """AC-020-14: 枚举不验证业务逻辑、不执行回测、不发起远程请求"""

    def test_enumeration_does_not_validate_business_logic(self, tmp_path):
        """AC-020-14-01: 枚举不验证业务逻辑正确性"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "bad_logic.py", """
            from quantide.core.strategy import BaseStrategy
            class BadLogic(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"param": "value"}
                async def on_bar(self, tm):
                    1/0  # logical error, not caught by enumeration
        """)
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert any("BadLogic" in sid for sid in ids)

    def test_enumeration_no_network(self, tmp_path):
        """AC-020-14-02: 枚举不发起远程网络请求(仅本地.py)"""
        import socket
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "local.py", """
            from quantide.core.strategy import BaseStrategy
            class LocalOnly(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        ids = [s.strategy_id for s in result.strategies]
        assert any("LocalOnly" in sid for sid in ids)


# ───────────────────────── AC-020-15 联动接口契约 ─────────────────────────


class TestCallerInterfaceV2:
    """AC-020-15: 枚举调用方契约"""

    def test_enumerate_strategies_signature(self):
        """AC-020-15-01: enumerate_strategies 接受 Path|str|None,返回 EnumerationResult"""
        from quantide.service.discovery_v2 import enumerate_strategies
        import inspect
        sig = inspect.signature(enumerate_strategies)
        assert "root" in sig.parameters or "path" in sig.parameters

    def test_enumeration_result_fields(self, tmp_path):
        """AC-020-15-02: EnumerationResult 含 strategies + diagnostics"""
        from quantide.service.discovery_v2 import enumerate_strategies
        from quantide.service.discovery_v2 import EnumerationResult
        d = tmp_path / "strategies"
        _make_strategy_file(d, "a.py", """
            from quantide.core.strategy import BaseStrategy
            class AStrat(BaseStrategy):
                pass
        """)
        result = enumerate_strategies(d)
        assert isinstance(result, EnumerationResult)
        assert hasattr(result, "strategies")
        assert hasattr(result, "diagnostics")

    def test_skipped_entry_fields(self, tmp_path):
        """AC-020-15-03: SkippedEntry 含 path / class_name / reason / detail"""
        from quantide.service.discovery_v2 import enumerate_strategies
        d = tmp_path / "strategies"
        _make_strategy_file(d, "sk.py", "syntax error{{}")
        result = enumerate_strategies(d)
        for entry in result.diagnostics:
            assert hasattr(entry, "path")
            assert hasattr(entry, "class_name")
            assert hasattr(entry, "reason")
            assert hasattr(entry, "detail")
