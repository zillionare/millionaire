"""Input identities and native-period panel dispatch for factor tracking."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from quantide.factors.plugins import discover_factor_plugins
from quantide.factors.registry import factor_version
from quantide.factors.research import STATISTICS_VERSION
from quantide.service.factor_profiles import TrackingProfile
from quantide.service.factor_profiles import profile_hash as _profile_hash
from quantide.service.factor_sources import SOURCE_FIELDS


def _panel_fingerprint(panel: Any) -> str:
    digest = hashlib.sha256()
    digest.update(",".join(panel.columns).encode())
    digest.update(str(panel.shape).encode())
    digest.update(panel.hash_rows(seed=0).to_numpy().tobytes())
    return digest.hexdigest()


def _universe_hash(panel: Any) -> str:
    assets = sorted({str(asset) for asset in panel["asset"].to_list()})
    return hashlib.sha256("\n".join(assets).encode()).hexdigest()


def _idempotency_key(factor_id: str, profile: TrackingProfile, snapshot: dict[str, Any]) -> str:
    payload = {
        "factor_id": factor_id,
        "factor_version": factor_version(factor_id),
        "statistics_version": STATISTICS_VERSION,
        "dependency_hash": snapshot.get("dependency_hash"),
        "profile_revision": profile.revision,
        "profile_hash": _profile_hash(profile),
        "panel_start": snapshot.get("panel_start"),
        "evaluation_start": snapshot.get("evaluation_start"),
        "data_hash": snapshot.get("data_hash"),
        "universe_hash": snapshot.get("universe_hash"),
        "calendar_version": snapshot.get("calendar_version"),
        "data_cutoff": snapshot.get("data_cutoff"),
        "source_token": snapshot.get("source_token"),
    }
    payload.update({field: snapshot.get(field) for field in SOURCE_FIELDS})
    return hashlib.sha1(  # noqa: S324
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def dispatch_panel_groups(
    factor_ids: list[str],
    lookback: str,
    refresh: Callable[..., None],
    **options: Any,
) -> bool:
    """Keep native signals on their own panels while daily factors share raw prices."""
    discovery = discover_factor_plugins()
    groups: dict[str, list[str]] = {}
    for factor_id in factor_ids:
        plugin = discovery.by_id(factor_id)
        key = factor_id if plugin is not None and plugin.bar_interval != "1d" else "1d"
        groups.setdefault(key, []).append(factor_id)
    if len(groups) <= 1:
        return False
    for factor_ids_in_group in groups.values():
        refresh(factor_ids_in_group, lookback, **options)
    return True
