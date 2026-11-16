"""A股动量与趋势反转机器学习选股策略 (LightGBM 截面排序).

Universe selection:
- ``market_cap_trim`` (default): drop the largest and smallest 5% by
  point-in-time ``total_mv``, then drop suspended/ST stocks.  All remaining
  stocks are eligible. Market cap comes from the configured data home's daily_basic store.
- ``liquidity``: legacy top-N by 20-day mean amount.
- In backtest, the universe is re-selected every ``universe_rebalance_days``
  (default 20) trading days; this bounds the cost of refetching the feature
  panel while avoiding a fixed full-period universe.
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

if TYPE_CHECKING:
    from quantide.strategies.example._ml_explanation import MLExplanation
    from quantide.strategies.example.ml_momentum_reversal import MLMomentumReversalStrategy

from quantide.config.settings import get_data_home
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.daily_basic import daily_basic
from quantide.data.models.stocks import stock_list
from quantide.factors.alpha import (
    FEATURE_COLS,
    _zscore_1d,
)


def _training_feature_panel(
    feature_cols: Sequence[str] | None,
    label_cache_key: tuple[Any, ...] | None,
    hist_df: pl.DataFrame,
    horizon: int,
    train_window: int,
) -> tuple[list[str], pl.DataFrame]:
    """Training feature panel."""
    selected_features = tuple(feature_cols or FEATURE_COLS)
    z_cols = [f"{c}_z" for c in selected_features]

    # A cache key is optional because callers without a stable panel identity
    # must not cache by ``id(hist_df)``: once that frame is released, Python can
    # reuse its id for a different panel.  Labels do not depend on the selected
    # features, so feature_cols intentionally stays out of this key.  The
    # current normalized feature columns are joined below on every invocation.
    label_key = None
    if label_cache_key is not None:
        history_key = (
            hist_df.height,
            hist_df["date"].min(),
            hist_df["date"].max(),
            hist_df["asset"].n_unique(),
        )
        label_key = (
            tuple(label_cache_key),
            history_key,
            int(horizon),
        )

    labels = _LABEL_CACHE.get(label_key) if label_key is not None else None
    labels = _training_return_labels(hist_df, horizon, label_key, labels)

    # Labels may be reused across feature subsets, but the normalized inputs
    # must always come from the caller's historical frame.  This keeps feature
    # selection correct and limits the cached object to the small label table.
    labeled = hist_df.select(["date", "asset", *z_cols]).join(
        labels, on=["date", "asset"], how="inner"
    )
    valid_train = labeled.filter(
        pl.col("future_n_trading_day_close_return").is_not_null()
        & pl.col("future_n_trading_day_close_return").is_finite()
    )
    if valid_train.is_empty():
        raise RuntimeError("训练样本不足：没有可用的未来收盘收益标签")

    train_dates = valid_train["date"].unique().sort().tail(max(5, train_window))
    valid_train = valid_train.filter(pl.col("date").is_in(train_dates.to_list()))
    if valid_train.is_empty():
        raise RuntimeError("训练样本不足：训练窗口内没有可用的标签")

    n_assets = valid_train["asset"].n_unique()
    if n_assets > 1:
        valid_train = valid_train.with_columns(
            (
                pl.col("future_n_trading_day_close_return").rank().over("date")
                / pl.len().over("date").clip(lower_bound=1)
                - 0.5
            ).alias("label_y")
        )
    else:
        valid_train = valid_train.with_columns(
            (pl.col("future_n_trading_day_close_return").clip(-0.2, 0.2) * 2.5).alias("label_y")
        )
    return z_cols, valid_train


def _append_ranked_candidates(
    ranked: pl.DataFrame,
    results: list[dict[str, Any]],
    date_str: str,
    model_engine: str,
) -> None:
    """Append ranked candidates."""
    for idx, row in enumerate(ranked.iter_rows(named=True), start=1):
        asset = str(row["asset"])
        close_val = float(row.get("close") or 0.0)
        ma_bounce = float(row.get("ma20_support_bounce") or 0.0)
        ma_align = float(row.get("ma_alignment") or 0.0)
        ma20_slp = float(row.get("ma20_slope") or 0.0)
        ma_support_val = round(ma_bounce + 0.5 * ma_align + 5.0 * max(ma20_slp, 0.0), 4)
        results.append(
            {
                "rank": idx,
                "asset": asset,
                "name": _resolve_stock_name(asset),
                "board": str(row.get("board") or "其他"),
                "close": round(close_val, 4),
                "ret_1d": round(float(row.get("ret_1d") or 0.0), 4),
                "ret_5d": round(float(row.get("ret_5d") or 0.0), 4),
                "ret_20d": round(float(row.get("ret_20d") or 0.0), 4),
                "ml_score": round(float(row.get("ml_score") or 0.0), 4),
                "rs_board_20d": round(float(row.get("rs_board_20d") or 0.0), 4),
                "ma_support": ma_support_val,
                "kline_pattern": _describe_kline_pattern(row),
                "signal_reason": _describe_signal_reason(row),
                "as_of_date": date_str,
                "model_engine": model_engine,
            }
        )


def _append_price_action_reasons(row: Mapping[str, Any], rs20: float, parts: list[str]) -> None:
    """Append momentum, resilience and candle signals to a stock explanation."""
    rs5 = float(row.get("rs_board_5d") or 0.0)
    if abs(rs20) >= abs(rs5) or rs20 > 0:
        parts.append(f"板块超额{rs20 * 100:+.1f}%")
    else:
        parts.append(f"5日超额{rs5 * 100:+.1f}%")

    ma20_bounce = float(row.get("ma20_support_bounce") or 0.0)
    ma20_slope = float(row.get("ma20_slope") or 0.0)
    ma_align = float(row.get("ma_alignment") or 0.0)
    sharpe_mom = float(row.get("sharpe_mom_20d") or 0.0)
    _describe_moving_average_signal(ma20_bounce, ma20_slope, ma_align, parts, sharpe_mom)

    clv_flow = float(row.get("clv_money_flow") or 0.0)
    intra_vs_over = float(row.get("intraday_vs_overnight_5d") or 0.0)
    resilience = float(row.get("downside_resilience") or 0.0)
    if clv_flow > 0.0:
        parts.append("日内资金净流入")
    elif intra_vs_over > 0.0:
        parts.append("盘中主力承接")
    elif resilience > 0.0:
        parts.append("逆市抗跌韧性")
    else:
        parts.append("短线反转修复")


try:
    import lightgbm as lgb

    _HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover
    lgb = None  # type: ignore[assignment]
    _HAS_LIGHTGBM = False


#: 流水线版本（策略源码哈希）：策略逻辑变化时归因缓存自动失效
def _pipeline_version(source_file: str | Path | None = None) -> str:
    """Invalidate model artifacts when any implementation component changes."""
    digest = hashlib.sha256()
    source = (
        Path(source_file) if source_file else Path(__file__).with_name("ml_momentum_reversal.py")
    )
    digest.update(source.read_bytes())
    for name in ("_ml_support.py", "_ml_explanation.py"):
        digest.update(Path(__file__).with_name(name).read_bytes())
    return digest.hexdigest()[:12]


PIPELINE_VERSION: str = _pipeline_version()


def _ranked_prediction_result(
    cross_df: pl.DataFrame,
    model: object | None,
    engine: str,
    feature_cols: Sequence[str] | None,
    target_date: datetime.date,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, int]]:
    """Score a cross-section and expose candidates, prices and complete ranks."""
    scores = _score_cross_section(cross_df, model, engine, feature_cols)
    scored_df = cross_df.with_columns(pl.Series("ml_score", scores)).sort(
        ["ml_score", "asset"], descending=[True, False]
    )
    price_map = {
        str(r["asset"]): float(r["close"])
        for r in scored_df.select(["asset", "close"]).iter_rows(named=True)
    }
    full_ranks = {str(a): i for i, a in enumerate(scored_df["asset"].to_list(), start=1)}
    ranked = _format_candidate_rows(
        scored_df,
        target_date,
        engine,
        top_k,
    )
    return ranked, price_map, full_ranks


def _training_return_labels(
    hist_df: pl.DataFrame,
    horizon: int,
    label_key: tuple[Any, ...] | None,
    labels: pl.DataFrame | None,
) -> pl.DataFrame:
    """Training return labels."""
    if labels is None:
        labels = compute_future_close_return_labels(
            hist_df.select(["date", "asset", "close"]), horizon=horizon
        ).select(["date", "asset", "future_n_trading_day_close_return"])
        if label_key is not None:
            if len(_LABEL_CACHE) >= _LABEL_CACHE_MAX:
                _LABEL_CACHE.pop(next(iter(_LABEL_CACHE)))
            _LABEL_CACHE[label_key] = labels
    return labels


def _describe_moving_average_signal(
    ma20_bounce: float,
    ma20_slope: float,
    ma_align: float,
    parts: list[str],
    sharpe_mom: float,
) -> None:
    """Describe moving average signal."""
    if ma20_bounce > 0.5:
        parts.append("MA20回踩支撑")
    elif ma20_slope > 0.0:
        parts.append(f"MA20斜率向上({ma20_slope * 100:+.1f}%)")
    elif ma_align >= 0.66:
        parts.append("均线多头排列")
    else:
        parts.append(f"夏普动量{sharpe_mom:+.2f}")


def _resolve_explanation_training_windows(
    bt_end: datetime.date | None,
    bt_start: datetime.date | None,
    build_signal: datetime.date | None,
    refit_build: datetime.date | None,
    refit_signal: datetime.date | None,
    self: MLExplanation,
    signal_date: datetime.date,
) -> tuple[datetime.date | None, datetime.date | None, datetime.date | None]:
    """Resolve explanation training windows."""
    if bt_start is not None and bt_end is not None:
        try:
            build_signal, refit_build, refit_signal = self._replay_context(
                signal_date, bt_start, bt_end
            )
        except Exception:
            build_signal = refit_build = refit_signal = None
    return build_signal, refit_build, refit_signal


def _retrain_replay_model(
    hist_slice: pl.DataFrame,
    is_live: bool,
    self: MLMomentumReversalStrategy,
    signal_date: datetime.date,
) -> None:
    """Retrain replay model."""
    if not is_live and self._should_retrain(signal_date):
        training_df = self._training_slice(hist_slice, signal_date)
        self._model, self._model_engine = _fit_ml_model(
            training_df,
            train_window=self.train_window,
            horizon=self.future_return_horizon,
            use_lightgbm=self.use_lightgbm,
            feature_cols=self.selected_features or FEATURE_COLS,
            label_cache_key=self._panel_cache_key(signal_date),
        )
        self._save_model_artifact(
            self._model,
            self._model_engine,
            training_df,
            effective_from=signal_date,
        )
        self._mark_retrained()


def _bars_fingerprint() -> tuple[object, ...]:
    """行情数据的轻量指纹（数据更新后使面板缓存失效）。"""
    try:
        return (
            daily_bars.end,
            daily_bars.total_dates,
            daily_bars.last_update_time,
        )
    except Exception:  # pragma: no cover - 数据层未就绪
        return ()


#: 因子面板缓存（键：选池规格 + 因子集 + 信号日 + 持仓 + 数据指纹）。
#: 只保留最近 2 个面板：单个面板约 2000 只 × 80 天 × 45 列 ≈ 55MB，
#: 上限 2 份把常驻内存压在 ~110MB。命中场景：同一进程内重复回测、
#: 以及归因回放反复请求同一面板。
_PANEL_CACHE: dict[tuple[Any, ...], pl.DataFrame] = {}
_PANEL_CACHE_MAX = 2

#: 未来收盘收益标签缓存（键：面板键 + 训练历史范围 + 标签前瞻期）。
#: 缓存 date、asset 和收益标签三列，训练特征从当前面板拼回。
#: 避免为每个因子集在缓存中保留一份大面板。
_LABEL_CACHE: dict[tuple[Any, ...], pl.DataFrame] = {}
_LABEL_CACHE_MAX = 6

#: 归因用的模型缓存（按训练参数 + 因子集 + 截面日 + 持仓键控）
_EXPLAIN_MODEL_CACHE: dict[tuple[Any, ...], tuple[object, str]] = {}

#: 归因用的截面缓存（只保留当前这一条：约 2000 行、1MB）
_EXPLAIN_CROSS_SECTION_CACHE: dict[tuple[Any, ...], pl.DataFrame] = {}


def _parse_custom_assets(config: dict[str, Any]) -> list[str] | None:
    """Extract custom asset list from strategy config if specified."""
    raw = config.get("symbols") or config.get("universe") or config.get("symbol")
    if raw is None:
        return None
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",") if s.strip()]
        return items or None
    if isinstance(raw, (list, tuple, set)):
        items = [str(s).strip() for s in raw if str(s).strip()]
        return items or None
    return None


def _coerce_date(
    dt: datetime.date | datetime.datetime | str | None,
) -> datetime.date | None:
    """Convert date/datetime/ISO-string into ``datetime.date``."""
    if dt is None:
        return None
    if isinstance(dt, datetime.datetime):
        return dt.date()
    if isinstance(dt, datetime.date):
        return dt
    if isinstance(dt, str):
        s = dt.strip()
        if not s:
            return None
        return datetime.date.fromisoformat(s[:10])
    return None


def _future_return_horizon(config: dict[str, Any], default: int = 3) -> int:
    """Resolve the model label horizon without treating it as an exit rule."""
    raw = config.get("future_return_horizon")
    if raw is None:
        raw = config.get("horizon", default)
    return max(1, int(raw))


def _ensure_data_connected() -> bool:
    """Connect local daily_bars/calendar/stock_list if not yet initialized."""
    if getattr(daily_bars, "_initialized", False):
        return True
    default_home = Path(get_data_home())
    cal_path = default_home / "data" / "calendar.parquet"
    bars_path = default_home / "data" / "bars" / "daily"
    stocks_path = default_home / "data" / "stock_list.parquet"
    basic_path = default_home / "data" / "daily_basic.parquet"
    if not cal_path.exists() or not bars_path.exists():
        return False
    try:
        calendar.load(cal_path)
        if stocks_path.exists():
            stock_list.load(stocks_path)
        daily_bars.connect(bars_path, cal_path)
        if basic_path.exists():
            daily_basic.load(basic_path)
        return True
    except Exception:
        return False


def _resolve_stock_name(asset: str) -> str:
    """Resolve human-readable stock name with fallback to asset code."""
    try:
        if stock_list.size > 0:
            name = stock_list.get_name(asset)
            if name:
                return str(name)
    except Exception:
        pass
    return asset


def compute_future_close_return_labels(df: pl.DataFrame, horizon: int = 3) -> pl.DataFrame:
    """Attach a supervised future close-return target to a daily-bar panel.

    ``horizon`` counts rows within each asset's sorted daily-bar history, so it
    represents trading days rather than calendar days.  The target is used only
    when fitting the model; it is never consulted by the daily exit policy.
    Rows without a complete forward window remain null.  Callers must pass a
    history frame cut off at the signal date when training, which leaves the
    signal-day target null and prevents lookahead at decision time.
    """
    horizon = max(1, int(horizon))
    if df.is_empty():
        return df.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("future_n_trading_day_close_return")
        )

    ordered = df.sort(["asset", "date"])
    close = pl.col("close").cast(pl.Float64)
    future_close = close.shift(-horizon).over("asset")
    return ordered.with_columns(
        pl.when(future_close.is_not_null() & (close != 0.0))
        .then(future_close / close - 1.0)
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("future_n_trading_day_close_return")
    )


def _fit_ml_model(
    hist_df: pl.DataFrame,
    train_window: int = 45,
    horizon: int = 3,
    use_lightgbm: bool = True,
    feature_cols: list[str] | None = None,
    label_cache_key: tuple[Any, ...] | None = None,
) -> tuple[object | None, str]:
    """Train the ranking model strictly on leak-free historical samples.

    The target is the future ``horizon``-trading-day close return computed from
    ``hist_df``. The caller MUST still filter the training frame strictly before
    the signal date; this function does not define or implement an exit rule.

    Args:
        hist_df: 截至信号日的标准化特征面板。
        train_window: 训练窗口（交易日）。
        horizon: future close-return label's forward trading-day count.
        use_lightgbm: True 用 LightGBM，False 用岭回归。
        feature_cols: 参与训练的因子；为空表示全部因子。
        label_cache_key: 稳定的面板内容键；相同训练历史的标签可跨训练复用。

    Returns:
        tuple: (模型, 引擎名)。
    """
    z_cols, valid_train = _training_feature_panel(
        feature_cols, label_cache_key, hist_df, horizon, train_window
    )

    x_train = valid_train.select(z_cols).fill_null(0.0).fill_nan(0.0).to_numpy().astype(np.float64)
    y_train = valid_train["label_y"].fill_null(0.0).fill_nan(0.0).to_numpy().astype(np.float64)

    if use_lightgbm and _HAS_LIGHTGBM and len(x_train) >= 30:
        min_child = max(5, min(20, len(x_train) // 10))
        model = lgb.LGBMRegressor(
            n_estimators=50,
            max_depth=4,
            num_leaves=15,
            learning_rate=0.05,
            min_child_samples=min_child,
            subsample_for_bin=5000,
            random_state=42,
            verbosity=-1,
            n_jobs=1,
        )
        model.fit(x_train, y_train)
        return model, "LightGBM"

    if len(x_train) >= 8:
        n_feat = x_train.shape[1]
        reg = 10.0 * np.eye(n_feat, dtype=np.float64)
        ridge_w = np.linalg.solve(x_train.T @ x_train + reg, x_train.T @ y_train)
        return ridge_w, "Prior-Ridge"

    return None, "Prior-Ridge"


def _score_cross_section(
    pred_df: pl.DataFrame,
    model: object | None,
    model_engine: str,
    feature_cols: Sequence[str] | None = None,
) -> np.ndarray:
    """预测目标日截面的模型得分（截面 z-score，不含任何手工先验）。"""
    cols = feature_cols or FEATURE_COLS
    if pred_df.is_empty():
        return np.array([], dtype=np.float64)

    z_cols = [f"{c}_z" for c in cols]
    x_pred = pred_df.select(z_cols).fill_null(0.0).fill_nan(0.0).to_numpy().astype(np.float64)

    if model is None:
        raise RuntimeError("模型不可用，无法计算截面得分")

    predict = getattr(model, "predict", None)
    if model_engine == "LightGBM" and callable(predict):
        raw_pred = np.asarray(predict(x_pred), dtype=np.float64)
        return _zscore_1d(raw_pred) if len(x_pred) > 1 else raw_pred

    if isinstance(model, np.ndarray):
        ridge_pred = x_pred @ model
        return _zscore_1d(ridge_pred) if len(x_pred) > 1 else ridge_pred

    raise RuntimeError(f"未知的模型引擎: {model_engine}")


def _signal_value(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    return float(row.get(key) or default)


def _reversal_pattern(row: Mapping[str, Any]) -> str | None:
    if _signal_value(row, "low_open_bull") > 0.0004 or (
        _signal_value(row, "overnight_gap") < -0.004 and _signal_value(row, "intraday_ret") > 0.012
    ):
        return "低开阳线弱转强"
    if _signal_value(row, "ma20_support_bounce") > 0.5:
        return "均线回踩支撑"
    if _signal_value(row, "lower_shadow") >= 0.42 and _signal_value(row, "intraday_ret") >= -0.005:
        return "长下影探底"
    return None


def _trend_pattern(row: Mapping[str, Any]) -> str | None:
    if _signal_value(row, "ret_1d") >= 0.035 and _signal_value(row, "vol_ratio_5_20", 1.0) >= 1.15:
        return "放量突破动量"
    if (
        _signal_value(row, "intraday_vs_overnight_5d") > 0.025
        and _signal_value(row, "clv_money_flow") > 0.15
    ):
        return "日内主力推升"
    if _signal_value(row, "rev_5d_shrink_vol") > 0.015 and _signal_value(row, "intraday_ret") > 0:
        return "缩量回调企稳"
    if _signal_value(row, "ma_alignment") >= 0.66 and _signal_value(row, "ma20_slope") > 0:
        return "多头趋势稳健"
    return None


def _describe_kline_pattern(row: dict[str, Any]) -> str:
    """Describe reversal signals first, then momentum and trend signals."""
    return _reversal_pattern(row) or _trend_pattern(row) or "量价共振向上"


def _describe_signal_reason(row: dict[str, Any]) -> str:
    """Build a concise 3-part explanation string for the selected stock."""
    parts: list[str] = []

    rs20 = float(row.get("rs_board_20d") or 0.0)
    _append_price_action_reasons(row, rs20, parts)

    return " | ".join(parts)


def _format_candidate_rows(
    scored_df: pl.DataFrame,
    target_date: datetime.date,
    model_engine: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Format top-N scored rows into UI & strategy selection dicts."""
    if scored_df.is_empty():
        return []

    # Eligibility is applied before ranking and ``limit`` is only an upper
    # bound.  An all-ineligible cross-section must not be repopulated with
    # locked-at-limit names just to fill top_k.
    eligibility = pl.lit(True)
    if "volume" in scored_df.columns:
        eligibility = eligibility & (pl.col("volume").fill_null(0) > 0)
    if "is_st" in scored_df.columns:
        eligibility = eligibility & ~pl.col("is_st").fill_null(False)
    if "up_limit" in scored_df.columns:
        eligibility = eligibility & ~(
            (pl.col("up_limit") > 0) & (pl.col("close") >= pl.col("up_limit") * 0.999)
        )
    tradable = scored_df.filter(eligibility)

    ranked = tradable.sort(["ml_score", "asset"], descending=[True, False]).head(limit)
    date_str = target_date.isoformat()

    results: list[dict[str, Any]] = []
    _append_ranked_candidates(ranked, results, date_str, model_engine)
    return results


