"""Shared builders for daily and 30m dry-run shadow execution."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from quantide.service.runtime_models import StrategyRuntime


def config_symbols(
    config: Mapping[str, Any] | None, *, include_universe: bool = False
) -> list[str]:
    """Extract configured securities using the strategy's alias precedence."""
    values = config or {}
    keys = ["symbols", "symbol", "asset", "assets", "security", "securities"]
    if include_universe:
        keys.insert(1, "universe")
    for key in keys:
        value = values.get(key)
        if isinstance(value, str):
            symbols = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (list, tuple, set)):
            symbols = [str(item).strip() for item in value if str(item).strip()]
        else:
            symbols = []
        if symbols:
            return symbols
    return []


def runtime_symbols(runtime: StrategyRuntime) -> list[str]:
    return list(runtime.symbols) if runtime.symbols else config_symbols(runtime.config)


def position_snapshots(broker: Any) -> list[dict[str, Any]]:
    raw = getattr(broker, "positions", {}) or {}
    values = raw.values() if isinstance(raw, dict) else raw
    return [
        {
            "asset": pos.asset,
            "shares": float(pos.shares),
            "avail": float(pos.avail),
            "price": float(pos.price),
            "mv": float(pos.mv),
        }
        for pos in values
    ]


def build_shadow_strategy(
    runtime: StrategyRuntime, broker: Any, day: Any, config: dict[str, Any]
) -> Any | None:
    """Instantiate a shadow strategy with an effective model, or return None."""
    from quantide.service.discovery import strategy_loader

    strategy_cls = strategy_loader.load_from_cache().get(runtime.strategy_name)
    if strategy_cls is None:
        logger.warning("dry-run 策略不存在: {}", runtime.strategy_name)
        return None
    strategy: Any = strategy_cls(broker, {**config, "_shadow_mode": True})
    try:
        asyncio.run(strategy.init())
        if hasattr(strategy, "_load_model_from_store"):
            strategy._model = None
            if not strategy._load_model_from_store(day):
                logger.warning("dry-run 缺少 {} 生效的模型: {}", day, runtime.runtime_id)
                return None
    except Exception as exc:
        logger.exception("dry-run 初始化失败 {}: {}", runtime.runtime_id, exc)
        return None
    return strategy


__all__ = [
    "build_shadow_strategy",
    "config_symbols",
    "position_snapshots",
    "runtime_symbols",
]
