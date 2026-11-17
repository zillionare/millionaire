"""Persisted wind-tunnel records and five-state badge views."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from quantide.audit.factor import factor_config_hash
from quantide.audit.future import frame_digest
from quantide.audit.models import AuditReport, canonical_hash
from quantide.audit.plugin_factor import plugin_config_hash
from quantide.audit.store import ReportStore
from quantide.config.paths import get_app_config_dir
from quantide.core.atomic_files import write_json
from quantide.factors.alpha import FEATURE_COLS
from quantide.factors.plugins import FactorPlugin, discover_factor_plugins
from quantide.factors.registry import external_feature_ids, factor_version

BadgeStatus = Literal["PASS", "FAIL", "INCONCLUSIVE", "STALE", "UNVERIFIED"]

_RECORD_FILE = "wind-tunnel-records.json"
_LOCK = threading.RLock()
_DATA_HASH_CACHE: dict[tuple[str, str, str], str] = {}


@dataclass(frozen=True)
class WindTunnelBadgeView:
    """Current badge state for one factor or backtest target."""

    target_kind: Literal["factor", "backtest"]
    target_id: str
    badge_status: BadgeStatus
    run_id: str | None
    checked_at: str | None
    source_hash: str
    recorded_source_hash: str | None
    data_hash: str
    config_hash: str
    check_items: tuple[dict[str, object], ...] = field(default_factory=tuple)
    first_difference_summary: str | None = None
    recorded_data_hash: str | None = None
    recorded_config_hash: str | None = None
    data_end: str | None = None
    recorded_data_end: str | None = None
    message: str = ""


def _record_path() -> Path:
    return get_app_config_dir() / _RECORD_FILE


def _load_records() -> dict[str, dict[str, Any]]:
    path = _record_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    records = payload.get("factors")
    return records if isinstance(records, dict) else {}


def _save_records(records: dict[str, dict[str, Any]]) -> None:
    write_json(_record_path(), {"schema_version": "1.0", "factors": records})


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float) and not (value == value and abs(value) != float("inf")):
        return None
    return value


def _data_signature() -> str:
    """Cheap change detector for the persisted daily-bar files."""
    try:
        from quantide.data.models.daily_bars import daily_bars

        if not getattr(daily_bars, "_initialized", False):
            return "uninitialized"
        path = getattr(daily_bars, "_store_path", None)
        if path is None:
            return "unknown"
        root = Path(path)
        files = [root] if root.is_file() else sorted(root.rglob("*.parquet"))
        digest = hashlib.sha256()
        for item in files:
            try:
                stat = item.stat()
            except OSError:
                continue
            digest.update(str(item).encode())
            digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
        return digest.hexdigest()
    except Exception:
        return "unknown"


def _first_difference_summary(payload: dict[str, Any]) -> str | None:
    difference = payload.get("first_difference")
    if not isinstance(difference, dict):
        return None
    return (
        f"{difference.get('time') or '—'} · {difference.get('asset') or '—'} · "
        f"{difference.get('column') or '—'}：期望 {difference.get('expected')}，"
        f"实际 {difference.get('actual')}"
    )


def _check_items(payload: dict[str, Any]) -> tuple[dict[str, object], ...]:
    items = []
    for check in payload.get("checks") or []:
        if not isinstance(check, dict):
            continue
        items.append(
            {
                "id": str(check.get("check_id") or ""),
                "required": bool(check.get("required", False)),
                "status": str(check.get("status") or ""),
                "message": str(check.get("message") or ""),
            }
        )
    return tuple(items)


def remember_factor_audit(
    result: Any,
    *,
    data_start: dt.date | None,
    data_end: dt.date | None,
    cutoffs: tuple[dt.date, ...],
    modes: tuple[str, ...],
    seeds: tuple[int, ...],
) -> None:
    """Persist the latest badge record for one completed wind-tunnel run."""
    report: AuditReport = result.report
    payload = report.as_dict()
    record = {
        "factor_id": result.factor_id,
        "run_id": report.run_id,
        "status": report.status.value,
        "checked_at": report.generated_at,
        "source_hash": report.spec.source_hash,
        "config_hash": report.spec.config_hash,
        "data_hash": report.spec.data_hash,
        "data_signature": _data_signature(),
        "data_start": data_start.isoformat() if data_start else None,
        "data_end": data_end.isoformat() if data_end else None,
        "cutoffs": [value.isoformat() for value in cutoffs],
        "modes": list(modes),
        "seeds": list(seeds),
        "check_items": list(_check_items(payload)),
        "first_difference_summary": _first_difference_summary(payload),
    }
    with _LOCK:
        records = _load_records()
        records[result.factor_id] = _json_value(record)
        _save_records(records)


def _cutoff_dates(record: dict[str, Any]) -> tuple[dt.date, ...]:
    values = record.get("cutoffs") or []
    dates: list[dt.date] = []
    for value in values:
        try:
            dates.append(dt.date.fromisoformat(str(value)))
        except ValueError:
            continue
    return tuple(dates)


def _record_dates(record: dict[str, Any]) -> tuple[dt.date | None, dt.date | None]:
    def _parse(value: Any) -> dt.date | None:
        try:
            return dt.date.fromisoformat(str(value)) if value else None
        except ValueError:
            return None

    return _parse(record.get("data_start")), _parse(record.get("data_end"))


def _current_data_hash(record: dict[str, Any]) -> tuple[str, str | None]:
    signature = _data_signature()
    if signature == record.get("data_signature"):
        return str(record.get("data_hash") or ""), record.get("data_end")
    start, end = _record_dates(record)
    if start is None or end is None:
        return signature, record.get("data_end")
    key = (signature, start.isoformat(), end.isoformat())
    with _LOCK:
        cached = _DATA_HASH_CACHE.get(key)
    if cached is not None:
        return cached, end.isoformat()
    try:
        from quantide.service.factor_wind_tunnel import load_wind_tunnel_frame

        frame = load_wind_tunnel_frame(start, end)
        digest = frame_digest(frame)
        latest = frame["date"].max()
        data_end = latest.isoformat() if isinstance(latest, dt.date) else end.isoformat()
    except Exception:
        digest = signature
        data_end = end.isoformat()
    with _LOCK:
        _DATA_HASH_CACHE[key] = digest
    return digest, data_end


def _current_config_hash(
    factor_id: str, record: dict[str, Any], plugin: FactorPlugin | None
) -> str:
    cutoffs = _cutoff_dates(record)
    modes = tuple(str(value) for value in record.get("modes") or ())
    seeds = tuple(int(value) for value in record.get("seeds") or (0,))
    try:
        if plugin is not None:
            return plugin_config_hash(
                plugin,
                cutoffs=cutoffs,
                modes=modes or ("zero", "extreme", "random"),
                seeds=seeds,
            )
        return factor_config_hash(
            factor_id,
            cutoffs=cutoffs,
            modes=modes or ("random", "zero", "extreme"),
            seeds=seeds,
        )
    except Exception:
        return ""


def _fingerprints_match(
    record: dict[str, Any], source_hash: str, config_hash: str, data_hash: str
) -> bool:
    current = {
        "source_hash": source_hash,
        "config_hash": config_hash,
        "data_hash": data_hash,
    }
    return all(value and value == record.get(name) for name, value in current.items())


def _badge_status(
    recorded_status: str, source_hash: str, config_hash: str, data_hash: str, record: dict[str, Any]
) -> BadgeStatus:
    if not _fingerprints_match(record, source_hash, config_hash, data_hash):
        return "STALE"
    if recorded_status == "FAIL":
        return "FAIL"
    if recorded_status == "PASS":
        return "PASS"
    return "INCONCLUSIVE"


def _optional_text(value: Any) -> str | None:
    return str(value or "") or None


def _record_badge(
    factor_id: str,
    record: dict[str, Any],
    plugin: FactorPlugin | None,
    current_source: str,
) -> WindTunnelBadgeView:
    data_hash, data_end = _current_data_hash(record)
    config_hash = _current_config_hash(factor_id, record, plugin)
    return WindTunnelBadgeView(
        target_kind="factor",
        target_id=factor_id,
        badge_status=_badge_status(
            str(record.get("status") or ""), current_source, config_hash, data_hash, record
        ),
        run_id=_optional_text(record.get("run_id")),
        checked_at=_optional_text(record.get("checked_at")),
        source_hash=current_source,
        recorded_source_hash=_optional_text(record.get("source_hash")),
        data_hash=data_hash,
        recorded_data_hash=_optional_text(record.get("data_hash")),
        config_hash=config_hash,
        recorded_config_hash=_optional_text(record.get("config_hash")),
        check_items=tuple(
            dict(item) for item in record.get("check_items") or [] if isinstance(item, dict)
        ),
        first_difference_summary=_optional_text(record.get("first_difference_summary")),
        data_end=data_end,
        recorded_data_end=_optional_text(record.get("data_end")),
    )


def factor_wind_tunnel_badge(factor_id: str) -> WindTunnelBadgeView:
    """Return the five-state badge for one factor using current fingerprints."""
    record = _load_records().get(factor_id)
    plugin = discover_factor_plugins().by_id(factor_id)
    current_source = factor_version(factor_id)
    if record is not None:
        return _record_badge(factor_id, record, plugin, current_source)
    return WindTunnelBadgeView(
        target_kind="factor",
        target_id=factor_id,
        badge_status="UNVERIFIED",
        run_id=None,
        checked_at=None,
        source_hash=current_source,
        recorded_source_hash=None,
        data_hash=_data_signature(),
        config_hash="",
        message="尚未运行风洞体检。",
    )


_STATUS_PRIORITY: tuple[BadgeStatus, ...] = (
    "FAIL",
    "STALE",
    "INCONCLUSIVE",
    "UNVERIFIED",
    "PASS",
)


def _aggregate_status(badges: list[WindTunnelBadgeView]) -> BadgeStatus:
    for status in _STATUS_PRIORITY:
        if any(badge.badge_status == status for badge in badges):
            return status
    return "UNVERIFIED"


def _backtest_features(portfolio_id: str) -> list[str] | None:
    try:
        from quantide.service.strategy_runtime import strategy_runtime_manager

        run = strategy_runtime_manager.get_backtest_run_or_resolve(portfolio_id)
        features = run.config.get("features") if run is not None else None
    except Exception:
        return None
    return [str(value) for value in features] if isinstance(features, list) else None


def backtest_factor_ids(portfolio_id: str) -> list[str]:
    """Return the external factors used by one backtest.

    Deleted plugins stay in the result so their persisted report can be
    invalidated instead of silently disappearing from the aggregate badge.
    """
    features = _backtest_features(portfolio_id)
    if features is None:
        return external_feature_ids(None)
    return [factor_id for factor_id in features if factor_id not in FEATURE_COLS]


def backtest_wind_tunnel_badge(portfolio_id: str) -> WindTunnelBadgeView:
    """Aggregate the latest factor audits used by one backtest."""
    selected = backtest_factor_ids(portfolio_id)
    if not selected:
        return WindTunnelBadgeView(
            target_kind="backtest",
            target_id=portfolio_id,
            badge_status="UNVERIFIED",
            run_id=None,
            checked_at=None,
            source_hash="",
            recorded_source_hash=None,
            data_hash=_data_signature(),
            config_hash="",
            message="该回测未使用外部因子，暂无因子风洞证据。",
        )
    badges = [factor_wind_tunnel_badge(factor_id) for factor_id in selected]
    status = _aggregate_status(badges)
    check_items = tuple(
        {
            "id": badge.target_id,
            "required": True,
            "status": badge.badge_status,
            "message": badge.message or badge.first_difference_summary or "",
        }
        for badge in badges
    )
    return WindTunnelBadgeView(
        target_kind="backtest",
        target_id=portfolio_id,
        badge_status=status,
        run_id=next((badge.run_id for badge in badges if badge.run_id), None),
        checked_at=next((badge.checked_at for badge in badges if badge.checked_at), None),
        source_hash=canonical_hash([badge.source_hash for badge in badges]),
        recorded_source_hash=canonical_hash([badge.recorded_source_hash for badge in badges]),
        data_hash=canonical_hash([badge.data_hash for badge in badges]),
        config_hash=canonical_hash([badge.config_hash for badge in badges]),
        check_items=check_items,
        first_difference_summary=next(
            (badge.first_difference_summary for badge in badges if badge.first_difference_summary),
            None,
        ),
        message="按回测使用的外部因子汇总。",
    )


def latest_report_payload(
    record: dict[str, Any] | None = None, *, factor_id: str = ""
) -> dict[str, Any] | None:
    """Load the persisted audit report referenced by the latest record."""
    payload = record or _load_records().get(factor_id)
    if not isinstance(payload, dict):
        return None
    run_id = str(payload.get("run_id") or "")
    if not run_id:
        return None
    try:
        return ReportStore().load(run_id)
    except (OSError, ValueError):
        return None


def report_markdown(payload: dict[str, Any]) -> str:
    """Render one audit report as a stable Markdown evidence artifact."""
    lines = [
        "# 风洞体检报告",
        "",
        f"- run_id: `{payload.get('run_id') or '—'}`",
        f"- status: **{payload.get('status') or '—'}**",
        f"- generated_at: {payload.get('generated_at') or '—'}",
        f"- source_hash: `{payload.get('source_hash') or '—'}`",
        f"- config_hash: `{payload.get('config_hash') or '—'}`",
        f"- data_hash: `{payload.get('data_hash') or '—'}`",
        "",
        "## 检查项",
        "",
    ]
    for check in payload.get("checks") or []:
        if not isinstance(check, dict):
            continue
        lines.append(
            f"- **{check.get('check_id')}**: {check.get('status')} "
            f"{check.get('message') or ''}".rstrip()
        )
    difference = payload.get("first_difference")
    if isinstance(difference, dict):
        lines.extend(
            [
                "",
                "## 首次差异",
                "",
                f"- 时间: {difference.get('time')}",
                f"- 证券: {difference.get('asset')}",
                f"- 字段: {difference.get('column')}",
                f"- 期望: {difference.get('expected')}",
                f"- 实际: {difference.get('actual')}",
            ]
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "BadgeStatus",
    "WindTunnelBadgeView",
    "backtest_factor_ids",
    "backtest_wind_tunnel_badge",
    "factor_wind_tunnel_badge",
    "latest_report_payload",
    "remember_factor_audit",
    "report_markdown",
]
