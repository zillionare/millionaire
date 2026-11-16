"""Convert optimizer form values without mixing them with result rendering."""

from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any


def _supply_parameter_grid_defaults(
    base_config: dict[str, Any],
    default_params: Mapping[str, Any],
    key: str,
    param_grid: dict[str, list[Any]],
    values: list[Any],
) -> None:
    """Supply parameter grid defaults."""
    if not values:
        base_config[key] = default_params.get(key)
    elif len(values) == 1:
        base_config[key] = values[0]
    else:
        param_grid[key] = values


def _parse_param_values(text: str) -> list[Any]:
    """解析逗号分隔的参数取值（数值/布尔/字符串）。"""
    values: list[Any] = []
    for item in str(text or "").split(","):
        item = item.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in {"true", "false"}:
            values.append(lowered == "true")
            continue
        try:
            if "." in item or "e" in lowered:
                values.append(float(item))
            else:
                values.append(int(item))
        except (TypeError, ValueError):
            values.append(item)
    return values


def _parse_string_list(text: str) -> list[str]:
    """解析列表型参数（支持 ``a,b`` 或 ``['a', 'b']``）。"""
    raw = str(text or "").strip()
    if not raw:
        return []
    raw = raw.strip("[]")
    items = []
    for item in raw.split(","):
        cleaned = item.strip().strip("'\"")
        if cleaned:
            items.append(cleaned)
    return items


def optimization_parameters(
    strategy_params: Iterable[str], default_params: Mapping[str, Any], form: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """Split grid parameters from fixed scalars and list-valued strategy settings."""
    param_grid: dict[str, list[Any]] = {}
    base_config: dict[str, Any] = {}
    for key in strategy_params:
        raw = form.get(f"param_{key}")
        default_value = default_params.get(key)
        if isinstance(default_value, (list, tuple)):
            # 列表型参数（如指数池）不参与网格搜索，保持为列表。
            base_config[key] = (
                list(default_value)
                if raw is None
                else _parse_string_list(raw) or list(default_value)
            )
            continue
        if raw is None:
            base_config[key] = default_value
            continue
        values = _parse_param_values(raw)
        _supply_parameter_grid_defaults(base_config, default_params, key, param_grid, values)
    for key, value in default_params.items():
        if key not in strategy_params:
            base_config[key] = value
    return base_config, param_grid


def form_number[Number: (int, float)](
    form: Mapping[str, Any], key: str, default: Number, converter: Callable[[Any], Number]
) -> Number:
    """Use the established default when a numeric form value cannot be parsed."""
    try:
        return converter(form.get(key) or default)
    except (TypeError, ValueError):
        return default


def form_choice(form: Mapping[str, Any], key: str, choices: Collection[str], default: str) -> str:
    value = str(form.get(key) or default)
    return value if value in choices else default
