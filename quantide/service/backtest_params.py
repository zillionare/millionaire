"""回测参数与默认值的比较。

回测报告列表的参数列只展示"用户改过的参数"，因此需要把一次回测实际使用的
配置与默认配置逐项比较：策略默认参数 + Broker 费用默认参数 + 全部因子。
"""

from __future__ import annotations

from typing import Any

DEFAULT_FEE_PARAMS: dict[str, float] = {
    "commission": 1e-4,
    "stamp_duty": 5e-4,
    "transfer_fee": 1e-5,
    "min_commission": 5.0,
}

#: 费用类参数不参与"是否被修改"的比较（它们由 Broker 固定，不来自策略表单）。
FEE_PARAM_KEYS = tuple(DEFAULT_FEE_PARAMS)

#: 因子选择参数名。
FEATURE_PARAM_KEY = "features"


def default_backtest_params(strategy_cls: Any = None) -> dict[str, Any]:
    """回测的默认参数。

    Args:
        strategy_cls: 策略类；为空时只返回费用与因子默认值。

    Returns:
        dict: 默认参数字典。
    """
    from quantide.factors import FEATURE_COLS

    defaults: dict[str, Any] = dict(DEFAULT_FEE_PARAMS)
    defaults[FEATURE_PARAM_KEY] = list(FEATURE_COLS)
    if strategy_cls is not None:
        params = getattr(strategy_cls, "PARAMS", None)
        if not isinstance(params, dict):
            config_fn = getattr(strategy_cls, "default_config", None)
            params = config_fn() if callable(config_fn) else {}
        if isinstance(params, dict):
            defaults.update(params)
    return defaults


def _values_equal(left: Any, right: Any) -> bool:
    """比较两个参数值（数值带容差）。"""
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= max(1e-9, abs(float(right)) * 1e-6)
    if isinstance(left, (list, tuple, set)) and isinstance(right, (list, tuple, set)):
        return sorted(str(item) for item in left) == sorted(str(item) for item in right)
    return bool(left == right)


def changed_params(config: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """返回与默认值不同的参数。

    Args:
        config: 回测实际使用的配置。
        defaults: 默认配置。

    Returns:
        dict: 被修改的参数（保持配置中的顺序）。
    """
    changed: dict[str, Any] = {}
    for key, value in (config or {}).items():
        if key in FEE_PARAM_KEYS:
            # 费用参数由 Broker 固定，不视为用户修改
            continue
        if key == FEATURE_PARAM_KEY:
            if _values_equal(value, defaults.get(FEATURE_PARAM_KEY, value)):
                continue
            changed[key] = value
            continue
        if key not in defaults:
            changed[key] = value
            continue
        if not _values_equal(value, defaults[key]):
            changed[key] = value
    return changed


def format_changed_params(config: dict[str, Any], defaults: dict[str, Any]) -> str:
    """格式化"仅显示被修改的参数"的文本。

    Args:
        config: 回测实际使用的配置。
        defaults: 默认配置。

    Returns:
        str: 参数文本；没有修改时返回 ``默认``。
    """
    changed = changed_params(config, defaults)
    if not changed:
        return "默认"
    items = []
    for key, value in changed.items():
        if key == FEATURE_PARAM_KEY:
            items.append(f"因子={len(value or [])}项")
            continue
        if isinstance(value, (list, tuple, set)):
            items.append(f"{key}={len(value)}项")
            continue
        if isinstance(value, float):
            items.append(f"{key}={value:g}")
            continue
        items.append(f"{key}={value}")
    return ", ".join(items)
