"""Compact factor-tracking state for the overview page."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quantide.service.factor_sources import SOURCE_FIELDS

if TYPE_CHECKING:
    from quantide.service.factor_tracking import TrackingView

SUMMARY_VERSION = 1


def summary_path(root: Path, factor_id: str) -> Path:
    return root / "summaries" / f"{factor_id}.json"


def compact_current(current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep overview fields while dropping the large daily-series payloads."""
    if not isinstance(current, dict):
        return None
    primary = current.get("primary_metrics")
    primary = primary if isinstance(primary, dict) else {}
    rank_ic = primary.get("rank_ic")
    rank_ic = rank_ic if isinstance(rank_ic, dict) else {}
    deciles = primary.get("deciles")
    deciles = deciles if isinstance(deciles, dict) else {}
    diagnostics = primary.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    compact: dict[str, Any] = {
        key: current.get(key)
        for key in (
            "status",
            "data_cutoff",
            "computed_at",
            "profile_revision",
            "profile_hash",
            "factor_version",
            "statistics_version",
            "input_revision",
        )
    }
    compact.update({field: current.get(field) for field in SOURCE_FIELDS})
    compact["primary_metrics"] = {
        "holding_days": primary.get("holding_days"),
        "rank_ic": {key: rank_ic.get(key) for key in ("mean", "t_naive", "n_days")},
        "deciles": {
            key: deciles.get(key) for key in ("d1_mean_common", "d10_mean_common", "d1_minus_d10")
        },
        "diagnostics": {"as_of_date": diagnostics.get("as_of_date")},
    }
    if deciles.get("buckets") is not None:
        compact["primary_metrics"]["deciles"]["buckets"] = deciles.get("buckets")
    return compact


def summary_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": SUMMARY_VERSION,
        "current": compact_current(state.get("current")),
        "last_attempt": state.get("last_attempt"),
    }


def tracking_summary(
    factor_id: str,
    *,
    source: dict[str, Any] | None = None,
    latest_day: datetime.date | None = None,
    revision: int | None = None,
) -> TrackingView:
    """Return compact overview state without parsing 500 KB snapshots."""
    from quantide.service import factor_tracking as ft

    profile = ft.load_profile(factor_id)
    state = ft._load_summary_state(factor_id)
    current = state.get("current")
    last_attempt = state.get("last_attempt")
    status = ft._view_status(
        profile,
        current,
        last_attempt,
        ft.is_refreshing(factor_id),
        source if source is not None else ft._source_versions(),
        latest_day if latest_day is not None else ft._latest_market_day(),
        revision if revision is not None else ft._manifest_revision(),
    )
    return ft.TrackingView(profile, current, last_attempt, status)


def tracking_summaries(factor_ids: list[str]) -> dict[str, TrackingView]:
    from quantide.service import factor_tracking as ft

    source = ft._source_versions()
    latest_day = ft._latest_market_day()
    revision = ft._manifest_revision()
    return {
        factor_id: tracking_summary(
            factor_id,
            source=source,
            latest_day=latest_day,
            revision=revision,
        )
        for factor_id in factor_ids
    }
