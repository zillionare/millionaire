"""FR-0402 coverage tests for broker port adapters and isolated broker state."""

import asyncio
import datetime

import pytest

from quantide.core.enums import BrokerKind
from quantide.data.sqlite import db
from quantide.service.abstract_broker import AbstractBroker
from quantide.service.backtest_broker import BacktestBroker
from quantide.service.sim_broker import PaperBroker


class _NoDataFeed:
    """FR-0402 port double that deliberately supplies no match data."""

    def get_price_for_match(self, _asset, _tm):
        return None


@pytest.fixture
def sqlite_db(tmp_path):
    """FR-0402: initialize a fresh file-backed SQLite database for each broker test.

    Restore the previous session-level DB connection after each test so
    later tests in the suite aren't polluted (e.g., discovery fixtures).
    """
    previous_initialized = getattr(db, "_initialized", False)
    previous_path = db.db_path if getattr(db, "_initialized", False) else None
    db.init(tmp_path / "test.db")
    yield db
    db.close()
    if previous_initialized and previous_path:
        db._initialized = False
        db.init(previous_path)
    else:
        db._initialized = previous_initialized


@pytest.mark.parametrize("broker_type", ["abstract", "backtest", "paper"])
def test_broker_types_keep_isolated_portfolio_identity(
    broker_type, monkeypatch, sqlite_db
) -> None:
    """FR-0402 AC-6: each broker retains its own portfolio identity and broker kind."""
    day = datetime.date(2024, 1, 2)
    if broker_type == "abstract":
        broker = AbstractBroker(portfolio_id="abstract", kind=BrokerKind.BACKTEST)
    elif broker_type == "backtest":
        monkeypatch.setattr(
            "quantide.service.backtest_broker.calendar.replace_time",
            lambda date, hour, minute=0: datetime.datetime(
                date.year, date.month, date.day, hour, minute
            ),
        )
        monkeypatch.setattr(
            "quantide.service.backtest_broker.calendar.day_shift", lambda *_: day
        )
        broker = BacktestBroker(day, day, "backtest", _NoDataFeed())
    else:
        broker = PaperBroker(
            portfolio_id="paper",
            market_data=None,
            market_value_update_interval=0,
        )

    assert broker.portfolio_id == broker_type
    assert broker.kind in {BrokerKind.BACKTEST, BrokerKind.SIMULATION}


@pytest.mark.asyncio
async def test_abstract_broker_awake_delivers_early_result_without_timeout() -> None:
    """FR-0402 AC-1: awake results are returned deterministically by a later wait."""
    broker = AbstractBroker()
    broker.awake("order-1", {"status": "filled"})

    result, remaining = await broker.wait("order-1", timeout=0.01)

    assert result == {"status": "filled"}
    assert remaining == 0.0


@pytest.mark.asyncio
async def test_abstract_broker_wait_times_out_with_empty_result() -> None:
    """FR-0402 AC-1: waiting without an awake signal ends with a deterministic timeout."""
    result, remaining = await AbstractBroker().wait("missing", timeout=0.001)

    assert result is None
    assert remaining == 0
