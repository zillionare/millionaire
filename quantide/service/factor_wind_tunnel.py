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
from quantide.data.utils.resampler import ohlcv_aggregations
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
class WindTunnelInput:
    """Native audit bars and the exact raw daily data used to aggregate them."""

    frame: pl.DataFrame
    source_daily: pl.DataFrame | None = None


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


class MonthlyCalendarUnavailable(ValueError):
    """The authoritative calendar cannot prove whether a month is closed."""


def _closed_month_filter(monthly: pl.DataFrame) -> pl.DataFrame:
    from quantide.data.models.calendar import calendar

    drops: list[tuple[str, dt.date]] = []
    for asset_key, values in monthly.group_by("asset"):
        asset = asset_key[0] if isinstance(asset_key, tuple) else asset_key
        last = values["dt"].max()
        if not isinstance(last, dt.date):
            continue
        try:
            following = calendar.day_shift(last, 1)
        except Exception as exc:
            raise MonthlyCalendarUnavailable(
                f"交易日历不可用，无法判定 {asset} {last} 所在月是否闭合: {exc}"
            ) from exc
        if following <= last:
            raise MonthlyCalendarUnavailable(f"交易日历未能越过 {asset} {last}，无法判定月线闭合")
        if following.year == last.year and following.month == last.month:
            drops.append((str(asset), last))
    for asset, last in drops:
        monthly = monthly.filter(~((pl.col("asset") == asset) & (pl.col("dt") == last)))
    return monthly


def _monthly_frame(frame: pl.DataFrame, price_adjustment: str = "hfq") -> pl.DataFrame:
    """Aggregate closed monthly OHLC with correct per-day adjustment provenance."""
    frame = frame.sort(["asset", "date"])
    adjusted = price_adjustment == "hfq" and "adjust" in frame.columns
    if adjusted:
        frame = frame.with_columns(
            (pl.col(column) * pl.col("adjust")).alias(column)
            for column in ("open", "high", "low", "close")
        ).drop("adjust")
    provenance = (
        [pl.col("adjust").last().alias("adjust")]
        if not adjusted and "adjust" in frame.columns
        else []
    )
    monthly = (
        frame.with_columns(pl.col("date").dt.truncate("1mo").alias("dt"))
        .group_by(["asset", "dt"])
        .agg(*ohlcv_aggregations(), *provenance, pl.col("date").max().alias("date"))
        .with_columns(pl.col("date").alias("dt"))
        .sort(["asset", "dt"])
    )
    if monthly.is_empty():
        return monthly
    monthly = _closed_month_filter(monthly)
    if not adjusted and "adjust" not in monthly.columns:
        monthly = monthly.with_columns(pl.lit(1.0).alias("adjust"))
    return monthly


def load_wind_tunnel_inputs(
    start: dt.date,
    end: dt.date,
    *,
    assets: list[str] | None = None,
    interval: str = "1d",
    price_adjustment: str = "hfq",
) -> WindTunnelInput:
    """Load one source snapshot, retaining daily provenance for monthly peers."""
    if interval == "30m":
        from quantide.data.models.minute_bars import minute_bars

        frame = minute_bars.get_bars_in_range(start, end, assets=assets, adjust=None)
    else:
        from quantide.data.models.daily_bars import daily_bars

        if interval == "1M":
            start = start.replace(day=1)
        frame = daily_bars.get_bars_in_range(
            start, end, assets=assets, adjust=None, eager_mode=True
        )
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    if frame is None or frame.is_empty():
        raise ValueError("指定区间没有可用行情")
    source_daily = None
    if interval == "30m":
        frame = frame.with_columns(pl.col("date").cast(pl.Datetime("ms")).alias("dt"))
        date_col = "dt"
    else:
        frame = frame.with_columns(pl.col("date").cast(pl.Date))
        date_col = "date"
        if interval == "1M":
            source_daily = frame
            frame = _monthly_frame(frame, price_adjustment)
            date_col = "dt"
    frame = frame.sort(["asset", date_col])
    if "available_at" not in frame.columns:
        frame = frame.with_columns(pl.col(date_col).alias("available_at"))
    return WindTunnelInput(frame, source_daily)


def load_wind_tunnel_frame(
    start: dt.date,
    end: dt.date,
    *,
    assets: list[str] | None = None,
    interval: str = "1d",
    price_adjustment: str = "hfq",
) -> pl.DataFrame:
    """Load native bars; callers needing monthly peers retain the input record."""
    return load_wind_tunnel_inputs(
        start, end, assets=assets, interval=interval, price_adjustment=price_adjustment
    ).frame


def _cutoffs_for(frame: pl.DataFrame, count: int = 3, date_col: str = "date") -> tuple[Any, ...]:
    return interior_cutoffs(frame[date_col].to_list(), count)


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


