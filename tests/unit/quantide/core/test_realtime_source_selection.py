"""Persisted source choices and legacy configurations select one publisher."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from quantide.config.paths import set_app_config_dir_override
from quantide.config.realtime_source import configure_realtime_source, realtime_source
from quantide.core.runtime import modes
from quantide.core.runtime.adapter_registry import AdapterRegistry
from quantide.providers import extensions, tushare_publisher


@pytest.fixture
def profile(tmp_path, monkeypatch):
    previous = set_app_config_dir_override(tmp_path / "config")
    monkeypatch.setattr(modes, "_quote_publisher", None)
    try:
        yield tmp_path
    finally:
        set_app_config_dir_override(previous)


@pytest.mark.parametrize("selected", ["tushare", "extension", "tencent", "none", ""])
def test_explicit_and_legacy_selection_starts_only_expected_source(profile, monkeypatch, selected):
    from quantide.config import tencent_trial

    if selected:
        configure_realtime_source(selected)
    monkeypatch.setattr(tencent_trial, "trial_status", lambda: SimpleNamespace(enabled=True))
    monkeypatch.setattr(extensions, "quote_provider_enabled", lambda: True)
    sources = {name: Mock() for name in ("tushare", "extension", "tencent")}
    monkeypatch.setattr(extensions, "load_quote_provider", lambda: sources["extension"])
    monkeypatch.setattr(tushare_publisher, "TusharePublisher", lambda: sources["tushare"])
    bootstrap = modes.RuntimeBootstrap(mode="paper")
    monkeypatch.setattr(bootstrap, "_create_tencent_publisher", lambda: sources["tencent"])
    bootstrap._start_embedded_publisher(AdapterRegistry())
    expected = selected or "extension"
    for name, source in sources.items():
        assert source.start.call_count == int(name == expected)


def test_disabling_extension_preserves_other_source_but_enabling_selects_it(profile):
    configure_realtime_source("tushare")
    extensions.configure_quote_provider(False)
    assert realtime_source() == "tushare"
    (extensions.extension_directory() / "quote_provider.py").write_text("# trusted extension")
    extensions.configure_quote_provider(True)
    assert realtime_source() == "extension"
    extensions.configure_quote_provider(False)
    assert realtime_source() == "none"


@pytest.mark.parametrize("source", [None, [], {}, 42, "unknown"])
def test_invalid_persisted_realtime_source_is_rejected(profile, source):
    path = profile / "config" / "realtime-source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source": source}), encoding="utf-8")
    with pytest.raises(ValueError, match="未知实时行情配置"):
        realtime_source()
