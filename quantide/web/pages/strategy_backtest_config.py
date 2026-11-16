"""Strategy backtest config."""

import base64
import json
from collections.abc import Mapping
from typing import Any, cast

from fasthtml.common import *
from monsterui.all import *
from starlette.requests import Request

from quantide.core.strategy import BaseStrategy
from quantide.service.discovery import strategy_loader
from quantide.service.risk_programs import (
    ALLOW_SAME_BAR_REPURCHASE_KEY,
    RISK_PROGRAMS_KEY,
    available_risk_programs,
    normalize_risk_programs,
)
from quantide.web.pages.strategy_deploy_views import (
    _removed_risk_warning,
)
from quantide.web.pages.strategy_format import (
    _coerce_form_value,
    _coerce_parameter_text,
)
from quantide.web.pages.strategy_routes import (
    BROKER_FEE_PARAM_DEFAULTS,
    TRADE_PARAM_KEYS,
)


def _append_selected_risk_programs(
    by_id: Mapping[str, dict[str, Any]],
    form: Mapping[str, Any],
    programs: list[dict[str, Any]],
    raw_ids: list[object],
    selected: list[dict[str, Any]],
) -> None:
    """Append selected risk programs."""
    for index, program_id in enumerate(raw_ids):
        program_id = str(program_id)
        program = by_id.get(program_id)
        if program is None:
            raise ValueError(f"不支持的回测风控程序: {program_id}")
        params = dict(program.get("params") or {})
        for key, _default in params.items():
            raw = form.get(f"risk_param_{programs.index(program)}_{key}")
            if raw is not None and str(raw).strip():
                params[key] = _coerce_form_value(raw)
        priority = _coerce_form_value(form.get(f"risk_priority_{programs.index(program)}", index))
        selected.append({"id": program_id, "params": params, "priority": priority})


def _parse_params(form: Mapping[str, Any], prefix: str = "param_") -> dict[str, Any]:
    """解析回测表单参数。

    同名多值字段（例如因子勾选）会解析成列表。
    """
    config: dict[str, Any] = {}
    getlist = getattr(form, "getlist", None)
    for k in form.keys():
        if not k.startswith(prefix):
            continue
        param_name = k[len(prefix) :]
        values = list(getlist(k)) if callable(getlist) else [form[k]]
        values = [v for v in values if not (isinstance(v, str) and not v.strip())]
        if not values:
            continue
        if len(values) > 1:
            config[param_name] = values
            continue
        v = values[0]
        # Try to infer type
        v = _coerce_parameter_text(v)
        config[param_name] = v
    return config


def _split_backtest_params(default_params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """拆分策略参数与交易参数。

    Args:
        default_params: 策略默认参数。

    Returns:
        tuple: (策略参数, 交易参数)。
    """
    strategy_params = {k: v for k, v in default_params.items() if k not in TRADE_PARAM_KEYS}
    trade_params = {k: v for k, v in default_params.items() if k in TRADE_PARAM_KEYS}
    for key, value in BROKER_FEE_PARAM_DEFAULTS.items():
        trade_params.setdefault(key, value)
    return strategy_params, trade_params


def _decode_backtest_prefill(req: Request | None) -> dict[str, Any]:
    """解析回测向导的预填参数（参数优化结果回填）。

    Args:
        req: 请求对象。

    Returns:
        dict: 预填内容；无有效预填时返回空字典。
    """
    query = getattr(req, "query_params", {}) or {}
    raw = query.get("prefill")
    if not raw:
        return {}
    try:
        padded = raw + "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_risk_program_selection(
    form: Mapping[str, Any], strategy_cls: type[BaseStrategy], interval: str
) -> tuple[list[dict[str, Any]], bool]:
    """Parse and server-validate risk IDs, priorities, and parameters."""
    if not form.get("risk_selection_present"):
        raise KeyError("risk selection was not submitted")
    getlist = getattr(form, "getlist", None)
    raw_ids = (
        list(getlist("risk_program_id"))
        if callable(getlist)
        else ([form.get("risk_program_id")] if form.get("risk_program_id") else [])
    )
    # Browsers omit unchecked boxes, while a few form adapters represent an
    # explicit empty selection as a single blank value.  Both mean no risk
    # program was selected when the presence marker is submitted.
    raw_ids = [value for value in raw_ids if str(value or "").strip()]
    programs = available_risk_programs(strategy_cls, interval)
    by_id = {str(item["id"]): item for item in programs}
    selected: list[dict[str, Any]] = []
    _append_selected_risk_programs(by_id, form, programs, raw_ids, selected)
    normalized = normalize_risk_programs(
        selected,
        host_strategy_cls=strategy_cls,
        frame_type=interval,
    )
    values = (
        list(getlist(ALLOW_SAME_BAR_REPURCHASE_KEY))
        if callable(getlist)
        else [form.get(ALLOW_SAME_BAR_REPURCHASE_KEY)]
    )
    allow_same_bar = any(str(value).lower() == "true" for value in values)
    return normalized, allow_same_bar


def _form_to_config(
    form: Mapping[str, Any],
    base_config: dict[str, Any],
    editable_keys: tuple[str, ...] = tuple(BROKER_FEE_PARAM_DEFAULTS),
) -> dict[str, Any]:
    """把 form 中允许覆盖的字段合并到 base_config。

    默认只允许交易费用（``custom_commission`` 等）覆盖；策略参数
    始终沿用回测配置，防止转入后偏离回测结果。
    """
    out: dict[str, Any] = dict(base_config)
    for key in editable_keys:
        form_key = f"custom_{key}"
        if form_key in form:
            out[key] = _coerce_form_value(form[form_key])
        elif key not in out:
            out[key] = BROKER_FEE_PARAM_DEFAULTS.get(key)
    return out


def _deployment_risk_config(
    form: Mapping[str, Any],
    base_config: dict[str, Any],
    strategy_name: str,
    interval: str = "1d",
) -> tuple[dict[str, Any], str]:
    """Validate inherited/edited risk choices for a paper/live deployment."""
    config = dict(base_config or {})
    source = dict(base_config or {})
    if form.get("risk_selection_present"):
        strategy_cls = strategy_loader.load_from_cache().get(strategy_name)
        if strategy_cls is None:
            raise ValueError("源回测策略不存在，无法校验风控程序")
        selected, allow_same_bar = _parse_risk_program_selection(
            form, cast(type[BaseStrategy], strategy_cls), interval
        )
        config[RISK_PROGRAMS_KEY] = selected
        config[ALLOW_SAME_BAR_REPURCHASE_KEY] = allow_same_bar
        return config, _removed_risk_warning(source, selected, interval=interval)
    if RISK_PROGRAMS_KEY in config:
        strategy_cls = strategy_loader.load_from_cache().get(strategy_name)
        if strategy_cls is not None:
            config[RISK_PROGRAMS_KEY] = normalize_risk_programs(
                config[RISK_PROGRAMS_KEY],
                host_strategy_cls=cast(type[BaseStrategy], strategy_cls),
                frame_type=interval,
            )
    return config, ""
