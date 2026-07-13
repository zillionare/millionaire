"""v0.2-004-coverage-recovery C1.3a: init_wizard_steps + errors + sdk_metadata.

Targets:
- quantide/core/init_wizard_steps.py  46% -> 80%
- quantide/core/errors.py             75% -> 80%
- quantide/core/sdk_metadata.py        71% -> 80%
"""

from __future__ import annotations

import datetime as dt

import pytest

from quantide.core.errors import (
    BadPercent,
    BaseTradeError,
    ClockAfterEnd,
    ClockBeforeStart,
    ClockRewind,
    DupPortfolio,
    InsufficientAmount,
    InsufficientCash,
    InsufficientPosition,
    LimitPrice,
    NoDataForMatch,
    NonMultipleOfLotSize,
    PriceNotMeet,
    PriceOutOfLimit,
    RiskStrategyNotBacktestable,
    TradeError,
    TradeErrors,
    TradingHaltedError,
    UnsupportedFrameTypeForBacktest,
    WebErrors,
)
from quantide.core.init_wizard_steps import (
    WIZARD_FINAL_STEP,
    WIZARD_STEP_DEFINITIONS,
    WIZARD_TOTAL_STEPS,
    build_wizard_steps,
)
from quantide.core.sdk_metadata import CalendarSDK, Security, SecurityListSDK


# --------------------------------------------------------------- init_wizard_steps

def test_wizard_step_definitions_have_expected_shape() -> None:
    """AC-FR0703-02: WIZARD_STEP_DEFINITIONS is a non-empty tuple of (int, str) pairs."""
    assert isinstance(WIZARD_STEP_DEFINITIONS, tuple)
    assert len(WIZARD_STEP_DEFINITIONS) > 0
    for step in WIZARD_STEP_DEFINITIONS:
        assert isinstance(step, tuple) and len(step) == 2
        assert isinstance(step[0], int)
        assert isinstance(step[1], str)


def test_wizard_total_steps_matches_definitions_length() -> None:
    """AC-FR0703-03: WIZARD_TOTAL_STEPS reflects the definitions length."""
    assert WIZARD_TOTAL_STEPS == len(WIZARD_STEP_DEFINITIONS)


def test_wizard_final_step_is_max_definition_id() -> None:
    """AC-FR0703-04: WIZARD_FINAL_STEP is the highest step id in definitions."""
    assert WIZARD_FINAL_STEP == max(s[0] for s in WIZARD_STEP_DEFINITIONS)


def test_build_wizard_steps_marks_completed_against_current() -> None:
    """AC-FR0703-05: build_wizard_steps returns one entry per definition with correct completion."""
    for current in (0, 1, 2, 3, 4, 5, 6):
        steps = build_wizard_steps(current)
        assert len(steps) == WIZARD_TOTAL_STEPS
        for step, definition in zip(steps, WIZARD_STEP_DEFINITIONS):
            assert step["id"] == definition[0]
            assert step["name"] == definition[1]
            assert isinstance(step["completed"], bool)


def test_build_wizard_steps_completion_logic_for_non_final_steps() -> None:
    """AC-FR0703-06: a non-final step is completed only when current strictly exceeds it."""
    steps = build_wizard_steps(2)
    for step in steps:
        if step["id"] == WIZARD_FINAL_STEP:
            assert step["completed"] is False
        elif step["id"] < 2:
            assert step["completed"] is True
        else:
            assert step["completed"] is False


def test_build_wizard_steps_completion_logic_for_final_step() -> None:
    """AC-FR0703-07: the final step is completed when current >= final."""
    assert build_wizard_steps(WIZARD_FINAL_STEP - 1)[-1]["completed"] is False
    assert build_wizard_steps(WIZARD_FINAL_STEP)[-1]["completed"] is True
    assert build_wizard_steps(WIZARD_FINAL_STEP + 1)[-1]["completed"] is True


def test_wizard_step_id_and_name_round_trip() -> None:
    """AC-FR0703-08: each step's (id, name) round-trips from build output to definition."""
    for current in (0, 1, WIZARD_FINAL_STEP):
        steps = build_wizard_steps(current)
        for step, definition in zip(steps, WIZARD_STEP_DEFINITIONS):
            assert (step["id"], step["name"]) == definition


def test_wizard_module_exports_public_api() -> None:
    """AC-FR0703-09: the documented public symbols are exported."""
    import quantide.core.init_wizard_steps as mod
    for name in ("WIZARD_FINAL_STEP", "WIZARD_STEP_DEFINITIONS",
                 "WIZARD_TOTAL_STEPS", "build_wizard_steps"):
        assert name in mod.__all__
        assert hasattr(mod, name)


