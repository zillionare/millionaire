"""Internal context for one factor-tracking refresh attempt."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from quantide.service import factor_profiles


@dataclass(frozen=True)
class RefreshContext:
    factor_id: str
    profile: factor_profiles.TrackingProfile
    source: dict[str, Any]
    source_revision: int
    now: datetime.datetime
    should_cancel: Any
    checkpoint: Any
    fence: Any = None
