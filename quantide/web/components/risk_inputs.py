"""Shared field names and numeric typing for strategy risk selection."""

from typing import Any

import fasthtml.common as fh
from fasthtml.common import FT


def RiskParameterInput(index: int, key: str, value: Any, cls: str) -> FT:
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    return fh.Input(
        name=f"risk_param_{index}_{key}",
        value=str(value),
        type="number" if numeric else "text",
        step="any" if isinstance(value, float) else None,
        cls=cls,
    )


def RiskProgramCheckbox(program: dict[str, Any], checked: bool, text_class: str) -> FT:
    program_id = str(program["id"])
    return fh.Label(
        fh.Input(
            type="checkbox",
            name="risk_program_id",
            value=program_id,
            checked=checked,
            cls="checkbox checkbox-sm",
        ),
        fh.Span(str(program.get("name") or program_id), cls=text_class),
        cls="flex items-center gap-2 cursor-pointer",
    )