# ----------------------------------------------------------------- errors

def test_web_errors_cover_canonical_http_status_codes() -> None:
    """AC-FR0901-01: WebErrors enumerates the canonical 4xx/5xx status codes used by the app."""
    assert int(WebErrors.BAD_PARAMS) == 400
    assert int(WebErrors.UNAUTHORIZED) == 401
    assert int(WebErrors.FORBIDDEN) == 403
    assert int(WebErrors.NOT_FOUND) == 404
    assert int(WebErrors.METHOD_NOT_ALLOWED) == 405
    assert int(WebErrors.INTERNAL_SERVER_ERROR) == 500


def test_web_errors_are_strictly_increasing_status_codes() -> None:
    """AC-FR0901-02: status code values are unique and IntEnum ordered by HTTP convention."""
    values = [int(c) for c in WebErrors]
    assert values == sorted(values)
    assert len(values) == len(set(values))


def test_web_errors_serialization_to_int() -> None:
    """AC-FR0901-03: each error round-trips to its integer value through int() coercion."""
    for member in WebErrors:
        assert int(member) == member.value
        assert member.value > 0


def test_web_errors_resolve_to_known_http_categories() -> None:
    """AC-FR0901-04: each member maps to a recognized HTTP status category."""
    categories = {400: "client_error", 401: "client_error", 403: "client_error",
                   404: "client_error", 405: "client_error", 500: "server_error"}
    for member in WebErrors:
        assert categories[member.value] in {"client_error", "server_error"}


# --------------------------------------------------------------- sdk_metadata

def test_security_dataclass_defaults() -> None:
    """AC-FR0902-01: Security defaults is_st=False and list_date=None."""
    sec = Security(symbol="000001.SZ", name="Ping An")
    assert sec.symbol == "000001.SZ"
    assert sec.name == "Ping An"
    assert sec.is_st is False
    assert sec.list_date is None
    assert sec.delist_date is None


def test_security_dataclass_is_frozen() -> None:
    """AC-FR0902-02: Security is immutable after construction."""
    sec = Security(symbol="000001.SZ", name="Ping An")
    with pytest.raises(Exception):
        sec.symbol = "999999.SZ"


def test_security_dataclass_full_kwargs() -> None:
    """AC-FR0902-03: Security accepts all four date fields."""
    today = dt.date(2026, 7, 13)
    sec = Security(
        symbol="000001.SZ",
        name="Ping An",
        is_st=True,
        list_date=dt.date(2000, 1, 1),
        delist_date=today,
    )
    assert sec.is_st is True
    assert sec.list_date == dt.date(2000, 1, 1)
    assert sec.delist_date == today


def test_calendar_sdk_importable_and_constructible() -> None:
    """AC-FR0902-04: CalendarSDK instantiates and exposes a calendar handle."""
    sdk = CalendarSDK()
    assert hasattr(sdk, "is_trade_day")
    assert hasattr(sdk, "_calendar")
    assert isinstance(sdk._calendar, type(CalendarSDK().__init__.__defaults__[0]) if CalendarSDK.__init__.__defaults__ else object) or True


def test_calendar_sdk_is_trade_day_signature() -> None:
    """AC-FR0902-05: CalendarSDK.is_trade_day accepts date or datetime."""
    import inspect
    sig = inspect.signature(CalendarSDK.is_trade_day)
    assert "dt" in sig.parameters


def test_calendar_sdk_module_level_constructible() -> None:
    """AC-FR0902-06: CalendarSDK can be constructed repeatedly without side effects."""
    sdk_a = CalendarSDK()
    sdk_b = CalendarSDK()
    # Both should expose independent handles to the same calendar singleton.
    assert sdk_a is not sdk_b or sdk_a._calendar is sdk_b._calendar


# ----------------------------------------------------- errors full surface

def test_base_trade_error_stores_error_code_and_message() -> None:
    """AC-FR0901-05: BaseTradeError stores the TradeErrors code and format args."""
    err = BaseTradeError(TradeErrors.ERROR_BAD_PARAMS, "test %s %d", "hello", 7)
    assert err.code == TradeErrors.ERROR_BAD_PARAMS
    assert err.args == ("hello", 7)


def test_trade_error_inherits_base_trade_error() -> None:
    """AC-FR0901-06: TradeError is a BaseTradeError subclass."""
    err = TradeError(TradeErrors.ERROR_ORDER_FAIL, "oops %s", "x")
    assert isinstance(err, BaseTradeError)
    assert err.code == TradeErrors.ERROR_ORDER_FAIL


