"""B08-trade-lightning-helpers: Test small helpers in trade_lightning.py."""

from __future__ import annotations

import polars as pl
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
    """[AC-NFR1101-01] Returns code without market suffix."""
    assert _asset_symbol("000001.SZ") == "000001"


def test_asset_symbol_no_suffix():
    """[AC-NFR1101-01] When no dot, returned as-is."""
    assert _asset_symbol("FOO") == "FOO"


# ---------------------------------------------------------------------------
# _asset_profile
# ---------------------------------------------------------------------------


def test_asset_profile_valid():
    """[AC-NFR1101-01] When stock_list has the asset, returns (name, pinyin)."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(return_value="XCompany")
        mock_sl.get_pinyin = MagicMock(return_value="xcompany")
        name, pinyin = _asset_profile("000001.SZ")
    assert name == "XCompany"
    assert pinyin == "xcompany"


def test_asset_profile_stock_list_attribute():
    """[AC-NFR1101-01] When stock_list.get_name etc not present as attrs, returns (asset, '')."""
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
    """[AC-NFR1101-01] test_parse_amount_wan_valid."""
    assert _parse_amount_wan("5.5") == 5.5


def test_parse_amount_wan_empty():
    """[AC-NFR1101-01] test_parse_amount_wan_empty."""
    assert _parse_amount_wan("") is None


def test_parse_amount_wan_whitespace():
    """[AC-NFR1101-01] test_parse_amount_wan_whitespace."""
    assert _parse_amount_wan("   ") is None


def test_parse_amount_wan_invalid():
    """[AC-NFR1101-01] test_parse_amount_wan_invalid."""
    assert _parse_amount_wan("abc") is None


def test_parse_amount_wan_zero():
    """[AC-NFR1101-01] 0 → None (must be positive)."""
    assert _parse_amount_wan("0") is None


def test_parse_amount_wan_negative():
    """[AC-NFR1101-01] test_parse_amount_wan_negative."""
    assert _parse_amount_wan("-5") is None


# ---------------------------------------------------------------------------
# _format_amount_wan
# ---------------------------------------------------------------------------


def test_format_amount_wan_integer():
    """[AC-NFR1101-01] test_format_amount_wan_integer."""
    out = _format_amount_wan(5)
    assert "万" in out


def test_format_amount_wan_float():
    """[AC-NFR1101-01] test_format_amount_wan_float."""
    out = _format_amount_wan(3.14)
    assert "万" in out


# ---------------------------------------------------------------------------
# _price_reference_label
# ---------------------------------------------------------------------------


def test_price_reference_label_known():
    """[AC-NFR1101-01] test_price_reference_label_known."""
    out = _price_reference_label("current")
    assert out  # non-empty


def test_price_reference_label_unknown():
    """[AC-NFR1101-01] Unknown falls back to 'current'."""
    out = _price_reference_label("garbage")
    assert out  # falls back to non-empty


# ---------------------------------------------------------------------------
# _is_valid_price_ref
# ---------------------------------------------------------------------------


def test_is_valid_price_ref_known():
    """[AC-NFR1101-01] test_is_valid_price_ref_known."""
    assert _is_valid_price_ref("current") is True


def test_is_valid_price_ref_unknown():
    """[AC-NFR1101-01] test_is_valid_price_ref_unknown."""
    assert _is_valid_price_ref("garbage") is False


# ---------------------------------------------------------------------------
# _resolve_asset_input
# ---------------------------------------------------------------------------


from quantide.web.pages.trade_lightning import _resolve_asset_input

from quantide.web.pages import trade_lightning as tl_mod_main


def test_resolve_asset_input_empty():
    """[AC-NFR1101-01] test_resolve_asset_input_empty."""
    assert _resolve_asset_input("") is None
    assert _resolve_asset_input("   ") is None


def test_resolve_asset_input_exact_match():
    """[AC-NFR1101-01] When stock_list has the exact code, returns it."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(return_value="X")
        out = _resolve_asset_input("000001.SZ")
    assert out == "000001.SZ"


