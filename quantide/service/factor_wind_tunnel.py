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
from quantide.factors.plugins import discover_factor_plugins
from quantide.factors.registry import compute_feature_panel


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
) -> AuditReport:
    plugin = discover_factor_plugins().by_id(factor_id)
    if plugin is not None:
        return audit_factor_plugin(plugin, raw, cutoffs=cutoffs)
    factor_definition(factor_id)
    if "available_at" not in raw.columns:
        raw = raw.with_columns(pl.col("date").alias("available_at"))
    return audit_factor(raw, factor_id, cutoffs=cutoffs)


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


def _orthogonality_for(factor_id: str, raw: pl.DataFrame) -> FactorOrthogonalitySummary:
    panel = compute_feature_panel(raw)
    if factor_id not in panel.columns:
        return _empty_orthogonality(factor_id)
    try:
        return orthogonality_summary(factor_id, panel)
    except ValueError:
        return _empty_orthogonality(factor_id)


def run_factor_wind_tunnel(
    factor_id: str,
    *,
    frame: pl.DataFrame | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    assets: list[str] | None = None,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None = None,
    save: bool = True,
) -> WindTunnelResult:
    """Run the deterministic audit and orthogonality check for one factor."""
    raw = frame
    if raw is None:
        if start is None or end is None:
            raise ValueError("必须提供 frame 或 start/end")
        raw = load_wind_tunnel_frame(start, end, assets=assets)
    resolved_cutoffs = tuple(cutoffs) if cutoffs is not None else _cutoffs_for(raw)
    report = _audit(factor_id, raw, cutoffs=resolved_cutoffs)
    orthogonality = _empty_orthogonality(factor_id)
    if report.status is AuditStatus.PASS:
        orthogonality = _orthogonality_for(factor_id, raw)
    if save:
        ReportStore().save(report)
    return WindTunnelResult(
        factor_id=factor_id,
        report=report,
        orthogonality=orthogonality,
        metadata={"cutoffs": [value.isoformat() for value in resolved_cutoffs]},
    )


__all__ = ["WindTunnelResult", "load_wind_tunnel_frame", "run_factor_wind_tunnel"]
