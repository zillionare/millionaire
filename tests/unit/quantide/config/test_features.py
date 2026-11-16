"""Edition feature gates."""

import pytest

from quantide.config.features import (
    FeatureUnavailableError,
    require_live_trading,
    supports_live_trading,
)


def test_ce_does_not_support_live_trading(monkeypatch):
    monkeypatch.setattr("quantide.config.features.get_runtime_edition", lambda: "millionaire")

    assert supports_live_trading() is False
    with pytest.raises(FeatureUnavailableError, match="CE edition"):
        require_live_trading()


def test_private_edition_supports_live_trading(monkeypatch):
    monkeypatch.setattr("quantide.config.features.get_runtime_edition", lambda: "zillionaire")

    assert supports_live_trading() is True
    require_live_trading()

def test_millionaire_pro_edition_supports_live_trading(monkeypatch):
    monkeypatch.setattr(
        "quantide.config.features.get_runtime_edition", lambda: "millionaire-pro"
    )

    assert supports_live_trading() is True
    require_live_trading()