def _stable_universe_rank(asset: str, mode: str) -> str:
    """返回资产的稳定随机序（与调仓日无关，仅依赖代码与模式）。

    Args:
        asset: 证券代码。
        mode: 选池模式。

    Returns:
        str: 十六进制哈希串，可直接用于排序。
    """
    digest = hashlib.blake2b(f"{mode}:{asset}".encode(), digest_size=8).hexdigest()
    return digest


_INDEX_POOL_CACHE: dict[tuple[tuple[str, ...], datetime.date], set[str]] = {}


def _index_pit_universe(
    target_date: datetime.date,
    codes: list[str] | None,
) -> set[str]:
    """读取指数成分 PIT 快照（按代码+日期缓存）。"""
    codes = [str(c).strip() for c in (codes or []) if str(c).strip()]
    if not codes:
        codes = ["000300.SH", "000905.SH", "000852.SH"]
    key = (tuple(codes), target_date)
    cached = _INDEX_POOL_CACHE.get(key)
    if cached is not None:
        return cached
    pool: set[str] = set()
    try:
        from quantide.data import get_index_weight_store

        store = get_index_weight_store()
        for code in codes:
            try:
                frame = store.constituents(code, target_date, include_weight=False)
            except Exception:
                continue
            if frame is not None and not frame.is_empty() and "con_code" in frame.columns:
                pool.update(frame["con_code"].to_list())
    except Exception:
        pool = set()
    if len(_INDEX_POOL_CACHE) >= 256:
        _INDEX_POOL_CACHE.clear()
    _INDEX_POOL_CACHE[key] = pool
    return pool


