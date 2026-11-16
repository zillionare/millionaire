"""v0.2-003 FR-0703 AC-FR-0703-1..2 configuration isolation contracts."""

from __future__ import annotations

from quantide.config import branding
from quantide.config.paths import normalize_data_home
from quantide.config.output_paths import temporary_runtime_dir


def test_branding_environment_override_is_opt_in_and_restored(monkeypatch):
    """AC-FR-0703-1: a valid opt-in edition override changes only branding."""
    monkeypatch.setenv("QUANTIDE_ENABLE_EDITION_OVERRIDE", "true")
    monkeypatch.setenv("QUANTIDE_EDITION", "zillionaire")
    branding._get_installed_release_package.cache_clear()
    branding._load_source_tree_release_package.cache_clear()

    active = branding.get_branding()

    assert active.edition == "zillionaire"
    assert active.product_name == "Zillionaire"
    assert active.runtime_name == "quantide"


def test_normalize_data_home_uses_temporary_storage_for_blank_values(monkeypatch, tmp_path):
    """AC-FR-0703-1: unconfigured runs never write into HOME or the checkout."""
    monkeypatch.delenv("QUANTIDE_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert normalize_data_home("") == str(temporary_runtime_dir() / "market")
    assert not (tmp_path / ".quantide").exists()
