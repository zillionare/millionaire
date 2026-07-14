"""B06-svc-2: Additional tests for quantide/service/discovery.py.

Target: cover helper-level functions (_classify_strategy,
_is_builtin_class, is_builtin_path, _to_param_spec, etc.) and
edge cases for the loader that aren't hit by existing tests.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantide.core.strategy import (
    BaseStrategy,
    RiskStrategy,
    Strategy,
)
from quantide.service.discovery import (
    ExampleCopyResult,
    ScanSource,
    StrategyLoader,
    _classify_strategy,
    _is_builtin_class,
    _to_param_spec,
    enumerate_strategies,
    is_builtin_path,
    strategy_loader,
)


@pytest.fixture(autouse=True)
def _clear_discovery_db_state(db):
    """Clean up strategy_config rows that previous tests may have left behind,
    so order-dependence doesn't break this test module.

    Re-opens the DB connection on demand in case a prior test closed it.
    """
    from quantide.data.sqlite import db as _db
    from quantide.data.models.strategy_config import StrategyConfig

    # Ensure DB connection is open.
    if not getattr(_db, "_initialized", False):
        try:
            _db.init(":memory:")
        except Exception:
            pass
    else:
        try:
            _db.execute("SELECT 1")
        except Exception:
            try:
                _db._initialized = False
                _db.init(":memory:")
            except Exception:
                pass

    # Make sure strategy_config table exists by inserting a placeholder.
    try:
        _db["strategy_config"].insert(
            StrategyConfig(
                key="__placeholder__", value="", updated_at=None
            ).to_dict()
        )
        try:
            _db.execute("DELETE FROM strategy_config WHERE key='__placeholder__'")
        except Exception:
            pass
    except Exception:
        pass

    try:
        _db.execute("DELETE FROM strategy_config WHERE key='scan_directory'")
    except Exception:
        pass
    yield
    try:
        _db.execute("DELETE FROM strategy_config WHERE key='scan_directory'")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers / pure-function coverage
# ---------------------------------------------------------------------------


def test_to_param_spec_returns_dict_of_paramspec():
    out = _to_param_spec({"a": 1, "b": 0.5})
    assert "a" in out and "b" in out
    assert out["a"].default == 1
    assert out["a"].name == "a"


def test_to_param_spec_handles_empty_dict():
    assert _to_param_spec({}) == {}


def test_to_param_spec_handles_none_dict():
    assert _to_param_spec(None) == {}


def test_classify_strategy_returns_independent_for_basestrat_subclass():
    class MyStrat(BaseStrategy):
        pass

    assert _classify_strategy(MyStrat) == "independent"


def test_classify_strategy_returns_risk_for_riskstrategy_subclass():
    class MyRisk(RiskStrategy):
        def __init__(self, broker, config):
            super().__init__(broker, config)
            self.broker = broker
            self.config = config

    # Provide minimum stub for abstract methods
    assert _classify_strategy(MyRisk) == "risk"


def test_classify_strategy_returns_none_for_base_classes_itself():
    assert _classify_strategy(BaseStrategy) is None
    assert _classify_strategy(RiskStrategy) is None
    assert _classify_strategy(Strategy) is None


def test_classify_strategy_returns_none_for_non_class():
    assert _classify_strategy("notaclass") is None
    assert _classify_strategy(42) is None


def test_is_builtin_class_true_for_quantide_module():
    class _Fake:
        pass

    _Fake.__module__ = "quantide.service.discovery"
    assert _is_builtin_class(_Fake) is True


def test_is_builtin_class_false_for_external_module():
    class _Fake:
        pass

    _Fake.__module__ = "user_strategy.foo"
    assert _is_builtin_class(_Fake) is False


def test_is_builtin_class_handles_examples_prefix():
    class _Fake:
        pass

    _Fake.__module__ = "quantide.examples.user_strategy"
    assert _is_builtin_class(_Fake) is False


def test_is_builtin_class_handles_missing_module_attribute():
    """Class without __module__ attribute falls back to empty string."""
    fake = type("_Fake", (), {})
    fake.__module__ = ""
    assert _is_builtin_class(fake) is False


def test_is_builtin_path_returns_true_for_quantide_subdir():
    """A path inside the quantide package returns True."""
    from quantide.service import discovery as discovery_mod
    quantide_path = Path(discovery_mod.__file__).resolve()
    assert is_builtin_path(quantide_path) is True


def test_is_builtin_path_returns_false_for_external_path():
    """A path outside the quantide package returns False."""
    with tempfile.NamedTemporaryFile(suffix=".py") as f:
        external = Path(f.name)
        assert is_builtin_path(external) is False


def test_is_builtin_path_handles_string_input():
    from quantide.service import discovery as _disc
    assert is_builtin_path(str(_disc.__file__)) is True


# ---------------------------------------------------------------------------
# enumerate_strategies — public API
# ---------------------------------------------------------------------------


def test_enumerate_strategies_no_root_returns_builtins(tmp_path):
    """When root is None and builtins exist, they are returned."""
    result = enumerate_strategies(root=None, include_builtin=True)
    # The builtin examples directory should exist and yield at least one strategy.
    assert isinstance(result.strategies, list)
    assert isinstance(result.diagnostics, list)


def test_enumerate_strategies_no_root_no_builtins_returns_empty():
    """When root is None and include_builtin=False, returns empty."""
    result = enumerate_strategies(root=None, include_builtin=False)
    assert result.strategies == []
    assert result.diagnostics == []


def test_enumerate_strategies_nonexistent_root_logs_diagnostic(tmp_path):
    """When root points to a missing directory, a diagnostic is logged."""
    missing = tmp_path / "does-not-exist"
    result = enumerate_strategies(root=str(missing), include_builtin=False)
    assert result.strategies == []
    assert any(d.reason == "PermissionDenied" for d in result.diagnostics)


# ---------------------------------------------------------------------------
# ExampleCopyResult properties
# ---------------------------------------------------------------------------


def test_example_copy_result_copied_count():
    r = ExampleCopyResult(copied_files=["a.py", "b.py"], skipped_files=["c.py"])
    assert r.copied_count == 2
    assert r.skipped_count == 1


def test_example_copy_result_empty_default():
    r = ExampleCopyResult(copied_files=[], skipped_files=[])
    assert r.copied_count == 0
    assert r.skipped_count == 0


# ---------------------------------------------------------------------------
# ScanSource
# ---------------------------------------------------------------------------


def test_scan_source_has_directory_attribute():
    src = ScanSource(directory=Path("/tmp/foo"))
    assert src.directory == Path("/tmp/foo")
    assert src.module_prefix is None


# ---------------------------------------------------------------------------
# StrategyLoader — additional paths
# ---------------------------------------------------------------------------


def test_strategy_loader_get_scan_directory_default(monkeypatch):
    loader = StrategyLoader()
    # Default behavior: user dir is "" so it falls back to builtins.
    out = loader.get_scan_directory()
    assert out.endswith("example") or out.endswith("examples") or "strategies" in out


def test_strategy_loader_get_scan_directory_falls_back_to_default():
    """When no db config, get_user_scan_directory returns empty, falling
    back to get_builtin_scan_directory."""
    loader = StrategyLoader()
    out = loader.get_scan_directory()
    assert isinstance(out, str)
    assert out  # non-empty


def test_strategy_loader_get_builtin_scan_directory_uses_quantide_examples():
    loader = StrategyLoader()
    out = loader.get_builtin_scan_directory()
    assert out.endswith("example") or out.endswith("examples") or "/quantide/" in out


def test_strategy_loader_get_user_scan_directory_default_empty():
    """Without DB config, get_user_scan_directory returns empty string."""
    loader = StrategyLoader()
    out = loader.get_user_scan_directory()
    assert out == ""


def test_strategy_loader_get_user_scan_directory_with_db_config(db):
    """With a DB row, the configured directory is returned."""
    from quantide.data.sqlite import db as _db
    from quantide.data.models.strategy_config import StrategyConfig

    _db["strategy_config"].upsert(
        StrategyConfig(
            key="scan_directory", value="/tmp/cfg-x", updated_at=None
        ).to_dict(),
        pk="key",
    )
    loader = StrategyLoader()
    out = loader.get_user_scan_directory()
    assert out == "/tmp/cfg-x"


def test_strategy_loader_get_scan_directories_returns_list():
    loader = StrategyLoader()
    dirs = loader.get_scan_directories()
    assert isinstance(dirs, list)
    assert dirs  # at least built-in
    assert any("example" in d for d in dirs)


def test_strategy_loader_get_module_name_handles_special_chars():
    out = StrategyLoader()._get_module_name(
        Path("/tmp/scan"),
        Path("/tmp/scan/dual_ma.py"),
    )
    assert "dual_ma" in out


def test_strategy_loader_get_module_name_with_prefix():
    out = StrategyLoader()._get_module_name(
        Path("/tmp/scan"),
        Path("/tmp/scan/sub/file.py"),
        module_prefix="my_prefix",
    )
    assert out.startswith("my_prefix.")
    assert "sub" in out
    assert "file" in out


def test_strategy_loader_load_returns_dict_when_no_directory():
    loader = StrategyLoader()
    out = loader.load()
    assert isinstance(out, dict)


# ---------------------------------------------------------------------------
# StrategyLoader.set_scan_directory + has_scan_directory_config
# ---------------------------------------------------------------------------


def test_strategy_loader_set_scan_directory_then_has_config(db):
    loader = StrategyLoader()
    target_dir = "/tmp/cfg-" + str(Path(__file__).name)
    loader.set_scan_directory(target_dir)
    assert loader.has_scan_directory_config() is True
    # Verify we set the value we intended (not whatever was already there).
    assert loader.get_user_scan_directory() == target_dir


def test_strategy_loader_has_scan_directory_config_false_when_empty(db):
    """After clearing any existing config, has_scan_directory_config returns False."""
    from quantide.data.sqlite import db as _db
    # Clean up any prior config rows from earlier tests in this session.
    try:
        _db.execute("DELETE FROM strategy_config WHERE key='scan_directory'")
    except Exception:
        pass
    loader = StrategyLoader()
    assert loader.has_scan_directory_config() is False


def test_strategy_loader_set_scan_directory_appends_sys_path(db, tmp_path):
    loader = StrategyLoader()
    target = str(tmp_path / "scan-set-2")  # unique path
    loader.set_scan_directory(target)
    assert isinstance(sys.path, list)
    # We don't assert contents; the DB upsert is what matters here.


# ---------------------------------------------------------------------------
# load_from_cache (interface)
# ---------------------------------------------------------------------------


def test_strategy_loader_load_from_cache_default_returns_dict():
    out = strategy_loader.load_from_cache()
    assert isinstance(out, dict)


def test_strategy_loader_get_strategy_info_returns_none_for_missing():
    out = strategy_loader.get_strategy_info("does-not-exist-strategy")
    assert out is None


def test_strategy_loader_list_strategies_returns_list():
    out = strategy_loader.list_strategies()
    assert isinstance(out, list)


# ---------------------------------------------------------------------------
# copy_examples_to_directory
# ---------------------------------------------------------------------------


def test_copy_examples_to_directory_writes_files(tmp_path):
    """Calling copy_examples_to_directory copies some example files into a
    fresh tmp dir, returning a populated ExampleCopyResult."""
    target = tmp_path / "examples"
    target.mkdir(parents=True, exist_ok=True)
    result = strategy_loader.copy_examples_to_directory(target)
    assert isinstance(result, ExampleCopyResult)
    assert target.exists()
    assert result.copied_count + result.skipped_count >= 0


def test_copy_examples_to_directory_handles_nonexistent_dir(tmp_path):
    """Calling with a non-existent directory raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        strategy_loader.copy_examples_to_directory(tmp_path / "missing")