def _cap_universe(
    cap: pl.DataFrame,
    universe_size: int,
    holdings: list[str] | None,
    mode: str,
) -> list[str]:
    """按稳定哈希把可选池精确裁剪到 universe_size（持仓优先保留）。"""
    assets = sorted(cap["asset"].unique().to_list())
    if universe_size > 0 and len(assets) > universe_size:
        held = [a for a in (holdings or []) if a in set(assets)]
        ranked = sorted(
            [a for a in assets if a not in set(held)],
            key=lambda asset: _stable_universe_rank(asset, mode),
        )
        picked = held + ranked[: max(0, universe_size - len(held))]
        cap = cap.filter(pl.col("asset").is_in(picked))
    return sorted(cap["asset"].unique().to_list())


def _filter_universe(
    bars_df: pl.DataFrame,
    target_date: datetime.date,
    universe_size: int,
    mode: str = "market_cap_trim",
    trim_pct: float = 0.05,
    holdings: list[str] | None = None,
    index_codes: list[str] | None = None,
) -> list[str]:
    """Select a tradable point-in-time pool, retaining eligible held securities."""
    on_date = bars_df.filter(pl.col("date") == target_date)
    if on_date.is_empty():
        return []
    if mode == "index_pit":
        pool = _index_pit_universe(target_date, index_codes)
        if pool:
            cap = _eligible_universe(on_date.filter(pl.col("asset").is_in(pool)), False)
            return _cap_universe(cap, universe_size, holdings, mode)
        mode = "market_cap_trim"
    if mode == "market_cap_trim" and "total_mv" in on_date.columns:
        trimmed_cap = _trim_market_cap(on_date, trim_pct)
        if trimmed_cap is not None:
            return _cap_universe(trimmed_cap, universe_size, holdings, mode)
    eligible = _eligible_universe(on_date, True)
    if eligible.is_empty():
        return []
    return _liquidity_universe(bars_df, eligible, universe_size)


