"""ML prediction explanations and historical model replay."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

from quantide.core.enums import FrameType
from quantide.data.models.calendar import calendar
from quantide.factors.alpha import (
    FACTOR_VERSION,
    FEATURE_COLS,
    _zscore_1d,
)
from quantide.strategies.example._ml_support import (
    _EXPLAIN_CROSS_SECTION_CACHE as _EXPLAIN_CROSS_SECTION_CACHE,
)
from quantide.strategies.example._ml_support import (
    _EXPLAIN_MODEL_CACHE as _EXPLAIN_MODEL_CACHE,
)
from quantide.strategies.example._ml_support import (
    _HAS_LIGHTGBM as _HAS_LIGHTGBM,
)
from quantide.strategies.example._ml_support import (
    _INDEX_POOL_CACHE as _INDEX_POOL_CACHE,
)
from quantide.strategies.example._ml_support import (
    _LABEL_CACHE as _LABEL_CACHE,
)
from quantide.strategies.example._ml_support import (
    _LABEL_CACHE_MAX as _LABEL_CACHE_MAX,
)
from quantide.strategies.example._ml_support import (
    _PANEL_CACHE as _PANEL_CACHE,
)
from quantide.strategies.example._ml_support import (
    _PANEL_CACHE_MAX as _PANEL_CACHE_MAX,
)
from quantide.strategies.example._ml_support import (
    _bars_fingerprint as _bars_fingerprint,
)
from quantide.strategies.example._ml_support import (
    _cap_universe as _cap_universe,
)
from quantide.strategies.example._ml_support import (
    _coerce_date as _coerce_date,
)
from quantide.strategies.example._ml_support import (
    _describe_kline_pattern as _describe_kline_pattern,
)
from quantide.strategies.example._ml_support import (
    _describe_moving_average_signal as _describe_moving_average_signal,
)
from quantide.strategies.example._ml_support import (
    _describe_signal_reason as _describe_signal_reason,
)
from quantide.strategies.example._ml_support import (
    _ensure_data_connected as _ensure_data_connected,
)
from quantide.strategies.example._ml_support import (
    _filter_liquid_universe as _filter_liquid_universe,
)
from quantide.strategies.example._ml_support import (
    _filter_universe as _filter_universe,
)
from quantide.strategies.example._ml_support import (
    _fit_ml_model as _fit_ml_model,
)
from quantide.strategies.example._ml_support import (
    _format_candidate_rows as _format_candidate_rows,
)
from quantide.strategies.example._ml_support import (
    _future_return_horizon as _future_return_horizon,
)
from quantide.strategies.example._ml_support import (
    _index_pit_universe as _index_pit_universe,
)
from quantide.strategies.example._ml_support import (
    _parse_custom_assets as _parse_custom_assets,
)
from quantide.strategies.example._ml_support import (
    _ranked_prediction_result as _ranked_prediction_result,
)
from quantide.strategies.example._ml_support import (
    _resolve_explanation_training_windows as _resolve_explanation_training_windows,
)
from quantide.strategies.example._ml_support import (
    _resolve_stock_name as _resolve_stock_name,
)
from quantide.strategies.example._ml_support import (
    _retrain_replay_model as _retrain_replay_model,
)
from quantide.strategies.example._ml_support import (
    _score_cross_section as _score_cross_section,
)
from quantide.strategies.example._ml_support import (
    _stable_universe_rank as _stable_universe_rank,
)
from quantide.strategies.example._ml_support import (
    _training_return_labels as _training_return_labels,
)
from quantide.strategies.example._ml_support import (
    compute_future_close_return_labels as compute_future_close_return_labels,
)
from quantide.strategies.example._ml_support import (
    lgb as lgb,
)


class MLExplanation:
    """Build explanations independently of order execution."""

    if TYPE_CHECKING:
        _pipeline_version: str
        train_window: int
        future_return_horizon: int
        universe_size: int
        universe_mode: str
        market_cap_trim_pct: float
        selected_features: list[str]
        use_lightgbm: bool
        universe_rebalance_days: int
        retrain_days: int
        _cached_norm_panel: pl.DataFrame | None

        def _held_assets(self, as_of: datetime.date | None = None) -> list[str]: ...
        def _ensure_backtest_panel(self, signal_date: datetime.date) -> None: ...
        def _panel_cache_key(self, signal_date: datetime.date) -> tuple[Any, ...]: ...

    def _explain_cache_keys(
        self, signal_date: datetime.date, build_signal: datetime.date | None = None
    ) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
        """构造归因缓存的键。

        Args:
            signal_date: 决策日。

        Returns:
            tuple: (截面缓存键, 模型缓存键)。
        """
        base = (
            self._pipeline_version,
            FACTOR_VERSION,
            self.train_window,
            self.future_return_horizon,
            self.universe_size,
            self.universe_mode,
            round(self.market_cap_trim_pct, 6),
            tuple(self.selected_features or FEATURE_COLS),
            tuple(self._held_assets()),
            signal_date,
            build_signal or signal_date,
        )
        return base, base + (self.use_lightgbm,)

    def _backtest_bar_dates(
        self, bt_start: datetime.date, bt_end: datetime.date
    ) -> list[datetime.date]:
        """回测逐日推进的 bar 日期序列（交易日）。"""
        try:
            frames = calendar.get_frames(bt_start, bt_end, FrameType.DAY)
        except Exception:
            return []
        return [f for f in frames if isinstance(f, datetime.date)]

    def _replay_panel_builds(
        self, bt_start: datetime.date, bt_end: datetime.date
    ) -> list[tuple[datetime.date, datetime.date]]:
        """回放回测过程中每次重建因子面板的 (构建信号日, 窗口结束信号日)。

        面板按 ``universe_rebalance_days`` 刷新一次，因此选股池在两次刷新之间
        保持不变；归因必须用同一个构建日，才能复现当时的选池。
        """
        builds: list[tuple[datetime.date, datetime.date]] = []
        window_end: datetime.date | None = None
        for bar_date in self._backtest_bar_dates(bt_start, bt_end):
            try:
                signal_date = calendar.day_shift(bar_date, -1)
            except Exception:
                continue
            if window_end is None or signal_date > window_end:
                rebalance_end = calendar.shift(
                    signal_date, self.universe_rebalance_days, FrameType.DAY
                )
                window_end = max(signal_date, min(rebalance_end, bt_end))
                builds.append((signal_date, window_end))
        return builds

    def _replay_context(
        self,
        target_signal: datetime.date,
        bt_start: datetime.date,
        bt_end: datetime.date,
    ) -> tuple[datetime.date, datetime.date, datetime.date]:
        """定位某信号日在回测中对应的面板构建日与最近一次模型重训。

        Args:
            target_signal: 目标信号日（成交日的前一交易日）。
            bt_start: 回测起始交易日。
            bt_end: 回测结束交易日。

        Returns:
            tuple: (目标截面所用面板的构建信号日, 重训所用面板的构建信号日,
            重训的信号日)。
        """
        builds = self._replay_panel_builds(bt_start, bt_end)

        def _build_for(signal_date: datetime.date) -> datetime.date:
            for build_signal, window_end in builds:
                if build_signal <= signal_date <= window_end:
                    return build_signal
            return signal_date

        target_build = _build_for(target_signal)

        bar_dates = self._backtest_bar_dates(bt_start, bt_end)
        refit_signal = target_signal
        refit_build = target_build
        for index, bar_date in enumerate(bar_dates):
            try:
                signal_date = calendar.day_shift(bar_date, -1)
            except Exception:
                continue
            if signal_date > target_signal:
                break
            position = index + 1
            if (position - 1) % max(1, self.retrain_days) == 0:
                refit_signal = signal_date
                refit_build = _build_for(signal_date)
        return target_build, refit_build, refit_signal

    def _explain_cross_section(
        self, signal_date: datetime.date, build_signal: datetime.date | None = None
    ) -> pl.DataFrame:
        """取归因用的目标日截面（只缓存当前这一条）。

        整张因子面板约 160k 行、100MB，不做缓存；这里只缓存目标日截面
        （约 2000 行、1MB），够「同一次交易在特征页与 SHAP 页之间切换」
        不重复计算；换一笔交易则重新计算。

        Args:
            signal_date: 决策日。

        Returns:
            pl.DataFrame: 目标日截面（含原始因子与 z 因子）；可能为空。
        """
        build_signal = build_signal or signal_date
        cross_key, _ = self._explain_cache_keys(signal_date, build_signal)
        cached = _EXPLAIN_CROSS_SECTION_CACHE.get(cross_key)
        if cached is not None:
            return cached
        self._ensure_backtest_panel(build_signal)
        panel = self._cached_norm_panel
        if panel is None or panel.is_empty():
            return pl.DataFrame()
        target_date = panel.filter(pl.col("date") <= pl.lit(signal_date))["date"].max()
        if target_date is None:
            return pl.DataFrame()
        keep = (
            ["date", "asset", "close"]
            + [c for c in (self.selected_features or FEATURE_COLS)]
            + [f"{c}_z" for c in (self.selected_features or FEATURE_COLS)]
        )
        cross = panel.filter(pl.col("date") == target_date).select(
            [c for c in keep if c in panel.columns]
        )
        _EXPLAIN_CROSS_SECTION_CACHE.clear()
        _EXPLAIN_CROSS_SECTION_CACHE[cross_key] = cross
        return cross

    def _attribution_model(
        self, target_date: datetime.date, build_signal: datetime.date | None = None
    ) -> tuple[object, str]:
        """取（或训练）归因所需的模型，按决策日缓存。

        模型缓存键含流水线版本、因子版本、训练参数、因子集与当时持仓；
        命中即复用，未命中时临时构建训练面板（不常驻）。

        Args:
            target_date: 截面日。

        Returns:
            tuple: (模型, 引擎名)。
        """
        build_signal = build_signal or target_date
        _, key = self._explain_cache_keys(target_date, build_signal)
        cached = _EXPLAIN_MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        self._ensure_backtest_panel(build_signal)
        panel = self._cached_norm_panel
        if panel is None or panel.is_empty():
            raise RuntimeError("归因面板为空，无法训练模型")
        hist = panel.filter(pl.col("date") <= pl.lit(target_date))
        if hist.is_empty():
            raise RuntimeError("归因训练数据为空")
        model, engine = _fit_ml_model(
            hist,
            train_window=self.train_window,
            horizon=self.future_return_horizon,
            use_lightgbm=self.use_lightgbm,
            feature_cols=self.selected_features or FEATURE_COLS,
            label_cache_key=self._panel_cache_key(build_signal),
        )
        if len(_EXPLAIN_MODEL_CACHE) >= 8:
            _EXPLAIN_MODEL_CACHE.pop(next(iter(_EXPLAIN_MODEL_CACHE)))
        _EXPLAIN_MODEL_CACHE[key] = (model, engine)
        return model, engine

    def explain_features(
        self, asset: str, signal_date: datetime.date
    ) -> list[tuple[str, float]] | None:
        """返回该资产在决策日的因子取值（与模型输入同源）。

        使用策略自己的面板（同一选股池、同一复权口径），因此展示的数值就是
        模型当时看到的值。

        Args:
            asset: 证券代码。
            signal_date: 决策日。

        Returns:
            list | None: (因子名, 取值) 列表；数据不足时返回 ``None``。
        """
        try:
            cross = self._explain_cross_section(signal_date)
        except Exception:
            return None
        if cross is None or cross.is_empty():
            return None
        row = cross.filter(pl.col("asset") == asset)
        if row.is_empty():
            return None
        values = row.row(0, named=True)
        result: list[tuple[str, float]] = []
        for col in FEATURE_COLS:
            value = values.get(col)
            if value is None:
                continue
            try:
                result.append((col, float(value)))
            except (TypeError, ValueError):
                continue
        return result or None

    def explain_prediction(
        self,
        asset: str,
        signal_date: datetime.date,
        bt_start: datetime.date | None = None,
        bt_end: datetime.date | None = None,
    ) -> dict[str, Any] | None:
        """返回该资产在决策日的最终得分归因。

        最终得分就是模型输出（截面 z-score），不含任何手工先验。模型部分用
        LightGBM 自带的 TreeSHAP（``pred_contrib=True``）给出逐特征贡献，
        基线 + 贡献之和可精确还原该股票的截面得分。

        Args:
            asset: 证券代码。
            signal_date: 决策日（信号日，即成交日的前一交易日）。
            bt_start: 回测起始交易日；给出时按回测节奏回放选池与训练，得到与
                当次决策完全一致的截面与模型。
            bt_end: 回测结束交易日。

        Returns:
            dict | None: 归因结果；数据不足或资产不在截面内时返回 ``None``。
        """
        build_signal: datetime.date | None = None
        refit_build: datetime.date | None = None
        refit_signal: datetime.date | None = None
        build_signal, refit_build, refit_signal = _resolve_explanation_training_windows(
            bt_end, bt_start, build_signal, refit_build, refit_signal, self, signal_date
        )
        try:
            cross = self._explain_cross_section(signal_date, build_signal)
        except Exception:
            return None
        if cross is None or cross.is_empty():
            return None

        return _explain_prediction_cross(
            self, asset, cross, build_signal, refit_signal, refit_build
        )


@dataclass
class _AttributionNumbers:
    scores: np.ndarray
    contributions: np.ndarray
    baseline: float


def _model_attribution(
    model: object | None, engine: str, x: np.ndarray, index: int
) -> _AttributionNumbers | None:
    """Normalize predictions and feature contributions with the same cross-section scale."""
    predict = getattr(model, "predict", None)
    if engine == "LightGBM" and callable(predict):
        raw = np.asarray(predict(x), dtype=np.float64)
        shap = np.asarray(predict(x, pred_contrib=True), dtype=np.float64)
        scale = float(np.std(raw)) + 1e-6
        contributions = shap[index][:-1] / scale
        baseline = (float(shap[index][-1]) - float(np.mean(raw))) / scale
    elif isinstance(model, np.ndarray):
        raw = x @ model
        scale = float(np.std(raw)) + 1e-6
        contributions = (x[index] * model) / scale
        baseline = -float(np.mean(raw)) / scale
    else:
        return None
    return _AttributionNumbers(_zscore_1d(raw), contributions, baseline)


def _prediction_features(
    cross: pl.DataFrame,
    index: int,
    features: Sequence[str],
    z_row: np.ndarray,
    contributions: np.ndarray,
) -> list[dict[str, Any]]:
    raw = cross.row(index, named=True)
    values = [
        {
            "name": name,
            "value": None if raw.get(name) is None else float(raw[name]),
            "z": float(z_row[i]),
            "total": float(contributions[i]),
        }
        for i, name in enumerate(features)
    ]
    return sorted(values, key=lambda item: abs(item["total"]), reverse=True)


def _explain_prediction_cross(
    self: MLExplanation,
    asset: str,
    cross: pl.DataFrame,
    build_signal: datetime.date | None,
    refit_signal: datetime.date | None,
    refit_build: datetime.date | None,
) -> dict[str, Any] | None:
    """Attribute the selected asset using the model effective for this decision."""
    target_date = cross["date"][0]
    assets = cross["asset"].to_list()
    if asset not in assets:
        return None
    index = assets.index(asset)
    model, engine = self._attribution_model(
        refit_signal or target_date, refit_build or build_signal
    )
    features = self.selected_features or FEATURE_COLS
    x = (
        cross.select([f"{name}_z" for name in features])
        .fill_null(0.0)
        .fill_nan(0.0)
        .to_numpy()
        .astype(np.float64)
    )
    numbers = _model_attribution(model, engine, x, index)
    if numbers is None:
        return None
    return {
        "asset": asset,
        "date": target_date,
        "engine": engine,
        "score": float(numbers.scores[index]),
        "baseline": float(numbers.baseline),
        "rank": sorted(range(len(assets)), key=lambda i: (-numbers.scores[i], assets[i])).index(
            index
        )
        + 1,
        "cross_section": len(assets),
        "features": _prediction_features(cross, index, features, x[index], numbers.contributions),
    }
