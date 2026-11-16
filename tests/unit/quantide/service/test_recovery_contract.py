"""Account recovery tests using committed SQLite facts and real paper matching."""

import datetime
from types import SimpleNamespace

import pytest

from quantide.core.enums import OrderStatus
from quantide.data.sqlite import db
from quantide.service.sim_broker import PaperBroker

SYMBOL = "000001.SZ"
DAY = datetime.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)


@pytest.fixture
def broker(tmp_path):
    db.init(tmp_path / "account.db")
    broker = PaperBroker.create(
        "recovery", principal=10000, commission=0, stamp_tax=0, min_commission=0,
        market_data=SimpleNamespace(snapshot=lambda symbols: {}),
    )
    broker.set_clock(DAY)
    yield broker
    broker.close()
    db.close()


async def buy(broker, shares=100, volume=1000):
    result = await broker.buy(SYMBOL, shares, price=10, timeout=0.001)
    broker._on_quote_update({SYMBOL: {"lastPrice": 10, "volume": volume}})
    return result.qt_oid


@pytest.mark.asyncio
async def test_full_liquidation_survives_reload(broker):
    await buy(broker)
    broker.set_clock(DAY + datetime.timedelta(days=1))
    broker.settle_t1()
    await broker.sell(SYMBOL, 100, price=11, timeout=0.001)
    broker._on_quote_update({SYMBOL: {"lastPrice": 11}})
    assert db.get_asset(portfolio_id="recovery").cash == 10100
    assert db.get_positions(portfolio_id="recovery").is_empty()
    broker.close()
    loaded = PaperBroker.load("recovery", market_data=SimpleNamespace(snapshot=lambda symbols: {}))
    try:
        assert loaded.cash == 10100
        assert loaded.positions == []
        assert db.trades_all(portfolio_id="recovery").height == 2
    finally:
        loaded.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_reload_restores_pending_and_partial_orders(broker, partial):
    order_id = await broker.buy(SYMBOL, 200, price=10, timeout=0.001)
    if partial:
        broker._on_quote_update({SYMBOL: {"lastPrice": 10, "volume": 1}})
    broker.close()
    loaded = PaperBroker.load("recovery", market_data=SimpleNamespace(snapshot=lambda symbols: {}))
    loaded.set_clock(DAY)
    loaded.apply_fee_config(commission=0, stamp_tax=0, min_commission=0)
    try:
        loaded._on_quote_update({SYMBOL: {"lastPrice": 10, "volume": 100}})
        assert db.get_order(order_id.qt_oid).status == OrderStatus.SUCCEEDED
        assert loaded.positions[0].shares == 200
        assert loaded.cash == 8000
        assert db.trades_all(portfolio_id="recovery")["shares"].sum() == 200
    finally:
        loaded.close()


@pytest.mark.asyncio
async def test_failed_snapshot_rolls_back_entire_fill(broker):
    order_id = await broker.buy(SYMBOL, 100, price=10, timeout=0.001)
    db.db.conn.execute(
        "CREATE TRIGGER fail_account BEFORE INSERT ON assets "
        "BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END"
    )
    broker._on_quote_update({SYMBOL: {"lastPrice": 10}})
    assert broker.cash == 10000
    assert broker.positions == []
    assert db.trades_all(portfolio_id="recovery").is_empty()
    assert db.get_order(order_id.qt_oid).filled == 0
    db.db.conn.execute("DROP TRIGGER fail_account")
    broker._on_quote_update({SYMBOL: {"lastPrice": 10}})
    assert broker.cash == 9000
    assert db.trades_all(portfolio_id="recovery").height == 1


@pytest.mark.asyncio
async def test_missed_close_settles_only_previous_day_and_survives_second_reload(broker):
    await buy(broker)
    broker.close()
    clock = SimpleNamespace(now=lambda: DAY)
    quotes = SimpleNamespace(snapshot=lambda symbols: {})
    intraday = PaperBroker.load("recovery", market_data=quotes, clock=clock)
    assert intraday.positions[0].avail == 0
    intraday.close()
    clock.now = lambda: DAY + datetime.timedelta(days=1)
    loaded = PaperBroker.load("recovery", market_data=quotes, clock=clock)
    try:
        assert loaded.positions[0].avail == 100
        # A next-day buy must not become sellable on an intraday restart.
        await buy(loaded)
        assert loaded.positions[0].shares == 200
        assert loaded.positions[0].avail == 100
    finally:
        loaded.close()
    reloaded = PaperBroker.load("recovery", market_data=quotes, clock=clock)
    try:
        assert reloaded.positions[0].avail == 100
        await reloaded.sell(SYMBOL, 100, price=10, timeout=0.001)
        reloaded.on_quote({SYMBOL: {"price": 10}})
        assert reloaded.positions[0].shares == 100
        assert reloaded.positions[0].avail == 0
    finally:
        reloaded.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [SystemExit, TimeoutError])
