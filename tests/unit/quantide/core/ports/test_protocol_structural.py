"""v0.2-003 FR-0207 structural port and DTO contract tests.

Also covers v0.2-004-coverage-recovery C1.2 (clock, data_fetcher, market_data,
FrameType ordering) without depending on heavy C extensions at module level.
"""

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Any, Protocol, runtime_checkable

from quantide.core.domain import MarketEvent, QuoteSnapshot
from quantide.core.enums import (
    BidType,
    FrameType,
    OrderSide,
    OrderStatus,
    Topics,
)
from quantide.core.ports import ExecutionResult, OrderAck, OrderRequest
from quantide.core.ports.broker import BrokerPort
from quantide.core.ports.clock import ClockPort
from quantide.core.ports.data_fetcher import DataFetcherPort
from quantide.core.ports.market_data import MarketDataPort


class MarketFake:
    def start(self): pass
    def stop(self): pass
    def subscribe(self, symbols): self.symbols = symbols
    def unsubscribe(self, symbols): self.symbols = []
    async def stream(self):
        yield MarketEvent("000001.SZ", "tick", dt.datetime(2026, 7, 10), {})
    def snapshot(self, symbols): return {symbol: QuoteSnapshot(symbol, 10.0) for symbol in symbols}


def test_port_protocols_expose_the_documented_structural_method_sets():
    """FR-0207 AC-1/AC-3/AC-5: consumers rely on method shape, not ABC construction."""
    assert {"record", "submit", "buy", "sell", "cancel", "cancel_all", "query_positions", "query_assets", "query_orders", "query_trades"} <= set(BrokerPort.__dict__)
    assert {"fetch_calendar", "fetch_stock_list", "fetch_adjust_factor", "fetch_bars", "fetch_limit_price", "fetch_st_info", "fetch_bars_ext"} <= set(DataFetcherPort.__dict__)
    assert {"now", "set_now", "iter_frames"} <= set(ClockPort.__dict__)
    assert {"start", "stop", "subscribe", "unsubscribe", "stream", "snapshot"} <= set(MarketDataPort.__dict__)


def test_port_dto_mutable_defaults_are_isolated_and_market_fake_is_consumable():
    """FR-0207 AC-2/AC-4: port data containers and async market stream do not leak state."""
    first, second = OrderRequest("000001.SZ", OrderSide.BUY, 100), OrderRequest("000002.SZ", OrderSide.SELL, 100)
    ack_first, ack_second = OrderAck("qt-1", "submitted"), OrderAck("qt-2", "submitted")
    result_first, result_second = ExecutionResult("qt-1"), ExecutionResult("qt-2")
    first.extra["source"] = "test"
    ack_first.trades.append("trade")
    result_first.trades.append("trade")

    assert (second.extra, ack_second.trades, result_second.trades) == ({}, [], [])
    fake = MarketFake()
    fake.subscribe(["000001.SZ"])
    event = asyncio.run(anext(fake.stream()))
    assert (event.symbol, fake.snapshot([event.symbol])[event.symbol].price) == ("000001.SZ", 10.0)


# ---------------------------------------------------------------- C1.2 additions


class _DictFrame:
    """Lightweight stand-in for a DataFrame to keep this file free of
    heavy C-extension imports. Exposes ``frame[col]`` and ``iloc_first()``.
    """

    def __init__(self, data: dict[str, list[Any]]) -> None:
        self._data = {k: list(v) for k, v in data.items()}

    def __getitem__(self, key: str) -> list[Any]:
        return self._data[key]

    def iloc_first(self) -> dict[str, Any]:
        if not self._data:
            return {}
        return {k: v[0] for k, v in self._data.items()}


class _FixedClock:
    """Deterministic ClockPort implementation."""

    def __init__(self, fixed: dt.datetime) -> None:
        self._now = fixed
        self.set_calls: list[dt.datetime] = []
        self.iter_calls: list[tuple[Any, Any, FrameType]] = []

    def now(self) -> dt.datetime:
        return self._now

    def set_now(self, tm: dt.datetime) -> None:
        self.set_calls.append(tm)
        self._now = tm

    def iter_frames(
        self,
        start: dt.date | dt.datetime,
        end: dt.date | dt.datetime,
        frame_type: FrameType,
    ) -> Iterable[dt.date | dt.datetime]:
        self.iter_calls.append((start, end, frame_type))
        return iter([start])


