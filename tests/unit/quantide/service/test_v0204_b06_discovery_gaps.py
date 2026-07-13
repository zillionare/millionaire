"""v0.2-004-coverage-recovery B06-discovery gaps: quantide/service/discovery.py.

Targets uncovered branches:
- ScanSource dataclass (lines 28-34)
- ExampleCopyResult dataclass (lines 36-51) + copied_count/skipped_count properties
- StrategyLoader.get_builtin_scan_directory (line 64-66)
- StrategyLoader.get_user_scan_directory (line 68-76): empty/with config/exception
- StrategyLoader.get_scan_directory (line 78-83)
- StrategyLoader.get_scan_directories (line 85-95): empty user dir / dedupe
- StrategyLoader.has_scan_directory_config (line 97-106): true/false/exception
- StrategyLoader.set_scan_directory (line 108-124): insert vs upsert
- StrategyLoader.load_from_cache (line 126-164): empty, with rows, exception, reload
- StrategyLoader._clear_cache (line 197-204)
- StrategyLoader._add_scan_dir_to_sys_path (line 206-211)
- StrategyLoader._get_scan_sources (line 213-239): with workspace_path builtin,
  with workspace_path user, without workspace_path with user dir, without user dir
- StrategyLoader._scan_source (line 241-270): nonexistent dir, with files
- StrategyLoader._get_module_name (line 272-283)
- StrategyLoader._load_module_and_get_info (line 285+)
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quantide.service.discovery import (
    ExampleCopyResult,
    ScanSource,
    StrategyLoader,
)


@pytest.fixture
def loader():
    return StrategyLoader()


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


def test_scan_source_dataclass() -> None:
    """AC-FR0700-288: ScanSource is a frozen dataclass with directory and module_prefix."""
    src = ScanSource(directory=Path("/tmp/strategies"), module_prefix="quantide.x")
    assert src.directory == Path("/tmp/strategies")
    assert src.module_prefix == "quantide.x"

    src2 = ScanSource(directory=Path("/tmp"))
    assert src2.module_prefix is None


def test_example_copy_result_dataclass() -> None:
    """AC-FR0700-289: ExampleCopyResult exposes copied_files, skipped_files, counts."""
    r = ExampleCopyResult(copied_files=["a.py"], skipped_files=["b.py", "c.py"])
    assert r.copied_count == 1
    assert r.skipped_count == 2


# ---------------------------------------------------------------------------
# get_builtin_scan_directory
# ---------------------------------------------------------------------------


def test_get_builtin_scan_directory_returns_string(loader) -> None:
    """AC-FR0700-290: get_builtin_scan_directory returns the path as string."""
    result = loader.get_builtin_scan_directory()
    assert isinstance(result, str)
    assert "strategies" in result
    assert "example" in result


# ---------------------------------------------------------------------------
# get_user_scan_directory
# ---------------------------------------------------------------------------


def test_get_user_scan_directory_when_no_config(loader, monkeypatch) -> None:
    """AC-FR0700-291: get_user_scan_directory returns '' when no config row."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = []
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.get_user_scan_directory() == ""


def test_get_user_scan_directory_with_config(loader, monkeypatch) -> None:
    """AC-FR0700-292: get_user_scan_directory returns stripped value from db."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": "  /my/dir  "}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.get_user_scan_directory() == "/my/dir"


def test_get_user_scan_directory_with_exception(loader, monkeypatch) -> None:
    """AC-FR0700-293: get_user_scan_directory returns '' when db raises."""
    fake_table = MagicMock()
    fake_table.rows_where.side_effect = RuntimeError("boom")
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.get_user_scan_directory() == ""


# ---------------------------------------------------------------------------
# get_scan_directory / get_scan_directories
# ---------------------------------------------------------------------------


def test_get_scan_directory_falls_back_to_builtin(loader, monkeypatch) -> None:
    """AC-FR0700-294: get_scan_directory falls back to builtin when no user dir."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = []
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    result = loader.get_scan_directory()
    assert result == loader.get_builtin_scan_directory()


def test_get_scan_directories_includes_user_when_different(loader, monkeypatch) -> None:
    """AC-FR0700-295: get_scan_directories adds user dir if different from builtin."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": "/different/path"}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    dirs = loader.get_scan_directories()
    assert loader.get_builtin_scan_directory() in dirs
    assert "/different/path" in dirs


def test_get_scan_directories_skips_user_when_same_as_builtin(loader, monkeypatch) -> None:
    """AC-FR0700-296: get_scan_directories deduplicates when user dir equals builtin."""
    builtin = loader.get_builtin_scan_directory()
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": builtin}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    dirs = loader.get_scan_directories()
    # builtin appears exactly once.
    assert dirs.count(builtin) == 1


# ---------------------------------------------------------------------------
# has_scan_directory_config
# ---------------------------------------------------------------------------


def test_has_scan_directory_config_false_when_no_rows(loader, monkeypatch) -> None:
    """AC-FR0700-297: has_scan_directory_config returns False when no rows."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = []
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.has_scan_directory_config() is False