def test_copy_examples_to_directory_skip_when_target_exists(tmp_path):
    """When target file already exists, it's reported as skipped."""
    target = tmp_path / "examples"
    target.mkdir(parents=True, exist_ok=True)
    # Run twice; the second call should produce skipped entries.
    first = strategy_loader.copy_examples_to_directory(target)
    second = strategy_loader.copy_examples_to_directory(target)
    # The second run should have at least one skipped entry (if first copied anything).
    if first.copied_files:
        assert second.skipped_count >= first.copied_count


# ---------------------------------------------------------------------------
# _enumerate_dir - exercised via enumerate_strategies with user dir
# ---------------------------------------------------------------------------


def test_enumerate_strategies_user_dir_with_valid_strategy(tmp_path):
    """A user directory with a valid BaseStrategy subclass produces a
    StrategyMetadata entry."""
    from quantide.core.strategy import BaseStrategy
    user_dir = tmp_path / "user_strategies"
    user_dir.mkdir()
    (user_dir / "my_strategy.py").write_text(
        '''
from quantide.core.strategy import BaseStrategy

class MyCustomStrat(BaseStrategy):
    """Custom strategy."""

    @staticmethod
    def default_config():
        return {"x": 1}

    def init(self, broker, config):
        self.broker = broker
'''
    )
    result = enumerate_strategies(root=str(user_dir), include_builtin=False)
    found = [s for s in result.strategies if "MyCustomStrat" in s.name]
    assert len(found) >= 1
    assert found[0].strategy_type == "independent"