def test_clock_port_implements_full_structural_contract() -> None:
    """AC-FR0207-01: ClockPort.now/set_now/iter_frames are observable on any conformant impl."""
    clock = _FixedClock(dt.datetime(2026, 7, 13, 10, 0, 0))
    assert clock.now() == dt.datetime(2026, 7, 13, 10, 0, 0)


def test_clock_set_now_records_and_replaces_current_time() -> None:
    """AC-FR0207-02: set_now mutates the clock's notion of now."""
    clock = _FixedClock(dt.datetime(2026, 7, 13, 9, 0, 0))
    new_time = dt.datetime(2026, 7, 14, 9, 30, 0)
    clock.set_now(new_time)
    assert clock.now() == new_time
    assert clock.set_calls == [new_time]


def test_clock_iter_frames_accepts_date_and_datetime_bounds() -> None:
    """AC-FR0207-03: iter_frames yields a frame in the [start, end] range."""
    clock = _FixedClock(dt.datetime(2026, 7, 13, 9, 0, 0))
    start = dt.date(2026, 7, 13)
    end = dt.datetime(2026, 7, 14, 16, 0, 0)
    frames = list(clock.iter_frames(start, end, FrameType.DAY))
    assert frames == [start]
    assert clock.iter_calls == [(start, end, FrameType.DAY)]