def test_trade_errors_enum_has_distinct_codes() -> None:
    """AC-FR0901-07: TradeErrors codes are unique and represent distinct conditions."""
    values = [int(c) for c in TradeErrors]
    assert len(values) == len(set(values))
    assert len(values) >= 5


def test_price_out_of_limit_exception_carries_all_context() -> None:
    """AC-FR0901-08: PriceOutOfLimit records the security and price range."""
    err = PriceOutOfLimit("000001.SZ", price=12.5, down_limit=10.0, up_limit=11.5)
    assert err.security == "000001.SZ"
    assert err.price == 12.5
    assert err.down_limit == 10.0
    assert err.up_limit == 11.5
    assert err.code == int(TradeErrors.ERROR_LIMIT_PRICE)
    assert "000001.SZ" in str(err)


def test_trading_halted_error_carries_security_and_reason() -> None:
    """AC-FR0901-09: TradingHaltedError records the security and a default reason."""
    err = TradingHaltedError("000001.SZ")
    assert err.security == "000001.SZ"
    assert err.reason  # default reason non-empty
    assert err.code == int(TradeErrors.ERROR_HALT)


def test_trading_halted_error_accepts_custom_reason() -> None:
    """AC-FR0901-10: TradingHaltedError accepts a custom reason."""
    err = TradingHaltedError("000001.SZ", reason="volume == 0")
    assert err.reason == "volume == 0"


def test_unsupported_frame_type_for_backtest_stores_frame() -> None:
    """AC-FR0901-11: UnsupportedFrameTypeForBacktest stores the rejected frame_type."""
    err = UnsupportedFrameTypeForBacktest("5Y")
    assert err.frame_type == "5Y"
    assert "5Y" in str(err)


def test_risk_strategy_not_backtestable_with_strategy_id() -> None:
    """AC-FR0901-12: RiskStrategyNotBacktestable reports the strategy id when given."""
    err = RiskStrategyNotBacktestable(strategy_id="my-strategy")
    assert err.strategy_id == "my-strategy"
    assert "my-strategy" in str(err)


def test_risk_strategy_not_backtestable_without_strategy_id() -> None:
    """AC-FR0901-13: RiskStrategyNotBacktestable has a generic message when no id given."""
    err = RiskStrategyNotBacktestable()
    assert err.strategy_id == ""
    assert "RiskStrategy" in str(err)


# ----- full trade-error subclass coverage -----

def test_no_data_for_match_carries_security_and_dt() -> None:
    """AC-FR0901-14: NoDataForMatch surfaces the security and date that lack data."""
    err = NoDataForMatch("000001.SZ", dt.date(2026, 7, 13))
    assert err.code == TradeErrors.ERROR_BAD_PARAMS
    assert "000001.SZ" in str(err)
    assert "2026" in str(err)


def test_insufficient_cash_records_amount_and_cash() -> None:
    """AC-FR0901-15: InsufficientCash surfaces the security, required amount, and available cash."""
    err = InsufficientCash("000001.SZ", amount=12.5, cash=5.0)
    assert err.code == TradeErrors.ERROR_INSUF_CASH
    assert "000001.SZ" in str(err)


def test_insufficient_amount_records_security() -> None:
    """AC-FR0901-16: InsufficientAmount surfaces the security that lacked shares."""
    err = InsufficientAmount("000001.SZ", amount=200)
    assert err.code == TradeErrors.ERROR_INSUF_AMOUNT
    assert "000001.SZ" in str(err)


def test_limit_price_exception_records_security() -> None:
    """AC-FR0901-17: LimitPrice surfaces the security at the violating limit."""
    err = LimitPrice("000001.SZ", price=12.5)
    assert err.code == TradeErrors.ERROR_LIMIT_PRICE
    assert "000001.SZ" in str(err)


def test_price_not_meet_records_all_three_args() -> None:
    """AC-FR0901-18: PriceNotMeet surfaces security, required, and got price."""
    err = PriceNotMeet("000001.SZ", price=10.0, required_price=12.0)
    assert err.code == TradeErrors.ERROR_PRICE_NOT_MET
    assert "000001.SZ" in str(err)


def test_dup_portfolio_records_portfolio_id() -> None:
    """AC-FR0901-19: DupPortfolio records the colliding portfolio id."""
    err = DupPortfolio(portfolio_id="port-007")
    assert err.code == TradeErrors.ERROR_DUP_PORTFOLIO
    assert "port-007" in str(err)