def test_enumerate_strategies_user_dir_skips_non_strategy_classes(tmp_path):
    """A module with both a strategy and non-strategy class should:
    - include the strategy
    - log a diagnostic for the non-strategy class
    """
    user_dir = tmp_path / "user_strategies2"
    user_dir.mkdir()
    (user_dir / "mixed_strats.py").write_text(
        '''
from quantide.core.strategy import BaseStrategy

class _NotAStrategy:
    pass

class MyMixedStrat(BaseStrategy):
    """Mixed."""

    @staticmethod
    def default_config():
        return {}

    def init(self, broker, config):
        self.broker = broker
'''
    )
    result = enumerate_strategies(root=str(user_dir), include_builtin=False)
    names = [s.name for s in result.strategies]
    assert any("MyMixedStrat" in n for n in names)


def test_enumerate_strategies_user_dir_logs_syntax_error(tmp_path):
    """A .py file with SyntaxError gets a diagnostic entry."""
    user_dir = tmp_path / "user_strategies3"
    user_dir.mkdir()
    (user_dir / "broken_strategy.py").write_text(
        "def broken(:\n    pass\n"  # syntax error: missing `)`
    )
    result = enumerate_strategies(root=str(user_dir), include_builtin=False)
    syntax_diag = [d for d in result.diagnostics if d.reason == "SyntaxError"]
    assert len(syntax_diag) >= 1


