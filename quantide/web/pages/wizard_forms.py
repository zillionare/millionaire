"""Wizard forms."""

import datetime
from collections.abc import Mapping
from typing import Any

from fasthtml.common import *
from monsterui.all import *

from quantide.config.paths import normalize_data_home
from quantide.web.pages.wizard_state import (
    DATA_INIT_DEFAULTS,
    DATA_INIT_FIELD_ALIASES,
    GATEWAY_DEFAULTS,
    GATEWAY_FIELD_ALIASES,
    GATEWAY_FORM_FIELDS,
    RUNTIME_DEFAULTS,
    RUNTIME_FIELD_ALIASES,
    RUNTIME_FORM_FIELDS,
)


def _format_date_zh(value: datetime.date | str) -> str:
    if isinstance(value, datetime.date):
        return value.strftime("%Y年%m月%d日")
    text = str(value or "").strip()
    if not text:
        return ""
    if "年" in text and "月" in text and "日" in text:
        return text
    try:
        dt = datetime.datetime.strptime(text, "%Y-%m-%d").date()
        return dt.strftime("%Y年%m月%d日")
    except Exception:
        return text


def _parse_epoch_input(value: str) -> datetime.date:
    text = str(value or "").strip()
    for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无效的日期格式: {value}")


def _pick_first_value(
    source: dict[str, Any] | None,
    keys: tuple[str, ...],
    default: Any,
) -> Any:
    if source is None:
        return default
    for key in keys:
        if key in source:
            return source[key]
    return default


def _coerce_checkbox(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text not in {"0", "false", "off", "no"}


def _normalize_form_values(
    source: dict[str, Any] | None,
    aliases: Mapping[str, tuple[str, ...]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    return {
        field: _pick_first_value(source, field_aliases, defaults[field])
        for field, field_aliases in aliases.items()
    }


def _extract_form_updates(
    source: dict[str, Any] | None,
    aliases: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    if source is None:
        return {}
    updates: dict[str, Any] = {}
    for field, field_aliases in aliases.items():
        for key in field_aliases:
            if key in source:
                updates[field] = source[key]
                break
    return updates


def _runtime_form_state(source: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = {**RUNTIME_DEFAULTS, RUNTIME_FORM_FIELDS["home"]: normalize_data_home()}
    values = _normalize_form_values(source, RUNTIME_FIELD_ALIASES, defaults)
    host = str(
        values[RUNTIME_FORM_FIELDS["host"]] or RUNTIME_DEFAULTS[RUNTIME_FORM_FIELDS["host"]]
    ).strip()
    values[RUNTIME_FORM_FIELDS["host"]] = host or RUNTIME_DEFAULTS[RUNTIME_FORM_FIELDS["host"]]
    values[RUNTIME_FORM_FIELDS["localhost_only"]] = (
        values[RUNTIME_FORM_FIELDS["host"]] == "127.0.0.1"
    )
    return values


def _gateway_form_state(source: dict[str, Any] | None = None) -> dict[str, Any]:
    values = _normalize_form_values(source, GATEWAY_FIELD_ALIASES, GATEWAY_DEFAULTS)
    values[GATEWAY_FORM_FIELDS["enabled"]] = _coerce_checkbox(
        values[GATEWAY_FORM_FIELDS["enabled"]],
        default=True,
    )
    return values


def _data_init_form_state(source: dict[str, Any] | None = None) -> dict[str, Any]:
    return _normalize_form_values(source, DATA_INIT_FIELD_ALIASES, DATA_INIT_DEFAULTS)


def _merge_state(base_state: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    return base_state | updates


def _parse_int_input(value: Any, label: str, default: int) -> int:
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label}必须是整数") from exc


def _parse_positive_int_input(value: Any, label: str, default: int) -> int:
    parsed = _parse_int_input(value, label, default)
    return max(1, parsed)
