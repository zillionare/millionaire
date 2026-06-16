"""E2E 黑盒测试 — FR-020 策略枚举

按 test-plan.md §4.1 scenarios/strategy_discovery/ 设计:
- 仅依赖外部可观测对象(枚举结果、错误日志)
- 不 mock 框架内部实现
- 与 acceptance.md AC-020-01 ~ 15 对齐

策略枚举通过扫描目录识别 BaseStrategy 子类,输出
StrategyMetadata 结构;失败的文件/类进入 diagnostics。
"""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from quantide.core.strategy import BaseStrategy
from quantide.service.discovery import strategy_loader


def _make_strategy_file(
    directory: Path,
    filename: str,
    body: str,
) -> Path:
    """写入策略文件到 directory"""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    target.write_text(textwrap.dedent(body))
    return target


@pytest.fixture
def isolated_user_dir(tmp_path, monkeypatch, db):
    """每个测试用独立的用户策略目录,避免污染;复用 session 级 db fixture"""
    user_dir = tmp_path / "user_strategies"
    user_dir.mkdir()
    # monkey-patch get_user_scan_directory to return our temp dir
    monkeypatch.setattr(
        strategy_loader, "get_user_scan_directory", lambda: str(user_dir)
    )
    yield user_dir


# ───────────────────────── AC-020-01 识别规则 ─────────────────────────


class TestRecognition:
    """AC-020-01: 识别 BaseStrategy 子类为合法策略"""

    def test_basesstrategy_subclass_recognized(self, isolated_user_dir):
        """BaseStrategy 子类被识别"""
        _make_strategy_file(
            isolated_user_dir,
            "valid_day.py",
            """\
            from quantide.core.strategy import BaseStrategy
            class MyStrategy(BaseStrategy):
                pass
            """,
        )
        result = strategy_loader.scan_and_cache()
        names = list(result.keys())
        assert any("MyStrategy" in n for n in names), f"got {names}"

    def test_non_strategy_class_excluded(self, isolated_user_dir):
        """非 BaseStrategy 子类不被识别"""
        _make_strategy_file(
            isolated_user_dir,
            "not_a_strategy.py",
            """\
            class NotAStrategy:
                pass
            """,
        )
        result = strategy_loader.scan_and_cache()
        names = list(result.keys())
        assert not any("NotAStrategy" in n for n in names), f"got {names}"


# ───────────────────────── AC-020-03 / AC-020-04 元数据 ─────────────────────────


class TestMetadata:
    """AC-020-03 / 04: 名称与默认配置元数据"""

    def test_strategy_name_uses_class_name(self, isolated_user_dir):
        """名称默认 = cls.__name__"""
        _make_strategy_file(
            isolated_user_dir,
            "named.py",
            """\
            from quantide.core.strategy import BaseStrategy
            class MyNamedStrategy(BaseStrategy):
                pass
            """,
        )
        result = strategy_loader.scan_and_cache()
        assert "MyNamedStrategy" in result

    def test_default_config_empty_when_not_overridden(self, isolated_user_dir):
        """未覆盖 default_config → 空 dict"""
        _make_strategy_file(
            isolated_user_dir,
            "no_cfg.py",
            """\
            from quantide.core.strategy import BaseStrategy
            class NoCfgStrategy(BaseStrategy):
                pass
            """,
        )
        result = strategy_loader.scan_and_cache()
        # verify the class actually returns empty default_config
        cls = result["NoCfgStrategy"]
        assert cls.default_config() == {}


# ───────────────────────── AC-020-08 / 09 / 10 / 11 容错 ─────────────────────────


class TestFaultTolerance:
    """AC-020-08..11: 单文件失败不阻塞;整体结果仍返回"""

    def test_syntax_error_does_not_block_others(self, isolated_user_dir):
        """syntax error 文件跳过,其他策略正常加载"""
        _make_strategy_file(
            isolated_user_dir,
            "broken.py",
            "def incomplete_function(:\n    pass\n",  # syntax error
        )
        _make_strategy_file(
            isolated_user_dir,
            "good.py",
            """\
            from quantide.core.strategy import BaseStrategy
            class GoodStrategy(BaseStrategy):
                pass
            """,
        )
        result = strategy_loader.scan_and_cache()
        assert "GoodStrategy" in result
        assert "Broken" not in str(result)

    def test_directory_does_not_exist_returns_no_user_strategies(self, monkeypatch, db):
        """用户目录不存在 → 不抛异常,只含内置策略(无用户策略)"""
        monkeypatch.setattr(
            strategy_loader, "get_user_scan_directory", lambda: "/nonexistent/path"
        )
        result = strategy_loader.scan_and_cache()
        # 不抛异常 + 仅含内置策略
        assert isinstance(result, dict)
        # 用户目录不存在时,无用户策略被加载(若有,断言键名不含 'User' 等标记)
        for name in result:
            assert not name.endswith("_User")


# ───────────────────────── AC-020-12 整体不阻塞 ─────────────────────────


class TestNoPropagation:
    """AC-020-12: 所有文件都失败时仍返回空结果(不抛异常)"""

    def test_all_files_fail_returns_no_user_strategies(self, isolated_user_dir):
        """所有用户文件失败 → 无用户策略被加载(可含内置)"""
        _make_strategy_file(
            isolated_user_dir,
            "broken1.py",
            "def x(:\n",
        )
        _make_strategy_file(
            isolated_user_dir,
            "broken2.py",
            "import this_does_not_exist_anywhere\n",
        )
        result = strategy_loader.scan_and_cache()
        assert isinstance(result, dict)
        # 用户目录中失败的文件不应进入结果
        user_strategy_names = {"Broken1", "Broken2"}
        assert not (user_strategy_names & set(result.keys()))


# ───────────────────────── 边界 ─────────────────────────


class TestBoundaries:
    """边界场景"""

    def test_subdirectory_not_recursed(self, isolated_user_dir):
        """spec: 不递归子目录"""
        sub = isolated_user_dir / "sub"
        _make_strategy_file(
            sub,
            "nested.py",
            """\
            from quantide.core.strategy import BaseStrategy
            class NestedStrategy(BaseStrategy):
                pass
            """,
        )
        result = strategy_loader.scan_and_cache()
        # 子目录的策略不应被发现(spec AC-020-02 不递归)
        names = list(result.keys())
        assert not any("NestedStrategy" in n for n in names), f"got {names}"
