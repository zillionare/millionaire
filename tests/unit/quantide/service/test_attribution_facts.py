"""Account-fact attribution adapter and benchmark tests."""

from __future__ import annotations

import datetime as dt

from quantide.service.attribution_facts import (
    AccountFacts,
    CashFlowFact,
    CorporateActionFact,
    FactSnapshot,
    TradeFact,
    attribution_report,
    facts_from_counter_state,
)

D0 = dt.date(2024, 1, 2)
D1 = dt.date(2024, 1, 3)
D2 = dt.date(2024, 1, 4)


def _facts(
    snapshots,
    trades=(),
    flows=(),
    actions=(),
    benchmark=None,
) -> AccountFacts:
    return AccountFacts(
        "portfolio",
        "backtest",
        tuple(snapshots),
        tuple(trades),
        tuple(flows),
        tuple(actions),
        benchmark or {},
    )


def test_round_trip_trade_and_mark_to_market_reconcile() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 10000, 10000, {}, {}),
            FactSnapshot(D1, 9995, 8995, {"A": 100}, {"A": 10}),
            FactSnapshot(D2, 10195, 8995, {"A": 100}, {"A": 12}),
        ],
        [TradeFact(D1, "A", "buy", 100, 10, fee=5, strategy="trend")],
        benchmark={D1: 0.005, D2: 0.01},
    )
    report = attribution_report(facts)
    assert report["status"] == "OK"
    assert report["delta_equity"] == 195
    assert report["costs"] == -5
    assert report["price_pnl"] == 200
    assert report["residual"] == 0
    assert report["strategy_contributions"]["trend"] != 0
    assert (
        abs(sum(report["linked"]["linked_contributions"].values()) - report["linked"]["linked_sum"])
        < 1e-9
    )
    assert report["benchmark"]["status"] == "OK"


def test_external_flow_is_removed_before_attribution() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 10000, 10000, {}, {}),
            FactSnapshot(D1, 11000, 11000, {}, {}),
        ],
        flows=[CashFlowFact(D1, 1000)],
    )
    report = attribution_report(facts)
    assert report["delta_equity"] == 0
    assert report["residual"] == 0


def test_split_keeps_wealth_conservation() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 1000, 0, {"A": 100}, {"A": 10}),
            FactSnapshot(D1, 1200, 0, {"A": 200}, {"A": 6}),
        ],
        actions=[CorporateActionFact(D1, "A", "split", ratio=2)],
    )
    report = attribution_report(facts)
    assert report["delta_equity"] == 200
    assert report["price_pnl"] == 200
    assert report["residual"] == 0


def test_dividend_and_zero_return_period_are_explicit() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 1000, 0, {"A": 100}, {"A": 10}),
            FactSnapshot(D1, 1050, 50, {"A": 100}, {"A": 10}),
        ],
        actions=[CorporateActionFact(D1, "A", "dividend", amount=50)],
    )
    report = attribution_report(facts)
    assert report["dividends"] == 50
    assert report["delta_equity"] == 50
    assert report["residual"] == 0


def test_counter_snapshot_is_insufficient_and_says_why() -> None:
    facts = facts_from_counter_state(
        "counter",
        {"cash": 1000, "positions": {"A": {"shares": 10, "price": 5}}, "trades": []},
    )
    report = attribution_report(facts)
    assert report["status"] == "INSUFFICIENT"
    assert "snapshots" in report["reason"]
    assert facts.warnings


def test_missing_benchmark_is_not_applicable() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 1000, 1000, {}, {}),
            FactSnapshot(D1, 1010, 1010, {}, {}),
        ]
    )
    report = attribution_report(facts)
    assert report["benchmark"]["status"] == "NOT_APPLICABLE"


def test_markdown_report_is_ai_readable_and_matches_json() -> None:
    from quantide.service.attribution_facts import attribution_markdown

    facts = _facts(
        [
            FactSnapshot(D0, 1000, 1000, {}, {}),
            FactSnapshot(D1, 1010, 1010, {}, {}),
        ],
        benchmark={D1: 0.005},
    )
    report = attribution_report(facts)
    markdown = attribution_markdown(report)
    assert "# 收益归因" in markdown
    assert report["fingerprint"] in markdown
    assert "收益归因不是盈利保证" in markdown
    insufficient = attribution_markdown({"status": "INSUFFICIENT", "reason": "x"})
    assert "数据不足" in insufficient


