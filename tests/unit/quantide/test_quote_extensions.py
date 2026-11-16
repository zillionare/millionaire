"""Persistent opt-in and runtime quote extension loading without external services."""

import json

import pytest

from quantide.config.paths import set_app_config_dir_override
from quantide.core.runtime import modes
from quantide.providers.extensions import (
    configure_quote_provider,
    extension_directory,
    load_quote_provider,
    quote_provider_enabled,
)


@pytest.fixture
def extension_home(tmp_path):
    previous = set_app_config_dir_override(tmp_path / "config")
    try:
        yield extension_directory()
    finally:
        set_app_config_dir_override(previous)


def test_disabled_provider_does_not_execute_user_python(extension_home):
    (extension_home / "quote_provider.py").write_text("raise AssertionError('must not execute')")
    assert quote_provider_enabled() is False
    assert load_quote_provider() is None


def test_provider_requires_explicit_code_and_valid_configuration(extension_home):
    with pytest.raises(FileNotFoundError):
        configure_quote_provider(True)
    (extension_home / "quote-provider.json").write_text(json.dumps({"enabled": "true"}))
    with pytest.raises(ValueError, match="boolean"):
        load_quote_provider()


def test_enabled_provider_publishes_in_service_process_and_has_lifecycle(extension_home, monkeypatch):
    from quantide.core.enums import Topics
    from quantide.core.runtime.adapter_registry import AdapterRegistry
    from quantide.providers import extensions

    source = extension_home / "quote_provider.py"
    source.write_text('''
class Publisher:
    def __init__(self, publish, symbols):
        self.publish = publish
        self.symbols = symbols
        self.started = False
    def start(self):
        self.started = True
        self.publish({"000001.SZ": {"price": 10.5}},
                     {"000001.SZ": {"up_limit": 11.0, "down_limit": 9.0}})
    def stop(self):
        self.started = False

def create_publisher(*, publish, subscribed_symbols):
    return Publisher(publish, subscribed_symbols)
''', encoding="utf-8")
    configure_quote_provider(True)
    assert quote_provider_enabled() is True
    events = []
    monkeypatch.setattr(extensions.msg_hub, "publish", lambda topic, rows: events.append((topic, rows)))
    monkeypatch.setattr(modes, "_quote_publisher", None)
    bootstrap = modes.RuntimeBootstrap(mode="paper")
    # An enabled extension takes priority, without starting the demonstration source.
    monkeypatch.setattr(bootstrap, "_create_tencent_publisher", lambda: pytest.fail("wrong source"))
    bootstrap._start_embedded_publisher(AdapterRegistry())
    publisher = modes._quote_publisher
    assert publisher.started
    assert events == [
        (Topics.QUOTES_ALL.value, {"000001.SZ": {"price": 10.5}}),
        (Topics.STOCK_LIMIT.value, {"000001.SZ": {"up_limit": 11.0, "down_limit": 9.0}}),
    ]
    publisher.stop()
    assert not publisher.started
    configure_quote_provider(False)
    assert load_quote_provider() is None
    assert source.exists(), "Disabling an extension must retain user implementation"