def _filter_liquid_universe(
    bars_df: pl.DataFrame,
    target_date: datetime.date,
    universe_size: int,
) -> list[str]:
    """Backward-compatible liquidity-only universe filter."""
    return _filter_universe(bars_df, target_date, universe_size, mode="liquidity")


def _drop_st_names(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty() or stock_list.size == 0:
        return frame
    if "name" not in stock_list.data.columns:
        return frame
    try:
        st_names = set(
            stock_list.data.filter(
                pl.col("name").str.to_uppercase().str.contains("ST")
                | pl.col("name").str.contains("退")
            )["asset"].to_list()
        )
        if st_names:
            return frame.filter(~pl.col("asset").is_in(st_names))
    except Exception:
        pass
    return frame


def _liquidity_universe(
    bars_df: pl.DataFrame, eligible: pl.DataFrame, universe_size: int
) -> list[str]:
    """Rank eligible securities by their trailing mean traded amount."""
    cols = set(bars_df.columns)
    assets = eligible["asset"].unique().to_list()
    if universe_size <= 0 or len(assets) <= universe_size:
        return sorted(assets)

    recent_dates = bars_df["date"].unique().sort().tail(20).to_list()
    amt_expr = pl.col("amount") if "amount" in cols else (pl.col("volume") * pl.col("close"))
    top_liquid = (
        bars_df.filter(pl.col("date").is_in(recent_dates) & pl.col("asset").is_in(assets))
        .group_by("asset")
        .agg(amt_expr.mean().alias("avg_amt"))
        .sort(["avg_amt", "asset"], descending=[True, False])
        .head(universe_size)
    )
    return top_liquid["asset"].to_list()


def _eligible_universe(frame: pl.DataFrame, require_close: bool) -> pl.DataFrame:
    """Exclude suspended and ST securities after a pool's size filter."""
    condition = pl.col("volume") > 0
    if require_close:
        condition = condition & (pl.col("close") > 0)
    if "is_st" in frame.columns:
        condition = condition & ~pl.col("is_st").fill_null(False)
    return _drop_st_names(frame.filter(condition))


def _trim_market_cap(on_date: pl.DataFrame, trim_pct: float) -> pl.DataFrame | None:
    """Trim an exact number from both cap tails before tradability filtering."""
    cap = on_date.filter(
        (pl.col("close") > 0) & pl.col("total_mv").is_not_null() & (pl.col("total_mv") > 0)
    )
    if cap.is_empty():
        return None
    cap = cap.sort(["total_mv", "asset"])
    n_trim = int(cap.height * trim_pct)
    if n_trim > 0:
        cap = cap.slice(n_trim, max(0, cap.height - 2 * n_trim))
    return _eligible_universe(cap, False)