def _monthly_orthogonality(
    factor_id: str,
    raw: pl.DataFrame,
    plugin: FactorPlugin,
    daily_frame: pl.DataFrame | None,
) -> FactorOrthogonalitySummary:
    """Rebuild each monthly plugin from the same raw daily bars in its own basis."""
    if raw.is_empty() or "dt" not in raw.columns or daily_frame is None:
        return _empty_orthogonality(factor_id)
    original = daily_frame
    if original.is_empty() or "adjust" not in original.columns:
        return _empty_orthogonality(factor_id)
    hfq = _monthly_frame(original, "hfq")
    raw_monthly = _monthly_frame(original, "raw")
    frames = {"hfq": hfq, "raw": raw_monthly}
    panel = compute_plugin(frames.get(plugin.price_adjustment, hfq), plugin).select(
        ["asset", "dt", factor_id]
    )
    peers = [
        item
        for item in discover_factor_plugins().plugins
        if item.factor_id != factor_id and item.bar_interval == "1M"
    ]
    for peer in peers:
        try:
            computed = compute_plugin(frames.get(peer.price_adjustment, hfq), peer)
        except Exception:
            continue
        panel = panel.join(
            computed.select(["asset", "dt", peer.factor_id]),
            on=["asset", "dt"],
            how="left",
        )
    return orthogonality_summary(
        factor_id,
        panel,
        peers=[item.factor_id for item in peers],
        date_col="dt",
    )


def _matching_monthly_source(
    raw: pl.DataFrame, plugin: FactorPlugin, daily: pl.DataFrame | None
) -> pl.DataFrame | None:
    """Accept explicit provenance only when it reproduces the supplied monthly bars."""
    if daily is None or daily.is_empty():
        return None
    try:
        expected = _monthly_frame(daily, plugin.price_adjustment)
        columns = list(
            dict.fromkeys(
                column
                for column in (
                    "asset",
                    "dt",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "adjust",
                    *plugin.required_columns,
                )
                if column in raw.columns and column in expected.columns
            )
        )
        if not {"asset", "dt", *plugin.required_columns}.issubset(columns):
            return None
        supplied = raw.select(columns).with_columns(pl.col("dt").cast(pl.Datetime("ms")))
        expected = expected.select(columns).with_columns(pl.col("dt").cast(pl.Datetime("ms")))
        return (
            daily if supplied.sort(["asset", "dt"]).equals(expected.sort(["asset", "dt"])) else None
        )
    except (ValueError, pl.exceptions.PolarsError):
        return None


def _orthogonality_for(
    factor_id: str,
    raw: pl.DataFrame,
    plugin: FactorPlugin | None = None,
    *,
    daily_frame: pl.DataFrame | None = None,
) -> FactorOrthogonalitySummary:
    interval = plugin.bar_interval if plugin is not None else "1d"
    date_col = "date" if interval == "1d" else "dt"
    try:
        if interval == "1M" and plugin is not None:
            return _monthly_orthogonality(factor_id, raw, plugin, daily_frame)
        panel = compute_feature_panel(raw, interval=interval)
        if plugin is not None and factor_id not in panel.columns:
            computed = compute_plugin(raw, plugin)
            panel = panel.join(
                computed.select(["asset", date_col, factor_id]),
                on=["asset", date_col],
                how="left",
            )
        if factor_id not in panel.columns:
            return _empty_orthogonality(factor_id)
        return orthogonality_summary(factor_id, panel, date_col=date_col)
    except (ValueError, Exception):
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
    date_col = "dt" if "dt" in raw.columns else "date"
    dates = raw[date_col].to_list()
    data_start = (
        min(dates).date()
        if dates and isinstance(min(dates), dt.datetime)
        else min(dates)
        if dates
        else None
    )
    data_end = (
        max(dates).date()
        if dates and isinstance(max(dates), dt.datetime)
        else max(dates)
        if dates
        else None
    )
    remember_factor_audit(
        result,
        data_start=data_start,
        data_end=data_end,
        cutoffs=cutoffs,
        modes=modes,
        seeds=seeds,
    )


def _wind_inputs(
    factor_id: str,
    frame: pl.DataFrame | None,
    start: dt.date | None,
    end: dt.date | None,
    assets: list[str] | None,
    plugin: FactorPlugin | None,
    interval: str | None,
    source_daily: pl.DataFrame | None,
) -> tuple[pl.DataFrame, FactorPlugin | None, str, str, pl.DataFrame | None]:
    resolved_plugin = plugin or discover_factor_plugins().by_id(factor_id)
    bar_interval = interval or (resolved_plugin.bar_interval if resolved_plugin else "1d")
    if resolved_plugin is not None and bar_interval != resolved_plugin.bar_interval:
        raise ValueError("请求周期与因子固有周期不一致")
    raw = frame
    if raw is None:
        if start is None or end is None:
            raise ValueError("必须提供 frame 或 start/end")
        adjustment = str(getattr(resolved_plugin, "price_adjustment", "hfq") or "hfq")
        loaded = load_wind_tunnel_inputs(
            start, end, assets=assets, interval=bar_interval, price_adjustment=adjustment
        )
        raw, source_daily = loaded.frame, loaded.source_daily
    elif resolved_plugin is not None and bar_interval == "1M":
        source_daily = _matching_monthly_source(raw, resolved_plugin, source_daily)
    date_col = "date" if bar_interval == "1d" else "dt"
    return raw, resolved_plugin, bar_interval, date_col, source_daily


