"""The broker configuration refactor retains established constructor calls."""

import datetime

import pytest

from quantide.service.backtest_broker import BacktestBroker
from quantide.service.backtest_options import BacktestOptions


@pytest.fixture
def configured_broker(monkeypatch):
    def initialize(self, start, end, portfolio_id, data_feed, options):
        self.options = options

    monkeypatch.setattr(BacktestBroker, "_initialize_backtest", initialize)
    return lambda *args, **kwargs: BacktestBroker(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 3), "compat", None, *args, **kwargs
    )


def test_existing_positional_and_keyword_options(configured_broker):
    broker = configured_broker(10000, 0.001, 0.002, 3.0, 0.00001, save_logs=True)
    assert broker.options.principal == 10000
    assert broker.options.commission == 0.001
    assert broker.options.stamp_duty == 0.002
    assert broker.options.min_commission == 3.0
    assert broker.options.transfer_fee == 0.00001
    assert broker.options.save_logs is True


def test_named_configuration_and_explicit_overrides(configured_broker):
    broker = configured_broker(options=BacktestOptions(principal=25000), commission=0.003)
    assert broker.options.principal == 25000
    assert broker.options.commission == 0.003


def test_duplicate_and_unknown_options_remain_errors(configured_broker):
    with pytest.raises(TypeError, match="Multiple values"):
        configured_broker(10000, principal=20000)
    with pytest.raises(TypeError, match="unexpected"):
        configured_broker(unknown_option=True)
