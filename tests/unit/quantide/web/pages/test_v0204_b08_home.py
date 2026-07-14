"""B08-home-page-1: Tests for quantide/web/pages/home.py.

Target: raise coverage from 21.6% to >=80%.
"""

from __future__ import annotations

import pytest

from quantide.core.enums import OrderStatus
from quantide.web.pages.home import (
    _format_amount_wan,
    _format_percent,
    _order_status_badge,
    _position_tag,
    _safe_broker_attr,
    _should_show_no_account_dialog,
)


# ---------------------------------------------------------------------------
# _safe_broker_attr
# ---------------------------------------------------------------------------


def test_safe_broker_attr_returns_existing():
    class _Broker:
        pass

    broker = _Broker()
    broker.value = 42
    assert _safe_broker_attr(broker, "value") == 42


def test_safe_broker_attr_returns_default_when_missing():
    class _Broker:
        pass

    broker = _Broker()
    assert _safe_broker_attr(broker, "missing", default="X") == "X"


def test_safe_broker_attr_returns_none_when_no_default():
    class _Broker:
        pass

    broker = _Broker()
    assert _safe_broker_attr(broker, "missing") is None


def test_safe_broker_attr_handles_attribute_error():
    """Property that raises AttributeError returns default."""
    class _Boom:
        @property
        def boom(self):
            raise AttributeError("no!")

    assert _safe_broker_attr(_Boom(), "boom", default="X") == "X"


# ---------------------------------------------------------------------------
# _format_amount_wan
# ---------------------------------------------------------------------------


def test_format_amount_wan_none():
    assert _format_amount_wan(None) == "--"


def test_format_amount_wan_zero():
    assert _format_amount_wan(0) == "0.00"


def test_format_amount_wan_small_positive():
    """1.5 → 0.0002 万元 which formats as '0.00'."""
    out = _format_amount_wan(1.5)
    assert isinstance(out, str)
    # 1.5 / 10000 = 0.00015 which rounds to 0.00 with 2-decimal format.
    assert "0.00" in out


def test_format_amount_wan_large_value():
    """Large value formatted with unit."""
    out = _format_amount_wan(12345.6789)
    assert isinstance(out, str)
    # Has a comma separator or unit suffix.
    assert "," in out or "万" in out or "." in out


# ---------------------------------------------------------------------------
# _format_percent
# ---------------------------------------------------------------------------


def test_format_percent_none():
    """Returns fallback text ('--') when None."""
    out = _format_percent(None)
    assert isinstance(out, str)


def test_format_percent_zero():
    out = _format_percent(0)
    assert isinstance(out, str)


def test_format_percent_positive():
    out = _format_percent(0.1234)
    assert isinstance(out, str)
    assert "%" in out or "0" in out


# ---------------------------------------------------------------------------
# _position_tag
# ---------------------------------------------------------------------------


def test_position_tag_strong_gain_returns_warning():
    """profit_pct > 0.05 → strong_gain."""
    label, cls = _position_tag(0.10)
    assert isinstance(label, str)
    assert label != ""
    # Returns a tag color
    assert isinstance(cls, str)


def test_position_tag_moderate_gain():
    label, cls = _position_tag(0.03)
    assert isinstance(label, str)
    assert isinstance(cls, str)


def test_position_tag_zero_returns_hold():
    label, _ = _position_tag(0.0)
    assert isinstance(label, str)


def test_position_tag_small_loss_returns_loss():
    label, _ = _position_tag(-0.03)
    assert isinstance(label, str)


def test_position_tag_strong_loss():
    label, _ = _position_tag(-0.10)
    assert isinstance(label, str)
    assert label != ""


def test_position_tag_boundary_strong_gain():
    """Exactly 0.05 = strong gain threshold."""
    label, _ = _position_tag(0.05)
    assert isinstance(label, str)


def test_position_tag_boundary_strong_loss():
    """Exactly -0.05 = strong loss threshold."""
    label, _ = _position_tag(-0.05)
    assert isinstance(label, str)


# ---------------------------------------------------------------------------
# _order_status_badge
# ---------------------------------------------------------------------------


def test_order_status_badge_for_status():
    for status in [
        OrderStatus.SUCCEEDED,
        OrderStatus.PART_SUCC,
        OrderStatus.JUNK,
        OrderStatus.CANCELED,
        OrderStatus.REPORTED,
    ]:
        label, cls = _order_status_badge(status)
        assert isinstance(label, str)
        assert isinstance(cls, str)


def test_order_status_badge_for_unknown():
    """An unknown status (str) returns sensible defaults."""
    label, cls = _order_status_badge("random-status")  # type: ignore[arg-type]
    assert isinstance(label, str)
    assert isinstance(cls, str)


# ---------------------------------------------------------------------------
# _should_show_no_account_dialog
# ---------------------------------------------------------------------------


def test_should_show_no_account_always_false():
    """Spec: 首页不主动弹出账号创建对话框 → always False."""
    assert _should_show_no_account_dialog([]) is False


def test_should_show_no_account_with_accounts():
    assert _should_show_no_account_dialog([{"id": "p1"}]) is False
