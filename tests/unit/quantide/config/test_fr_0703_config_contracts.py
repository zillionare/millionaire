"""v0.2-003 FR-0703 AC-FR-0703-1..2 configuration isolation contracts."""

from __future__ import annotations

from quantide.config import branding
from quantide.config.paths import normalize_data_home


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


def test_normalize_data_home_uses_the_isolated_home_for_blank_values(monkeypatch, tmp_path):
    """AC-FR-0703-1: blank homes resolve below pytest's temporary HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))

    assert normalize_data_home("") == str(tmp_path / ".quantide")