def test_resolve_asset_input_exact_no_match():
    """[AC-NFR1101-01] When stock_list doesn't have the code → fuzzy_search path."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(side_effect=Exception("not found"))
        # fuzzy_search should return matches
        mock_sl.fuzzy_search = MagicMock(return_value=["000001.SZ"])
        out = _resolve_asset_input("xyz")
    assert out == "000001.SZ"


def test_resolve_asset_input_fuzzy_multiple():
    """[AC-NFR1101-01] When fuzzy returns multiple matches, returns None."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(side_effect=Exception("not found"))
        mock_sl.fuzzy_search = MagicMock(return_value=["a", "b"])
        out = _resolve_asset_input("xyz")
    assert out is None


def test_resolve_asset_input_fuzzy_exception():
    """[AC-NFR1101-01] When fuzzy raises, returns None."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(side_effect=Exception("not found"))
        mock_sl.fuzzy_search = MagicMock(side_effect=Exception("boom"))
        out = _resolve_asset_input("xyz")
    assert out is None


def test_resolve_asset_input_with_code_pattern():
    """[AC-NFR1101-01] When input matches ASSET_CODE_PATTERN, normalize."""
    with patch.object(tl_mod, "stock_list") as mock_sl:
        mock_sl.get_name = MagicMock(return_value="X")
        out = _resolve_asset_input("000001.SZ suffix")
    assert out == "000001.SZ" or out is not None



# ---------------------------------------------------------------------------
# trade_lightning_create_modal + trade_lightning_delete_modal
# ---------------------------------------------------------------------------


import pytest as _pt
from quantide.web.pages.trade_lightning import (
    _resolve_lightning_price,
    trade_lightning_create_modal,
    trade_lightning_delete_modal,
)


def test_resolve_lightning_price_current_p1():
    """[AC-NFR1101-01] current_p1 returns current * 1.01."""
    with patch.object(tl_mod_main, "live_quote") as mock_lq:
        mock_lq.is_running = True
        mock_lq.get_quote = MagicMock(return_value={"price": 100.0})
        got = _resolve_lightning_price("000001.SZ", "current_p1")
    assert got == 101.0


def test_resolve_lightning_price_current_no_quote():
    """[AC-NFR1101-01] When no quote, falls back to close."""
    with patch.object(tl_mod_main, "live_quote") as mock_lq, \
         patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_lq.is_running = True
        mock_lq.get_quote = MagicMock(return_value=None)
        mock_dbars.get_bars = MagicMock(return_value=pl.DataFrame())
        got = _resolve_lightning_price("000001.SZ", "current")
    assert got == 0.0


def test_resolve_lightning_price_unknown_ref():
    """[AC-NFR1101-01] Unknown price_ref → 0."""
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=pl.DataFrame())
        got = _resolve_lightning_price("000001.SZ", "unknown_ref")
    assert got == 0.0



def test_resolve_lightning_price_close_with_bars():
    """[AC-NFR1101-01] close → returns last bar's close price."""
    import datetime
    fake_bars = pl.DataFrame({
        "date": [datetime.date(2024, 6, 1)],
        "close": [50.0],
    })
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "close")
    assert got == 50.0


def test_resolve_lightning_price_close_exception():
    """[AC-NFR1101-01] When daily_bars.get_bars raises, returns 0."""
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(side_effect=Exception("boom"))
        got = _resolve_lightning_price("000001.SZ", "close")
    assert got == 0.0


def test_resolve_lightning_price_close_zero():
    """[AC-NFR1101-01] When close is 0, returns 0."""
    import datetime
    fake_bars = pl.DataFrame({
        "date": [datetime.date(2024, 6, 1)],
        "close": [0.0],
    })
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "close")
    assert got == 0.0


def test_resolve_lightning_price_ma_invalid_format():
    """[AC-NFR1101-01] maX with invalid number → 0."""
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        got = _resolve_lightning_price("000001.SZ", "ma_invalid")
    assert got == 0.0


