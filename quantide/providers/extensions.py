"""Explicitly enabled, persistent user quote providers loaded inside the service process."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Protocol, cast

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import write_json
from quantide.core.enums import Topics
from quantide.core.message import msg_hub


class QuotePublisher(Protocol):
    """Lifecycle expected from a user-supplied quote publisher."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


def extension_directory() -> Path:
    """Keep user code outside the versioned installation, including during upgrades."""
    directory = ensure_app_config_dir() / "extensions"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def quote_provider_enabled() -> bool:
    """Fail startup on damaged configuration rather than silently choosing another source."""
    config = extension_directory() / "quote-provider.json"
    if not config.exists():
        return False
    payload = json.loads(config.read_text(encoding="utf-8"))
    if type(payload.get("enabled")) is not bool:
        raise ValueError("quote-provider.json requires a boolean enabled field")
    return cast(bool, payload["enabled"])


def configure_quote_provider(enabled: bool) -> None:
    """Only execute user Python after an explicit local enable command."""
    directory = extension_directory()
    if enabled and not (directory / "quote_provider.py").is_file():
        raise FileNotFoundError(f"Create {directory / 'quote_provider.py'} before enabling it")
    write_json(directory / "quote-provider.json", {"enabled": enabled})
    from quantide.config.realtime_source import configure_realtime_source, realtime_source

    if enabled:
        configure_realtime_source("extension")
    elif realtime_source() == "extension":
        configure_realtime_source("none")


def publish_quotes(quotes: dict[str, dict[str, Any]], limits: dict[str, Any] | None = None) -> None:
    """Publish normalized snapshots to the same hub used by paper matching and charts."""
    if not isinstance(quotes, dict):
        raise TypeError("quotes must map exchange-qualified symbols to snapshot dictionaries")
    if quotes:
        msg_hub.publish(Topics.QUOTES_ALL.value, quotes)
    if limits:
        msg_hub.publish(Topics.STOCK_LIMIT.value, limits)


def load_quote_provider() -> QuotePublisher | None:
    """Load create_publisher(publish=..., subscribed_symbols=...) from trusted user code."""
    if not quote_provider_enabled():
        return None
    from quantide.service.market_data_hub import market_data_hub

    path = extension_directory() / "quote_provider.py"
    spec = importlib.util.spec_from_file_location("millionaire_user_quote_provider", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load quote provider from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    publisher = module.create_publisher(
        publish=publish_quotes, subscribed_symbols=market_data_hub.subscribed_symbols
    )
    for method in ("start", "stop"):
        if not callable(getattr(publisher, method, None)):
            raise TypeError(f"Quote provider must implement {method}()")
    return cast(QuotePublisher, publisher)


def manage_quote_provider(action: str) -> int:
    """Expose persistent opt-in without executing the extension in the CLI process."""
    if action != "status":
        configure_quote_provider(action == "enable")
    print(f"Quote provider: {'enabled' if quote_provider_enabled() else 'disabled'}")
    print(f"User source: {extension_directory() / 'quote_provider.py'}")
    if action != "status":
        print("Restart the background service to apply this change.")
    return 0
