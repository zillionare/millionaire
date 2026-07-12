"""FR-0302 AC-1..AC-6: data model public-contract characterization."""

import datetime as dt

import polars as pl

from quantide.core.enums import BidType, BrokerKind, OrderSide
from quantide.core.init_wizard_steps import WIZARD_FINAL_STEP
from quantide.data.models.app_state import AppState
from quantide.data.models.calendar import Calendar
from quantide.data.models.entities import Order, Portfolio, Position
from quantide.data.models.index_bars import IndexBars
from quantide.data.models.strategy_config import StrategyConfig, StrategyInfo


def test_calendar_integer_date_and_time_round_trip():
    """FR-0302 AC-1: calendar converts fixed date and timezone-aware time integers."""
    calendar = Calendar()
    date = dt.date(2024, 1, 2)
    moment = dt.datetime(2024, 1, 2, 9, 31, tzinfo=dt.timezone.utc)

    assert calendar.int2date(calendar.date2int(date)) == date
    assert calendar.time2int(moment) == 202401020931
    assert calendar.int2time(202401020931).replace(tzinfo=None) == moment.replace(tzinfo=None)


def test_app_state_round_trip_and_readiness_are_derived_from_steps():
    """FR-0302 AC-4: state serialization preserves readiness and live/backtest gates."""
    state = AppState(
        init_completed=True,
        init_step=WIZARD_FINAL_STEP,
        app_home="/tmp/quantide",
        gateway_enabled=True,
        tushare_token="token",
        epoch=dt.date(2020, 1, 1),
    )

    restored = AppState.from_dict(state.to_dict() | {"ignored": "field"})

    assert restored.epoch == dt.date(2020, 1, 1)
    assert restored.is_fully_initialized
    assert restored.can_use_live_trading()
    assert restored.can_use_backtest()


def test_index_bars_schema_is_a_schema_marker_with_exact_columns_and_types():
    """FR-0302 AC-5: IndexBars exposes only the documented Polars schema."""
    assert IndexBars.SCHEMA == {
        "sector_id": pl.Utf8,
        "date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    }


def test_entities_normalize_serialized_dates_and_enum_values():
    """FR-0302 AC-6: persisted entity inputs restore date and enum value types."""
    order = Order("p1", "000001.SZ", 1, 10, 1, tm="2024-01-02T09:30:00")
    position = Position("p1", "2024-01-02T00:00:00", "000001.SZ", 1, 1, 10, 0, 10)
    portfolio = Portfolio("p1", "bt", "2024-01-02")

    assert (order.side, order.bid_type, order.tm) == (OrderSide.BUY, BidType.LATEST, dt.datetime(2024, 1, 2, 9, 30))
    assert position.dt == dt.date(2024, 1, 2)
    assert portfolio.kind is BrokerKind.BACKTEST


def test_strategy_entities_supply_ids_timestamps_and_database_schema():
    """FR-0302 AC-6: strategy entities provide isolated defaults and schemas."""
    first, second = StrategyConfig(), StrategyConfig()
    info = StrategyInfo(name="Momentum")

    assert first.id != second.id
    assert isinstance(first.updated_at, dt.datetime)
    assert info.to_dict()["name"] == "Momentum"
    assert {"id", "key", "value", "updated_at"} <= set(StrategyConfig.to_db_schema())
