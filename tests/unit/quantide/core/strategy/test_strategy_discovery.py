"""v0.2-003 FR-0205 strategy lifecycle and discovery contract tests."""

import datetime as dt
import inspect

from quantide.core.strategy import BaseStrategy, RiskStrategy, Strategy
from quantide.core.strategy_discovery import SkippedReason, StrategyDiscovery


class Broker:
    def __init__(self): self.records = []
    def get_history(self, *args, **kwargs): return (args, kwargs)
    def record(self, *args): self.records.append(args)


async def test_strategy_defaults_are_noops_and_base_delegates_public_operations():
    """FR-0205 AC-1/AC-2: lifecycle no-ops and get_bars/record delegate unchanged."""
    broker = Broker()
    strategy = BaseStrategy(broker, {})
    now = dt.datetime(2026, 7, 10)
    for hook in (strategy.init, strategy.on_start, strategy.on_stop):
        assert await hook() is None
    assert len(inspect.signature(BaseStrategy.on_bar).parameters) == 2
    assert strategy.get_bars("000001.SZ", 5, now, "1d", False) == (("000001.SZ", 5, now, "1d"), {"include_forming_bar": False})
    strategy.record("nav", 1.2, now, {"source": "test"})
    assert broker.records == [("nav", 1.2, now, {"source": "test"})]
    assert not hasattr(RiskStrategy(broker, {}), "buy")


def test_discovery_scans_only_top_level_concrete_strategies_and_records_failures(tmp_path):
    """FR-0205 AC-3/AC-4: risk has no buy API; broken and nested modules do not abort scan."""
    (tmp_path / "valid.py").write_text("from quantide.core.strategy import BaseStrategy\nclass Valid(BaseStrategy):\n    \"\"\"Valid strategy.\"\"\"\n")
    (tmp_path / "broken.py").write_text("def broken(:\n")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.py").write_text("from quantide.core.strategy import BaseStrategy\nclass Hidden(BaseStrategy): pass\n")

    result = StrategyDiscovery.discover(tmp_path)

    assert [(item.name, item.strategy_type, item.description) for item in result.strategies] == [("Valid", "independent", "Valid strategy.")]
    assert any(item.reason is SkippedReason.SyntaxError for item in result.diagnostics)
