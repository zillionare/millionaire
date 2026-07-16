"""v0.2-004-coverage-recovery B11-discovery: 5 tests for quantide/service/discovery.py.

Targets previously uncovered lines:
- StrategyLoader.load (lines 334-335): cache hit returns without scanning
- StrategyLoader.get_strategy_info (lines 347-348): exception -> None
- StrategyLoader.list_strategies (lines 356-358): exception -> []
- StrategyLoader.copy_examples_to_directory (line 373): NotADirectoryError
- StrategyLoader.scan_and_cache (lines 191-192): db insert failure swallowed
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quantide.data.models.strategy_config import StrategyInfo
from quantide.service.discovery import ScanSource, StrategyLoader


@pytest.fixture
def loader() -> StrategyLoader:
    return StrategyLoader()


def _patch_db(monkeypatch, fake_table: MagicMock) -> None:
    """Point discovery.db at a fake whose only table is ``fake_table``."""
    fake_db = MagicMock()
    fake_db.__getitem__ = lambda self, name: fake_table
    monkeypatch.setattr("quantide.service.discovery.db", fake_db)


def test_load_returns_cached_without_scanning(loader, monkeypatch) -> None:
    """AC-FR0700-B11-1: load() returns cached dict and skips scan when cache non-empty."""
    cached = {"MyStrategy": object()}
    monkeypatch.setattr(loader, "load_from_cache", lambda: cached)

    scan_calls: list[int] = []
    monkeypatch.setattr(
        loader, "scan_and_cache", lambda *a, **k: scan_calls.append(1) or {}
    )

    result = loader.load()
    assert result is cached
    assert scan_calls == []


def test_get_strategy_info_returns_none_on_db_exception(loader, monkeypatch) -> None:
    """AC-FR0700-B11-2: get_strategy_info returns None when db raises."""
    fake_table = MagicMock()
    fake_table.rows_where.side_effect = RuntimeError("db down")
    _patch_db(monkeypatch, fake_table)

    assert loader.get_strategy_info("X") is None


def test_list_strategies_returns_empty_on_db_exception(loader, monkeypatch) -> None:
    """AC-FR0700-B11-3: list_strategies returns [] when db raises."""
    fake_table = MagicMock()
    type(fake_table).rows = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    _patch_db(monkeypatch, fake_table)

    assert loader.list_strategies() == []


def test_copy_examples_to_directory_raises_not_a_directory_error(loader, tmp_path) -> None:
    """AC-FR0700-B11-4: copy_examples_to_directory raises NotADirectoryError for a file path."""
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("x")

    with pytest.raises(NotADirectoryError):
        loader.copy_examples_to_directory(file_path)


def test_scan_and_cache_swallows_db_insert_failure(loader, monkeypatch) -> None:
    """AC-FR0700-B11-5: scan_and_cache swallows db insert failure and still reloads."""
    info = StrategyInfo(
        name="MyStrat",
        module_path="m",
        file_path="m.py",
        scan_dir="/x",
    )
    fake_table = MagicMock()
    fake_table.insert.side_effect = RuntimeError("insert failed")
    _patch_db(monkeypatch, fake_table)

    monkeypatch.setattr(loader, "_clear_cache", lambda: None)
    monkeypatch.setattr(
        loader,
        "_get_scan_sources",
        lambda ws=None: [ScanSource(directory=Path("/x"))],
    )
    monkeypatch.setattr(loader, "_scan_source", lambda source: {"MyStrat": info})
    monkeypatch.setattr(loader, "load_from_cache", lambda: {})

    result = loader.scan_and_cache()
    assert result == {}
    fake_table.insert.assert_called_once()