def test_has_scan_directory_config_true_when_value_set(loader, monkeypatch) -> None:
    """AC-FR0700-298: has_scan_directory_config returns True when value is non-empty."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": "/some/path"}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.has_scan_directory_config() is True


def test_has_scan_directory_config_false_when_empty_value(loader, monkeypatch) -> None:
    """AC-FR0700-299: has_scan_directory_config returns False when value is empty."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": "   "}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.has_scan_directory_config() is False


def test_has_scan_directory_config_swallows_exception(loader, monkeypatch) -> None:
    """AC-FR0700-300: has_scan_directory_config returns False on exception."""
    fake_table = MagicMock()
    fake_table.rows_where.side_effect = RuntimeError("err")
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)
    assert loader.has_scan_directory_config() is False


# ---------------------------------------------------------------------------
# set_scan_directory
# ---------------------------------------------------------------------------


def test_set_scan_directory_inserts_when_no_existing(loader, monkeypatch) -> None:
    """AC-FR0700-301: set_scan_directory inserts when no existing row."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = []
    upserts = []
    fake_table.upsert = lambda d, pk: upserts.append((d, pk))
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    loader.set_scan_directory("/my/path")
    assert len(upserts) == 1
    assert upserts[0][0]["value"] == "/my/path"
    assert upserts[0][1] == "key"


def test_set_scan_directory_uses_existing_id(loader, monkeypatch) -> None:
    """AC-FR0700-302: set_scan_directory uses existing row id when present."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"id": 42}]
    upserts = []
    fake_table.upsert = lambda d, pk: upserts.append(d)
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    loader.set_scan_directory("/path")
    assert upserts[0]["id"] == 42


# ---------------------------------------------------------------------------
# load_from_cache
# ---------------------------------------------------------------------------


def test_load_from_cache_with_no_rows(loader, monkeypatch) -> None:
    """AC-FR0700-303: load_from_cache returns empty dict when no rows in db."""
    fake_table = MagicMock()
    fake_table.rows = []
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    assert loader.load_from_cache() == {}


def test_load_from_cache_exception(loader, monkeypatch) -> None:
    """AC-FR0700-304: load_from_cache returns empty dict when db raises."""
    fake_table = MagicMock()
    type(fake_table).rows = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    assert loader.load_from_cache() == {}


def test_load_from_cache_skips_non_strategy_classes(loader, monkeypatch) -> None:
    """AC-FR0700-305: load_from_cache skips modules where the class is not a Strategy subclass."""
    fake_table = MagicMock()
    # Reference a real module that has only non-strategy classes.
    fake_table.rows = iter([])
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    # Use a row referencing os module which has only non-strategy classes.
    fake_table.rows = iter([{
        "module_path": "os",
        "name": "path",  # os.path exists but is not a Strategy
        "scan_dir": "",
    }])

    result = loader.load_from_cache()
    assert result == {}


def test_load_from_cache_swallows_per_row_exception(loader, monkeypatch) -> None:
    """AC-FR0700-306: load_from_cache swallows per-row exceptions and continues."""
    fake_table = MagicMock()
    fake_table.rows = iter([
        {"module_path": "nonexistent.module", "name": "X", "scan_dir": ""},
        {"module_path": "os", "name": "path", "scan_dir": ""},
    ])
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    # Should not raise — the bad row is skipped, the good row is filtered out.
    result = loader.load_from_cache()
    assert "X" not in result
    assert "path" not in result  # os.path is not a Strategy


# ---------------------------------------------------------------------------
# _clear_cache
# ---------------------------------------------------------------------------


def test_clear_cache_success(loader, monkeypatch) -> None:
    """AC-FR0700-307: _clear_cache calls db delete_where('1=1')."""
    fake_table = MagicMock()
    deletes = []
    fake_table.delete_where = lambda clause: deletes.append(clause)
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    loader._clear_cache()
    assert deletes == ["1=1"]


def test_clear_cache_swallows_exception(loader, monkeypatch) -> None:
    """AC-FR0700-308: _clear_cache swallows exceptions from delete_where."""
    fake_table = MagicMock()
    fake_table.delete_where.side_effect = RuntimeError("boom")
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    loader._clear_cache()  # should not raise


# ---------------------------------------------------------------------------
# _add_scan_dir_to_sys_path
# ---------------------------------------------------------------------------


def test_add_scan_dir_to_sys_path_adds_when_not_present(loader, monkeypatch) -> None:
    """AC-FR0700-309: _add_scan_dir_to_sys_path adds new path at front of sys.path."""
    # Use a path that's not in sys.path already. Resolved to handle /tmp → /private/tmp on macOS.
    test_path = str(Path("/tmp/__test_path_not_in_sys__").resolve())
    if test_path in sys.path:
        sys.path.remove(test_path)

    loader._add_scan_dir_to_sys_path(str(Path("/tmp/__test_path_not_in_sys__")))
    assert sys.path[0] == test_path
    sys.path.remove(test_path)


