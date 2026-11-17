"""Cross-sectional rank-correlation diagnostics for factor redundancy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, cast

import polars as pl

from quantide.factors.registry import all_factor_ids, factor_definition, factor_plugin

ORTHOGONALITY_VERSION = "1.0.0"
DEFAULT_COLLINEARITY_THRESHOLD = 0.85


@dataclass(frozen=True)
class FactorCorrelationPeer:
    peer_factor_id: str
    peer_group: str
    mean_rank_corr: float
    abs_mean_rank_corr: float
    n_common_days: int


@dataclass(frozen=True)
class FactorOrthogonalitySummary:
    factor_id: str
    threshold: float
    max_abs_rank_corr: float | None
    nearest_peer_id: str | None
    high_collinearity: bool
    top_peers: tuple[FactorCorrelationPeer, ...]
    status: Literal["OK", "HIGH_COLLINEARITY", "INCONCLUSIVE"] = "OK"


def _daily_rank_corr(
    panel: pl.DataFrame,
    factor_id: str,
    peer_id: str,
    date_col: str = "date",
) -> pl.DataFrame:
    frame = (
        panel.select([date_col, "asset", factor_id, peer_id])
        .drop_nulls()
        .filter(pl.col(factor_id).is_finite() & pl.col(peer_id).is_finite())
    )
    if frame.is_empty():
        return pl.DataFrame()
    ranked = frame.with_columns(
        pl.col(factor_id).rank(method="average").over(date_col).alias("_factor_rank"),
        pl.col(peer_id).rank(method="average").over(date_col).alias("_peer_rank"),
    )
    return (
        ranked.group_by(date_col)
        .agg(
            pl.len().alias("n"),
            pl.corr("_factor_rank", "_peer_rank").alias("corr"),
        )
        .filter((pl.col("n") >= 2) & pl.col("corr").is_not_null() & pl.col("corr").is_finite())
        .sort(date_col)
    )


def _peer_summary(
    panel: pl.DataFrame,
    factor_id: str,
    peer_id: str,
    date_col: str = "date",
) -> FactorCorrelationPeer | None:
    daily = _daily_rank_corr(panel, factor_id, peer_id, date_col)
    if daily.is_empty():
        return None
    mean = float(cast(Any, daily["corr"].mean()))
    if not math.isfinite(mean):
        return None
    group = ""
    try:
        group = factor_definition(peer_id).group
    except KeyError:
        pass
    return FactorCorrelationPeer(
        peer_factor_id=peer_id,
        peer_group=group,
        mean_rank_corr=mean,
        abs_mean_rank_corr=abs(mean),
        n_common_days=daily.height,
    )


def orthogonality_summary(
    factor_id: str,
    panel: pl.DataFrame,
    *,
    peers: list[str] | tuple[str, ...] | None = None,
    threshold: float = DEFAULT_COLLINEARITY_THRESHOLD,
    min_common_days: int = 5,
    date_col: str = "date",
) -> FactorOrthogonalitySummary:
    """Compare one factor with every registered peer independently by day."""
    if factor_id not in panel.columns:
        raise ValueError(f"panel missing factor column: {factor_id}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    candidates = (
        list(peers)
        if peers is not None
        else [item for item in all_factor_ids() if item != factor_id and item in panel.columns]
    )
    summaries = [
        summary
        for peer in sorted(set(candidates) - {factor_id})
        if peer in panel.columns
        and (summary := _peer_summary(panel, factor_id, peer, date_col)) is not None
        and summary.n_common_days >= min_common_days
    ]
    summaries.sort(key=lambda item: (-item.abs_mean_rank_corr, item.peer_factor_id))
    top = tuple(summaries[:5])
    nearest = top[0] if top else None
    if nearest is None:
        return FactorOrthogonalitySummary(
            factor_id,
            threshold,
            None,
            None,
            False,
            (),
            "INCONCLUSIVE",
        )
    high = nearest.abs_mean_rank_corr > threshold
    return FactorOrthogonalitySummary(
        factor_id=factor_id,
        threshold=threshold,
        max_abs_rank_corr=nearest.abs_mean_rank_corr,
        nearest_peer_id=nearest.peer_factor_id,
        high_collinearity=high,
        top_peers=top,
        status="HIGH_COLLINEARITY" if high else "OK",
    )


def is_external_factor(factor_id: str) -> bool:
    return factor_plugin(factor_id) is not None


__all__ = [
    "DEFAULT_COLLINEARITY_THRESHOLD",
    "ORTHOGONALITY_VERSION",
    "FactorCorrelationPeer",
    "FactorOrthogonalitySummary",
    "is_external_factor",
    "orthogonality_summary",
]