def _wind_evidence(
    factor_id: str,
    raw: pl.DataFrame,
    cutoffs: tuple[Any, ...],
    modes: tuple[str, ...] | None,
    seeds: tuple[int, ...],
    plugin: FactorPlugin | None,
    resolved_plugin: FactorPlugin | None,
    source_daily: pl.DataFrame | None,
) -> tuple[AuditReport, FactorOrthogonalitySummary]:
    report = _audit(
        factor_id,
        raw,
        cutoffs=cutoffs,
        modes=_resolve_modes(factor_id, plugin, modes),
        seeds=seeds,
        plugin=plugin,
    )
    orthogonality = _empty_orthogonality(factor_id)
    if report.status is AuditStatus.PASS:
        orthogonality = _orthogonality_for(
            factor_id, raw, resolved_plugin, daily_frame=source_daily
        )
    return report, orthogonality


@dataclass(frozen=True)
class _WindRequest:
    factor_id: str
    frame: pl.DataFrame | None
    start: dt.date | None
    end: dt.date | None
    assets: list[str] | None
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None
    modes: tuple[str, ...] | None
    seeds: tuple[int, ...]
    plugin: FactorPlugin | None
    interval: str | None
    save: bool
    source_daily: pl.DataFrame | None = None


def _inconclusive_calendar_result(factor_id: str, message: str) -> WindTunnelResult:
    import uuid

    from quantide.audit.models import AuditCheck, AuditSpec

    spec = AuditSpec(
        spec_id=f"factor:{factor_id}",
        object_type="factor",
        object_id=factor_id,
        source_hash="",
        data_hash="",
        config_hash="",
        interval="1M",
        timezone="Asia/Shanghai",
        availability_contract="calendar_unavailable",
    )
    check = AuditCheck(
        check_id="monthly_calendar",
        required=True,
        status=AuditStatus.INCONCLUSIVE,
        message=message,
    )
    report = AuditReport(
        run_id=uuid.uuid4().hex,
        spec=spec,
        status=AuditStatus.INCONCLUSIVE,
        checks=(check,),
        generated_at=dt.datetime.now(dt.UTC).isoformat(),
    )
    return WindTunnelResult(
        factor_id=factor_id,
        report=report,
        orthogonality=_empty_orthogonality(factor_id),
        metadata={"diagnostic": message},
    )


def _execute_wind_request(request: _WindRequest) -> WindTunnelResult:
    try:
        raw, resolved_plugin, bar_interval, date_col, source_daily = _wind_inputs(
            request.factor_id,
            request.frame,
            request.start,
            request.end,
            request.assets,
            request.plugin,
            request.interval,
            request.source_daily,
        )
    except MonthlyCalendarUnavailable as exc:
        return _inconclusive_calendar_result(request.factor_id, str(exc))
    resolved_cutoffs = (
        tuple(request.cutoffs)
        if request.cutoffs is not None
        else _cutoffs_for(raw, date_col=date_col)
    )
    report, orthogonality = _wind_evidence(
        request.factor_id,
        raw,
        resolved_cutoffs,
        request.modes,
        request.seeds,
        request.plugin,
        resolved_plugin,
        source_daily,
    )
    result = WindTunnelResult(
        factor_id=request.factor_id,
        report=report,
        orthogonality=orthogonality,
        metadata={
            "cutoffs": [value.isoformat() for value in resolved_cutoffs],
            "price_adjustment": str(getattr(resolved_plugin, "price_adjustment", "hfq") or "hfq"),
            "orthogonality_provenance": (
                "native_frame"
                if bar_interval != "1M"
                else "original_raw_daily"
                if source_daily is not None
                else "raw_daily_unavailable"
            ),
        },
    )
    if request.save:
        _save_result(
            result,
            raw,
            resolved_cutoffs,
            _resolve_modes(request.factor_id, request.plugin, request.modes),
            request.seeds,
        )
    return result


def run_factor_wind_tunnel(
    factor_id: str,
    *,
    frame: pl.DataFrame | None = None,
    source_daily: pl.DataFrame | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    assets: list[str] | None = None,
    cutoffs: tuple[dt.date, ...] | list[dt.date] | None = None,
    modes: tuple[str, ...] | None = None,
    seeds: tuple[int, ...] = (0,),
    plugin: FactorPlugin | None = None,
    interval: str | None = None,
    save: bool = True,
) -> WindTunnelResult:
    """Run the deterministic audit and orthogonality check for one factor."""
    request = _WindRequest(
        factor_id=factor_id,
        frame=frame,
        start=start,
        end=end,
        assets=assets,
        cutoffs=cutoffs,
        modes=modes,
        seeds=seeds,
        plugin=plugin,
        interval=interval,
        save=save,
        source_daily=source_daily,
    )
    return _execute_wind_request(request)


__all__ = [
    "WindTunnelBadgeView",
    "WindTunnelResult",
    "WindTunnelInput",
    "backtest_wind_tunnel_badge",
    "factor_wind_tunnel_badge",
    "load_wind_tunnel_frame",
    "load_wind_tunnel_inputs",
    "run_factor_wind_tunnel",
]
