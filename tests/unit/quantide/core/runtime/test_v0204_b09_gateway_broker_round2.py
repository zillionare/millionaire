"""B09-gateway-broker-round2: Targeted coverage for ``quantide/core/runtime/gateway_broker.py``.

Covers missing branches in ``GatewayBrokerAdapter`` helpers and
``GatewayBrokerWrapper`` history/property paths.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from quantide.core.enums import BrokerKind, OrderSide
from quantide.core.ports import OrderRequest
from quantide.core.runtime.gateway_broker import (
    GatewayBrokerAdapter,
    GatewayBrokerWrapper,
    GatewayTradeStateConsistencyError,
)
from quantide.data.models import Asset, Position


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper.history: missing-data path & forming-bar branches
# ---------------------------------------------------------------------------


def _make_wrapper() -> GatewayBrokerWrapper:
    """Build a wrapper with a dummy adapter (no real gateway needed)."""
    return GatewayBrokerWrapper(object())  # type: ignore[arg-type]


def test_get_history_returns_empty_frame_when_daily_bars_lacks_methods(monkeypatch):
    """[AC-NFR1101-01] When daily_bars exposes neither get_bars nor get_history, an empty frame is returned."""
    wrapper = _make_wrapper()
    bare = object()  # no get_bars / get_history
    monkeypatch.setattr(
        "quantide.core.runtime.gateway_broker.daily_bars", bare, raising=True
    )
    out = wrapper.get_history("000001.SZ", 5, dt.datetime(2024, 1, 10, 10, 0))
    assert isinstance(out, pl.DataFrame)
    assert out.is_empty()


def test_get_history_provider_get_bars_path_returns_history(monkeypatch):
    """[AC-NFR1101-01] When provider exposes get_bars (not get_history), the _provider_get_bars branch is used."""
    wrapper = _make_wrapper()
    today = dt.date(2024, 1, 1)
    df = pl.DataFrame({"date": [today], "asset": ["000001.SZ"], "close": [10.0]})
    monkeypatch.setattr(wrapper, "_today", lambda: today)
    monkeypatch.setattr(wrapper, "_resolve_history_end_date", lambda end_dt: today)
    monkeypatch.setattr(wrapper, "_previous_trade_date", lambda d: today)
    monkeypatch.setattr(
        "quantide.core.runtime.gateway_broker.live_quote.get_daily_bar", lambda asset: None
    )

    # Provider exposes only get_bars (no get_history attr) -> exercises _provider_get_bars second branch.
    class _ProviderWithGetBars:
        def get_bars(self, **kwargs):
            return df

    monkeypatch.setattr(
        "quantide.core.runtime.gateway_broker.daily_bars", _ProviderWithGetBars(), raising=True
    )
    out = wrapper.get_history(
        "000001.SZ", 1, dt.datetime(2024, 1, 1, 9, 0), include_forming_bar=False
    )
    assert isinstance(out, pl.DataFrame)
    assert "close" in out.columns


def test_provider_get_bars_returns_empty_frame_when_provider_has_neither_method():
    """[AC-NFR1101-01] _provider_get_bars returns empty frame when provider exposes neither get_history nor get_bars."""
    wrapper = _make_wrapper()

    class _BareProvider:
        pass

    out = wrapper._provider_get_bars(_BareProvider(), "000001.SZ", 5, dt.date(2024, 1, 1), "1d")
    assert isinstance(out, pl.DataFrame)
    assert out.is_empty()


def test_maybe_attach_forming_bar_returns_hist_when_bar_date_mismatch(monkeypatch):
    """[AC-NFR1101-01] When forming bar's dt != today (end_date), hist is returned unchanged."""
    wrapper = _make_wrapper()
    today = dt.date(2024, 6, 17)
    monkeypatch.setattr(wrapper, "_today", lambda: today)
    hist = pl.DataFrame({"date": [today], "asset": ["000001.SZ"], "close": [10.0]})
    # bar dt is yesterday, not today -> mismatch path.
    bar = {"dt": dt.datetime(2024, 6, 16, 10, 0), "close": 11.0}
    monkeypatch.setattr(
        "quantide.core.runtime.gateway_broker.live_quote.get_daily_bar", lambda asset: bar
    )
    out = wrapper._maybe_attach_forming_bar(
        "000001.SZ", hist, today, dt.datetime(2024, 6, 17, 15, 0), 5
    )
    assert out is hist


