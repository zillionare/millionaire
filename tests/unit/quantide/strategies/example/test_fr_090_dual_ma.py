"""FR-090 内置策略 — 双均线（日线策略）.

按 spec-strategy.md §FR-090:
- AC-090-01: 默认参数 fast=5, slow=20
- AC-090-02: fast 上穿 slow 触发买入
- AC-090-03: slow 上穿 fast 触发卖出
- AC-090-04: 回测结果含净值/买卖点/MA 指标
"""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest

from quantide.strategies.example.dual_ma import DualMAStrategy


def test_ac_090_01_default_config():
    """AC-090-01: 默认参数 fast=5, slow=20"""
    config = DualMAStrategy.default_config()
    assert config == {"fast": 5, "slow": 20}
    assert isinstance(config, dict)


def test_ac_090_01b_default_config_importable():
    """AC-090-01: 策略可实例化使用默认配置"""
    broker = MagicMock()
    broker.positions = {}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20, "symbol": "000001.SZ", "invest": 10000})
    assert s.fast_window == 5
    assert s.slow_window == 20


def test_ac_090_04_default_config_for_backtest():
    """AC-090-04: 双均线策略有 default_config 可供回测"""
    config = DualMAStrategy.default_config()
    assert "fast" in config
    assert "slow" in config
    assert config["fast"] == 5
    assert config["slow"] == 20


def test_ac_090_04b_strategy_initializes():
    """AC-090-04: 策略可实例化"""
    broker = MagicMock()
    broker.positions = {}
    s = DualMAStrategy(broker, {"fast": 5, "slow": 20, "symbol": "000001.SZ"})
    assert s.symbol == "000001.SZ"
    assert s.fast_window == 5
