"""v0.2-003 FR-0206 core foundation contract tests."""

import datetime as dt

import pytest

from quantide.core.enums import FrameType, OrderSide
from quantide.core.errors import InsufficientCash, TradeError, TradeErrors
from quantide.core.sdk_metadata import Security, SecurityListSDK


def test_frame_type_round_trips_and_rejects_invalid_or_incompatible_values():
    """FR-0206 AC-1: frame integers and ordering follow the published enum mapping."""
    assert FrameType.from_int(FrameType.DAY.to_int()) is FrameType.DAY
    assert FrameType.MIN1 < FrameType.DAY < FrameType.MONTH
    with pytest.raises(KeyError):
        FrameType.from_int(99)
    with pytest.raises(TypeError):
        _ = FrameType.DAY < "1d"


def test_trade_error_preserves_code_and_interpolated_context():
    """FR-0206 AC-5: public errors retain their concrete type, code, and inputs."""
    error = InsufficientCash("000001.SZ", 1000, 100)

    assert isinstance(error, TradeError)
    assert error.code is TradeErrors.ERROR_INSUF_CASH
    assert str(error) == "(7 | Insufficient cash for 000001.SZ, required: 1000, got cash: 100)"


def test_security_list_filters_by_listing_st_and_reports_unknown_name():
    """FR-0206 AC-4: SecurityListSDK returns deterministic listing metadata and errors."""
    sdk = SecurityListSDK()
    sdk.register(Security("000001.SZ", "Alpha", list_date=dt.date(2026, 1, 1)))
    sdk.register(Security("000002.SZ", "ST Beta", is_st=True, list_date=dt.date(2026, 1, 1)))

    assert sdk.stocks_listed(dt.date(2026, 7, 10)) == ["000001.SZ"]
    assert sdk.days_since_ipo("000001.SZ", dt.date(2026, 1, 11)) == 10
    assert sdk.get_name("000001.SZ") == "Alpha"
    with pytest.raises(ValueError, match="Unknown security"):
        sdk.get_name("missing")
    assert OrderSide.BUY.value == 1