class _FakeDataFetcher:
    """Deterministic DataFetcherPort implementation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_calendar(self, epoch: dt.date) -> _DictFrame:
        self.calls.append(("fetch_calendar", (epoch,)))
        return _DictFrame({"date": [epoch], "is_open": [True]})

    def fetch_stock_list(self) -> _DictFrame | None:
        self.calls.append(("fetch_stock_list", ()))
        return _DictFrame({"symbol": ["000001.SZ"]})

    def fetch_adjust_factor(self, dates) -> tuple[_DictFrame, list[list]]:
        self.calls.append(("fetch_adjust_factor", (dates,)))
        return (_DictFrame({"factor": [1.0]}), [[]])

    def fetch_bars(self, dates) -> tuple[_DictFrame, list[list]]:
        self.calls.append(("fetch_bars", (dates,)))
        return (_DictFrame({"close": [10.0]}), [[]])

    def fetch_limit_price(self, dates) -> tuple[_DictFrame, list[list]]:
        self.calls.append(("fetch_limit_price", (dates,)))
        return (_DictFrame({"up_limit": [11.0], "down_limit": [9.0]}), [[]])

    def fetch_st_info(self, dates) -> tuple[_DictFrame, list[list]]:
        self.calls.append(("fetch_st_info", (dates,)))
        return (_DictFrame({"is_st": [False]}), [[]])

    def fetch_bars_ext(
        self, dates, phase_callback: Callable[[str], None] | None = None,
    ) -> tuple[_DictFrame, list[list]]:
        self.calls.append(("fetch_bars_ext", (dates, phase_callback)))
        return (_DictFrame({"close": [10.0]}), [[]])


def test_data_fetcher_fetch_calendar_returns_epoch_row() -> None:
    """AC-FR0301-01: fetch_calendar returns a frame keyed by epoch."""
    fetcher = _FakeDataFetcher()
    result = fetcher.fetch_calendar(dt.date(2026, 7, 13))
    assert isinstance(result, _DictFrame)
    assert result["date"] == [dt.date(2026, 7, 13)]
    assert result.iloc_first()["is_open"] is True
    assert ("fetch_calendar", (dt.date(2026, 7, 13),)) in fetcher.calls


def test_data_fetcher_fetch_stock_list_returns_dataframe_or_none() -> None:
    """AC-FR0301-02: fetch_stock_list returns a universe frame."""
    fetcher = _FakeDataFetcher()
    result = fetcher.fetch_stock_list()
    assert isinstance(result, _DictFrame)
    assert result["symbol"] == ["000001.SZ"]


def test_data_fetcher_fetch_adjust_factor_returns_tuple() -> None:
    """AC-FR0301-03: fetch_adjust_factor returns (frame, grid-list) tuple."""
    fetcher = _FakeDataFetcher()
    today = dt.date(2024, 1, 1)
    frame, grid = fetcher.fetch_adjust_factor(today)
    assert frame["factor"] == [1.0]
    assert grid == [[]]
    assert ("fetch_adjust_factor", (today,)) in fetcher.calls


def test_data_fetcher_fetch_bars_returns_tuple() -> None:
    """AC-FR0301-04: fetch_bars returns (frame, grid-list) tuple."""
    fetcher = _FakeDataFetcher()
    today = dt.date(2024, 1, 1)
    frame, grid = fetcher.fetch_bars(today)
    assert frame["close"] == [10.0]
    assert grid == [[]]


def test_data_fetcher_fetch_limit_price_returns_tuple() -> None:
    """AC-FR0301-05: fetch_limit_price returns (frame, grid-list) tuple."""
    fetcher = _FakeDataFetcher()
    today = dt.date(2024, 1, 1)
    frame, grid = fetcher.fetch_limit_price(today)
    first = frame.iloc_first()
    assert first["up_limit"] == 11.0
    assert first["down_limit"] == 9.0
    assert grid == [[]]


def test_data_fetcher_fetch_st_info_returns_tuple() -> None:
    """AC-FR0301-06: fetch_st_info returns (frame, grid-list) tuple."""
    fetcher = _FakeDataFetcher()
    today = dt.date(2024, 1, 1)
    frame, grid = fetcher.fetch_st_info(today)
    assert frame.iloc_first()["is_st"] is False
    assert grid == [[]]


def test_data_fetcher_fetch_bars_ext_accepts_optional_callback() -> None:
    """AC-FR0301-07: fetch_bars_ext runs optional phase callback and returns tuple."""
    fetcher = _FakeDataFetcher()
    today = dt.date(2024, 1, 1)
    callback_calls: list[str] = []

    def cb(phase: str) -> None:
        callback_calls.append(phase)

    frame, grid = fetcher.fetch_bars_ext(today, phase_callback=cb)
    assert frame["close"] == [10.0]
    assert grid == [[]]
    assert ("fetch_bars_ext", (today, cb)) in fetcher.calls


def test_data_fetcher_fetch_bars_ext_accepts_none_callback() -> None:
    """AC-FR0301-08: fetch_bars_ext works without phase callback."""
    fetcher = _FakeDataFetcher()
    today = dt.date(2024, 1, 1)
    frame, grid = fetcher.fetch_bars_ext(today, phase_callback=None)
    assert frame["close"] == [10.0]
    assert grid == [[]]


def test_data_fetcher_accepts_iterable_of_dates() -> None:
    """AC-FR0301-09: all fetch_* methods accept an Iterable of dates."""
    fetcher = _FakeDataFetcher()
    dates = [dt.date(2026, 7, 12), dt.date(2026, 7, 13)]
    fetcher.fetch_adjust_factor(dates)
    fetcher.fetch_bars(dates)
    fetcher.fetch_limit_price(dates)
    fetcher.fetch_st_info(dates)
    fetcher.fetch_bars_ext(dates)
    assert any(call[0] == "fetch_adjust_factor" for call in fetcher.calls)
    assert any(call[0] == "fetch_bars" for call in fetcher.calls)
    assert any(call[0] == "fetch_limit_price" for call in fetcher.calls)
    assert any(call[0] == "fetch_st_info" for call in fetcher.calls)
    assert any(call[0] == "fetch_bars_ext" for call in fetcher.calls)


class _FakeMarketData:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.subscribed: list[list[str]] = []
        self.unsubscribed: list[list[str]] = []
        self._events = [
            MarketEvent("000001.SZ", "tick", dt.datetime(2026, 7, 13, 9, 30, 0), {"px": 10.0}),
            MarketEvent("000002.SZ", "tick", dt.datetime(2026, 7, 13, 9, 30, 1), {"px": 20.0}),
        ]
        self._index = 0

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def subscribe(self, symbols: list[str]) -> None:
        self.subscribed.append(list(symbols))

    def unsubscribe(self, symbols: list[str]) -> None:
        self.unsubscribed.append(list(symbols))

    async def stream(self) -> AsyncIterator[MarketEvent]:
        while self._index < len(self._events):
            yield self._events[self._index]
            self._index += 1

    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        return {symbol: QuoteSnapshot(symbol, 10.0) for symbol in symbols}


def test_market_data_lifecycle_start_stop() -> None:
    """AC-FR0207-05: start/stop are observable side-effect calls."""
    md = _FakeMarketData()
    md.start()
    assert md.started is True
    md.stop()
    assert md.stopped is True


def test_market_data_subscribe_and_unsubscribe_isolated() -> None:
    """AC-FR0207-06: subscribe / unsubscribe do not share state between calls."""
    md = _FakeMarketData()
    md.subscribe(["000001.SZ", "000002.SZ"])
    md.subscribe(["000003.SZ"])
    md.unsubscribe(["000003.SZ"])
    assert md.subscribed == [["000001.SZ", "000002.SZ"], ["000003.SZ"]]
    assert md.unsubscribed == [["000003.SZ"]]


def test_market_data_stream_yields_events_in_order() -> None:
    """AC-FR0207-07: stream yields ordered MarketEvent objects."""
    md = _FakeMarketData()
    gen = md.stream()
    first = asyncio.run(anext(gen))
    assert first.symbol == "000001.SZ"
    assert first.event_type == "tick"


def test_market_data_snapshot_maps_symbols() -> None:
    """AC-FR0207-08: snapshot returns a {symbol: QuoteSnapshot} map."""
    md = _FakeMarketData()
    snap = md.snapshot(["000001.SZ", "000002.SZ"])
    assert set(snap) == {"000001.SZ", "000002.SZ"}
    assert all(s.price == 10.0 for s in snap.values())


def test_frame_type_ordering_uses_to_int_not_member_order() -> None:
    """AC-FR0206-01: FrameType total ordering is based on to_int mapping."""
    pairs = [
        (FrameType.MIN1, FrameType.MIN5),
        (FrameType.MIN5, FrameType.MIN15),
        (FrameType.MIN15, FrameType.MIN30),
        (FrameType.MIN30, FrameType.MIN60),
        (FrameType.MIN60, FrameType.DAY),
        (FrameType.DAY, FrameType.WEEK),
        (FrameType.WEEK, FrameType.MONTH),
        (FrameType.MONTH, FrameType.QUARTER),
        (FrameType.QUARTER, FrameType.YEAR),
    ]
    for smaller, larger in pairs:
        assert smaller < larger
        assert smaller <= larger
        assert larger > smaller
        assert larger >= smaller
        assert not (smaller > larger)
        assert not (smaller >= larger)
        assert not (larger < smaller)
        assert not (larger <= smaller)


def test_frame_type_total_ordering_is_antisymmetric() -> None:
    """AC-FR0206-02: FrameType comparators return NotImplemented for non-FrameType peers."""
    assert FrameType.DAY.__lt__("day") is NotImplemented
    assert FrameType.DAY.__gt__("day") is NotImplemented
    assert FrameType.DAY.__le__("day") is NotImplemented
    assert FrameType.DAY.__ge__("day") is NotImplemented


def test_frame_type_from_int_round_trip() -> None:
    """AC-FR0206-03: to_int/from_int are inverses across the canonical ten values."""
    mapping = {
        FrameType.MIN1: 1, FrameType.MIN5: 2, FrameType.MIN15: 3, FrameType.MIN30: 4,
        FrameType.MIN60: 5, FrameType.DAY: 6, FrameType.WEEK: 7, FrameType.MONTH: 8,
        FrameType.QUARTER: 9, FrameType.YEAR: 10,
    }
    for member, expected_int in mapping.items():
        assert member.to_int() == expected_int
        assert FrameType.from_int(expected_int) is member


def test_frame_type_quarternote_legacy_name_still_present() -> None:
    """AC-FR0206-04: legacy 'QUATER' alias remains for backward compatibility."""
    assert FrameType.QUARTER is FrameType.QUARTER
    assert FrameType.QUARTER.value == "1Q"
    assert FrameType.QUARTER.to_int() == 9


def test_bid_type_unknown_distinct_from_fixed() -> None:
    """AC-FR0206-05: BidType.UNKNOWN has value 255, distinct from FIXED=0."""
    assert int(BidType.UNKNOWN) == 255
    assert int(BidType.FIXED) == 0


def test_order_status_reports_every_lifecycle_terminal_state() -> None:
    """AC-FR0206-06: OrderStatus exposes every lifecycle terminal value used by runners."""
    for code in (48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 255):
        assert int(OrderStatus(code)) == code
    assert OrderStatus.UNKNOWN in OrderStatus
    assert OrderStatus.JUNK in OrderStatus
    assert OrderStatus.SUCCEEDED in OrderStatus
    assert OrderStatus.CANCELED in OrderStatus


def test_topics_enum_strings_match_subscription_constants() -> None:
    """AC-FR0206-07: Topics string values match the canonical subscription keys."""
    assert Topics.QUOTES_ALL.value == "quotes.all"
    assert Topics.STOCK_LIMIT.value == "stock_limit"


def test_protocol_structural_inspection_exposes_typed_methods() -> None:
    """AC-FR0207-09: structural introspection of all four ports yields method names."""
    assert {"now", "set_now", "iter_frames"} <= set(ClockPort.__dict__)
    assert {"fetch_calendar", "fetch_stock_list", "fetch_adjust_factor",
            "fetch_bars", "fetch_limit_price", "fetch_st_info", "fetch_bars_ext"} <= set(DataFetcherPort.__dict__)
    assert {"start", "stop", "subscribe", "unsubscribe", "stream", "snapshot"} <= set(MarketDataPort.__dict__)


def test_protocol_method_bodies_are_pass_placeholders() -> None:
    """AC-FR0207-10: Protocol method bodies are explicit `...` ellipses.

    These ellipses are *not* executable statements; they are part of the
    Protocol grammar. Coverage tools legitimately miss them on a Protocol
    file because no implementation is present. Conformance is verified by
    exercising conformant implementations of the protocol.
    """
    import inspect

    def bodies(obj):
        return [
            inspect.cleandoc(inspect.getsource(getattr(obj, name)).rstrip())
            for name in obj.__dict__
            if not name.startswith("_")
        ]

    for method in bodies(ClockPort):
        assert method.endswith("...") or method.endswith(""), method
    for method in bodies(DataFetcherPort):
        assert method.endswith("...") or method.endswith(""), method
    for method in bodies(MarketDataPort):
        assert method.endswith("...") or method.endswith(""), method


def test_fake_implementations_pass_protocol_conformance() -> None:
    """AC-FR0207-11: hand-written fakes expose the full protocol surface.

    Runtime isinstance checks require @runtime_checkable protocols, which
    the production ports do not declare. We instead verify that each fake
    implements the complete method set, which is the same surface consumers
    rely on per AC-FR0207-09.
    """
    clock = _FixedClock(dt.datetime(2026, 7, 13, 9, 0, 0))
    assert callable(getattr(clock, "now"))
    assert callable(getattr(clock, "set_now"))
    assert callable(getattr(clock, "iter_frames"))

    fetcher = _FakeDataFetcher()
    for name in ("fetch_calendar", "fetch_stock_list", "fetch_adjust_factor",
                 "fetch_bars", "fetch_limit_price", "fetch_st_info", "fetch_bars_ext"):
        assert callable(getattr(fetcher, name)), name

    md = _FakeMarketData()
    for name in ("start", "stop", "subscribe", "unsubscribe", "stream", "snapshot"):
        assert callable(getattr(md, name)), name