def test_resolve_history_end_date_pre_930_falls_back_on_calendar_error(monkeypatch):
    """[AC-NFR1101-01] Pre-9:30 path with calendar raising falls back to end_date - 1 day."""
    wrapper = _make_wrapper()
    end_dt = dt.datetime(2024, 6, 17, 9, 15)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("calendar not loaded")

    from quantide.data.models.calendar import calendar as cal_module_obj

    monkeypatch.setattr(cal_module_obj, "day_shift", _raise)
    assert wrapper._resolve_history_end_date(end_dt) == dt.date(2024, 6, 16)


def test_asset_property_returns_zero_asset_when_adapter_returns_falsy():
    """[AC-NBR1101-01] When adapter.query_assets returns falsy, an all-zero Asset is returned."""
    wrapper = _make_wrapper()
    wrapper._adapter = MagicMock()
    wrapper._adapter.query_assets.return_value = None
    asset = wrapper.asset
    assert isinstance(asset, Asset)
    assert asset.total == 0
    assert asset.cash == 0


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter._resolve_price / _resolve_sizing_price / submit
# ---------------------------------------------------------------------------


def _make_adapter() -> GatewayBrokerAdapter:
    return GatewayBrokerAdapter(MagicMock())


def test_resolve_price_returns_explicit_price_when_positive():
    """[AC-NFR1101-01] Explicit positive price is returned unchanged."""
    adapter = _make_adapter()
    req = OrderRequest(
        asset="000001.SZ", side=OrderSide.BUY, value=100, style="shares", price=12.5
    )
    assert adapter._resolve_price(req) == 12.5