async def test_accepted_next_open_order_reconciles_without_duplicate(broker, tmp_path, error_type):
    from quantide.service.runtime_intents import RuntimeIntentExecution
    from quantide.service.strategy_tracking import TrackingStore

    store = TrackingStore(tmp_path / "intents.db")
    row = store.enqueue_next_open_intent(
        runtime_id="run", portfolio_id="recovery", strategy_id="strategy",
        signal_date=DAY.date() - datetime.timedelta(days=1), target_date=DAY.date(),
        method="buy", args=[SYMBOL, 100], kwargs={"price": 10, "timeout": 0.001},
        intent_key="signal-1",
    )
    runtime = SimpleNamespace(status="running", mode="paper", broker=broker)
    manager = RuntimeIntentExecution()
    manager.get_runtime = lambda _: runtime
    manager.tracking_store = store
    original_buy = broker.buy

    async def accepted_then_disconnected(*args, **kwargs):
        await original_buy(*args, **kwargs)
        raise error_type("connection lost after broker acceptance")

    broker.buy = accepted_then_disconnected
    if error_type is SystemExit:
        with pytest.raises(SystemExit):
            await manager.process_next_open_intents("run", DAY)
    else:
        assert await manager.process_next_open_intents("run", DAY) == 0
    assert store.list_next_open_intents(runtime_id="run", status="processing")
    broker.close()
    loaded = PaperBroker.load(
        "recovery", market_data=SimpleNamespace(snapshot=lambda symbols: {}),
        clock=SimpleNamespace(now=lambda: DAY),
    )
    try:
        runtime.broker = loaded
        manager.tracking_store = TrackingStore(tmp_path / "intents.db")
        assert await manager.process_next_open_intents("run", DAY) == 0
        processed = store.list_next_open_intents(runtime_id="run", status="processed")
        assert [item["intent_id"] for item in processed] == [row["intent_id"]]
        assert db.orders_all(portfolio_id="recovery").height == 1
        loaded.on_quote({SYMBOL: {"price": 10}})
        assert loaded.cash == 9000
        assert db.trades_all(portfolio_id="recovery").height == 1
    finally:
        loaded.close()


@pytest.mark.asyncio
async def test_partial_cancellation_is_terminal_after_reload(broker):
    order_id = await buy(broker, shares=200, volume=1)
    assert broker.positions[0].shares == 100
    await broker.cancel_order(order_id)
    assert db.get_order(order_id).status == OrderStatus.PARTSUCC_CANCEL
    broker.close()
    loaded = PaperBroker.load(
        "recovery", market_data=SimpleNamespace(snapshot=lambda symbols: {}),
        clock=SimpleNamespace(now=lambda: DAY),
    )
    try:
        loaded.on_quote({SYMBOL: {"price": 10, "volume": 100}})
        assert loaded.cash == 9000
        assert loaded.positions[0].shares == 100
        assert db.trades_all(portfolio_id="recovery").height == 1
    finally:
        loaded.close()


@pytest.mark.asyncio
async def test_failed_cancellation_keeps_order_active_until_a_durable_result(broker):
    result = await broker.buy(SYMBOL, 100, price=10, timeout=0.001)
    db.db.conn.execute(
        "CREATE TRIGGER fail_cancel BEFORE UPDATE ON orders "
        "BEGIN SELECT RAISE(ABORT, 'disk failure during cancellation'); END"
    )
    with pytest.raises(Exception, match="disk failure"):
        await broker.cancel_order(result.qt_oid)
    assert db.get_order(result.qt_oid).status == OrderStatus.UNREPORTED
    db.db.conn.execute("DROP TRIGGER fail_cancel")
    broker.on_quote({SYMBOL: {"price": 10}})
    assert db.get_order(result.qt_oid).status == OrderStatus.SUCCEEDED
    assert broker.cash == 9000
