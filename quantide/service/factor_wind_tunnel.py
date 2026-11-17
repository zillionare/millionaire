"""Shared wind-tunnel and orthogonality service for CLI and Web callers."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from quantide.audit.cutoffs import interior_cutoffs
from quantide.audit.factor import audit_factor
from quantide.audit.models import AuditReport, AuditStatus
from quantide.audit.plugin_factor import audit_factor_plugin
from quantide.audit.store import ReportStore
from quantide.factors.metadata import factor_definition
from quantide.factors.orthogonality import (
    DEFAULT_COLLINEARITY_THRESHOLD,
    FactorOrthogonalitySummary,
    orthogonality_summary,
)
from quantide.factors.plugins import FactorPlugin, compute_plugin, discover_factor_plugins
from quantide.factors.registry import compute_feature_panel
from quantide.service.factor_audit import (
    WindTunnelBadgeView,
    backtest_wind_tunnel_badge,
    factor_wind_tunnel_badge,
)


@dataclass(frozen=True)
class WindTunnelResult:
    """One factor check plus cross-sectional redundancy diagnostics."""

    factor_id: str
    report: AuditReport
    orthogonality: FactorOrthogonalitySummary
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.report.status.value

    def as_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "status": self.status,
            "report": self.report.as_dict(),
            "orthogonality": {
                "threshold": self.orthogonality.threshold,
                "max_abs_rank_corr": self.orthogonality.max_abs_rank_corr,
                "nearest_peer_id": self.orthogonality.nearest_peer_id,
                "high_collinearity": self.orthogonality.high_collinearity,
                "status": self.orthogonality.status,
                "top_peers": [
                    {
                        "peer_factor_id": peer.peer_factor_id,
                        "peer_group": peer.peer_group,
                        "mean_rank_corr": peer.mean_rank_corr,
                        "abs_mean_rank_corr": peer.abs_mean_rank_corr,
                        "n_common_days": peer.n_common_days,
                    }
                    for peer in self.orthogonality.top_peers
                ],
            },
            "metadata": self.metadata,
        }


def load_wind_tunnel_frame(
    start: dt.date,
    end: dt.date,
    *,
    assets: list[str] | None = None,
) -> pl.DataFrame:
    """Load raw daily bars and add the availability column used by audits."""
    from quantide.data.models.daily_bars import daily_bars

    frame = daily_bars.get_bars_in_range(start, end, assets=assets, adjust=None, eager_mode=True)
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    if frame is None or frame.is_empty():
        raise ValueError("指定区间没有可用行情")
    frame = frame.with_columns(pl.col("date").cast(pl.Date)).sort(["asset", "date"])
    if "available_at" not in frame.columns:
        frame = frame.with_columns(pl.col("date").alias("available_at"))
    return frame


def _cutoffs_for(frame: pl.DataFrame, count: int = 3) -> tuple[dt.date, ...]:
    return interior_cutoffs(frame["date"].to_list(), count)


def _audit(
    factor_id: str,
    raw: pl.DataFrame,
    *,
    cutoffs: tuple[dt.date, ...] | None,
    modes: tuple[str, ...],
    seeds: tuple[int, ...],
    plugin: FactorPlugin | None = None,
) -> AuditReport:
    resolved = plugin or discover_factor_plugins().by_id(factor_id)
    if resolved is not None:
        return audit_factor_plugin(resolved, raw, cutoffs=cutoffs, modes=modes, seeds=seeds)
    factor_definition(factor_id)
    if "available_at" not in raw.columns:
        raw = raw.with_columns(pl.col("date").alias("available_at"))
    return audit_factor(raw, factor_id, cutoffs=cutoffs, modes=modes, seeds=seeds)


def _empty_orthogonality(factor_id: str) -> FactorOrthogonalitySummary:
    return FactorOrthogonalitySummary(
        factor_id=factor_id,
        threshold=DEFAULT_COLLINEARITY_THRESHOLD,
        max_abs_rank_corr=None,
        nearest_peer_id=None,
        high_collinearity=False,
        top_peers=(),
        status="INCONCLUSIVE",
    )


def _orthogonality_for(
    factor_id: str, raw: pl.DataFrame, plugin: FactorPlugin | None = None
) -> FactorOrthogonalitySummary:
    panel = compute_feature_panel(raw)
    if plugin is not None and factor_id not in panel.columns:
        try:
            computed = compute_plugin(raw, plugin)
            panel = panel.join(
                computed.select(["asset", "date", factor_id]),
                on=["asset", "date"],
                how="left",
            )
        except Exception:
            return _empty_orthogonality(factor_id)
    if factor_id not in panel.columns:
        return _empty_orthogonality(factor_id)
    try:
        return orthogonality_summary(factor_id, panel)
    except ValueError:
        return _empty_orthogonality(factor_id)


def _resolve_modes(
    factor_id: str, plugin: FactorPlugin | None, modes: tuple[str, ...] | None
) -> tuple[str, ...]:
    if modes:
        return modes
    if plugin is not None or discover_factor_plugins().by_id(factor_id) is not None:
        return ("zero", "extreme", "random")
    return ("random", "zero", "extreme")


def _save_result(
    result: WindTunnelResult,
    raw: pl.DataFrame,
    cutoffs: tuple[dt.date, ...],
    modes: tuple[str, ...],
    seeds: tuple[int, ...],
) -> None:
    from quantide.service.factor_audit import remember_factor_audit

    ReportStore().save(result.report)
    dates = raw["date"].to_list()
    remember_factor_audit(
        result,
        data_start=min(dates) if dates else None,
        data_end=max(dates) if dates else None,
        cutoffs=cutoffs,
        modes=modes,
        seeds=seeds,
    )


def run_factor_wind_tunnel(
    factor_id: str,
    *,
    frame: pl.DataFrame | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    assets: list[str] | None = None,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None = None,
    modes: tuple[str, ...] | None = None,
    seeds: tuple[int, ...] = (0,),
    plugin: FactorPlugin | None = None,
    save: bool = True,
) -> WindTunnelResult:
    """Run the deterministic audit and orthogonality check for one factor."""
    raw = frame
    if raw is None:
        if start is None or end is None:
            raise ValueError("必须提供 frame 或 start/end")
        raw = load_wind_tunnel_frame(start, end, assets=assets)
    resolved_cutoffs = tuple(cutoffs) if cutoffs is not None else _cutoffs_for(raw)
    report = _audit(
        factor_id,
        raw,
        cutoffs=resolved_cutoffs,
        modes=_resolve_modes(factor_id, plugin, modes),
        seeds=seeds,
        plugin=plugin,
    )
    orthogonality = _empty_orthogonality(factor_id)
    if report.status is AuditStatus.PASS:
        orthogonality = _orthogonality_for(factor_id, raw, plugin)
    result = WindTunnelResult(
        factor_id=factor_id,
        report=report,
        orthogonality=orthogonality,
        metadata={"cutoffs": [value.isoformat() for value in resolved_cutoffs]},
    )
    if save:
        _save_result(
            result,
            raw,
            resolved_cutoffs,
            _resolve_modes(factor_id, plugin, modes),
            seeds,
        )
    return result


__all__ = [
    "WindTunnelBadgeView",
    "WindTunnelResult",
    "backtest_wind_tunnel_badge",
    "factor_wind_tunnel_badge",
    "load_wind_tunnel_frame",
    "run_factor_wind_tunnel",
]