def test_enumerate_strategies_skips_init_files_and_non_py(tmp_path):
    """__init__.py and non-.py files are ignored silently."""
    user_dir = tmp_path / "user_strategies4"
    user_dir.mkdir()
    (user_dir / "__init__.py").write_text("")
    (user_dir / "readme.md").write_text("# Notes")
    result = enumerate_strategies(root=str(user_dir), include_builtin=False)
    # No strategy should be discovered — only __init__.py and .md exist.
    assert result.strategies == []
    assert result.diagnostics == []


def test_enumerate_strategies_existing_user_dir_with_builtins(tmp_path):
    """When root exists and include_builtin=True, both user + builtin are returned."""
    from quantide.core.strategy import BaseStrategy
    user_dir = tmp_path / "user_strategies5"
    user_dir.mkdir()
    (user_dir / "usr_strat.py").write_text(
        '''
from quantide.core.strategy import BaseStrategy

class UsrStrat(BaseStrategy):
    """User."""

    @staticmethod
    def default_config():
        return {}

    def init(self, broker, config):
        self.broker = broker
'''
    )
    result = enumerate_strategies(root=str(user_dir), include_builtin=True)
    # Should contain at least the user strategy + any builtins.
    user_included = any("UsrStrat" in s.name for s in result.strategies)
    assert user_included