def test_missing_fee_fact_is_visible_as_reconciliation_residual() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 1000, 1000, {}, {}),
            FactSnapshot(D1, 995, 995, {}, {}),
        ]
    )
    report = attribution_report(facts)
    assert report["status"] == "OK_WITH_RESIDUAL"
    assert report["delta_equity"] == -5
    assert report["end_equity"] == 995
    assert report["residual"] == -5
    assert report["reconciliation_issues"]


def test_missing_trade_fact_is_not_hidden_by_matching_equity() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 1000, 1000, {}, {}),
            FactSnapshot(D1, 1000, 900, {"A": 10}, {"A": 10}),
            FactSnapshot(D2, 1010, 900, {"A": 11}, {"A": 10}),
        ]
    )
    report = attribution_report(facts)
    assert report["status"] == "OK_WITH_RESIDUAL"
    assert report["reconciliation_issues"]


def test_position_mismatch_is_reported_even_when_equity_matches() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 1000, 1000, {}, {}),
            FactSnapshot(D1, 1000, 900, {"A": 10}, {"A": 10}),
        ]
    )
    report = attribution_report(facts)
    assert report["status"] == "OK_WITH_RESIDUAL"
    assert any("positions" in issue for issue in report["reconciliation_issues"])


def test_trade_contribution_is_assigned_to_each_trade_strategy() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 3000, 3000, {}, {}),
            FactSnapshot(D1, 3300, 900, {"A": 200}, {"A": 12}),
        ],
        [
            TradeFact(D1, "A", "buy", 100, 10, strategy="first"),
            TradeFact(D1, "A", "buy", 100, 11, strategy="second"),
        ],
    )
    report = attribution_report(facts)
    assert report["strategy_contributions"]["first"] == 200
    assert report["strategy_contributions"]["second"] == 100


def test_unknown_opening_holding_is_not_reallocated_to_known_buyer() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 2000, 1000, {"A": 100}, {"A": 10}),
            FactSnapshot(D1, 2000, 0, {"A": 200}, {"A": 10}),
            FactSnapshot(D2, 2200, 0, {"A": 200}, {"A": 11}),
        ],
        [TradeFact(D1, "A", "buy", 100, 10, strategy="known")],
    )
    report = attribution_report(facts)
    assert report["strategy_contributions"]["unassigned"] == 100
    assert report["strategy_contributions"]["known"] == 100


def test_known_and_unknown_lots_follow_split_together() -> None:
    facts = _facts(
        [
            FactSnapshot(D0, 2000, 1000, {"A": 100}, {"A": 10}),
            FactSnapshot(D1, 2000, 0, {"A": 200}, {"A": 10}),
            FactSnapshot(D2, 2000, 0, {"A": 400}, {"A": 5}),
            FactSnapshot(dt.date(2024, 1, 5), 2400, 0, {"A": 400}, {"A": 6}),
        ],
        [TradeFact(D1, "A", "buy", 100, 10, strategy="known")],
        actions=[CorporateActionFact(D2, "A", "split", ratio=2)],
    )
    report = attribution_report(facts)
    assert report["strategy_contributions"]["unassigned"] == 200
    assert report["strategy_contributions"]["known"] == 200


def test_benchmark_uses_requested_period_and_fingerprint_tracks_it() -> None:
    snapshots = [
        FactSnapshot(D0, 1000, 1000, {}, {}),
        FactSnapshot(D1, 1010, 1010, {}, {}),
        FactSnapshot(D2, 1020, 1020, {}, {}),
        FactSnapshot(dt.date(2024, 1, 5), 1030, 1030, {}, {}),
    ]
    facts = _facts(
        snapshots,
        benchmark={D1: 0.005, D2: 0.01, dt.date(2024, 1, 5): 0.02},
    )
    full = attribution_report(facts)
    periodic = attribution_report(facts, start=D1)
    assert periodic["benchmark"]["status"] == "OK"
    assert len(periodic["periods"]) == 2
    assert full["fingerprint"] != periodic["fingerprint"]


def test_benchmark_change_changes_facts_fingerprint() -> None:
    base = _facts(
        [FactSnapshot(D0, 1000, 1000, {}, {}), FactSnapshot(D1, 1010, 1010, {}, {})],
        benchmark={D1: 0.005},
    )
    changed = _facts(
        [FactSnapshot(D0, 1000, 1000, {}, {}), FactSnapshot(D1, 1010, 1010, {}, {})],
        benchmark={D1: 0.02},
    )
    assert base.fingerprint != changed.fingerprint