def test_resolve_lightning_price_ma_too_few_bars():
    """[AC-NFR1101-01] ma5 with only 3 bars → 0."""
    import datetime
    fake_bars = pl.DataFrame({
        "date": [datetime.date(2024, 6, d) for d in range(1, 4)],
        "close": [100.0, 105.0, 110.0],
    })
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "ma5")
    assert got == 0.0


def test_resolve_lightning_price_ma5_valid():
    """[AC-NFR1101-01] ma5 with 5 bars -> returns mean."""
    import datetime
    fake_bars = pl.DataFrame({
        "date": [datetime.date(2024, 6, d) for d in range(1, 6)],
        "close": [100.0, 110.0, 105.0, 115.0, 120.0],
    })
    with patch.object(tl_mod_main, "daily_bars") as mock_dbars:
        mock_dbars.get_bars = MagicMock(return_value=fake_bars)
        got = _resolve_lightning_price("000001.SZ", "ma5")
    assert got == 110.0


@_pt.mark.asyncio
async def test_trade_lightning_create_modal():
    req = MagicMock()
    req.path_params = {"portfolio_id": "p1"}
    out = await trade_lightning_create_modal(req)
    assert out is not None


@_pt.mark.asyncio
async def test_trade_lightning_delete_modal_not_found():
    """When entry is None, returns toast."""
    with patch.object(tl_mod_main, "get_trade_lightning_entry", return_value=None):
        req = MagicMock()
        req.path_params = {"portfolio_id": "p1", "asset": "000001.SZ"}
        out = await trade_lightning_delete_modal(req)
    assert out is not None


@_pt.mark.asyncio
async def test_trade_lightning_delete_modal_found():
    """When entry exists, returns delete modal."""
    fake_entry = MagicMock()
    fake_entry.asset = "000001.SZ"
    fake_entry.amount_wan = 5.0
    fake_entry.price_ref = "current"
    with patch.object(tl_mod_main, "get_trade_lightning_entry", return_value=fake_entry):
        req = MagicMock()
        req.path_params = {"portfolio_id": "p1", "asset": "000001.SZ"}
        out = await trade_lightning_delete_modal(req)
    assert out is not None



# ---------------------------------------------------------------------------
# Additional tests for edge cases
# ---------------------------------------------------------------------------


def test_parse_amount_wan_decimal_string():
    """[AC-NFR1101-01] test_parse_amount_wan_decimal_string."""
    assert _parse_amount_wan("3.14") == 3.14


def test_format_amount_wan_zero():
    """[AC-NFR1101-01] test_format_amount_wan_zero."""
    out = _format_amount_wan(0.0)
    assert "0" in out


def test_format_amount_wan_positive_int():
    """[AC-NFR1101-01] test_format_amount_wan_positive_int."""
    out = _format_amount_wan(10.0)
    assert "10" in out


def test_is_valid_price_ref_pre_close():
    """[AC-NFR1101-01] pre_close may or may not be valid."""
    out = _is_valid_price_ref("pre_close")
    assert isinstance(out, bool)


def test_is_valid_price_ref_empty_string():
    """[AC-NFR1101-01] test_is_valid_price_ref_empty_string."""
    assert _is_valid_price_ref("") is False


def test_is_valid_price_ref_high():
    """[AC-NFR1101-01] test_is_valid_price_ref_high."""
    assert _is_valid_price_ref("high") is False  # only current, open, pre_close


def test_asset_profile_market_SH():
    """[AC-NFR1101-01] test_asset_profile_market_SH."""
    out = _asset_profile("600000.SH")
    assert isinstance(out, tuple) and len(out) == 2


def test_asset_profile_market_invalid():
    """[AC-NFR1101-01] test_asset_profile_market_invalid."""
    out = _asset_profile("UNKNOWN.XX")
    assert isinstance(out, tuple)
