import sys
import textwrap
from collections.abc import Generator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from quantide.service.discovery import strategy_loader


@pytest.fixture(autouse=True)
def clean_strategy_scan_tables(db: Any) -> Generator[None]:
    db.execute("DELETE FROM strategy_info")
    db.execute("DELETE FROM strategy_config")
    strategy_loader._strategies = {}
    yield
    db.execute("DELETE FROM strategy_info")
    db.execute("DELETE FROM strategy_config")
    strategy_loader._strategies = {}


def test_scan_and_cache_includes_builtin_examples_without_user_directory(
    db: Any,
) -> None:
    strategies = strategy_loader.scan_and_cache()

    assert "DualMAStrategy" in strategies

    info = strategy_loader.get_strategy_info("DualMAStrategy")
    assert info is not None
    assert info.module_path == "quantide.strategies.example.dual_ma"
    assert Path(info.scan_dir) == Path(strategy_loader.get_builtin_scan_directory())


def test_scan_and_cache_prefers_user_directory_when_strategy_name_conflicts(
    db: Any,
    tmp_path: Path,
) -> None:
    user_dir = tmp_path / "strategies"
    user_dir.mkdir()

    module_name = f"user_strategy_{uuid4().hex}"
    strategy_file = user_dir / f"{module_name}.py"
    strategy_file.write_text(
        textwrap.dedent(
            '''
            from quantide.core.strategy import BaseStrategy


            class DualMAStrategy(BaseStrategy):
                """用户版双均线策略"""
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    strategy_loader.set_scan_directory(str(user_dir))
    strategies = strategy_loader.scan_and_cache()

    info = strategy_loader.get_strategy_info("DualMAStrategy")
    assert info is not None
    assert Path(info.scan_dir) == user_dir
    assert info.module_path == module_name
    assert info.description.strip() == "用户版双均线策略"
    assert strategies["DualMAStrategy"].__module__ == module_name

    sys.modules.pop(module_name, None)


def test_copy_examples_to_directory_copies_missing_files_and_skips_existing(
    db: Any,
    tmp_path: Path,
) -> None:
    user_dir = tmp_path / "strategies"
    user_dir.mkdir()

    first_result = strategy_loader.copy_examples_to_directory(user_dir)
    assert "dual_ma.py" in first_result.copied_files
    assert (user_dir / "dual_ma.py").exists()
    assert first_result.skipped_count == 0

    second_result = strategy_loader.copy_examples_to_directory(user_dir)
    assert "dual_ma.py" in second_result.skipped_files
    assert second_result.copied_count == 0
