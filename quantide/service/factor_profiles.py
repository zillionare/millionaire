"""Single tracking profile per factor with monotonic revisions."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from filelock import FileLock
from loguru import logger

from quantide.core.atomic_files import read_json_dict, write_json
from quantide.core.market_time import market_now
from quantide.factors.metadata import (
    FACTOR_METADATA,
    Holding,
    normalized_tracking_defaults,
)

HOLDING_CHOICES: tuple[Holding, ...] = (1, 2, 3, 5, 10, 20)
LOOKBACKS = ("1y", "3y", "5y", "all")
PROFILE_LOCK = threading.RLock()


@dataclass(frozen=True)
class TrackingProfile:
    factor_id: str
    revision: int
    enabled: bool
    lookback: str
    primary_holding_days: Holding
    comparison_holding_days: tuple[Holding, ...]
    price_field: str
    source: str
    source_study_id: str | None = None
    source_selected_at: str | None = None

    @property
    def effective_holding_days(self) -> tuple[Holding, ...]:
        return self.comparison_holding_days


def profiles_path(root: Path) -> Path:
    return root / "profiles.json"


def default_profile(factor_id: str) -> TrackingProfile:
    defaults = normalized_tracking_defaults(factor_id)
    return TrackingProfile(
        factor_id=factor_id,
        revision=0,
        enabled=True,
        lookback=defaults.lookback,
        primary_holding_days=defaults.primary_holding_days,
        comparison_holding_days=defaults.comparison_holding_days,
        price_field=defaults.price_field,
        source=defaults.source,
    )


def _holding(value: int) -> Holding:
    if value not in HOLDING_CHOICES:
        raise ValueError("invalid holding days")
    return value


def normalize_holdings(
    primary: int, comparison: list[int] | tuple[int, ...]
) -> tuple[Holding, ...]:
    values = {_holding(primary)}
    values.update(_holding(value) for value in comparison)
    if len(values) > 5:
        raise ValueError("holding period selection may contain at most 5 values")
    return tuple(sorted(values))


def _validate_profile(profile: TrackingProfile) -> None:
    if profile.lookback not in LOOKBACKS:
        raise ValueError("invalid lookback")
    if profile.price_field not in ("open", "close"):
        raise ValueError("invalid price field")
    expected = normalize_holdings(
        profile.primary_holding_days, list(profile.comparison_holding_days)
    )
    if expected != profile.comparison_holding_days:
        raise ValueError("tracking profile holdings are not normalized")


def _read_profiles(path: Path) -> dict[str, Any]:
    return read_json_dict(path)


def _write_profiles(path: Path, profiles: dict[str, Any]) -> None:
    write_json(path, profiles)


def load_profile(root: Path, factor_id: str) -> TrackingProfile:
    if factor_id not in FACTOR_METADATA:
        raise KeyError(factor_id)
    path = profiles_path(root)
    with PROFILE_LOCK:
        raw = _read_profiles(path).get(factor_id)
    if not isinstance(raw, dict):
        return default_profile(factor_id)
    try:
        profile = TrackingProfile(
            factor_id=factor_id,
            revision=int(raw["revision"]),
            enabled=bool(raw["enabled"]),
            lookback=str(raw["lookback"]),
            primary_holding_days=_holding(int(raw["primary_holding_days"])),
            comparison_holding_days=tuple(
                _holding(int(value)) for value in raw["comparison_holding_days"]
            ),
            price_field=str(raw["price_field"]),
            source=str(raw.get("source") or "user"),
            source_study_id=raw.get("source_study_id"),
            source_selected_at=raw.get("source_selected_at"),
        )
        _validate_profile(profile)
    except (KeyError, TypeError, ValueError):
        logger.warning("Invalid factor tracking profile: {}", factor_id)
        return default_profile(factor_id)
    return profile


def save_profile(
    root: Path,
    factor_id: str,
    *,
    lookback: str,
    primary_holding_days: int,
    comparison_holding_days: list[int] | tuple[int, ...],
    price_field: str = "open",
    enabled: bool = True,
    source_study_id: str | None = None,
) -> TrackingProfile:
    if factor_id not in FACTOR_METADATA:
        raise KeyError(factor_id)
    path = profiles_path(root)
    with PROFILE_LOCK, FileLock(str(path) + ".profiles.lock", timeout=30):
        current = load_profile(root, factor_id)
        profile = TrackingProfile(
            factor_id=factor_id,
            revision=current.revision + 1,
            enabled=enabled,
            lookback=lookback,
            primary_holding_days=_holding(primary_holding_days),
            comparison_holding_days=normalize_holdings(
                primary_holding_days, comparison_holding_days
            ),
            price_field=price_field,
            source="custom_study" if source_study_id else "user",
            source_study_id=source_study_id,
            source_selected_at=market_now().isoformat() if source_study_id else None,
        )
        _validate_profile(profile)
        profiles = _read_profiles(path)
        profiles[factor_id] = asdict(profile)
        _write_profiles(path, profiles)
    return profile


def reset_profile(root: Path, factor_id: str) -> TrackingProfile:
    if factor_id not in FACTOR_METADATA:
        raise KeyError(factor_id)
    path = profiles_path(root)
    with PROFILE_LOCK, FileLock(str(path) + ".profiles.lock", timeout=30):
        current = load_profile(root, factor_id)
        defaults = default_profile(factor_id)
        profile = TrackingProfile(
            factor_id=factor_id,
            revision=current.revision + 1,
            enabled=defaults.enabled,
            lookback=defaults.lookback,
            primary_holding_days=defaults.primary_holding_days,
            comparison_holding_days=defaults.comparison_holding_days,
            price_field=defaults.price_field,
            source=defaults.source,
        )
        profiles = _read_profiles(path)
        profiles[factor_id] = asdict(profile)
        _write_profiles(path, profiles)
    return profile


def profile_hash(profile: TrackingProfile) -> str:
    import hashlib

    payload = {
        "lookback": profile.lookback,
        "primary_holding_days": profile.primary_holding_days,
        "comparison_holding_days": profile.comparison_holding_days,
        "price_field": profile.price_field,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]  # noqa: S324
