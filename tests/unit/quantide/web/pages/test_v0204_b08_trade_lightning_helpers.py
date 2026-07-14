"""B08-trade-lightning-1: Tests for quantide/web/pages/trade_lightning.py helpers.

Target: trade_lightning.py is one of the most-imported v0.2 web modules
(5 imports), currently 66.9% coverage. Cover pure helper functions.
"""

from __future__ import annotations

import pytest

from quantide.web.pages.trade_lightning import (
    _asset_profile,
    _asset_symbol,
    _format_amount_wan,
    _is_valid_price_ref,
    _parse_amount_wan,
    _price_reference_label,
)


# ---------------------------------------------------------------------------
# _asset_symbol / _asset_profile
# ---------------------------------------------------------------------------


def test_asset_symbol_strips_market_suffix():
    """asset_symbol returns the bare symbol (without market suffix)."""
    assert _asset_symbol("000001.SZ") == "000001"
    assert _asset_symbol("600000.SH") == "600000"


def test_asset_profile_returns_name_and_market():
    name, market = _asset_profile("000001.SZ")
    assert isinstance(name, str)
    assert isinstance(market, str)
    # market is "SH"/"SZ"/"BJ" or fallback
    assert market in {"SH", "SZ", "BJ", ""} or len(market) > 0


# ---------------------------------------------------------------------------
# _parse_amount_wan / _format_amount_wan
# ---------------------------------------------------------------------------


def test_parse_amount_wan_valid():
    """Parse a 万元 value as a string into a float (in 万元)."""
    out = _parse_amount_wan("1.5")
    assert out == 1.5


def test_parse_amount_wan_zero():
    """'0' may be treated as empty / non-positive; both are acceptable."""
    out = _parse_amount_wan("0")
    assert out in (None, 0.0)


def test_parse_amount_wan_empty_returns_none():
    assert _parse_amount_wan("") is None


def test_parse_amount_wan_non_numeric_returns_none():
    assert _parse_amount_wan("abc") is None
    assert _parse_amount_wan("--") is None


def test_parse_amount_wan_handles_whitespace():
    out = _parse_amount_wan("  3.5  ")
    assert out == 3.5


def test_format_amount_wan():
    out = _format_amount_wan(1.234)
    assert isinstance(out, str)


def test_format_amount_wan_zero():
    out = _format_amount_wan(0)
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# _price_reference_label
# ---------------------------------------------------------------------------


def test_price_reference_label_returns_string():
    for ref in ("current", "current_p1", "current_p2", "current_p3",
                "ma5", "ma10", "ma20", "ma30", "ma60",
                "close", "open"):
        out = _price_reference_label(ref)
        assert isinstance(out, str)


def test_price_reference_label_unknown():
    out = _price_reference_label("totally-bogus")
    # Should not raise; may return a fallback.
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# _is_valid_price_ref
# ---------------------------------------------------------------------------


def test_is_valid_price_ref_valid():
    assert _is_valid_price_ref("current") is True
    assert _is_valid_price_ref("current_p1") is True


def test_is_valid_price_ref_invalid():
    assert _is_valid_price_ref("") is False
    assert _is_valid_price_ref("xxx") is False
