"""Independent performance attribution and Carino linking tests."""

from __future__ import annotations

import pytest

from quantide.audit.performance import (
    AttributionPeriod,
    AuditTrade,
    attribute_period,
    link_carino,
)


def test_price_only_attribution_reconciles() -> None:
    period = AttributionPeriod(
        start_equity=1_000,
        start_positions={"A": 10},
        start_prices={"A": 10},
        end_prices={"A": 12},
    )
    result = attribute_period(period)
    assert result.start_cash == 900
    assert result.end_equity == 1_020
    assert result.delta_equity == 20
    assert result.price_pnl == 20
    assert result.residual == 0
    assert result.contributions == {"A": 20}
    assert result.as_dict()["return_pct"] == pytest.approx(0.02)


def test_sell_execution_pnl_uses_end_mark() -> None:
    period = AttributionPeriod(
        start_equity=1_000,
        start_positions={"A": 10},
        start_prices={"A": 10},
        end_prices={"A": 12},
        trades=(AuditTrade("A", "sell", 5, 11),),
    )
    result = attribute_period(period)
    assert result.end_cash == 955
    assert result.end_positions == {"A": 5}
    assert result.price_pnl == 20
    assert result.execution_pnl == -5
    assert result.delta_equity == 15
    assert result.residual == 0


def test_fees_dividends_and_external_flow_are_separate_lines() -> None:
    period = AttributionPeriod(
        start_equity=1_000,
        start_positions={"A": 10},
        start_prices={"A": 10},
        end_prices={"A": 12},
        trades=(AuditTrade("A", "buy", 2, 10, fee=1, tax=0.5),),
        external_flow=50,
        dividends={"A": 10},
    )
    result = attribute_period(period)
    assert result.end_cash == pytest.approx(900 - 20 - 1.5 + 10 + 50)
    assert result.costs == pytest.approx(-1.5)
    assert result.dividends == 10
    assert result.execution_pnl == pytest.approx(4)
    assert result.delta_equity == pytest.approx(20 + 4 - 1.5 + 10)
    assert result.residual == 0
    assert sum(result.contributions.values()) == pytest.approx(result.delta_equity)


def test_invalid_period_does_not_emit_partial_result() -> None:
    with pytest.raises(ValueError):
        attribute_period(
            AttributionPeriod(
                start_equity=100,
                start_positions={"A": 10},
                start_prices={"A": 10},
                end_prices={"A": 9},
                trades=(AuditTrade("A", "sell", 11, 9),),
            )
        )
    with pytest.raises(ValueError):
        attribute_period(
            AttributionPeriod(
                start_equity=100,
                start_positions={"A": 10},
                start_prices={"A": 10},
                end_prices={},
            )
        )


def test_carino_linking_reconciles_multi_period_return() -> None:
    first = attribute_period(
        AttributionPeriod(
            start_equity=1_000,
            start_positions={"A": 100},
            start_prices={"A": 10},
            end_prices={"A": 11},
        )
    )
    second = attribute_period(
        AttributionPeriod(
            start_equity=first.end_equity,
            start_positions={"A": 100},
            start_prices={"A": 11},
            end_prices={"A": 12.1},
        )
    )
    linked = link_carino([first, second])
    assert linked["total_return"] == pytest.approx(0.21)
    assert linked["linked_sum"] == pytest.approx(linked["total_return"])
    assert linked["linked_contributions"]["A"] == pytest.approx(0.21)
