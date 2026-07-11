"""v0.2-003-coverage NFR-0020 AC-NFR0020-3: PaperBroker releases callbacks."""

from collections.abc import Callable
import threading
from typing import Any

import pytest

from quantide.core.enums import Topics
from quantide.core.message import msg_hub
from quantide.data.sqlite import db
from quantide.service import sim_broker
from quantide.service.sim_broker import PaperBroker


class RecordingMessageHub:
    """In-memory MessageHub boundary double for lifecycle assertions."""

    def __init__(self) -> None:
        self.subscribers: dict[str, list[Callable[[Any], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        self.subscribers.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        callbacks = self.subscribers.get(topic, [])
        if callback in callbacks:
            callbacks.remove(callback)
        if not callbacks:
            self.subscribers.pop(topic, None)

    def publish(self, topic: str, message: Any) -> None:
        for callback in self.subscribers.get(topic, []):
            callback(message)


class CallbackLock:
    """Lock probe that signals when a callback attempts to enter its critical section."""

    def __init__(self) -> None:
        self.enter_requested = threading.Event()
        self.entered = threading.Event()
        self.release_callback = threading.Event()
        self.block_on_entry = False
        self._lock = threading.RLock()

    def __enter__(self) -> "CallbackLock":
        self.enter_requested.set()
        self._lock.acquire()
        self.entered.set()
        if self.block_on_entry:
            self.release_callback.wait()
        return self

    def __exit__(self, *_: object) -> None:
        self._lock.release()


@pytest.fixture
def broker_and_hub(monkeypatch: pytest.MonkeyPatch):
    """Create a broker with an isolated hub and close it during test teardown."""
    db.init(":memory:")
    hub = RecordingMessageHub()
    monkeypatch.setattr(sim_broker, "msg_hub", hub)
    broker = PaperBroker(portfolio_id="cleanup-test")
    yield broker, hub
    broker.close()


def test_close_unsubscribes_callbacks_and_is_idempotent(broker_and_hub) -> None:
    """v0.2-003-coverage NFR-0020 AC-NFR0020-3: closed brokers receive no events."""
    broker, hub = broker_and_hub

    assert Topics.QUOTES_ALL.value in hub.subscribers
    assert Topics.STOCK_LIMIT.value in hub.subscribers
    queued_quote_callback = hub.subscribers[Topics.QUOTES_ALL.value][0]
    queued_limit_callback = hub.subscribers[Topics.STOCK_LIMIT.value][0]

    broker.close()
    broker.close()
    hub.publish(Topics.QUOTES_ALL.value, {"000001.SZ": {"lastPrice": 10.0}})
    hub.publish(Topics.STOCK_LIMIT.value, {"000001.SZ": {"up": 11.0, "down": 9.0}})
    queued_quote_callback({"000001.SZ": {"lastPrice": 10.0}})
    queued_limit_callback({"000001.SZ": {"up": 11.0, "down": 9.0}})

    assert hub.subscribers == {}
    assert broker._limits == {}


def test_close_waits_for_snapshotted_callback_and_blocks_future_mutation(broker_and_hub) -> None:
    """v0.2-003-coverage NFR-0020 AC-NFR0020-3: close synchronizes callbacks."""
    broker, hub = broker_and_hub
    quote_callback = hub.subscribers[Topics.QUOTES_ALL.value][0]
    limit_callback = hub.subscribers[Topics.STOCK_LIMIT.value][0]
    callback_lock = CallbackLock()
    broker._lock = callback_lock
    callback_done = threading.Event()
    close_done = threading.Event()

    def invoke_quote_callback() -> None:
        quote_callback({"000001.SZ": {"lastPrice": 10.0}})
        callback_done.set()

    def close_broker() -> None:
        broker.close()
        close_done.set()

    callback_thread = threading.Thread(target=invoke_quote_callback)
    close_thread = threading.Thread(target=close_broker)
    try:
        with callback_lock:
            callback_lock.enter_requested.clear()
            callback_lock.entered.clear()
            callback_lock.block_on_entry = True
            callback_thread.start()
            assert callback_lock.enter_requested.wait(timeout=1.0)

        assert callback_lock.entered.wait(timeout=1.0)
        close_thread.start()
        assert not close_done.wait(timeout=0.1)
    finally:
        callback_lock.release_callback.set()
        callback_thread.join(timeout=1.0)
        if close_thread.ident is not None:
            close_thread.join(timeout=1.0)

    assert callback_done.is_set()
    assert close_done.is_set()
    quote_state_after_close = broker._last_mv_update_time
    limit_callback({"000001.SZ": {"up": 11.0, "down": 9.0}})
    quote_callback({"000001.SZ": {"lastPrice": 12.0}})

    assert broker._limits == {}
    assert broker._last_mv_update_time == quote_state_after_close


def test_unit_teardown_removes_direct_broker_callbacks(paper_broker_cleanup_probe) -> None:
    """v0.2-003-coverage NFR-0020 AC-NFR0020-3: direct brokers are released."""
    db.init(":memory:")
    broker = PaperBroker(portfolio_id="unit-autocleanup")
    paper_broker_cleanup_probe.expect_closed(broker)

    with msg_hub._lock:
        callbacks = msg_hub._subscribers[Topics.QUOTES_ALL.value]
        assert any(callback.__self__ is broker for callback in callbacks)