def test_resolve_price_returns_zero_on_live_quote_exception(monkeypatch):
    """[AC-NFR1101-01] When live_quote.get_quote raises, price falls back to 0.0."""
    adapter = _make_adapter()
    req = OrderRequest(
        asset="000001.SZ", side=OrderSide.BUY, value=100, style="shares", price=0
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("quote err")

    monkeypatch.setattr(
        "quantide.core.runtime.gateway_broker.live_quote.get_quote", _raise
    )
    assert adapter._resolve_price(req) == 0.0


def test_resolve_sizing_price_returns_execution_price_on_exception(monkeypatch):
    """[AC-NFR1101-01] When get_price_limits raises, sizing price falls back to execution_price."""
    adapter = _make_adapter()
    req = OrderRequest(
        asset="000001.SZ", side=OrderSide.BUY, value=100, style="shares", price=0
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("limits err")

    monkeypatch.setattr(
        "quantide.core.runtime.gateway_broker.live_quote.get_price_limits", _raise
    )
    assert adapter._resolve_sizing_price(req, 15.0) == 15.0


@pytest.mark.asyncio
async def test_submit_rejects_invalid_shares():
    """[AC-NFR1101-01] submit() with zero shares returns rejected OrderAck."""
    adapter = _make_adapter()
    # _resolve_shares returns 0 when style='shares' and value<100.
    req = OrderRequest(
        asset="000001.SZ", side=OrderSide.BUY, value=50, style="shares", price=10.0
    )
    ack = await adapter.submit(req)
    assert ack.status == "rejected"
    assert ack.qt_oid is None


@pytest.mark.asyncio
async def test_submit_rejected_when_gateway_returns_unsuccessful():
    """[AC-NFR1101-01] submit() with gateway returning success=False yields rejected ack with error."""
    adapter = _make_adapter()
    adapter._client.post_form = MagicMock(return_value={"success": False, "error": "no cash"})
    req = OrderRequest(
        asset="000001.SZ",
        side=OrderSide.BUY,
        value=200,
        style="shares",
        price=10.0,
        extra={"qtoid": "qt1"},
    )
    ack = await adapter.submit(req)
    assert ack.status == "rejected"
    assert "no cash" in ack.message


# ---------------------------------------------------------------------------
# GatewayBrokerAdapter._resolve_shares target_pct branches
# ---------------------------------------------------------------------------


def test_resolve_shares_target_pct_buy_zero_when_delta_le_zero():
    """[AC-NFR1101-01] target_pct BUY side with delta <= 0 returns 0 shares."""
    adapter = _make_adapter()
    # asset total = 100k, current_value = 100k (1000 shares @ 100), target_pct=0.5
    # -> target_value=50k, delta=-50k -> BUY side -> 0 shares.
    adapter.query_assets = MagicMock(
        return_value=MagicMock(total=100_000)
    )
    adapter.query_positions = MagicMock(
        return_value=[MagicMock(asset="000001.SZ", shares=1000, price=100.0)]
    )
    req = OrderRequest(
        asset="000001.SZ",
        side=OrderSide.BUY,
        value=0.5,
        style="target_pct",
        price=100.0,
    )
    assert adapter._resolve_shares(req, 100.0) == 0


def test_resolve_qtoid_remapped_external_id_raises():
    """[AC-NFR1101-01] Re-mapping existing external_order_id to a different qtoid raises."""
    adapter = _make_adapter()
    adapter._external_order_id_to_qtoid["ext-1"] = "qt-A"
    with pytest.raises(GatewayTradeStateConsistencyError):
        adapter._remember_order_mapping(qtoid="qt-B", external_order_id="ext-1")


def test_parse_time_text_empty_returns_now():
    """[AC-NFR1101-01] Empty time string falls back to datetime.datetime.now()."""
    adapter = _make_adapter()
    out = adapter._parse_time_text("")
    assert isinstance(out, dt.datetime)


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper.positions / orders / deferred_orders
# ---------------------------------------------------------------------------


def test_positions_returns_dict_of_position_views():
    """[AC-NFR1101-01] positions property converts PositionView list to dict keyed by asset."""
    wrapper = _make_wrapper()
    today = dt.date(2024, 6, 17)
    wrapper._adapter = MagicMock()
    view = MagicMock(
        asset="000001.SZ", shares=100.0, avail=100.0, price=10.0, mv=1000.0, dt=today
    )
    wrapper._adapter.query_positions.return_value = [view]
    out = wrapper.positions
    assert isinstance(out, dict)
    assert "000001.SZ" in out
    pos = out["000001.SZ"]
    assert isinstance(pos, Position)
    assert pos.shares == 100.0


def test_orders_property_maps_status_and_side_strings():
    """[AC-NFR1101-01] orders property coerces side/status strings into enum members."""
    wrapper = _make_wrapper()
    wrapper._adapter = MagicMock()
    view = MagicMock(
        order_id="o1",
        asset="000001.SZ",
        side="buy",
        shares=100.0,
        price=10.0,
        status="filled",
        tm=dt.datetime(2024, 6, 17, 10, 0),
        filled=100.0,
        error="",
    )
    wrapper._adapter.query_orders.return_value = [view]
    out = wrapper.orders
    assert len(out) == 1
    order = next(iter(out.values()))
    assert order.side == OrderSide.BUY


# ---------------------------------------------------------------------------
# GatewayBrokerWrapper.kind / status / is_connected / cash / portfolio_*
# ---------------------------------------------------------------------------


def test_wrapper_properties_return_expected_values():
    """[AC-NFR1101-01] portfolio_id, portfolio_name, kind, status, is_connected return expected values."""
    wrapper = _make_wrapper()
    assert wrapper.portfolio_id == "gateway"
    assert wrapper.portfolio_name == "实盘网关"
    assert wrapper.kind == BrokerKind.QMT
    assert wrapper.status is True
    assert wrapper.is_connected is True


def test_cash_returns_asset_cash_when_adapter_has_view():
    """[AC-NFR1101-01] cash property delegates to asset.cash."""
    wrapper = _make_wrapper()
    wrapper._adapter = MagicMock()
    wrapper._adapter.query_assets.return_value = MagicMock(
        dt=dt.date(2024, 6, 17),
        principal=1_000_000,
        cash=500_000,
        frozen_cash=0,
        market_value=500_000,
        total=1_000_000,
    )
    assert wrapper.cash == 500_000
