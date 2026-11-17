"""Backtest presets and baseline-vs-variant ablation reports for research CLI/Web."""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

import polars as pl
from loguru import logger

from quantide.core.enums import FrameType
from quantide.data.models.calendar import calendar
from quantide.data.sqlite import db
from quantide.factors.universe import UniverseFilterConfig
from quantide.service.attribution import explain_prediction
from quantide.service.factor_audit import (
    feature_audit_binding,
    record_backtest_audit_binding,
)
from quantide.service.factor_presets import (
    FactorPreset,
    load_preset,
    resolve_strategy,
    strategy_interval,
)
from quantide.service.metrics import metrics
from quantide.service.runner import BacktestRunner
from quantide.service.shadow_support import config_symbols


def _parse_pct(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(str(value).strip().rstrip("%")) / 100.0
    except ValueError:
        return None


def _parse_number(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metrics_payload(portfolio_id: str, start: dt.date, end: dt.date) -> dict[str, Any]:
    stats = metrics(portfolio_id, start=start, end=end)
    values: dict[str, Any] = {}
    if stats is not None and "Value" in stats.columns:
        values = cast(dict[str, Any], stats["Value"].to_dict())
    return {
        "portfolio_id": portfolio_id,
        "annual_return": _parse_pct(values.get("CAGR")),
        "total_returns": _parse_pct(values.get("Total Return")),
        "max_drawdown": _parse_pct(values.get("Max Drawdown")),
        "sharpe": _parse_number(values.get("Sharpe Ratio")),
        "sortino": _parse_number(values.get("Sortino Ratio")),
        "calmar": _parse_number(values.get("Calmar Ratio")),
        "raw": values,
    }


def _trade_cost_summary(portfolio_id: str) -> dict[str, float]:
    trades = db.trades_all(portfolio_id)
    if trades is None or trades.is_empty():
        return {"turnover": 0.0, "total_fees": 0.0, "trade_count": 0.0}
    amount = (
        pl.col("amount").cast(pl.Float64).abs().sum() if "amount" in trades.columns else pl.lit(0.0)
    )
    fees = pl.col("fee").cast(pl.Float64).sum() if "fee" in trades.columns else pl.lit(0.0)
    row = trades.select(amount.alias("amount"), fees.alias("fee")).row(0, named=True)
    assets = db.query_assets(portfolio_id)
    avg_equity = 1.0
    if assets is not None and not assets.is_empty() and "total" in assets.columns:
        mean = assets["total"].cast(pl.Float64).mean()
        avg_equity = float(cast(Any, mean)) if mean else 1.0
    return {
        "turnover": float(row["amount"] or 0.0) / max(abs(avg_equity), 1.0),
        "total_fees": float(row["fee"] or 0.0),
        "trade_count": float(trades.height),
    }


def _equity_curve(portfolio_id: str) -> list[dict[str, Any]]:
    assets = db.query_assets(portfolio_id)
    if assets is None or assets.is_empty():
        return []
    assets = assets.sort("dt")
    return [
        {"date": str(row.get("dt")), "total": _parse_number(row.get("total"))}
        for row in assets.iter_rows(named=True)
    ]


def _annualized_turnover(turnover: float, start: dt.date, end: dt.date) -> float:
    years = max((end - start).days / 365.25, 1 / 252)
    return turnover / years


_EXECUTION_CONTRACT_KEYS = {
    "fill_timing",
    "slippage_pct",
    "commission",
    "stamp_duty",
    "transfer_fee",
    "min_commission",
    "auction_epsilon",
    "seed",
}

_FIXED_CONTRACT_KEYS: tuple[str, ...] = (
    "universe_mode",
    "universe_size",
    "index_pool_codes",
    "market_cap_trim_pct",
    "universe_rebalance_days",
    "min_listing_days",
    "exclude_st",
    "exclude_suspended",
    "exclude_limit_locked_on_close",
    "max_universe_size",
    "fill_timing",
    "slippage_pct",
    "commission",
    "stamp_duty",
    "transfer_fee",
    "min_commission",
    "auction_epsilon",
    "seed",
)


def _canonical_filter(config: dict[str, Any]) -> dict[str, Any]:
    nested = config.get("universe_filter")
    merged = {**config, **(nested if isinstance(nested, dict) else {})}
    return UniverseFilterConfig.from_mapping(merged, max_universe_size=None).as_dict()


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _effective_contract(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the same effective selection/execution values the strategy consumes."""
    filter_values = _canonical_filter(config)
    top_k = max(1, _integer(config.get("top_k"), 5))
    values: dict[str, Any] = {
        key: filter_values[key]
        for key in _FIXED_CONTRACT_KEYS
        if key in filter_values and key not in _EXECUTION_CONTRACT_KEYS
    }
    values.update(
        {
            "universe_mode": str(config.get("universe_mode", "market_cap_trim")).strip(),
            "universe_size": max(top_k, _integer(config.get("universe_size"), 2000)),
            "index_pool_codes": [str(item) for item in config.get("index_pool_codes") or []],
            "market_cap_trim_pct": min(
                0.5, max(0.0, _number(config.get("market_cap_trim_pct"), 0.05))
            ),
            "universe_rebalance_days": max(1, _integer(config.get("universe_rebalance_days"), 20)),
            "fill_timing": str(config.get("fill_timing", "auction_close")).strip().lower(),
            "slippage_pct": _number(config.get("slippage_pct"), 0.0),
            "commission": _number(config.get("commission"), 0.0),
            "stamp_duty": _number(config.get("stamp_duty", config.get("stamp_tax")), 0.0),
            "transfer_fee": _number(config.get("transfer_fee"), 0.0),
            "min_commission": _number(config.get("min_commission"), 0.0),
            "auction_epsilon": _number(config.get("auction_epsilon"), 0.0),
            "seed": _integer(config.get("seed"), 0),
            "symbols": config_symbols(config, include_universe=True) or None,
        }
    )
    return values


def _contract_conflicts(baseline: dict[str, Any], variant: dict[str, Any]) -> list[str]:
    return [
        key for key in sorted(set(baseline) | set(variant)) if baseline.get(key) != variant.get(key)
    ]


def _config_for(
    strategy_id: str,
    preset: FactorPreset | None,
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    cls = resolve_strategy(strategy_id)
    default_fn = getattr(cls, "default_config", None)
    config = dict(default_fn() if callable(default_fn) else getattr(cls, "PARAMS", {}) or {})
    if preset is not None:
        if preset.strategy_id != strategy_id:
            raise ValueError(
                f"预设 {preset.preset_id} 绑定策略 {preset.strategy_id}，不能用于 {strategy_id}"
            )
        config.update(preset.to_config())
    if params:
        config.update(params)
    interval = strategy_interval(strategy_id)
    supplied = str(config.get("bar_interval") or interval).strip()
    if supplied != interval:
        raise ValueError(f"配置周期 {supplied} 与策略周期 {interval} 不匹配")
    config["bar_interval"] = interval
    return config


def _signal_date(tm: Any) -> dt.date | None:
    if isinstance(tm, dt.datetime):
        if tm.time() > dt.time(9, 30):
            return tm.date()
        decision = tm.date()
    elif isinstance(tm, dt.date):
        decision = tm
    else:
        return None
    try:
        return calendar.day_shift(decision, -1)
    except Exception:
        return decision - dt.timedelta(days=1)


def _explain_with_class(
    strategy_cls: Any,
    config: dict[str, Any],
    run_id: str,
    asset: str,
    signal_date: dt.date,
    start: dt.date,
    end: dt.date,
) -> dict[str, Any] | None:
    from quantide.service import attribution

    if not attribution.supports_attribution(strategy_cls):
        return None
    try:
        strategy = strategy_cls(
            attribution._AttributionBroker(
                attribution.load_holdings_at(run_id, signal_date), end, start
            ),
            config,
        )
        strategy._positions_by_date = attribution.load_positions_by_date(run_id)
        explainer = getattr(strategy, "explain_prediction", None)
        if not callable(explainer):
            return None
        return cast(dict[str, Any] | None, explainer(asset, signal_date, start, end))
    except Exception:
        logger.exception(f"策略内 SHAP 回退失败: portfolio={run_id} asset={asset}")
        return None


def _shap_predictions(
    run_id: str,
    start: dt.date,
    end: dt.date,
    strategy_cls: Any = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    trades = db.trades_all(run_id)
    if trades is None or trades.is_empty() or "tm" not in trades.columns:
        return []
    seen: set[tuple[str, dt.date]] = set()
    predictions: list[dict[str, Any]] = []
    for row in trades.iter_rows(named=True):
        asset = str(row.get("asset") or "")
        signal_date = _signal_date(row.get("tm"))
        if not asset or signal_date is None or (asset, signal_date) in seen:
            continue
        seen.add((asset, signal_date))
        try:
            explanation = explain_prediction(run_id, asset, signal_date, bt_start=start, bt_end=end)
        except Exception:
            logger.exception(
                f"消融 SHAP 计算失败: portfolio={run_id} asset={asset} signal={signal_date}"
            )
            continue
        if explanation is None and strategy_cls is not None and config is not None:
            explanation = _explain_with_class(
                strategy_cls, config, run_id, asset, signal_date, start, end
            )
        if explanation:
            predictions.append(explanation)
    return predictions


def _shap_top_features(
    run_id: str,
    start: dt.date,
    end: dt.date,
    strategy_cls: Any = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    predictions = _shap_predictions(run_id, start, end, strategy_cls, config)
    if not predictions:
        return [], ["shap_unavailable"]
    totals: dict[str, float] = {}
    for explanation in predictions:
        for item in explanation.get("features") or []:
            name = str(item.get("name") or "")
            if not name:
                continue
            totals[name] = totals.get(name, 0.0) + abs(float(item.get("total") or 0.0))
    overall = sum(totals.values())
    if overall <= 0:
        return [], ["shap_unavailable"]
    count = len(predictions)
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return (
        [
            {
                "feature": name,
                "name": name,
                "mean_abs_shap": round(total / count, 6),
                "share": round(total / overall, 6),
            }
            for name, total in ranked
        ],
        [],
    )


def _execute_backtest(
    strategy_cls: Any,
    config: dict[str, Any],
    start: dt.date,
    end: dt.date,
    initial_cash: float,
    run_id: str,
    interval: str,
) -> dict[str, Any]:
    runner = BacktestRunner()
    return asyncio.run(
        runner.run(
            strategy_cls=strategy_cls,
            config=config,
            start_date=start,
            end_date=end,
            frame_type=FrameType(interval),
            initial_cash=initial_cash,
            portfolio_id=run_id,
            save_logs=False,
        )
    )


def _backtest_payload(
    *,
    strategy_id: str,
    preset: FactorPreset | None,
    start: dt.date,
    end: dt.date,
    initial_cash: float,
    run_id: str,
    config: dict[str, Any],
    cls: type,
) -> dict[str, Any]:
    metrics_payload = _metrics_payload(run_id, start, end)
    costs = _trade_cost_summary(run_id)
    shap_features, shap_diagnostics = _shap_top_features(run_id, start, end, cls, config)
    return {
        "portfolio_id": run_id,
        "strategy_id": strategy_id,
        "preset_id": preset.preset_id if preset is not None else None,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_cash": initial_cash,
        "config": config,
        "features": list(config.get("features") or []),
        "metrics": metrics_payload,
        "turnover": _annualized_turnover(costs["turnover"], start, end),
        "total_fees": costs["total_fees"],
        "trade_count": int(costs["trade_count"]),
        "equity_curve": _equity_curve(run_id),
        "shap_top_features": shap_features,
        "diagnostics": shap_diagnostics,
    }


def _freeze_experiment_binding(
    config: dict[str, Any], interval: str, start: dt.date, end: dt.date, run_id: str
) -> None:
    binding = feature_audit_binding(
        config,
        interval,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        run_id=run_id,
    )
    record_backtest_audit_binding(run_id, config, interval, run_id=run_id, binding=binding)


def _record_experiment_result(
    config: dict[str, Any],
    interval: str,
    start: dt.date,
    end: dt.date,
    run_id: str,
    execution: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = (execution or {}).get("universe_diagnostics") or {}
    record_backtest_audit_binding(
        run_id,
        config,
        interval,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        run_id=run_id,
        model_ref=str(execution.get("model_ref") or ""),
        diagnostics=diagnostics,
    )
    return diagnostics


def run_single_backtest(
    strategy_id: str,
    *,
    start: dt.date,
    end: dt.date,
    preset: FactorPreset | None = None,
    params: dict[str, Any] | None = None,
    initial_cash: float = 1_000_000.0,
    portfolio_id: str | None = None,
    fixed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one isolated backtest and return metrics, fees and equity curve."""
    from quantide.service.research_cli import _ensure_data

    _ensure_data()
    config = _config_for(strategy_id, preset, params)
    if fixed:
        config.update(fixed)
    cls = resolve_strategy(strategy_id)
    run_id = portfolio_id or uuid.uuid4().hex
    _freeze_experiment_binding(config, strategy_interval(strategy_id), start, end, run_id)
    execution = _execute_backtest(
        cls,
        config,
        start,
        end,
        initial_cash,
        run_id,
        strategy_interval(strategy_id),
    )
    universe_diagnostics = _record_experiment_result(
        config, strategy_interval(strategy_id), start, end, run_id, execution
    )
    payload = _backtest_payload(
        strategy_id=strategy_id,
        preset=preset,
        start=start,
        end=end,
        initial_cash=initial_cash,
        run_id=run_id,
        config=config,
        cls=cls,
    )
    payload["universe_diagnostics"] = universe_diagnostics
    payload["model_ref"] = str(execution.get("model_ref") or "")
    return payload


@dataclass(frozen=True)
class AblationStudySpec:
    """Baseline and 1-5 variants sharing every execution condition."""

    baseline_preset_id: str
    variant_preset_ids: tuple[str, ...]
    start: dt.date
    end: dt.date
    principal: float = 1_000_000.0
    commission: float = 1e-4
    stamp_tax: float = 5e-4
    transfer_fee: float = 1e-5
    min_commission: float = 5.0
    seed: int = 42
    strategy_id: str = ""
    universe_filter: dict[str, Any] = field(default_factory=dict)

    def fixed_config(self) -> dict[str, Any]:
        return {
            "commission": self.commission,
            "stamp_duty": self.stamp_tax,
            "transfer_fee": self.transfer_fee,
            "min_commission": self.min_commission,
            "seed": self.seed,
            "universe_filter": dict(self.universe_filter),
        }

    def __post_init__(self) -> None:
        if not 1 <= len(self.variant_preset_ids) <= 5:
            raise ValueError("消融对比需要 1~5 个 Variant 预设")
        if len(set(self.variant_preset_ids)) != len(self.variant_preset_ids):
            raise ValueError("Variant 预设不能重复")
        if self.baseline_preset_id in self.variant_preset_ids:
            raise ValueError("Baseline 不能同时作为 Variant")
        if self.start > self.end:
            raise ValueError("开始日期不能晚于结束日期")


def _variant_shap(baseline: dict[str, Any], variant: dict[str, Any]) -> list[dict[str, Any]]:
    changed = set(variant.get("features") or []) ^ set(baseline.get("features") or [])
    features = variant.get("shap_top_features") or []
    if not changed:
        return features
    return [item for item in features if item.get("feature") in changed]


def _comparison(baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    b_metrics = baseline["metrics"]
    v_metrics = variant["metrics"]
    annual = _parse_number(v_metrics.get("annual_return"))
    baseline_annual = _parse_number(b_metrics.get("annual_return"))
    return {
        "preset_id": variant.get("preset_id"),
        "portfolio_id": variant["portfolio_id"],
        "annual_return": annual,
        "annual_excess": (
            annual - baseline_annual if annual is not None and baseline_annual is not None else None
        ),
        "max_drawdown": v_metrics.get("max_drawdown"),
        "max_drawdown_delta": (
            (v_metrics.get("max_drawdown") or 0.0) - (b_metrics.get("max_drawdown") or 0.0)
        ),
        "sharpe": v_metrics.get("sharpe"),
        "calmar": v_metrics.get("calmar"),
        "turnover": variant["turnover"],
        "total_fees": variant["total_fees"],
        "equity_curve": variant["equity_curve"],
        "shap_top_features": _variant_shap(baseline, variant),
    }


def run_ablation(spec: AblationStudySpec) -> dict[str, Any]:
    """Run baseline and variants sequentially under identical fixed conditions."""
    from quantide.service.research_cli import _ensure_data

    _ensure_data()
    baseline_preset = load_preset(spec.baseline_preset_id)
    variants = [load_preset(preset_id) for preset_id in spec.variant_preset_ids]
    strategy_id = spec.strategy_id or baseline_preset.strategy_id
    for preset in (baseline_preset, *variants):
        if preset.strategy_id != strategy_id:
            raise ValueError("Baseline/Variant 必须绑定同一策略")
    baseline_config = _config_for(strategy_id, baseline_preset, None)
    baseline_contract = _effective_contract(baseline_config)
    for preset in variants:
        variant_config = _config_for(strategy_id, preset, None)
        conflicts = _contract_conflicts(baseline_contract, _effective_contract(variant_config))
        if conflicts:
            raise ValueError(
                "Variant 必须保持与 Baseline 相同的有效选池/执行合同: " + ", ".join(conflicts)
            )
    fixed = {**baseline_contract}
    fixed.update(spec.fixed_config())
    if not spec.universe_filter:
        fixed["universe_filter"] = _canonical_filter(baseline_config)
    if baseline_contract.get("symbols"):
        fixed["symbols"] = list(baseline_contract["symbols"])
    baseline = run_single_backtest(
        strategy_id,
        start=spec.start,
        end=spec.end,
        preset=baseline_preset,
        initial_cash=spec.principal,
        fixed=fixed,
    )
    runs = [
        run_single_backtest(
            strategy_id,
            start=spec.start,
            end=spec.end,
            preset=preset,
            initial_cash=spec.principal,
            fixed=fixed,
        )
        for preset in variants
    ]
    return {
        "spec": {
            "baseline_preset_id": spec.baseline_preset_id,
            "variant_preset_ids": list(spec.variant_preset_ids),
            "start": spec.start.isoformat(),
            "end": spec.end.isoformat(),
            "principal": spec.principal,
            "commission": spec.commission,
            "stamp_tax": spec.stamp_tax,
            "transfer_fee": spec.transfer_fee,
            "min_commission": spec.min_commission,
            "seed": spec.seed,
            "universe_filter": spec.universe_filter,
        },
        "strategy_id": strategy_id,
        "baseline": baseline,
        "variants": [_comparison(baseline, run) for run in runs],
    }


__all__ = [
    "AblationStudySpec",
    "run_ablation",
    "run_single_backtest",
]
