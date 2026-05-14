import pytest

from quantide.service.strategy_runtime import (
    StrategyBrokerProxy,
    strategy_runtime_manager,
)


class DummyBroker:
    def __init__(self):
        self.calls = []

    async def submit(self, request):
        raise AssertionError("StrategyBrokerProxy should not fallback to submit")

    async def buy_amount(
        self,
        asset,
        amount,
        price=0,
        order_time=None,
        timeout=0.5,
        **kwargs,
    ):
        self.calls.append(
            {
                "asset": asset,
                "amount": amount,
                "price": price,
                "order_time": order_time,
                "timeout": timeout,
                "kwargs": kwargs,
            }
        )
        return {"ok": True}


def test_remove_backtest_run_clears_history_and_runtimes():
    portfolio_id = "bt-remove-test"
    strategy_runtime_manager.create_backtest_runtime(
        portfolio_id=portfolio_id,
        strategy_name="DemoStrategy",
        config={},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=100000,
    )

    assert strategy_runtime_manager.get_backtest_run(portfolio_id) is not None
    strategy_runtime_manager.remove_backtest_run(portfolio_id)
    assert strategy_runtime_manager.get_backtest_run(portfolio_id) is None


@pytest.mark.asyncio
async def test_strategy_broker_proxy_uses_high_level_methods_with_strategy_id():
    broker = DummyBroker()
    proxy = StrategyBrokerProxy(broker, "strategy-1")

    result = await proxy.buy_amount("000001.SZ", 5000, price=10)

    assert result == {"ok": True}
    assert broker.calls == [
        {
            "asset": "000001.SZ",
            "amount": 5000,
            "price": 10,
            "order_time": None,
            "timeout": 0.5,
            "kwargs": {"strategy_id": "strategy-1"},
        }
    ]