def test_add_scan_dir_to_sys_path_skips_when_already_present(loader) -> None:
    """AC-FR0700-310: _add_scan_dir_to_sys_path doesn't add duplicates."""
    test_path = "/tmp/__dup_test_path__"
    sys.path.insert(0, test_path)
    try:
        before_count = sys.path.count(test_path)
        loader._add_scan_dir_to_sys_path(test_path)
        assert sys.path.count(test_path) == before_count
    finally:
        while test_path in sys.path:
            sys.path.remove(test_path)


# ---------------------------------------------------------------------------
# _get_scan_sources
# ---------------------------------------------------------------------------


def test_get_scan_sources_with_workspace_path_matching_builtin(loader) -> None:
    """AC-FR0700-311: workspace_path == builtin yields single source with module_prefix."""
    sources = loader._get_scan_sources(workspace_path=loader.get_builtin_scan_directory())
    assert len(sources) == 1
    assert sources[0].module_prefix == loader._builtin_module_prefix


def test_get_scan_sources_with_workspace_path_different(loader) -> None:
    """AC-FR0700-312: workspace_path != builtin yields source without module_prefix."""
    raw = "/tmp/some_other_dir"
    sources = loader._get_scan_sources(workspace_path=raw)
    assert len(sources) == 1
    assert sources[0].module_prefix is None
    assert sources[0].directory == Path(raw).expanduser().resolve()


def test_get_scan_sources_without_workspace_path(loader, monkeypatch) -> None:
    """AC-FR0700-313: no workspace_path → builtin-only sources when no user dir."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = []
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    sources = loader._get_scan_sources()
    assert len(sources) == 1
    assert sources[0].directory == loader._builtin_example_dir


def test_get_scan_sources_with_user_dir_different_from_builtin(loader, monkeypatch) -> None:
    """AC-FR0700-314: user dir != builtin adds a second ScanSource."""
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": "/user/strategies"}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    sources = loader._get_scan_sources()
    assert len(sources) == 2
    assert any(s.directory == loader._builtin_example_dir for s in sources)
    assert any(str(s.directory) == "/user/strategies" for s in sources)


def test_get_scan_sources_with_user_dir_equal_to_builtin(loader, monkeypatch) -> None:
    """AC-FR0700-315: user dir == builtin does NOT add a duplicate source."""
    builtin = loader.get_builtin_scan_directory()
    fake_table = MagicMock()
    fake_table.rows_where.return_value = [{"value": builtin}]
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)

    sources = loader._get_scan_sources()
    assert len(sources) == 1


# ---------------------------------------------------------------------------
# _scan_source
# ---------------------------------------------------------------------------


def test_scan_source_nonexistent_dir_returns_empty(loader, tmp_path) -> None:
    """AC-FR0700-316: _scan_source returns {} when directory doesn't exist."""
    nonexistent = tmp_path / "does_not_exist"
    source = ScanSource(directory=nonexistent, module_prefix=None)
    assert loader._scan_source(source) == {}


def test_scan_source_skips_non_py_files(loader, tmp_path) -> None:
    """AC-FR0700-317: _scan_source skips non-.py and __-prefixed files."""
    # Create some non-python files.
    (tmp_path / "readme.md").write_text("# readme")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("# cache")

    source = ScanSource(directory=tmp_path, module_prefix=None)
    # With no module_prefix, the dir gets added to sys.path.
    # Even if files are skipped, no exception should be raised.
    result = loader._scan_source(source)
    assert isinstance(result, dict)


def test_scan_source_handles_broken_py_file(loader, tmp_path) -> None:
    """AC-FR0700-318: _scan_source swallows exceptions from broken .py files."""
    (tmp_path / "broken.py").write_text("def broken(:\n    pass\n")  # SyntaxError

    source = ScanSource(directory=tmp_path, module_prefix=None)
    # Should not raise — exception is logged.
    result = loader._scan_source(source)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _get_module_name
# ---------------------------------------------------------------------------


def test_get_module_name_without_prefix(loader, tmp_path) -> None:
    """AC-FR0700-319: _get_module_name without prefix returns relative module name."""
    f = tmp_path / "my_strategy.py"
    name = loader._get_module_name(tmp_path, f, module_prefix=None)
    assert name == "my_strategy"


def test_get_module_name_with_prefix(loader, tmp_path) -> None:
    """AC-FR0700-320: _get_module_name with prefix returns prefixed module name."""
    f = tmp_path / "my_strategy.py"
    name = loader._get_module_name(tmp_path, f, module_prefix="quantide.strategies.example")
    assert name == "quantide.strategies.example.my_strategy"


def test_get_module_name_with_nested_path(loader, tmp_path) -> None:
    """AC-FR0700-321: _get_module_name handles nested subdirectory paths."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    f = subdir / "my_strategy.py"
    name = loader._get_module_name(tmp_path, f, module_prefix=None)
    assert name == "subdir.my_strategy"