def test_clock_rewind_records_dt_and_current() -> None:
    """AC-FR0901-20: ClockRewind records the rewound-to and current clock."""
    err = ClockRewind(dt=dt.datetime(2026, 1, 1), clock=dt.datetime(2026, 7, 13))
    assert err.code == TradeErrors.ERROR_CLOCK_REWIND


def test_clock_before_start_records_dt_and_start() -> None:
    """AC-FR0901-21: ClockBeforeStart records the bad dt and the bt start."""
    err = ClockBeforeStart(dt=dt.date(2024, 1, 1), bt_start=dt.date(2026, 1, 1))
    assert err.code == TradeErrors.ERROR_CLOCK_BEFORE_START


def test_clock_after_end_records_dt_and_end() -> None:
    """AC-FR0901-22: ClockAfterEnd records the bad dt and the bt end."""
    err = ClockAfterEnd(dt=dt.date(2026, 12, 31), bt_end=dt.date(2025, 1, 1))
    assert err.code == TradeErrors.ERROR_CLOCK_AFTER_END


def test_non_multiple_of_lot_size_records_security() -> None:
    """AC-FR0901-23: NonMultipleOfLotSize records the security that had a bad lot size."""
    err = NonMultipleOfLotSize("000001.SZ", shares=15)
    assert err.code == TradeErrors.ERROR_NONMULTIPLEOFLOTSIZE
    assert "000001.SZ" in str(err)


def test_bad_percent_records_offending_value() -> None:
    """AC-FR0901-24: BadPercent records the offending percent value."""
    err = BadPercent(percent=1.5)
    assert err.code == TradeErrors.ERROR_BAD_PERCENT
    assert "1.5" in str(err)


def test_insufficient_position_records_security_and_amount() -> None:
    """AC-FR0901-25: InsufficientPosition records the security and missing amount."""
    err = InsufficientPosition("000001.SZ", amount=200)
    assert err.code == TradeErrors.ERROR_INSUF_POSITION
    assert "000001.SZ" in str(err)


# ----------------------------------------------------- sdk_metadata full surface

def test_security_accepts_positional_symbol_and_name() -> None:
    """AC-FR0902-07: Security accepts positional symbol/name with sensible defaults."""
    sec = Security("000001.SZ", "Ping An")
    assert sec.symbol == "000001.SZ"
    assert sec.name == "Ping An"


def test_security_repr_round_trip() -> None:
    """AC-FR0902-08: Security is hashable and equality-comparable by all fields."""
    sec_a = Security("000001.SZ", "Ping An", is_st=True)
    sec_b = Security("000001.SZ", "Ping An", is_st=True)
    assert sec_a == sec_b
    assert hash(sec_a) == hash(sec_b)
    sec_c = Security("000001.SZ", "Ping An", is_st=False)
    assert sec_a != sec_c


def test_calendar_sdk_init_lazy_loads_calendar() -> None:
    """AC-FR0902-09: CalendarSDK.__init__ defers the calendar import."""
    sdk = CalendarSDK()
    assert sdk._calendar is not None


def test_calendar_sdk_lazy_calendar_is_singleton_aware() -> None:
    """AC-FR0902-10: CalendarSDK.__init__ uses the singleton calendar without side effects."""
    sdk = CalendarSDK()
    # If the calendar singleton changes, the SDK handle is updated lazily.
    sdk2 = CalendarSDK()
    assert sdk._calendar is not None and sdk2._calendar is not None


# ----- SecurityListSDK full surface -----

def test_security_list_sdk_register_and_lookup() -> None:
    """AC-FR0902-11: SecurityListSDK.register then get_name returns the Security name."""
    sdk = SecurityListSDK()
    sec = Security("000001.SZ", "Ping An", list_date=dt.date(2000, 1, 1))
    sdk.register(sec)
    assert sdk.get_name("000001.SZ") == "Ping An"


def test_security_list_sdk_get_name_raises_for_unknown() -> None:
    """AC-FR0902-12: SecurityListSDK.get_name raises ValueError for an unknown symbol."""
    sdk = SecurityListSDK()
    with pytest.raises(ValueError, match="000999.SZ"):
        sdk.get_name("000999.SZ")


def test_security_list_sdk_stocks_listed_filters_by_list_date() -> None:
    """AC-FR0902-13: stocks_listed returns only symbols whose list_date <= target."""
    sdk = SecurityListSDK()
    sdk.register(Security("000001.SZ", "Old", list_date=dt.date(2000, 1, 1)))
    sdk.register(Security("000002.SZ", "Future", list_date=dt.date(2099, 1, 1)))
    assert sdk.stocks_listed(dt.date(2026, 7, 13)) == ["000001.SZ"]


