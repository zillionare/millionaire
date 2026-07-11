"""v0.2-003 NFR-0020 AC-NFR-0020-1..4 isolation and determinism checks."""

from __future__ import annotations

from quantide.config.paths import (
    clear_app_config_dir_override,
    get_app_config_dir,
    set_app_config_dir_override,
)


def test_config_directory_override_is_reversible_between_isolated_cases(tmp_path):
    """AC-NFR-0020-1..2: mutable config state is reset after a test boundary."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    try:
        set_app_config_dir_override(first)
        assert get_app_config_dir() == first
        set_app_config_dir_override(second)
        assert get_app_config_dir() == second
    finally:
        clear_app_config_dir_override()


def test_temp_config_paths_are_deterministic_and_do_not_create_files(tmp_path):
    """AC-NFR0020-3..4: reading an isolated path has no filesystem side effect."""
    target = tmp_path / "config"
    try:
        set_app_config_dir_override(target)
        assert get_app_config_dir() == target
        assert get_app_config_dir() == target
        assert not target.exists()
    finally:
        clear_app_config_dir_override()
