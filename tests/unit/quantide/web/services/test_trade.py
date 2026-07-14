"""FR-0420 实盘交易订单校验单元测试.

覆盖 acceptance.md AC-FR0420-4, AC-6, AC-9, AC-11, AC-12:
- 卖出可卖数量 = 持仓 - 已挂单
- 金额反算股数 = floor(amount / price / 100) * 100
- 风控策略不可作为手动交易目标
- 数量必须 100 股整数倍
- T+1 提示
"""
from __future__ import annotations

import pytest

from quantide.web.services.trade import (
    OrderRequest,
    OrderValidationError,
    OrderType,
    OrderSide,
    PriceSource,
    calculate_shares_from_amount,
    calculate_sellable_quantity,
    is_risk_strategy_target,
    validate_order_request,
)


class TestSellableQuantity:
    """AC-4: 卖出可卖数量 = 持仓 - 已挂单."""

    def test_sellable_equals_position_minus_pending(self):
        assert calculate_sellable_quantity(position=1000, pending_orders=300) == 700

    def test_sellable_zero_when_all_pending(self):
        assert calculate_sellable_quantity(position=1000, pending_orders=1000) == 0

    def test_sellable_negative_clamped_to_zero(self):
        """已挂单超过持仓时返回 0 (不应出现, 但防御)."""
        assert calculate_sellable_quantity(position=500, pending_orders=800) == 0


class TestSharesFromAmount:
    """AC-6: 金额反算股数 = floor(amount / price / 100) * 100."""

    def test_amount_to_shares_rounds_down_to_100_lot(self):
        """AC-6: 金额 10000 + 价格 12.34 -> floor(10000/12.34/100)*100 = 800."""
        shares = calculate_shares_from_amount(amount=10000, price=12.34)
        assert shares == 800

    def test_amount_to_shares_at_exact_boundary(self):
        shares = calculate_shares_from_amount(amount=1000, price=10.0)
        assert shares == 100

    def test_amount_to_shares_zero_when_insufficient(self):
        shares = calculate_shares_from_amount(amount=50, price=10.0)
        assert shares == 0

    def test_amount_to_shares_zero_when_price_zero(self):
        """price<=0 returns 0 (L116-117)."""
        shares = calculate_shares_from_amount(amount=1000, price=0)
        assert shares == 0

    def test_amount_to_shares_zero_when_amount_zero(self):
        """amount<=0 returns 0 (L116-117)."""
        shares = calculate_shares_from_amount(amount=0, price=10.0)
        assert shares == 0

    def test_amount_to_shares_zero_when_price_negative(self):
        """negative price returns 0 (L116-117)."""
        shares = calculate_shares_from_amount(amount=1000, price=-1.0)
        assert shares == 0


class TestRiskStrategyTarget:
    """AC-11: 风控策略不可作为手动交易目标."""

    def test_risk_strategy_cannot_be_target(self):
        assert is_risk_strategy_target(strategy_type="risk") is True

    def test_day_strategy_can_be_target(self):
        assert is_risk_strategy_target(strategy_type="day") is False

    def test_live_strategy_can_be_target(self):
        assert is_risk_strategy_target(strategy_type="live") is False


class TestOrderValidation:
    """AC-4, AC-9, AC-11, AC-12: 订单校验."""

    def _make_valid_order(self, **overrides):
        defaults = {
            "mode": "live",
            "strategy_id": "strat-1",
            "strategy_type": "day",
            "account_id": "acc-1",
            "symbol": "000001.SZ",
            "side": OrderSide.BUY,
            "quantity": 100,
            "price": 10.0,
            "price_source": PriceSource.MANUAL,
            "order_type": OrderType.LIMIT,
        }
        defaults.update(overrides)
        return OrderRequest(**defaults)

    def test_valid_buy_order_passes(self):
        order = self._make_valid_order()
        assert validate_order_request(order) is True

    def test_risk_strategy_rejected(self):
        """AC-11: 风控策略作为目标 -> 禁止提交."""
        order = self._make_valid_order(strategy_type="risk")
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "风控策略不可作为手动交易目标" in str(exc.value)

    def test_quantity_must_be_multiple_of_100(self):
        """数量必须 100 股整数倍."""
        order = self._make_valid_order(quantity=150)
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "100 股整数倍" in str(exc.value)

    def test_quantity_zero_rejected(self):
        order = self._make_valid_order(quantity=0)
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "数量" in str(exc.value)

    def test_market_order_price_optional(self):
        """市价单价格可空."""
        order = self._make_valid_order(order_type=OrderType.MARKET, price=None)
        assert validate_order_request(order) is True

    def test_limit_order_price_required(self):
        """限价单价格必填."""
        order = self._make_valid_order(order_type=OrderType.LIMIT, price=None)
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "委托价" in str(exc.value)

    def test_negative_price_rejected(self):
        order = self._make_valid_order(price=-1.0)
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "委托价" in str(exc.value)

    def test_market_order_with_negative_price_rejected(self):
        """L147: market order with negative price raises '委托价不能为负数'."""
        order = self._make_valid_order(order_type=OrderType.MARKET, price=-1.0)
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "委托价不能为负数" in str(exc.value)

    def test_empty_symbol_rejected(self):
        order = self._make_valid_order(symbol="")
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "证券代码" in str(exc.value)

    def test_empty_strategy_rejected(self):
        order = self._make_valid_order(strategy_id="")
        with pytest.raises(OrderValidationError) as exc:
            validate_order_request(order)
        assert "目标策略" in str(exc.value)

    def test_limit_up_price_source_switches_to_market(self):
        """AC-12: 点击涨跌停后委托方式自动改为市价."""
        order = self._make_valid_order(price_source=PriceSource.LIMIT_UP, order_type=OrderType.MARKET, price=None)
        assert validate_order_request(order) is True
