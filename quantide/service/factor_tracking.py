"""Factor tracking profiles, snapshots and background refresh."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import threading
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filelock import FileLock
from loguru import logger

from quantide.config.paths import get_app_config_dir
from quantide.core.atomic_files import atomic_path, read_json_dict, write_json
from quantide.core.market_time import market_now
from quantide.core.scheduler import scheduler
from quantide.factors.alpha import FACTOR_VERSION
from quantide.factors.alphatest import MIN_CROSS_SECTION, load_factor_panel
from quantide.factors.metadata import FACTOR_METADATA, Holding
from quantide.factors.research import (
    STATISTICS_VERSION,
    HorizonRequest,
    common_cohort,
    study_horizon,
)
from quantide.service import factor_tracking_summary as _summary
from quantide.service.factor_profiles import (
    PROFILE_LOCK as _PROFILE_LOCK,
)
from quantide.service.factor_profiles import (
    TrackingProfile,
    profiles_path,
)
from quantide.service.factor_profiles import (
    default_profile as _default_profile,
)
from quantide.service.factor_profiles import (
    load_profile as _load_profile,
)
from quantide.service.factor_profiles import (
    normalize_holdings as _normalize_holdings,
)
from quantide.service.factor_profiles import (
    profile_hash as _profile_hash,
)
from quantide.service.factor_profiles import (
    reset_profile as _reset_profile,
)
from quantide.service.factor_profiles import (
    save_profile as _save_profile,
)
from quantide.service.factor_sources import (
    SOURCE_FIELDS as _SOURCE_FIELDS,
)
from quantide.service.factor_sources import (
    latest_market_day as _latest_market_day,
)
from quantide.service.factor_sources import (
    source_advanced as _source_advanced,
)
from quantide.service.factor_sources import (
    source_complete as _source_complete,
)
from quantide.service.factor_sources import (
    source_fields_match as _source_fields_match,
)
from quantide.service.factor_sources import (
    source_versions as _source_versions,
)
from quantide.service.factor_study import calendar_version, trading_days
from quantide.service.factor_tracking_context import RefreshContext as _RefreshContext
from quantide.service.factor_tracking_dates import lookback_start, panel_start
from quantide.service.scheduled_jobs import remove_owned_jobs

HOLDING_CHOICES: tuple[Holding, ...] = (1, 2, 3, 5, 10, 20)


@dataclass(frozen=True)
class TrackingView:
    profile: TrackingProfile
    current: dict[str, Any] | None
    last_attempt: dict[str, Any] | None
    status: str


def _root() -> Path:
    return get_app_config_dir() / "factor-tracking"


def _profiles_path() -> Path:
    return profiles_path(_root())


def _state_path(factor_id: str) -> Path:
    return _root() / "snapshots" / f"{factor_id}.json"


_STATE_LOCK = threading.RLock()
_REFRESH_LOCK = threading.RLock()
_REFRESHING: set[str] = set()
_PENDING_REFRESH: set[str] = set()


def default_profile(factor_id: str) -> TrackingProfile:
    return _default_profile(factor_id)


def normalize_holdings(
    primary: int, comparison: list[int] | tuple[int, ...]
) -> tuple[Holding, ...]:
    return _normalize_holdings(primary, comparison)


def load_profile(factor_id: str) -> TrackingProfile:
    return _load_profile(_root(), factor_id)


def save_profile(
    factor_id: str,
    *,
    lookback: str,
    primary_holding_days: int,
    comparison_holding_days: list[int] | tuple[int, ...],
    price_field: str = "open",
    enabled: bool = True,
    source_study_id: str | None = None,
) -> TrackingProfile:
    return _save_profile(
        _root(),
        factor_id,
        lookback=lookback,
        primary_holding_days=primary_holding_days,
        comparison_holding_days=comparison_holding_days,
        price_field=price_field,
        enabled=enabled,
        source_study_id=source_study_id,
    )


def reset_profile(factor_id: str) -> TrackingProfile:
    return _reset_profile(_root(), factor_id)


def load_state(factor_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        payload = read_json_dict(_state_path(factor_id))
        return {
            "current": payload.get("current"),
            "last_attempt": payload.get("last_attempt"),
        }


def _load_summary_state(factor_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        payload = read_json_dict(_summary.summary_path(_root(), factor_id))
        if payload.get("version") != _summary.SUMMARY_VERSION:
            payload = _summary.summary_payload(read_json_dict(_state_path(factor_id)))
            write_json(_summary.summary_path(_root(), factor_id), payload)
        return {"current": payload.get("current"), "last_attempt": payload.get("last_attempt")}


def _write_state(factor_id: str, state: dict[str, Any]) -> None:
    with _STATE_LOCK:
        write_json(_state_path(factor_id), state)
        write_json(_summary.summary_path(_root(), factor_id), _summary.summary_payload(state))


def is_refreshing(factor_id: str) -> bool:
    with _REFRESH_LOCK:
        return factor_id in _REFRESHING


def _manifest_path() -> Path:
    return _root() / "market-manifest.json"


def _read_manifest() -> dict[str, Any]:
    return read_json_dict(_manifest_path())


def _register_input(snapshot: dict[str, Any]) -> tuple[bool, int]:
    """Advance the global revision only when raw source versions change."""
    path = _manifest_path()
    with FileLock(str(path) + ".lock", timeout=30):
        manifest = _read_manifest()
        revision = int(manifest.get("revision") or 0)
        token = snapshot.get("source_token")
        stored_token = manifest.get("source_token")
        if token is not None and stored_token is not None and tuple(token) < tuple(stored_token):
            return False, revision
        if not any(snapshot.get(field) is not None for field in _SOURCE_FIELDS):
            if token is not None and stored_token is None:
                legacy_payload = {
                    "revision": revision,
                    "source_token": token,
                    "data_cutoff": snapshot.get("data_cutoff"),
                    "updated_at": market_now().isoformat(),
                }
                with atomic_path(path) as temporary:
                    temporary.write_text(json.dumps(legacy_payload), encoding="utf-8")
            return True, revision
        recorded = any(manifest.get(field) is not None for field in _SOURCE_FIELDS)
        same = recorded and all(
            manifest.get(field) == snapshot.get(field) for field in _SOURCE_FIELDS
        )
        if same or (token is None and stored_token is not None):
            return True, revision
        revision += 1
        payload: dict[str, Any] = {
            "revision": revision,
            "source_token": token,
            "data_cutoff": snapshot.get("data_cutoff"),
            "updated_at": market_now().isoformat(),
        }
        payload.update({field: snapshot.get(field) for field in _SOURCE_FIELDS})
        with atomic_path(path) as temporary:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return True, revision


def _manifest_revision() -> int:
    revision = _read_manifest().get("revision")
    return int(revision) if isinstance(revision, int) else 0


def tracking_view(factor_id: str) -> TrackingView:
    profile = load_profile(factor_id)
    state = load_state(factor_id)
    current = state.get("current")
    last_attempt = state.get("last_attempt")
    status = _view_status(
        profile,
        current,
        last_attempt,
        is_refreshing(factor_id),
        _source_versions(),
        _latest_market_day(),
        _manifest_revision(),
    )
    return TrackingView(profile, current, last_attempt, status)


def _attempt_status(last_attempt: dict[str, Any] | None) -> str | None:
    return last_attempt.get("status") if isinstance(last_attempt, dict) else None


_PENDING_STATUSES = ("failed", "insufficient", "interrupted", "source_unavailable")


def _pending_status(refreshing: bool, last_attempt: dict[str, Any] | None) -> str:
    if refreshing:
        return "calculating"
    status = _attempt_status(last_attempt)
    return str(status) if status in _PENDING_STATUSES else "uninitialized"


def _config_changed(profile: TrackingProfile, current: dict[str, Any]) -> bool:
    return (
        current.get("profile_revision") != profile.revision
        or current.get("profile_hash") != _profile_hash(profile)
        or current.get("factor_version") != FACTOR_VERSION
        or current.get("statistics_version") != STATISTICS_VERSION
    )


def _data_stale(
    current: dict[str, Any],
    latest_source: dict[str, Any] | None,
    latest_day: datetime.date | None,
    manifest_revision: int | None,
) -> bool | None:
    """Return True/False when source versions are known, None when unverifiable."""
    if (
        manifest_revision is not None
        and int(current.get("input_revision") or 0) < manifest_revision
    ):
        return True
    stored_known = all(current.get(field) is not None for field in _SOURCE_FIELDS)
    if _source_complete(latest_source):
        if not stored_known:
            return True
        assert latest_source is not None
        if any(current.get(field) != latest_source.get(field) for field in _SOURCE_FIELDS):
            return True
        return (
            latest_day is not None
            and str(current.get("data_cutoff") or "") < latest_day.isoformat()
        )
    if latest_day is not None and str(current.get("data_cutoff") or "") < latest_day.isoformat():
        return True
    return None


def _view_status(
    profile: TrackingProfile,
    current: dict[str, Any] | None,
    last_attempt: dict[str, Any] | None,
    refreshing: bool = False,
    latest_source: dict[str, Any] | None = None,
    latest_day: datetime.date | None = None,
    manifest_revision: int | None = None,
) -> str:
    if not profile.enabled:
        return "disabled"
    if not isinstance(current, dict):
        return _pending_status(refreshing, last_attempt)
    if refreshing:
        return "calculating"
    status = _attempt_status(last_attempt)
    if status in _PENDING_STATUSES:
        return str(status)
    if current.get("status") != "ok":
        return str(current.get("status") or "failed")
    stale = _data_stale(current, latest_source, latest_day, manifest_revision)
    if stale is None:
        return "source_unavailable"
    if stale:
        return "stale_data"
    return "normal"


def _attempt_payload(
    status: str,
    now: datetime.datetime,
    error: str | None = None,
    *,
    run_id: str = "",
    idempotency_key: str = "",
    started_at: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "started_at": started_at or now.isoformat(),
        "computed_at": now.isoformat(),
        "error": error,
    }


def _load_panel(
    profile: TrackingProfile, end: datetime.date
) -> tuple[Any, datetime.date, tuple[datetime.date, ...]]:
    start = panel_start(profile.lookback, end)
    panel = load_factor_panel(start, end)
    if panel.is_empty():
        raise RuntimeError("no market data available for factor tracking")
    data_cutoff = panel["date"].max()
    if not isinstance(data_cutoff, datetime.date):
        raise RuntimeError("factor panel has no data cutoff")
    days = trading_days(start, data_cutoff)
    return panel, data_cutoff, days


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
        "factor_version": FACTOR_VERSION,
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
    payload.update({field: snapshot.get(field) for field in _SOURCE_FIELDS})
    return hashlib.sha1(  # noqa: S324
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def _build_snapshot(
    factor_id: str,
    profile: TrackingProfile,
    panel: Any,
    data_cutoff: datetime.date,
    now: datetime.datetime,
    calendar_days: tuple[datetime.date, ...],
    source: dict[str, Any],
    source_revision: int | None,
) -> dict[str, Any]:
    evaluation_start = lookback_start(data_cutoff, profile.lookback)
    results = [
        study_horizon(
            panel,
            HorizonRequest(
                factor=factor_id,
                holding_days=holding,
                start=evaluation_start,
                end=data_cutoff,
                data_cutoff=data_cutoff,
                price=profile.price_field,
                calendar=calendar_days,
            ),
        )
        for holding in profile.effective_holding_days
    ]
    primary = next(
        result for result in results if result.holding_days == profile.primary_holding_days
    )
    status = "ok" if primary.daily_ic else "insufficient"
    latest_rows = panel.filter(panel["date"] == data_cutoff).to_dicts()
    latest_symbols = sum(
        1
        for row in latest_rows
        if isinstance(row.get(factor_id), (int, float)) and math.isfinite(row[factor_id])
    )
    snapshot = {
        "factor_id": factor_id,
        "profile_revision": profile.revision,
        "profile_hash": _profile_hash(profile),
        "factor_version": FACTOR_VERSION,
        "statistics_version": STATISTICS_VERSION,
        "dependency_hash": source.get("source_dependency_version"),
        "panel_start": panel_start(profile.lookback, data_cutoff).isoformat(),
        "evaluation_start": evaluation_start.isoformat(),
        "data_hash": _panel_fingerprint(panel),
        "universe_hash": _universe_hash(panel),
        "calendar_version": calendar_version(calendar_days),
        "data_cutoff": data_cutoff.isoformat(),
        "source_token": source.get("source_token"),
        "source_revision": source_revision,
        "computed_at": now.isoformat(),
        "source_kind": "tracking",
        "status": status,
        "primary_holding_days": profile.primary_holding_days,
        "primary_metrics": primary.as_dict(),
        "horizon_metrics": {str(result.holding_days): result.as_dict() for result in results},
        "common_cohort": common_cohort(results).as_dict(),
        "coverage": {
            "coverage_date": data_cutoff.isoformat(),
            "latest_symbols": latest_symbols,
            "min_cross_section": MIN_CROSS_SECTION,
            "sufficient": latest_symbols >= MIN_CROSS_SECTION,
        },
    }
    snapshot.update({field: source.get(field) for field in _SOURCE_FIELDS})
    snapshot["idempotency_key"] = _idempotency_key(factor_id, profile, snapshot)
    return snapshot


def _current_is_newer(state: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    current = state.get("current")
    return isinstance(current, dict) and str(current.get("data_cutoff") or "") > str(
        snapshot.get("data_cutoff") or ""
    )


def _current_matches(
    state: dict[str, Any],
    factor_id: str,
    profile: TrackingProfile,
    snapshot: dict[str, Any],
) -> bool:
    current = state.get("current")
    if not isinstance(current, dict) or current.get("status") != "ok":
        return False
    return current.get("idempotency_key") == _idempotency_key(factor_id, profile, snapshot)


def _publication_plan(
    factor_id: str,
    profile: TrackingProfile,
    latest: TrackingProfile,
    snapshot: dict[str, Any],
    state: dict[str, Any],
) -> tuple[bool, str, int | None]:
    if (
        not latest.enabled
        or latest.revision != profile.revision
        or _profile_hash(latest) != _profile_hash(profile)
    ):
        return False, "superseded", None
    if snapshot.get("status") != "ok":
        return False, str(snapshot.get("status") or "insufficient"), None
    attempt_revision = snapshot.get("source_revision")
    if attempt_revision is not None and not _source_complete(snapshot):
        return False, "source_unavailable", None
    if attempt_revision is not None:
        manifest = _read_manifest()
        if int(manifest.get("revision") or 0) > int(attempt_revision) and not _source_fields_match(
            manifest, snapshot
        ):
            return False, "superseded", _manifest_revision()
    accepted, revision = _register_input(snapshot)
    if not accepted or _current_is_newer(state, snapshot):
        return False, "superseded", revision
    if _current_matches(state, factor_id, profile, snapshot):
        return False, "succeeded", revision
    return True, "succeeded", revision


def _publish_snapshot(
    factor_id: str,
    profile: TrackingProfile,
    snapshot: dict[str, Any],
    now: datetime.datetime,
    run_id: str,
    started_at: str,
    *,
    fence: Any = None,
) -> dict[str, Any]:
    lock_path = getattr(fence, "lock_path", None)
    commit_lock = FileLock(str(lock_path), timeout=30) if lock_path else nullcontext()
    with _PROFILE_LOCK, _STATE_LOCK:
        if callable(fence) and not fence():
            return load_state(factor_id)
        with commit_lock:
            latest = load_profile(factor_id)
            state = load_state(factor_id)
            if callable(fence) and not fence():
                return state
            accepted, status, revision = _publication_plan(
                factor_id, profile, latest, snapshot, state
            )
            if revision is not None:
                snapshot["input_revision"] = revision
                snapshot["idempotency_key"] = _idempotency_key(factor_id, profile, snapshot)
            if accepted:
                state["current"] = snapshot
            state["last_attempt"] = _attempt_payload(
                status,
                now,
                run_id=run_id,
                idempotency_key=str(snapshot.get("idempotency_key") or ""),
                started_at=started_at,
            )
            _write_state(factor_id, state)
    return state


def _record_failure(
    factor_id: str,
    now: datetime.datetime,
    exc: Exception,
    *,
    run_id: str = "",
    started_at: str | None = None,
) -> dict[str, Any]:
    logger.exception("Factor tracking refresh failed: {}", factor_id)
    state = load_state(factor_id)
    state["last_attempt"] = _attempt_payload(
        "failed",
        now,
        str(exc),
        run_id=run_id,
        started_at=started_at,
    )
    _write_state(factor_id, state)
    return state


def _begin_attempt(factor_id: str, run_id: str, now: datetime.datetime) -> str:
    started_at = now.isoformat()
    state = load_state(factor_id)
    state["last_attempt"] = _attempt_payload(
        "running",
        now,
        run_id=run_id,
        started_at=started_at,
    )
    _write_state(factor_id, state)
    return started_at


def _source_unavailable(factor_id: str, now: datetime.datetime) -> dict[str, Any]:
    state = load_state(factor_id)
    state["last_attempt"] = _attempt_payload(
        "source_unavailable",
        now,
        "raw source versions unavailable; refusing to verify freshness",
    )
    _write_state(factor_id, state)
    return state


def _check_cancel(should_cancel: Any) -> None:
    if callable(should_cancel) and should_cancel():
        raise InterruptedError("factor tracking run cancelled")


def _record_cancelled(
    factor_id: str,
    now: datetime.datetime,
    *,
    run_id: str = "",
    started_at: str | None = None,
) -> dict[str, Any]:
    state = load_state(factor_id)
    state["last_attempt"] = _attempt_payload(
        "cancelled",
        now,
        "run cancelled",
        run_id=run_id,
        started_at=started_at,
    )
    _write_state(factor_id, state)
    return state


def _disabled_attempt(factor_id: str, now: datetime.datetime) -> dict[str, Any]:
    state = load_state(factor_id)
    state["last_attempt"] = _attempt_payload("disabled", now)
    _write_state(factor_id, state)
    return state


def _refresh_attempt(context: _RefreshContext) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    started_at = _begin_attempt(context.factor_id, run_id, context.now)
    try:
        _check_cancel(context.should_cancel)
        panel, data_cutoff, days = _load_panel(context.profile, context.now.date())
        if callable(context.checkpoint):
            context.checkpoint("panel", {"factor": context.factor_id, "rows": panel.height})
        _check_cancel(context.should_cancel)
        snapshot = _build_snapshot(
            context.factor_id,
            context.profile,
            panel,
            data_cutoff,
            context.now,
            days,
            context.source,
            context.source_revision,
        )
        _check_cancel(context.should_cancel)
        state = _publish_snapshot(
            context.factor_id,
            context.profile,
            snapshot,
            context.now,
            run_id,
            started_at,
            fence=context.fence,
        )
        if (
            state.get("current") is snapshot
            or _attempt_status(state.get("last_attempt")) == "superseded"
        ):
            _requeue_if_advanced(context.factor_id, context.source)
        return state
    except InterruptedError:
        _record_cancelled(context.factor_id, context.now, run_id=run_id, started_at=started_at)
        raise
    except Exception as exc:
        return _record_failure(
            context.factor_id,
            context.now,
            exc,
            run_id=run_id,
            started_at=started_at,
        )


def refresh_factor(
    factor_id: str,
    *,
    should_cancel: Any = None,
    checkpoint: Any = None,
    fence: Any = None,
) -> dict[str, Any]:
    profile = load_profile(factor_id)
    now = market_now()
    if not profile.enabled:
        return _disabled_attempt(factor_id, now)
    source = _source_versions(refresh=True)
    if not _source_complete(source):
        return _source_unavailable(factor_id, now)
    return _refresh_attempt(
        _RefreshContext(
            factor_id,
            profile,
            source,
            _manifest_revision(),
            now,
            should_cancel,
            checkpoint,
            fence,
        )
    )


def _requeue_if_advanced(factor_id: str, source: dict[str, Any]) -> None:
    if _source_advanced(source, _source_versions(refresh=True)):
        with _REFRESH_LOCK:
            _PENDING_REFRESH.add(factor_id)


def _active_profiles(factor_ids: list[str], lookback: str) -> list[TrackingProfile]:
    profiles = [load_profile(factor_id) for factor_id in factor_ids]
    return [profile for profile in profiles if profile.enabled and profile.lookback == lookback]


def _begin_group_runs(
    current: list[TrackingProfile], now: datetime.datetime
) -> dict[str, tuple[str, str]]:
    runs: dict[str, tuple[str, str]] = {}
    for profile in current:
        run_id = uuid.uuid4().hex
        runs[profile.factor_id] = (run_id, _begin_attempt(profile.factor_id, run_id, now))
    return runs


def _load_group_panel(
    profile: TrackingProfile, now: datetime.datetime
) -> tuple[Any, datetime.date, tuple[datetime.date, ...]]:
    return _load_panel(profile, now.date())


def _fail_group(
    current: list[TrackingProfile],
    runs: dict[str, tuple[str, str]],
    now: datetime.datetime,
    exc: Exception,
) -> None:
    for profile in current:
        run_id, started_at = runs[profile.factor_id]
        _record_failure(profile.factor_id, now, exc, run_id=run_id, started_at=started_at)


def _refresh_group_factor(
    profile: TrackingProfile,
    run: tuple[str, str],
    panel: Any,
    data_cutoff: datetime.date,
    days: tuple[datetime.date, ...],
    now: datetime.datetime,
    source: dict[str, Any],
    source_revision: int,
    *,
    fence: Any = None,
) -> bool:
    run_id, started_at = run
    try:
        snapshot = _build_snapshot(
            profile.factor_id, profile, panel, data_cutoff, now, days, source, source_revision
        )
    except Exception as exc:
        _record_failure(profile.factor_id, now, exc, run_id=run_id, started_at=started_at)
        return False
    state = _publish_snapshot(
        profile.factor_id,
        profile,
        snapshot,
        now,
        run_id,
        started_at,
        fence=fence,
    )
    return state.get("current") is snapshot


def _requeue_group(source: dict[str, Any], factor_ids: list[str]) -> None:
    if not factor_ids or not _source_advanced(source, _source_versions(refresh=True)):
        return
    with _REFRESH_LOCK:
        _PENDING_REFRESH.update(factor_ids)


def _group_source(current: list[TrackingProfile], now: datetime.datetime) -> dict[str, Any] | None:
    source = _source_versions(refresh=True)
    if not _source_complete(source):
        for profile in current:
            _source_unavailable(profile.factor_id, now)
        return None
    return source


def _run_group(
    current: list[TrackingProfile],
    runs: dict[str, tuple[str, str]],
    panel: Any,
    data_cutoff: datetime.date,
    days: tuple[datetime.date, ...],
    now: datetime.datetime,
    source: dict[str, Any],
    source_revision: int,
    should_cancel: Any,
    checkpoint: Any,
    fence: Any = None,
) -> None:
    for index, profile in enumerate(current):
        if callable(should_cancel) and should_cancel():
            _cancel_group(current[index:], runs, now)
            raise InterruptedError("factor tracking run cancelled")
        _refresh_group_factor(
            profile,
            runs[profile.factor_id],
            panel,
            data_cutoff,
            days,
            now,
            source,
            source_revision,
            fence=fence,
        )
        if callable(checkpoint):
            checkpoint("factors", {"completed": index + 1, "total": len(current)})


def _refresh_group(
    factor_ids: list[str],
    lookback: str,
    *,
    should_cancel: Any = None,
    checkpoint: Any = None,
    fence: Any = None,
) -> None:
    now = market_now()
    current = _active_profiles(factor_ids, lookback)
    if not current:
        return
    runs = _begin_group_runs(current, now)
    source = _group_source(current, now)
    if source is None:
        return
    active_ids = [profile.factor_id for profile in current]
    try:
        _check_cancel(should_cancel)
        panel, data_cutoff, days = _load_group_panel(current[0], now)
    except InterruptedError:
        _cancel_group(current, runs, now)
        raise
    except Exception as exc:
        _fail_group(current, runs, now, exc)
        return
    if callable(checkpoint):
        checkpoint("panel", {"factors": active_ids, "rows": panel.height})
    _run_group(
        current,
        runs,
        panel,
        data_cutoff,
        days,
        now,
        source,
        _manifest_revision(),
        should_cancel,
        checkpoint,
        fence,
    )
    _requeue_group(source, active_ids)


def _cancel_group(
    current: list[TrackingProfile],
    runs: dict[str, tuple[str, str]],
    now: datetime.datetime,
) -> None:
    for profile in current:
        run_id, started_at = runs[profile.factor_id]
        _record_cancelled(profile.factor_id, now, run_id=run_id, started_at=started_at)


def _take_pending(factor_ids: list[str]) -> list[str]:
    with _REFRESH_LOCK:
        pending = [factor_id for factor_id in factor_ids if factor_id in _PENDING_REFRESH]
        _PENDING_REFRESH.difference_update(pending)
    return pending


def _release_pending(factor_ids: list[str]) -> None:
    for factor_id in _take_pending(factor_ids):
        trigger_refresh(factor_id)


def trigger_refresh(factor_id: str) -> bool:
    from quantide.service.factor_tracking_worker import trigger_refresh as _trigger

    return _trigger(factor_id)


def cancel_refresh(factor_id: str) -> bool:
    from quantide.service.factor_tracking_worker import cancel_refresh as _cancel

    return _cancel(factor_id)


def trigger_refresh_all() -> int:
    from quantide.service.factor_tracking_worker import (
        trigger_refresh_all as _trigger_all,
    )

    return _trigger_all()


def _recover_interrupted() -> None:
    from quantide.service.factor_tracking_worker import recover

    recover()
    for factor_id in FACTOR_METADATA:
        state = load_state(factor_id)
        attempt = state.get("last_attempt")
        if isinstance(attempt, dict) and attempt.get("status") == "running":
            interrupted = dict(attempt)
            interrupted["status"] = "interrupted"
            state["last_attempt"] = interrupted
            _write_state(factor_id, state)


def _needs_backfill() -> bool:
    for factor_id in FACTOR_METADATA:
        profile = load_profile(factor_id)
        if not profile.enabled:
            continue
        view = tracking_view(factor_id)
        if view.status != "normal":
            return True
        if isinstance(view.current, dict) and _config_changed(profile, view.current):
            return True
    return False


def _warm_summaries() -> None:
    """Migrate large snapshots to compact overview files before serving."""
    for factor_id in FACTOR_METADATA:
        try:
            _load_summary_state(factor_id)
        except Exception as exc:
            logger.warning("因子跟踪摘要预热失败 {}: {}", factor_id, exc)


def _startup_catch_up() -> None:
    try:
        _recover_interrupted()
        if _needs_backfill():
            trigger_refresh_all()
    except Exception as exc:
        logger.warning("因子跟踪启动补查失败: {}", exc)


class FactorTrackingService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._scheduled = False

    def start(self, *, recover: bool = True) -> None:
        with self._lock:
            if self._scheduled:
                return
            scheduler.add_job(
                trigger_refresh_all,
                "cron",
                hour=18,
                minute=45,
                id="factor_tracking_daily",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=None,
                name="factor_tracking.daily",
            )
            self._scheduled = True
        from quantide.service.factor_study_worker import ensure_worker as ensure_study_worker
        from quantide.service.factor_tracking_worker import ensure_worker

        _warm_summaries()
        ensure_worker()
        ensure_study_worker()
        if recover:
            threading.Thread(target=_startup_catch_up, daemon=True).start()

    def stop(self) -> None:
        from quantide.service.factor_study_worker import stop_worker as stop_study_worker
        from quantide.service.factor_tracking_worker import stop_worker

        remove_owned_jobs(self, scheduler, ("factor_tracking_daily",))
        stop_study_worker()
        stop_worker()


factor_tracking_service = FactorTrackingService()
