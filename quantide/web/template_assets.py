"""Render trusted JS/CSS source templates with explicit named values."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent / "templates"
SLOT = re.compile(r"@@([a-zA-Z_][a-zA-Z_0-9]*)@@")


@lru_cache(maxsize=32)
def _source(name: str) -> str:
    if Path(name).name != name:
        raise ValueError("Asset template must be a file name")
    return (ROOT / name).read_text(encoding="utf-8")


def render_asset(name: str, **values: Any) -> str:
    """Replace slots in one pass, so an inserted value never becomes a template."""
    return SLOT.sub(lambda match: str(values[match.group(1)]), _source(name))
