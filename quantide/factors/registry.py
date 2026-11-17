"""Unified factor catalog: built-in factors plus discovered external plugins."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Sequence

import polars as pl

from quantide.factors.alpha import (
    FACTOR_VERSION,
    FEATURE_COLS,
    FEATURE_GROUPS,
    compute_alpha_features,
)
from quantide.factors.metadata import (
    FACTOR_METADATA,
    GLOBAL_TRACKING_DEFAULTS,
    FactorDefinition,
    TrackingDefaults,
)
from quantide.factors.plugins import (
    FactorPlugin,
    PluginDiscovery,
    SkippedFactorEntry,
    augment_panel_with_plugins,
    discover_factor_plugins,
)

EXTERNAL_GROUP = "自定义因子"


def _tracking_defaults(plugin: FactorPlugin) -> TrackingDefaults:
    return TrackingDefaults(
        GLOBAL_TRACKING_DEFAULTS.lookback,
        GLOBAL_TRACKING_DEFAULTS.primary_holding_days,
        GLOBAL_TRACKING_DEFAULTS.comparison_holding_days,
        GLOBAL_TRACKING_DEFAULTS.price_field,
        f"plugin:{plugin.source_hash}",
    )


def plugin_definition(plugin: FactorPlugin) -> FactorDefinition:
    """Adapt an external plugin to the existing factor metadata contract."""
    parameters = (
        f"bar_interval={plugin.bar_interval}",
        f"warmup_bars={plugin.warmup_bars}",
        f"availability={plugin.availability}",
        f"price_adjustment={plugin.price_adjustment}",
    )
    return FactorDefinition(
        factor_id=plugin.factor_id,
        display_name=plugin.display_name,
        group=plugin.group or EXTERNAL_GROUP,
        direction=plugin.direction,
        principle=plugin.principle,
        formula=plugin.formula,
        parameters=parameters,
        example=plugin.example,
        data_requirements="、".join(plugin.required_columns),
        caveats=plugin.caveats,
        recommended_tracking=_tracking_defaults(plugin),
    )


def _builtin_definitions() -> dict[str, FactorDefinition]:
    return dict(FACTOR_METADATA)


def discovery() -> PluginDiscovery:
    """Return the current tolerant plugin scan."""
    return discover_factor_plugins()


def factor_plugin(factor_id: str) -> FactorPlugin | None:
    return discovery().by_id(factor_id)


def all_factor_ids(interval: str | None = None) -> list[str]:
    """Return builtins and external factor IDs, optionally for one interval."""
    builtins = list(FEATURE_COLS) if interval in (None, "1d") else []
    return [
        *builtins,
        *(
            plugin.factor_id
            for plugin in discovery().plugins
            if interval is None or plugin.bar_interval == interval
        ),
    ]


def feature_groups(interval: str | None = None) -> OrderedDict[str, list[str]]:
    """Return factor groups, optionally filtered to one bar interval."""
    groups: OrderedDict[str, list[str]] = OrderedDict()
    if interval in (None, "1d"):
        groups.update((group, list(ids)) for group, ids in FEATURE_GROUPS.items())
    for plugin in discovery().plugins:
        if interval is not None and plugin.bar_interval != interval:
            continue
        groups.setdefault(plugin.group or EXTERNAL_GROUP, []).append(plugin.factor_id)
    return groups


def feature_docs() -> dict[str, str]:
    from quantide.factors.alpha import FEATURE_DOCS

    docs = dict(FEATURE_DOCS)
    for plugin in discovery().plugins:
        docs[plugin.factor_id] = (
            f"计算：{plugin.formula or plugin.principle or '外部插件'}\n"
            f"含义：{plugin.principle or plugin.display_name}\n"
            f"示例：{plugin.example or '外部因子插件'}"
        )
    return docs


def factor_metadata(interval: str | None = None) -> dict[str, FactorDefinition]:
    metadata = _builtin_definitions() if interval in (None, "1d") else {}
    for plugin in discovery().plugins:
        if interval is None or plugin.bar_interval == interval:
            metadata[plugin.factor_id] = plugin_definition(plugin)
    return metadata


def factor_definition(factor_id: str) -> FactorDefinition:
    metadata = factor_metadata()
    if factor_id not in metadata:
        raise KeyError(factor_id)
    return metadata[factor_id]


def list_factor_definitions(interval: str | None = None) -> list[FactorDefinition]:
    metadata = factor_metadata(interval)
    return [metadata[factor_id] for factor_id in all_factor_ids(interval)]


def plugin_skipped_entries() -> tuple[SkippedFactorEntry, ...]:
    return discovery().skipped


def _failed_wind_tunnel_ids(candidates: Sequence[str]) -> set[str]:
    try:
        from quantide.service.factor_audit import factor_wind_tunnel_badge

        return {
            factor_id
            for factor_id in candidates
            if factor_wind_tunnel_badge(factor_id).badge_status == "FAIL"
        }
    except Exception:
        return set()


def resolve_feature_selection(
    requested: Sequence[str] | None, interval: str | None = None
) -> list[str]:
    groups = feature_groups(interval)
    ordered = [name for names in groups.values() for name in names]
    if not requested:
        failed = _failed_wind_tunnel_ids(ordered)
        return [name for name in ordered if name not in failed]
    known = set(ordered)
    all_known = set(all_factor_ids())
    unknown = [name for name in requested if name not in known]
    cross_period = [name for name in unknown if name in all_known]
    if cross_period:
        raise ValueError(
            f"因子周期与策略周期 {interval or '全部'} 不匹配: "
            f"{', '.join(sorted(set(cross_period)))}"
        )
    if unknown:
        raise ValueError(f"未知因子: {', '.join(sorted(set(unknown)))}")
    failed = _failed_wind_tunnel_ids(requested)
    if failed:
        raise ValueError(f"风洞 FAIL 因子已被阻断: {', '.join(sorted(failed))}")
    selected = set(requested)
    return [name for name in ordered if name in selected]


def factor_source_hash(factor_id: str) -> str:
    plugin = factor_plugin(factor_id)
    return plugin.source_hash if plugin is not None else ""


def factor_version(factor_id: str) -> str:
    plugin = factor_plugin(factor_id)
    return plugin.source_hash if plugin is not None else FACTOR_VERSION


def catalog_version() -> str:
    parts = [FACTOR_VERSION]
    for plugin in discovery().plugins:
        parts.append(f"{plugin.factor_id}:{plugin.source_hash}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def external_feature_ids(
    requested: Sequence[str] | None = None, interval: str | None = None
) -> list[str]:
    selected = set(requested) if requested is not None else None
    return [
        plugin.factor_id
        for plugin in discovery().plugins
        if (selected is None or plugin.factor_id in selected)
        and (interval is None or plugin.bar_interval == interval)
    ]


def _raw_plugin_panel(panel: pl.DataFrame) -> pl.DataFrame:
    """Normalize raw keys without applying any price adjustment."""
    exprs = []
    if "date" in panel.columns:
        exprs.append(pl.col("date").cast(pl.Date).alias("date"))
    if "dt" in panel.columns:
        exprs.append(pl.col("dt").cast(pl.Datetime("ms")).alias("dt"))
    if "asset" in panel.columns:
        exprs.append(pl.col("asset").cast(pl.Utf8).alias("asset"))
    return panel.with_columns(exprs) if exprs else panel


def compute_feature_panel(
    panel: pl.DataFrame,
    feature_cols: Sequence[str] | None = None,
    *,
    stock_meta: pl.DataFrame | None = None,
    strict_plugins: bool = False,
    interval: str = "1d",
) -> pl.DataFrame:
    """Compute built-in factors and join raw-price external factor columns.

    Built-in factors are computed on the adjusted panel. External plugins are
    always fed the raw panel, so their declared ``price_adjustment`` is applied
    exactly once inside ``compute_plugin``.
    """
    date_col = "dt" if interval != "1d" else "date"
    if interval == "1d":
        result = compute_alpha_features(panel, stock_meta=stock_meta)
    else:
        result = panel.select(["asset", date_col])
    external = external_feature_ids(feature_cols, interval)
    if not external:
        return result
    raw = _raw_plugin_panel(panel)
    augmented = augment_panel_with_plugins(raw, external, strict=strict_plugins, interval=interval)
    columns = [name for name in external if name in augmented.columns]
    if not columns:
        return result
    return result.join(
        augmented.select(["asset", date_col, *columns]),
        on=["asset", date_col],
        how="left",
    )


__all__ = [
    "EXTERNAL_GROUP",
    "all_factor_ids",
    "catalog_version",
    "compute_feature_panel",
    "discovery",
    "external_feature_ids",
    "factor_definition",
    "factor_metadata",
    "factor_plugin",
    "factor_source_hash",
    "factor_version",
    "feature_docs",
    "feature_groups",
    "list_factor_definitions",
    "plugin_definition",
    "plugin_skipped_entries",
    "resolve_feature_selection",
]
