"""Strategy and backtest runtime state models."""

from __future__ import annotations

import datetime
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyRuntime:
    runtime_id: str
    mode: str
    strategy_name: str
    strategy_id: str
    portfolio_id: str
    account_kind: str
    status: str
    config: dict[str, Any]
    interval: str = "1d"
    source_backtest_portfolio_id: str = ""
    symbols: list[str] = field(default_factory=list)
    principal: float = 0.0
    started_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    error: str = ""
    stop_event: threading.Event | None = None
    thread: threading.Thread | None = None
    broker: Any = None


@dataclass
class BacktestRun:
    runtime_id: str
    portfolio_id: str
    strategy_name: str
    config: dict[str, Any]
    interval: str
    start_date: str
    end_date: str
    initial_cash: float
    status: str
    save_logs: bool = False
    log_path: str = ""
    cheat_on_close: bool = False
    cheat_on_close_time: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    error: str = ""
