"""v0.2-004-coverage-recovery B12-discovery: 7 tests for quantide/service/discovery.py.

Targets previously uncovered lines:
- _enumerate_dir ImportError branch (lines 547-548, 554)
- _enumerate_dir ModuleInitError branch (lines 555-556, 562)
- _enumerate_dir reload-already-imported branch (line 536)
- _enumerate_dir invalid default_config branch (lines 578-585)
- _load_module_and_get_info truthy params attribute (line 307)
- _scan_source file-processing exception swallow (lines 268-269)
- _iter_copyable_example_files missing builtin dir (line 396)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from quantide.service.discovery import ScanSource, StrategyLoader, enumerate_strategies


def _write_user_strategy(directory: Path, filename: str, body: str) -> Path:
    """Write a .py strategy file into ``directory`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(body)
    return path


# ---------------------------------------------------------------------------
# _enumerate_dir error branches (exercised via enumerate_strategies)
# ---------------------------------------------------------------------------


def test_enumerate_dir_records_import_error_diagnostic(tmp_path: Path) -> None:
    """AC-FR0700-B12-1: a module that fails to import a dependency records an ImportError diagnostic."""
    _write_user_strategy(
        tmp_path,
        "b12_import_err.py",
        "import nonexistent_pkg_xyz_12345\n",
    )

    result = enumerate_strategies(root=str(tmp_path), include_builtin=False)

    import_diags = [d for d in result.diagnostics if d.reason == "ImportError"]
    assert len(import_diags) == 1
    assert import_diags[0].class_name is None
    assert import_diags[0].path.endswith("b12_import_err.py")
    assert "nonexistent_pkg_xyz_12345" in import_diags[0].detail
    assert result.strategies == []


def test_enumerate_dir_records_module_init_error_diagnostic(tmp_path: Path) -> None:
    """AC-FR0700-B12-2: a module that raises a non-import exception at init records a ModuleInitError diagnostic."""
    _write_user_strategy(
        tmp_path,
        "b12_runtime_err.py",
        "raise RuntimeError('init boom')\n",
    )

    result = enumerate_strategies(root=str(tmp_path), include_builtin=False)

    init_diags = [d for d in result.diagnostics if d.reason == "ModuleInitError"]
    assert len(init_diags) == 1
    assert init_diags[0].class_name is None
    assert "init boom" in init_diags[0].detail
    assert result.strategies == []


def test_enumerate_dir_invalid_default_config_records_diagnostic(tmp_path: Path) -> None:
    """AC-FR0700-B12-3: a strategy whose default_config() raises records an InvalidConfig diagnostic."""
    _write_user_strategy(
        tmp_path,
        "b12_bad_config.py",
        '''from quantide.core.strategy import BaseStrategy


class BadConfigStrat(BaseStrategy):
    """Bad config strategy."""

    @staticmethod
    def default_config():
        raise ValueError("config broken")
''',
    )

    result = enumerate_strategies(root=str(tmp_path), include_builtin=False)

    invalid_diags = [
        d for d in result.diagnostics if d.reason == "InvalidConfig" and d.class_name == "BadConfigStrat"
    ]
    assert len(invalid_diags) == 1
    assert "config broken" in invalid_diags[0].detail
    assert result.strategies == []


def test_enumerate_dir_reloads_already_imported_module(tmp_path: Path) -> None:
    """AC-FR0700-B12-4: enumerating the same directory twice reloads the cached module (line 536)."""
    _write_user_strategy(
        tmp_path,
        "b12_reload_strat.py",
        '''from quantide.core.strategy import BaseStrategy


class ReloadStrat(BaseStrategy):
    """Reloadable strategy."""

    @staticmethod
    def default_config():
        return {"window": 5}
''',
    )

    first = enumerate_strategies(root=str(tmp_path), include_builtin=False)
    second = enumerate_strategies(root=str(tmp_path), include_builtin=False)

    first_names = [s.name for s in first.strategies]
    second_names = [s.name for s in second.strategies]
    assert "ReloadStrat" in first_names
    assert "ReloadStrat" in second_names


# ---------------------------------------------------------------------------
# _load_module_and_get_info: truthy params class attribute
# ---------------------------------------------------------------------------


def test_load_module_and_get_info_reads_truthy_params_attribute(tmp_path: Path) -> None:
    """AC-FR0700-B12-5: a strategy class with a truthy ``params`` attribute populates StrategyInfo.params."""
    module_stem = "b12_param_strat"
    _write_user_strategy(
        tmp_path,
        f"{module_stem}.py",
        '''from quantide.core.strategy import BaseStrategy


class ParamStrat(BaseStrategy):
    """Strategy with params attribute."""

    params = {"window": 10, "threshold": 0.5}

    @staticmethod
    def default_config():
        return {}
''',
    )
    sys.path.insert(0, str(tmp_path))
    try:
        importlib.import_module(module_stem)
        loader = StrategyLoader()
        infos = loader._load_module_and_get_info(module_stem, str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))

    param_infos = [i for i in infos if i.name == "ParamStrat"]
    assert len(param_infos) == 1
    parsed = json.loads(param_infos[0].params)
    assert parsed == {"window": 10, "threshold": 0.5}


# ---------------------------------------------------------------------------
# _scan_source: file-processing exception is swallowed
# ---------------------------------------------------------------------------


def test_scan_source_swallows_file_processing_exception(tmp_path: Path, monkeypatch) -> None:
    """AC-FR0700-B12-6: _scan_source swallows per-file exceptions and returns an empty dict."""
    _write_user_strategy(tmp_path, "b12_trigger.py", "# placeholder\n")

    loader = StrategyLoader()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("scan boom")

    monkeypatch.setattr(loader, "_load_module_and_get_info", _raise)

    source = ScanSource(directory=tmp_path)
    result = loader._scan_source(source)

    assert result == {}


# ---------------------------------------------------------------------------
# _iter_copyable_example_files: missing builtin directory
# ---------------------------------------------------------------------------


def test_iter_copyable_example_files_raises_when_builtin_missing(tmp_path: Path) -> None:
    """AC-FR0700-B12-7: _iter_copyable_example_files raises FileNotFoundError when builtin dir is absent."""
    loader = StrategyLoader()
    missing_dir = tmp_path / "does_not_exist"
    loader._builtin_example_dir = missing_dir

    with pytest.raises(FileNotFoundError) as excinfo:
        loader._iter_copyable_example_files()

    assert str(missing_dir) in str(excinfo.value)
