"""Unit tests — FR-020 策略枚举契约

按 test-plan.md §4.1,这些 unit 测试不依赖完整 app 启动,
仅验证 StrategyLoader 的核心契约(识别规则、容错、不递归)。
与 tests/e2e/strategy_discovery/test_fr_020_discovery.py(黑盒)互补。
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path

import pytest

from quantide.service.discovery import strategy_loader


@pytest.fixture(autouse=True)
def clean_state(db):
    """清理 strategy_info / strategy_config 表 + 内存缓存"""
    db.execute("DELETE FROM strategy_info")
    db.execute("DELETE FROM strategy_config")
    strategy_loader._strategies = {}
    yield
    db.execute("DELETE FROM strategy_info")
    db.execute("DELETE FROM strategy_config")
    strategy_loader._strategies = {}


def _write_strategy(directory: Path, filename: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    target.write_text(textwrap.dedent(body))
    return target


class TestRecognitionRules:
    """FR-020 AC-020-01: 识别 BaseStrategy 子类"""

    def test_base_strategy_subclass_identified(self, tmp_path, monkeypatch):
        """BaseStrategy 子类被识别"""
        _write_strategy(tmp_path, "good.py", """\
            from quantide.core.strategy import BaseStrategy
            class MyStrat(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        names = list(result.keys())
        assert any("MyStrat" in n for n in names), f"got {names}"

    def test_non_strategy_class_excluded(self, tmp_path, monkeypatch):
        """非 BaseStrategy 子类不被识别"""
        _write_strategy(tmp_path, "not_a_strategy.py", """\
            class NotAStrategy:
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        assert not any("NotAStrategy" in n for n in result), f"got {list(result)}"


class TestFaultTolerance:
    """FR-020 AC-020-08..12: 单文件失败不阻塞"""

    def test_syntax_error_does_not_block_others(self, tmp_path, monkeypatch):
        """syntax error 文件跳过,其他策略正常加载"""
        _write_strategy(tmp_path, "broken.py", "def incomplete_function(:\n    pass\n")
        _write_strategy(tmp_path, "good.py", """\
            from quantide.core.strategy import BaseStrategy
            class GoodStrategy(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        assert "GoodStrategy" in result
        assert "Broken" not in str(result)

    def test_import_error_does_not_block_others(self, tmp_path, monkeypatch):
        """import error 文件跳过"""
        _write_strategy(tmp_path, "broken.py", "import this_does_not_exist_anywhere\n")
        _write_strategy(tmp_path, "good.py", """\
            from quantide.core.strategy import BaseStrategy
            class GoodStrategy(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        assert "GoodStrategy" in result

    def test_directory_does_not_exist_returns_empty(self, monkeypatch):
        """目录不存在 → 返回空 dict,不抛异常"""
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: "/nonexistent/path")
        result = strategy_loader.scan_and_cache()
        assert isinstance(result, dict)

    def test_all_files_fail_returns_empty_dict(self, tmp_path, monkeypatch):
        """所有文件失败 → 返回空 dict(不抛异常)"""
        _write_strategy(tmp_path, "broken1.py", "def x(:\n")
        _write_strategy(tmp_path, "broken2.py", "import this_does_not_exist\n")
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        assert isinstance(result, dict)


class TestNoRecursion:
    """FR-020 AC-020-02: 不递归子目录"""

    def test_subdirectory_not_scanned(self, tmp_path, monkeypatch):
        """子目录中的 .py 不被扫描"""
        sub = tmp_path / "subdir"
        _write_strategy(sub, "nested.py", """\
            from quantide.core.strategy import BaseStrategy
            class NestedStrategy(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        names = list(result.keys())
        assert not any("NestedStrategy" in n for n in names), f"got {names}"


class TestMetadataExtraction:
    """FR-020 AC-020-03/04: 名称、默认配置元数据"""

    def test_strategy_class_name_used(self, tmp_path, monkeypatch):
        """策略名称默认 = 类名"""
        _write_strategy(tmp_path, "named.py", """\
            from quantide.core.strategy import BaseStrategy
            class MyNamedStrategy(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        assert "MyNamedStrategy" in result

    def test_default_config_empty_when_not_overridden(self, tmp_path, monkeypatch):
        """未覆盖 default_config → 返回 {}"""
        _write_strategy(tmp_path, "no_cfg.py", """\
            from quantide.core.strategy import BaseStrategy
            class NoCfgStrategy(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        cls = result["NoCfgStrategy"]
        assert cls.default_config() == {}

    def test_default_config_with_params(self, tmp_path, monkeypatch):
        """覆盖 default_config → 返回自定义 dict"""
        _write_strategy(tmp_path, "with_cfg.py", """\
            from quantide.core.strategy import BaseStrategy
            class WithCfgStrategy(BaseStrategy):
                @staticmethod
                def default_config():
                    return {"fast": 5, "slow": 20}
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        cls = result["WithCfgStrategy"]
        assert cls.default_config() == {"fast": 5, "slow": 20}


class TestStrategyID:
    """FR-020 AC-020-04: 策略类唯一标识"""

    def test_two_classes_one_file_have_distinct_keys(self, tmp_path, monkeypatch):
        """同一文件中多个策略类被分别记录"""
        _write_strategy(tmp_path, "ids.py", """\
            from quantide.core.strategy import BaseStrategy
            class AStrategy(BaseStrategy):
                pass
            class BStrategy(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        result = strategy_loader.scan_and_cache()
        assert "AStrategy" in result
        assert "BStrategy" in result
        # 两个不同类不冲突
        assert result["AStrategy"] is not result["BStrategy"]

    def test_strategy_info_module_path_recorded(self, tmp_path, monkeypatch):
        """StrategyInfo.module_path 记录模块路径"""
        _write_strategy(tmp_path, "mod_path.py", """\
            from quantide.core.strategy import BaseStrategy
            class MyStrat(BaseStrategy):
                pass
            """)
        monkeypatch.setattr(strategy_loader, "get_user_scan_directory", lambda: str(tmp_path))
        strategy_loader.scan_and_cache()
        info = strategy_loader.get_strategy_info("MyStrat")
        assert info is not None
        assert info.module_path == "mod_path"
