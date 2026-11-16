"""Independent account ledger invariant tests."""

from __future__ import annotations

import datetime as dt

import pytest

from quantide.audit.account import AccountLedger


def test_initial_nav_is_one_and_weights_sum_to_one() -> None:
    ledger = AccountLedger(100_000)
    snapshot = ledger.snapshot(dt.date(2024, 1, 2))
    assert snapshot["nav"] == 1
    assert snapshot["equity"] == 100_000
    assert ledger.validate() == []


def test_t_plus_one_and_fee_do_not_create_money() -> None:
    ledger = AccountLedger(10_000)
    day1 = dt.date(2024, 1, 2)
    day2 = dt.date(2024, 1, 3)
    ledger.buy("000001", 100, 10, day1, day2, fee=5)
    assert ledger.cash == pytest.approx(8_995)
    assert ledger.snapshot(day1)["nav"] == pytest.approx(0.9995)
    with pytest.raises(ValueError):
        ledger.sell("000001", 100, 11)
    before = ledger.snapshot(day1)
    ledger.settle(day2)
    ledger.sell("000001", 100, 11, fee=5, tax=1)
    assert ledger.cash == pytest.approx(8_995 + 1_100 - 6)
    assert ledger.fees_paid == pytest.approx(10)
    assert ledger.taxes_paid == pytest.approx(1)
    assert ledger.realized_pnl == pytest.approx(100)
    assert ledger.validate() == []
    assert before["positions"]["000001"]["shares"] == 100
    assert ledger.positions == {}


def test_rejected_orders_have_no_side_effects() -> None:
    ledger = AccountLedger(1_000)
    day = dt.date(2024, 1, 2)
    with pytest.raises(ValueError):
        ledger.buy("000001", 100, 20, day, day)
    assert ledger.snapshot(day)["equity"] == 1_000
    assert ledger.positions == {}
    assert ledger.cash == 1_000


def test_split_preserves_wealth_and_available_shares() -> None:
    ledger = AccountLedger(1_000)
    day1 = dt.date(2024, 1, 2)
    ledger.buy("000001", 100, 5, day1, day1)
    ledger.settle(day1)
    before = ledger.equity()
    ledger.split("000001", 2)
    ledger.mark("000001", 2.5)
    assert ledger.equity() == pytest.approx(before)
    assert ledger.positions["000001"].shares == 200
    assert ledger.positions["000001"].available == 200


def test_dividend_and_external_flow_are_explicit() -> None:
    ledger = AccountLedger(1_000)
    day = dt.date(2024, 1, 2)
    ledger.buy("000001", 100, 5, day, day)
    ledger.settle(day)
    ledger.dividend("000001", 20)
    ledger.deposit(100)
    ledger.withdraw(30)
    snapshot = ledger.snapshot(day)
    assert snapshot["external_flow"] == pytest.approx(70)
    assert snapshot["dividends"] == pytest.approx(20)
    assert snapshot["equity"] == pytest.approx(1_090)


def test_invalid_actions_are_rejected_without_mutation() -> None:
    ledger = AccountLedger(100)
    for action in (
        lambda: ledger.withdraw(101),
        lambda: ledger.deposit(-1),
        lambda: ledger.split("missing", 2),
        lambda: ledger.dividend("missing", 1),
        lambda: ledger.mark("missing", 1),
    ):
        with pytest.raises((ValueError, KeyError)):
            action()
    assert ledger.validate() == []
    assert ledger.cash == 100
