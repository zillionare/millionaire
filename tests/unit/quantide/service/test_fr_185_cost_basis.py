"""FR-185 持仓成本基准（加权均价经典方案 A）单元测试.

按 spec-strategy.md §FR-185 + interfaces.md §4.4 positions 表:
- F-CB-1: 买入时加权更新 cost_basis = (old_qty * old_price + buy_qty * buy_price) / new_qty
- F-CB-2: 部分卖出时 cost_basis 不变 (剩余持仓成本保留)
- F-CB-3: 全部卖出时清仓 (持仓记录从 _positions 删除)
- F-CB-4: 首次建仓 cost_basis = buy_price

边界:
- 同日反复买卖 (F-CB-1 累加 + F-CB-2/3 处理)
- 多次部分卖出后再次买入 (先 F-CB-2 保留, 再 F-CB-1 加权更新)

测试策略:
- 用 paper_broker fixture (db :memory: + PaperBroker + DummyMarketData)
- set_clock 虚拟时间避免 wall clock 不可重现
- 构造 Trade 直接调 _apply_trade_to_portfolio (private, unit test 范围可接受)
- 验证 pos.price / pos.shares / _positions 状态
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.domain import QuoteSnapshot
from quantide.core.enums import OrderSide
from quantide.data.sqlite import Position, Trade, db
from quantide.service.sim_broker import PaperBroker


AC_TEST_DATE = datetime.datetime(2024, 6, 3, 9, 30, 0)


class _DummyMarketData:
    def __init__(self):
        self._quotes: dict[str, QuoteSnapshot] = {}

    def set_quote(self, symbol: str, price: float, volume: float | None = None):
        self._quotes[symbol] = QuoteSnapshot(
            symbol=symbol,
            price=price,
            open=price,
            high=price,
            low=price,
            volume=volume,
            amount=(price * volume) if volume is not None else None,
            ts=datetime.datetime.now(),
        )

    def snapshot(self, symbols):
        return {s: self._quotes[s] for s in symbols if s in self._quotes}


@pytest.fixture
def paper_broker() -> PaperBroker:
    db.init(":memory:")
    return PaperBroker(
        portfolio_id="paper-unit",
        principal=100000,
        market_data=_DummyMarketData(),
        market_value_update_interval=0.0,
    )


def _make_trade(
    asset: str,
    shares: int,
    price: float,
    side: OrderSide,
    fee: float = 0.0,
) -> Trade:
    """构造一个 Trade 用于 _apply_trade_to_portfolio 测试."""
    return Trade(
        portfolio_id="paper-unit",
        tid="t-test",
        qtoid="o-test",
        foid="f-test",
        asset=asset,
        shares=shares,
        price=price,
        amount=shares * price,
        tm=AC_TEST_DATE,
        side=side,
        cid="c-test",
        fee=fee,
    )


def test_f_cb_4_first_build(paper_broker):
    """AC-185-04: 首次建仓 cost_basis ← buy_price.

    步骤: 空仓 → BUY 100 股 @ 10.0 → 期望 pos.price == 10.0, shares == 100.
    """
    paper_broker.set_clock(AC_TEST_DATE)
    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )

    pos = paper_broker._positions["AAPL"]
    assert pos.shares == 100
    assert pos.price == 10.0, f"F-CB-4 first build: cost_basis 应等于首次买入价 10.0, 实际 {pos.price}"


def test_f_cb_1_buy_weighted_average(paper_broker):
    """AC-185-01: 买入加权更新 cost_basis = (old_qty * old + buy_qty * buy) / new_qty.

    步骤:
    - T1: 空仓 → BUY 100 @ 10.0 (cost_basis = 10.0)
    - T2: 已有 100 → BUY 100 @ 12.0 (cost_basis = (100*10 + 100*12) / 200 = 11.0)
    - T3: 已有 200 → BUY 100 @ 14.0 (cost_basis = (200*11 + 100*14) / 300 = 12.0)
    """
    paper_broker.set_clock(AC_TEST_DATE)

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )
    assert paper_broker._positions["AAPL"].price == 10.0

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=12.0, side=OrderSide.BUY)
    )
    expected_t2 = (100 * 10.0 + 100 * 12.0) / 200
    assert paper_broker._positions["AAPL"].price == expected_t2, (
        f"F-CB-1 t2: 期望 {expected_t2}, 实际 {paper_broker._positions['AAPL'].price}"
    )

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=14.0, side=OrderSide.BUY)
    )
    expected_t3 = (200 * 11.0 + 100 * 14.0) / 300
    assert paper_broker._positions["AAPL"].price == expected_t3


def test_f_cb_2_partial_sell_keeps_cost(paper_broker):
    """AC-185-02: 部分卖出 cost_basis 不变.

    步骤:
    - T1: BUY 100 @ 10.0 (cost = 10.0)
    - T2: BUY 100 @ 12.0 (cost = 11.0, shares = 200)
    - T3: SELL 50 @ 15.0 → shares = 150, cost_basis 仍为 11.0 (不变)
    """
    paper_broker.set_clock(AC_TEST_DATE)

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )
    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=12.0, side=OrderSide.BUY)
    )
    expected_cost = (100 * 10.0 + 100 * 12.0) / 200
    assert paper_broker._positions["AAPL"].price == expected_cost

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=50, price=15.0, side=OrderSide.SELL)
    )
    pos = paper_broker._positions["AAPL"]
    assert pos.shares == 150
    assert pos.price == expected_cost, (
        f"F-CB-2 partial sell: cost_basis 应保持 {expected_cost}, 实际 {pos.price}"
    )


def test_f_cb_3_full_sell_clears(paper_broker):
    """AC-185-03: 全部卖出 cost_basis 清仓, _positions 删除.

    步骤:
    - T1: BUY 100 @ 10.0
    - T2: SELL 100 @ 12.0 → shares = 0, 持仓从 _positions 删除
    """
    paper_broker.set_clock(AC_TEST_DATE)

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )
    assert "AAPL" in paper_broker._positions

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=12.0, side=OrderSide.SELL)
    )
    assert "AAPL" not in paper_broker._positions, (
        "F-CB-3 full sell: 全部卖出应从 _positions 删除"
    )


def test_f_cb_2_then_1_partial_sell_then_buy(paper_broker):
    """needs AC (Sage): 边界: 多次部分卖出后再次买入 — 先 F-CB-2 保留成本, 再 F-CB-1 加权更新.

    步骤:
    - T1: BUY 100 @ 10.0 (cost = 10.0, shares = 100)
    - T2: SELL 50 @ 15.0 (cost 不变 = 10.0, shares = 50)
    - T3: BUY 50 @ 14.0 (加权: (50*10 + 50*14) / 100 = 12.0)
    """
    paper_broker.set_clock(AC_TEST_DATE)

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )
    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=50, price=15.0, side=OrderSide.SELL)
    )
    pos = paper_broker._positions["AAPL"]
    assert pos.shares == 50
    assert pos.price == 10.0, "部分卖出后 cost_basis 应保持 10.0"

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=50, price=14.0, side=OrderSide.BUY)
    )
    expected = (50 * 10.0 + 50 * 14.0) / 100
    assert paper_broker._positions["AAPL"].price == expected


def test_f_cb_1_does_not_apply_when_no_existing_position(paper_broker):
    """needs AC (Sage): 边界: 旧持仓 shares == 0 时 (不应出现但兜底), F-CB-1 不除以 0.

    步骤: BUY 0 股 @ 10.0 → new_shares = 0, 加权被跳过 (L792 if), shares 保持 0.
    实际场景: 不会发生 (buy 0 股非法), 但代码 L792 有 if 保护.
    """
    paper_broker.set_clock(AC_TEST_DATE)

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )
    pos_before = paper_broker._positions["AAPL"]
    cost_before = pos_before.price

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=0, price=20.0, side=OrderSide.BUY)
    )
    pos_after = paper_broker._positions["AAPL"]
    assert pos_after.shares == 100, "shares 不变 (F-CB-1 不加 0 股)"
    assert pos_after.price == cost_before, "price 不变 (F-CB-1 不加 0 股触发加权)"


def test_multiple_assets_independent(paper_broker):
    """needs AC (Sage): 边界: 多 asset 独立 — AAPL cost_basis 不影响 GOOG cost_basis.

    步骤:
    - AAPL: BUY 100 @ 10.0
    - GOOG: BUY 50 @ 100.0
    - AAPL: BUY 50 @ 12.0 (加权: 10.4)
    - GOOG: 期望保持 100.0 (不变)
    """
    paper_broker.set_clock(AC_TEST_DATE)

    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=100, price=10.0, side=OrderSide.BUY)
    )
    paper_broker._apply_trade_to_portfolio(
        _make_trade("GOOG", shares=50, price=100.0, side=OrderSide.BUY)
    )
    paper_broker._apply_trade_to_portfolio(
        _make_trade("AAPL", shares=50, price=12.0, side=OrderSide.BUY)
    )

    assert paper_broker._positions["AAPL"].price == (100 * 10.0 + 50 * 12.0) / 150
    assert paper_broker._positions["GOOG"].price == 100.0, "GOOG 不受 AAPL 影响"