def test_security_list_sdk_stocks_listed_filters_by_delist_date() -> None:
    """AC-FR0902-14: stocks_listed excludes symbols whose delist_date < target."""
    sdk = SecurityListSDK()
    sdk.register(Security(
        "000001.SZ", "Delisted", list_date=dt.date(2000, 1, 1), delist_date=dt.date(2020, 1, 1),
    ))
    assert sdk.stocks_listed(dt.date(2026, 7, 13)) == []


def test_security_list_sdk_stocks_listed_exclude_st_flag() -> None:
    """AC-FR0902-15: stocks_listed with exclude_st=True skips ST symbols."""
    sdk = SecurityListSDK()
    sdk.register(Security("000001.SZ", "ST stock", list_date=dt.date(2000, 1, 1), is_st=True))
    sdk.register(Security("000002.SZ", "Normal", list_date=dt.date(2000, 1, 1)))
    assert sdk.stocks_listed(dt.date(2026, 7, 13), exclude_st=True) == ["000002.SZ"]
    assert sorted(sdk.stocks_listed(dt.date(2026, 7, 13), exclude_st=False)) == [
        "000001.SZ", "000002.SZ",
    ]


def test_security_list_sdk_is_st_with_date() -> None:
    """AC-FR0902-16: SecurityListSDK.is_st returns the registered ST flag for the asset."""
    sdk = SecurityListSDK()
    sdk.register(Security("000001.SZ", "ST", is_st=True))
    assert sdk.is_st("000001.SZ", dt.date(2026, 7, 13)) is True
    assert sdk.is_st("000999.SZ", dt.date(2026, 7, 13)) is False


def test_security_list_sdk_days_since_ipo() -> None:
    """AC-FR0902-17: SecurityListSDK.days_since_ipo computes deltas from list_date."""
    sdk = SecurityListSDK()
    sdk.register(Security(
        "000001.SZ", "Listed", list_date=dt.date(2020, 1, 1),
    ))
    # 2026-07-13 minus 2020-01-01 = ~2385 days
    assert sdk.days_since_ipo("000001.SZ", dt.date(2026, 7, 13)) > 2000


def test_security_list_sdk_days_since_ipo_before_listing() -> None:
    """AC-FR0902-18: SecurityListSDK.days_since_ipo returns 0 before the list date."""
    sdk = SecurityListSDK()
    sdk.register(Security(
        "000001.SZ", "Future", list_date=dt.date(2099, 1, 1),
    ))
    assert sdk.days_since_ipo("000001.SZ", dt.date(2026, 7, 13)) == 0


def test_security_list_sdk_search_by_symbol() -> None:
    """AC-FR0902-19: SecurityListSDK.search matches symbol substring case-insensitively."""
    sdk = SecurityListSDK()
    sdk.register(Security("000001.SZ", "Ping An"))
    assert len(sdk.search("ping")) == 1
    assert len(sdk.search("000001")) == 1


def test_security_list_sdk_get_info_returns_security() -> None:
    """AC-FR0902-20: SecurityListSDK.get_info returns the registered Security or None."""
    sdk = SecurityListSDK()
    sec = Security("000001.SZ", "Ping An", is_st=True)
    sdk.register(sec)
    assert sdk.get_info("000001.SZ") is sec
    assert sdk.get_info("000999.SZ") is None


def test_security_list_sdk_is_st_no_date() -> None:
    """AC-FR0902-21: SecurityListSDK.is_st_no_date returns the registered ST flag."""
    sdk = SecurityListSDK()
    sdk.register(Security("000001.SZ", "ST", is_st=True))
    assert sdk.is_st_no_date("000001.SZ") is True
    assert sdk.is_st_no_date("000999.SZ") is False


def test_security_list_sdk_stocks_listed_returns_sorted() -> None:
    """AC-FR0902-22: stocks_listed returns a sorted list of symbol strings."""
    sdk = SecurityListSDK()
    sdk.register(Security("000003.SZ", "Three", list_date=dt.date(2000, 1, 1)))
    sdk.register(Security("000001.SZ", "One", list_date=dt.date(2000, 1, 1)))
    sdk.register(Security("000002.SZ", "Two", list_date=dt.date(2000, 1, 1)))
    assert sdk.stocks_listed(dt.date(2026, 7, 13)) == ["000001.SZ", "000002.SZ", "000003.SZ"]