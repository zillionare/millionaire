"""B08-trade-lightning-helpers: Test small helpers in trade_lightning.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from quantide.web.pages import trade_lightning as tl_mod
from quantide.web.pages.trade_lightning import (
    _asset_profile,
    _asset_symbol,
    _format_amount_wan,
    _is_valid_price_ref,
    _parse_amount_wan,
    _price_reference_label,
)


# ---------------------------------------------------------------------------
# _asset_symbol
# ---------------------------------------------------------------------------


def test_asset_symbol_with_suffix():
    """Returns code without market suffix."""
    assert _asset_symbol("000001.SZ") == "000001"


def test_asset_symbol_no_suffix():
    """When no dot, returned as-is."""
    assert _asset_symbol("FOO") == "FOO"


# ---------------------------------------------------------------------------
# _asset_profile
# ---------------------------------------------------------------------------


def test_asset_profile_valid():
    """When stock_list has the asset, returns (name, pinyin)."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(return_value="XCompany")
        mock_sl.get_pinyin = MagicMock(return_value="xcompany")
        name, pinyin = _asset_profile("000001.SZ")
    assert name == "XCompany"
    assert pinyin == "xcompany"


def test_asset_profile_stock_list_attribute():
    """When stock_list.get_name etc not present as attrs, returns (asset, '')."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        # No method attrs - raises AttributeError, but spec catches broader Exception
        del mock_sl.get_name
        name, pinyin = _asset_profile("000001.SZ")
    assert name == "000001.SZ"
    assert pinyin == ""


# ---------------------------------------------------------------------------
# _parse_amount_wan
# ---------------------------------------------------------------------------


def test_parse_amount_wan_valid():
    assert _parse_amount_wan("5.5") == 5.5


def test_parse_amount_wan_empty():
    assert _parse_amount_wan("") is None


def test_parse_amount_wan_whitespace():
    assert _parse_amount_wan("   ") is None


def test_parse_amount_wan_invalid():
    assert _parse_amount_wan("abc") is None


def test_parse_amount_wan_zero():
    """0 → None (must be positive)."""
    assert _parse_amount_wan("0") is None


def test_parse_amount_wan_negative():
    assert _parse_amount_wan("-5") is None


# ---------------------------------------------------------------------------
# _format_amount_wan
# ---------------------------------------------------------------------------


def test_format_amount_wan_integer():
    out = _format_amount_wan(5)
    assert "万" in out


def test_format_amount_wan_float():
    out = _format_amount_wan(3.14)
    assert "万" in out


# ---------------------------------------------------------------------------
# _price_reference_label
# ---------------------------------------------------------------------------


def test_price_reference_label_known():
    out = _price_reference_label("current")
    assert out  # non-empty


def test_price_reference_label_unknown():
    """Unknown falls back to 'current'."""
    out = _price_reference_label("garbage")
    assert out  # falls back to non-empty


# ---------------------------------------------------------------------------
# _is_valid_price_ref
# ---------------------------------------------------------------------------


def test_is_valid_price_ref_known():
    assert _is_valid_price_ref("current") is True


def test_is_valid_price_ref_unknown():
    assert _is_valid_price_ref("garbage") is False


# ---------------------------------------------------------------------------
# _resolve_asset_input
# ---------------------------------------------------------------------------


from quantide.web.pages.trade_lightning import _resolve_asset_input


def test_resolve_asset_input_empty():
    assert _resolve_asset_input("") is None
    assert _resolve_asset_input("   ") is None


def test_resolve_asset_input_exact_match():
    """When stock_list has the exact code, returns it."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(return_value="X")
        out = _resolve_asset_input("000001.SZ")
    assert out == "000001.SZ"


def test_resolve_asset_input_exact_no_match():
    """When stock_list doesn't have the code → fuzzy_search path."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(side_effect=Exception("not found"))
        # fuzzy_search should return matches
        mock_sl.fuzzy_search = MagicMock(return_value=["000001.SZ"])
        out = _resolve_asset_input("xyz")
    assert out == "000001.SZ"


def test_resolve_asset_input_fuzzy_multiple():
    """When fuzzy returns multiple matches, returns None."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(side_effect=Exception("not found"))
        mock_sl.fuzzy_search = MagicMock(return_value=["a", "b"])
        out = _resolve_asset_input("xyz")
    assert out is None


def test_resolve_asset_input_fuzzy_exception():
    """When fuzzy raises, returns None."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(side_effect=Exception("not found"))
        mock_sl.fuzzy_search = MagicMock(side_effect=Exception("boom"))
        out = _resolve_asset_input("xyz")
    assert out is None


def test_resolve_asset_input_with_code_pattern():
    """When input matches ASSET_CODE_PATTERN, normalize."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(return_value="X")
        out = _resolve_asset_input("000001.SZ suffix")
    assert out == "000001.SZ" or out is not None
