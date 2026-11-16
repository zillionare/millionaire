"""A-share ML momentum/reversal example strategy."""

from __future__ import annotations

import datetime
import hashlib
import pickle
from typing import Any, cast

import polars as pl

from quantide.core.enums import FrameType
from quantide.core.ports.broker import StrategyBroker
from quantide.core.strategy import BaseStrategy
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.daily_basic import daily_basic
from quantide.data.models.stocks import stock_list
from quantide.factors.alpha import (
    FACTOR_VERSION,
    FEATURE_COLS,
    compute_alpha_features,
    standardize_features,
)
from quantide.factors.catalog import resolve_feature_selection
from quantide.service.model_store import ModelArtifact, model_key, model_store
from quantide.strategies.example._ml_explanation import MLExplanation
from quantide.strategies.example._ml_rebalance import MLRebalance
from quantide.strategies.example._ml_selection import SelectionOptions
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
from quantide.strategies.example._ml_support import _pipeline_version
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


def _cache_backtest_feature_panel(
    self: MLMomentumReversalStrategy,
    raw_panel: pl.DataFrame,
    signal_date: datetime.date,
    fetch_end: datetime.date,
    panel_key: tuple[Any, ...],
) -> None:
    """Compute and cache the normalized feature panel for the backtest window."""
    stock_meta = stock_list.data if stock_list.size > 0 else None
    feat_panel = compute_alpha_features(raw_panel, stock_meta=stock_meta)
    self._cached_norm_panel = standardize_features(
        feat_panel, self.selected_features or FEATURE_COLS
    )
    self._panel_start = signal_date
    self._panel_end = fetch_end
    is_live = getattr(self.broker, "_bt_start", None) is None
    if not is_live:
        if len(_PANEL_CACHE) >= _PANEL_CACHE_MAX:
            _PANEL_CACHE.pop(next(iter(_PANEL_CACHE)))
        _PANEL_CACHE[panel_key] = self._cached_norm_panel


PIPELINE_VERSION = _pipeline_version(__file__)


class MLMomentumReversalStrategy(MLRebalance, MLExplanation, BaseStrategy):
    """A股动量与趋势反转机器学习选股策略 (LightGBM 截面排序)"""

    _pipeline_version = PIPELINE_VERSION
    VERSION = "v1.0.0"
    BAR_INTERVAL = "1d"
    #: 声明本策略支持逐次预测归因（web 层据此动态加载 SHAP 面板）
    ATTRIBUTION = "shap"
    #: 声明回测向导应展示“选择因子”步骤。
    SUPPORTS_FEATURE_SELECTION = True
    PARAMS: dict[str, Any] = {
        "top_k": 5,
        "universe_size": 2000,
        "universe_mode": "market_cap_trim",
        "market_cap_trim_pct": 0.05,
        "universe_rebalance_days": 20,
        "train_window": 45,
        "future_return_horizon": 3,
        "retrain_days": 5,
        "slippage_pct": 0.001,
        "use_lightgbm": True,
        "bar_interval": "1d",
        "fill_timing": "auction_close",
        "auction_epsilon": 0.001,
        "index_pool_codes": ["000300.SH", "000905.SH", "000852.SH"],
    }
    params = PARAMS

    @staticmethod
    def default_config() -> dict[str, Any]:
        """Return default strategy parameters."""
        return dict(MLMomentumReversalStrategy.PARAMS)

    def __init__(self, broker: StrategyBroker, config: dict[str, Any] | None = None) -> None:
        merged = {**self.default_config(), **(config or {})}
        if config and "future_return_horizon" not in config and "horizon" in config:
            merged["future_return_horizon"] = config["horizon"]
        super().__init__(broker, merged)
        self.top_k = max(1, int(self.config.get("top_k", 5)))
        self.universe_size = max(self.top_k, int(self.config.get("universe_size", 2000)))
        self.universe_mode = str(self.config.get("universe_mode", "market_cap_trim")).strip()
        self.index_pool_codes = list(
            self.config.get("index_pool_codes") or ["000300.SH", "000905.SH", "000852.SH"]
        )
        self.live_min_quote_coverage = float(self.config.get("live_min_quote_coverage", 0.90))
        self.market_cap_trim_pct = min(
            0.5,
            max(0.0, float(self.config.get("market_cap_trim_pct", 0.05))),
        )
        self.universe_rebalance_days = max(1, int(self.config.get("universe_rebalance_days", 20)))
        self.train_window = max(10, int(self.config.get("train_window", 45)))
        self.future_return_horizon = _future_return_horizon(config or self.config)
        self.retrain_days = max(1, int(self.config.get("retrain_days", 5)))
        self.use_lightgbm = bool(self.config.get("use_lightgbm", True))
        self.selected_features: list[str] = resolve_feature_selection(self.config.get("features"))
        self.custom_assets = _parse_custom_assets(self.config)
        #: dry-run 影子模式：只加载模型，不训练
        self._shadow_mode = bool(self.config.get("_shadow_mode", False))

        self._model: object | None = None
        self._model_engine: str = "LightGBM" if self.use_lightgbm else "Prior-Ridge"
        #: 模型持久化键（策略名 + 模型相关配置哈希），回测/仿真/实盘共用
        self._model_key = model_key(self.__class__.__name__, self.config)
        self._model_train_end: datetime.date | None = None
        self._model_effective_from: datetime.date | None = None
        self._model_pending: bool = False
        self._model_due_logged: datetime.date | None = None
        #: 归因用：回测期间的每日持仓快照（日期 → 资产 → 股数）
        self._positions_by_date: dict[datetime.date, dict[str, float]] = {}
        #: 重训计数按「交易日」推进（实盘每 2 秒一次 on_bar 不应算作一天）
        self._days_since_train: int = 0
        self._last_train_day: datetime.date | None = None
        #: 已执行决策的信号日（实盘按日去重，避免重复下单）
        self._last_executed_signal_date: datetime.date | None = None
        #: 实盘行情缺失标志（置 True 时本次 on_bar 不交易，下次重试）
        self._data_missing: bool = False
        self._last_data_missing_log: datetime.date | None = None
        self._cached_norm_panel: pl.DataFrame | None = None
        self._panel_start: datetime.date | None = None
        self._panel_end: datetime.date | None = None

    async def init(self) -> None:
        """Initialize strategy state and log configuration."""
        self.log(
            f"MLMomentumReversalStrategy Initialized: top_k={self.top_k}, "
            f"universe_size={self.universe_size}, "
            f"universe_mode={self.universe_mode}, "
            f"market_cap_trim_pct={self.market_cap_trim_pct}, "
            f"train_window={self.train_window}, "
            f"future_return_horizon={self.future_return_horizon}, "
            f"use_lightgbm={self.use_lightgbm}, "
        )
        if self._is_live_mode():
            try:
                if self._shadow_mode:
                    self._load_model_from_store(datetime.date.today())
                else:
                    self._ensure_live_model(datetime.date.today())
            except Exception as exc:  # pragma: no cover - 数据未就绪时保持 pending
                self._model_pending = True
                self.log(f"模型加载/初始化失败，等待后台重训: {exc}", level="WARNING")

    def _is_live_mode(self) -> bool:
        return getattr(self.broker, "_bt_start", None) is None

    def _load_model_from_store(self, day: datetime.date | None = None) -> bool:
        """加载最新模型；只接受 effective_from <= day 的版本。"""
        model, meta = model_store.load(self._model_key)
        if model is None or meta is None:
            self._model_pending = True
            return False
        try:
            effective = datetime.date.fromisoformat(str(meta.effective_from))
        except Exception:
            self._model_pending = True
            return False
        if day is not None and effective > day:
            self._model_pending = True
            return False
        try:
            train_end = datetime.date.fromisoformat(str(meta.train_end))
        except Exception:
            self._model_pending = True
            return False
        self._model = model
        self._model_engine = meta.engine or self._model_engine
        self._model_train_end = train_end
        self._model_effective_from = effective
        self._model_pending = False
        return True

    def _model_due(self, day: datetime.date) -> bool:
        if self._model is None or self._model_train_end is None:
            return True
        try:
            elapsed = calendar.count_trading_days(self._model_train_end, day) - 1
        except Exception:
            return False
        return elapsed >= self.retrain_days

    def _save_model_artifact(
        self,
        model: object | None,
        engine: str,
        training_frame: pl.DataFrame,
        *,
        effective_from: datetime.date,
    ) -> None:
        if model is None or training_frame is None or training_frame.is_empty():
            return
        try:
            train_end = training_frame["date"].max()
            if isinstance(train_end, datetime.datetime):
                train_end = train_end.date()
            if not isinstance(train_end, datetime.date):
                return
            model_hash = hashlib.sha1(pickle.dumps(model)).hexdigest()[:16]
            meta = ModelArtifact(
                model_key=self._model_key,
                strategy_name=self.__class__.__name__,
                config_hash=self._model_key.rsplit("-", 1)[-1],
                train_end=train_end.isoformat(),
                effective_from=effective_from.isoformat(),
                engine=engine,
                feature_version=FACTOR_VERSION,
                pipeline_version=PIPELINE_VERSION,
                model_hash=model_hash,
                data_fingerprint=str(_bars_fingerprint()),
                metrics={},
                extra={
                    "retrain_days": self.retrain_days,
                    "future_return_horizon": self.future_return_horizon,
                    "train_window": self.train_window,
                },
            )
            model_store.save(key=self._model_key, model=model, metadata=meta)
            self._model_train_end = train_end
            self._model_effective_from = effective_from
        except Exception as exc:  # pragma: no cover - 持久化失败不应中断策略
            self.log(f"模型落盘失败: {exc}", level="WARNING")

    def _ensure_live_model(self, day: datetime.date) -> bool:
        """启动时加载模型；如缺失或过期，在启动阶段训练一次（不占决策窗口）。"""
        loaded = self._load_model_from_store(day)
        if loaded and not self._model_due(day):
            return True
        if not getattr(daily_bars, "_initialized", False):
            self._model_pending = True
            return False
        self._ensure_backtest_panel(day)
        panel = self._cached_norm_panel
        if panel is None or panel.is_empty():
            self._model_pending = True
            return False
        train_df = panel.filter(pl.col("date") < day)
        if train_df.is_empty():
            self._model_pending = True
            return False
        model, engine = _fit_ml_model(
            train_df,
            train_window=self.train_window,
            horizon=self.future_return_horizon,
            use_lightgbm=self.use_lightgbm,
            feature_cols=self.selected_features or FEATURE_COLS,
            label_cache_key=self._panel_cache_key(day),
        )
        if model is None:
            self._model_pending = True
            return False
        self._model = model
        self._model_engine = engine
        self._save_model_artifact(model, engine, train_df, effective_from=day)
        self._model_pending = False
        # 启动阶段构建的面板只用于训练；14:57 必须用最新 forming bar 重建。
        self._cached_norm_panel = None
        self._panel_start = None
        self._panel_end = None
        self.log(f"模型已就绪: train_end={self._model_train_end} effective={day} engine={engine}")
        return True

    def train_model_for_day(self, as_of: datetime.date) -> bool:
        """收盘后训练：使用截至 as_of 的数据，供下一交易日使用。"""
        try:
            next_day = calendar.shift(as_of, 1, FrameType.DAY)
        except Exception:
            next_day = as_of + datetime.timedelta(days=1)
        if not getattr(daily_bars, "_initialized", False):
            return False
        self._ensure_backtest_panel(next_day)
        panel = self._cached_norm_panel
        if panel is None or panel.is_empty():
            return False
        train_df = panel.filter(pl.col("date") <= as_of)
        if train_df.is_empty():
            return False
        model, engine = _fit_ml_model(
            train_df,
            train_window=self.train_window,
            horizon=self.future_return_horizon,
            use_lightgbm=self.use_lightgbm,
            feature_cols=self.selected_features or FEATURE_COLS,
            label_cache_key=self._panel_cache_key(next_day),
        )
        if model is None:
            return False
        self._model = model
        self._model_engine = engine
        self._save_model_artifact(model, engine, train_df, effective_from=next_day)
        self._cached_norm_panel = None
        self._panel_start = None
        self._panel_end = None
        self.log(f"模型已重训: train_end={as_of} effective={next_day} engine={engine}")
        return True

    @classmethod
    def select_stocks(
        cls,
        as_of_date: datetime.date | datetime.datetime | str | None = None,
        config: dict[str, Any] | None = None,
        bars_df: pl.DataFrame | None = None,
    ) -> list[dict[str, Any]]:
        """Run alpha feature engineering and LightGBM ranking for ``as_of_date``.

        Args:
            as_of_date: Target signal date (None uses latest available date).
            config: Optional parameter overrides.
            bars_df: Optional pre-loaded daily bars DataFrame for testing/caching.

        Returns:
            List of top-K ranked stock dictionaries with scores and explanations.
        """
        cfg = {**cls.default_config(), **(config or {})}
        if config and "future_return_horizon" not in config and "horizon" in config:
            cfg["future_return_horizon"] = config["horizon"]
        options = SelectionOptions.from_config(cfg, config, as_of_date)
        if bars_df is None:
            bars_df = _load_selection_bars(options)
        if bars_df.is_empty():
            return []
        panel = bars_df.with_columns(pl.col("date").cast(pl.Date))
        if options.custom_assets:
            panel = panel.filter(pl.col("asset").is_in(options.custom_assets))
        if options.as_of is not None:
            panel = panel.filter(pl.col("date") <= options.as_of)
        if panel.is_empty():
            return []
        target_date = cast(datetime.date, panel["date"].max())
        if options.custom_assets:
            candidates = sorted(panel["asset"].unique().to_list())
        else:
            panel = daily_basic.attach(panel)
            candidates = _filter_universe(
                panel,
                target_date,
                options.universe_size,
                mode=options.universe_mode,
                trim_pct=options.trim_pct,
                index_codes=cfg.get("index_pool_codes"),
            )
        if not candidates:
            return []
        return _rank_selection_panel(
            panel.filter(pl.col("asset").is_in(candidates)),
            target_date,
            options,
            cfg.get("features"),
        )

    def _resolve_signal_date(self, tm: datetime.datetime) -> datetime.date:
        """Resolve the latest completed daily bar date visible at ``tm``."""
        cur_date = tm.date()
        if tm.time() <= datetime.time(9, 30):
            if calendar.day_frames is not None:
                return calendar.day_shift(cur_date, -1)
            return cur_date - datetime.timedelta(days=1)
        return cur_date

    def _held_assets(self, as_of: datetime.date | None = None) -> list[str]:
        """返回持仓的证券代码列表。

        Args:
            as_of: 持仓快照日期；给出时优先使用 ``_positions_by_date`` 中该日期
                （含之前最近一个交易日）的持仓，用于归因时还原回测当时的选股池。

        Returns:
            list[str]: 持仓代码（已排序）。
        """
        if as_of is not None and self._positions_by_date:
            eligible = [day for day in self._positions_by_date if day <= as_of]
            if eligible:
                return sorted(self._positions_by_date[max(eligible)])
        positions = getattr(self.broker, "positions", None) or {}
        held: list[str] = []
        for asset, position in positions.items():
            shares = float(getattr(position, "shares", 0) or 0)
            if shares > 0:
                held.append(str(asset))
        return sorted(held)

    def _should_retrain(self, day_key: datetime.date) -> bool:
        """判断是否需要重训模型。

        重训节奏按**交易日**推进：只有当信号日（或最后可用 bar 日）发生变化时
        计数才 +1。回测里每个 bar 对应一个交易日（每 5 个交易日重训一次）；
        实盘里 on_bar 每 2 秒调用一次，但信号日一天只变一次，
        因此实盘同样是每 5 个交易日重训一次。

        Args:
            day_key: 当前信号日（回测路径）或最后可用 bar 日（轻量路径）。

        Returns:
            bool: 是否需要重训。
        """
        if self._last_train_day != day_key:
            self._last_train_day = day_key
            self._days_since_train += 1
        return self._model is None or self._days_since_train >= self.retrain_days

    def _in_decision_window(self, tm: datetime.datetime) -> bool:
        """实盘/模拟盘的决策窗口：交易日 14:57 之后（含盘后补算）。

        回测由 runner 决定触发时刻，不做限制。
        """
        if getattr(self.broker, "_bt_start", None) is not None:
            return True
        if str(self.config.get("fill_timing", "")).strip().lower() in {
            "next_open",
            "open",
        }:
            try:
                from quantide.service.execution_clock import execution_clock

                return execution_clock.phase(tm).name == "post_close"
            except Exception:
                return tm.time() >= datetime.time(15, 0)
        try:
            from quantide.service.execution_clock import execution_clock

            phase = execution_clock.phase(tm)
        except Exception:
            return True
        # 只允许在集合竞价窗口内“启动”新决策；14:57 已开始的计算可以
        # 自然跑过 15:00，但收盘后重启/新进入的 on_bar 不再补交易。
        return phase.name == "auction"

    def _mark_retrained(self) -> None:
        """记录一次重训完成，重置交易日计数。"""
        self._days_since_train = 0

    def _panel_cache_key(self, signal_date: datetime.date) -> tuple[Any, ...]:
        """因子面板的缓存键（必须覆盖所有影响面板内容的要素）。"""
        bt_end = getattr(self.broker, "_bt_end", None)
        is_live = getattr(self.broker, "_bt_start", None) is None
        return (
            signal_date,
            self.train_window,
            self.universe_rebalance_days,
            _coerce_date(bt_end),
            self.universe_size,
            self.universe_mode,
            tuple(self.index_pool_codes),
            round(self.market_cap_trim_pct, 6),
            tuple(self.selected_features or FEATURE_COLS),
            tuple(self._held_assets(signal_date)),
            self.custom_assets,
            _bars_fingerprint(),
            "live" if is_live else "backtest",
        )

    def _panel_end_for(self, signal_date: datetime.date) -> datetime.date:
        """面板窗口结束信号日。"""
        bt_end_attr = getattr(self.broker, "_bt_end", None)
        bt_end_date = _coerce_date(bt_end_attr) or signal_date
        rebalance_end = calendar.shift(signal_date, self.universe_rebalance_days, FrameType.DAY)
        return max(signal_date, min(rebalance_end, bt_end_date))

    def _load_bars(
        self,
        start: datetime.date,
        end: datetime.date,
        assets: list[str] | None = None,
        *,
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """通过 broker 视图取日线；回测走 HistBarView，实盘走 LiveBarView。

        选股池构建必须用已完成 bar（``include_forming_bar=False``），否则
        当日 forming 行缺少 PIT 市值，会让 market_cap_trim 退化成全市场。
        """
        broker = self.broker
        if hasattr(broker, "get_bars_range"):
            try:
                return cast(
                    pl.DataFrame,
                    broker.get_bars_range(
                        assets,
                        start,
                        end,
                        adjust=None,
                        include_forming_bar=include_forming_bar,
                    ),
                )
            except TypeError:  # 兼容未实现该参数的 broker
                return cast(pl.DataFrame, broker.get_bars_range(assets, start, end, adjust=None))
        return daily_bars.get_bars_in_range(start, end, assets=assets, adjust=None, eager_mode=True)

    def _ensure_backtest_panel(self, signal_date: datetime.date) -> None:
        """Pre-fetch and compute causal feature panel covering the backtest window.

        面板按内容键缓存（模块级），参数优化时同一选股池/因子集的面板可跨组合
        复用，避免每个组合重复抓取与计算因子。

        实盘时，LiveBarView 会把今日 forming bar 拼到面板末尾；训练/标签只用
        完成 bar（date < signal_date），forming bar 仅参与当日截面打分，避免
        用盘中价污染前瞻标签。
        """
        if (
            self._cached_norm_panel is not None
            and self._panel_start is not None
            and self._panel_end is not None
            and self._panel_start <= signal_date <= self._panel_end
        ):
            return

        panel_key = self._panel_cache_key(signal_date)
        cached_panel = _PANEL_CACHE.get(panel_key)
        if cached_panel is not None:
            self._cached_norm_panel = cached_panel
            self._panel_start = signal_date
            self._panel_end = self._panel_end_for(signal_date)
            return

        lookback = max(self.train_window + 35, 80)
        fetch_start = calendar.shift(signal_date, -lookback, FrameType.DAY)
        fetch_end = self._panel_end_for(signal_date)

        if self.custom_assets:
            universe_assets: list[str] | None = self.custom_assets
        else:
            # Select liquid universe strictly using history up to signal_date
            # 实盘：用今日 forming bar 的价格/成交量/ST 参与选池；
            # 市值用最近已结算的 PIT 值向前填充（今日市值尚未结算）。
            init_bars = self._load_bars(
                calendar.shift(signal_date, -25, FrameType.DAY),
                signal_date,
            )
            assert isinstance(init_bars, pl.DataFrame)
            if init_bars.is_empty():
                self._cached_norm_panel = pl.DataFrame()
                return
            init_bars = init_bars.with_columns(pl.col("date").cast(pl.Date))
            latest_init_dt: datetime.date = init_bars["date"].max()  # type: ignore[assignment]
            init_bars = daily_basic.attach(init_bars)
            if "total_mv" in init_bars.columns:
                fill_cols = [col for col in ("total_mv", "circ_mv") if col in init_bars.columns]
                init_bars = init_bars.sort(["asset", "date"]).with_columns(
                    [pl.col(col).forward_fill().over("asset") for col in fill_cols]
                )
            universe_assets = _filter_universe(
                init_bars,
                latest_init_dt,
                self.universe_size,
                mode=self.universe_mode,
                trim_pct=self.market_cap_trim_pct,
                holdings=self._held_assets(latest_init_dt),
                index_codes=self.index_pool_codes,
            )
            self._live_universe_assets = set(universe_assets)
            self.log(
                f"Universe selected on {latest_init_dt}: "
                f"{len(universe_assets)} assets, mode={self.universe_mode}"
            )
            if not universe_assets:
                self._cached_norm_panel = pl.DataFrame()
                return

        raw_panel = self._load_bars(fetch_start, fetch_end, assets=universe_assets)
        assert isinstance(raw_panel, pl.DataFrame)
        if raw_panel.is_empty():
            self._cached_norm_panel = pl.DataFrame()
            return

        _cache_backtest_feature_panel(self, raw_panel, signal_date, fetch_end, panel_key)

    def _training_slice(self, panel: pl.DataFrame, signal_date: datetime.date) -> pl.DataFrame:
        """训练用面板：剔除今日 forming bar，避免用盘中价污染前瞻标签。"""
        if panel.is_empty():
            return panel
        return panel.filter(pl.col("date") < signal_date)

    # ---------------- 精确归因：回放回测的选池/训练节奏 ----------------

    def _pull_factor_frames(self, tm: datetime.datetime) -> list[pl.DataFrame]:
        """Pull factor frames."""
        assets = self.custom_assets or [str(self.config.get("symbol", "000001.SZ"))]
        frames: list[pl.DataFrame] = []
        lookback = max(self.train_window + 30, 65)
        for asset in assets:
            try:
                hist = self.get_bars(asset, lookback, tm, "1d")
            except Exception:
                continue
            if isinstance(hist, pl.DataFrame) and not hist.is_empty():
                if "asset" not in hist.columns:
                    hist = hist.with_columns(pl.lit(asset).alias("asset"))
                frames.append(hist)
        return frames

    def _rank_small_universe(
        self, tm: datetime.datetime, is_live: bool
    ) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, int]]:
        """Pull and rank a small explicitly configured stock universe."""
        # 轻量路径：不走 2000 只成分股的面板，直接按需拉取少量标的的日线，
        # 现场算因子并打分。适用两种情形：
        #   1) 全局行情数据层未就绪（单测 / 独立脚本 / 数据未连接），
        #      此时只能通过 get_bars 取数；
        #   2) 配置显式指定了 <=10 只标的（symbols / universe / symbol），
        #      拉少量标的比构建整面板更省。
        # 注意：本路径与回测路径必须保持同样的重训节奏（按交易日），
        # 否则实盘行为与回测不一致。
        frames = self._pull_factor_frames(tm)
        if not frames:
            return [], {}, {}

        panel = pl.concat(frames, how="diagonal_relaxed").with_columns(pl.col("date").cast(pl.Date))
        if panel.height < 5:
            return [], {}, {}

        feature_cols = self.selected_features or FEATURE_COLS
        feat_df = compute_alpha_features(panel)
        norm_df = standardize_features(feat_df, feature_cols)
        target_date: datetime.date = norm_df["date"].max()  # type: ignore[assignment]
        if is_live and self._model is None:
            self._load_model_from_store(target_date)
            if self._model is None:
                self._model_pending = True
                if self._model_due_logged != target_date:
                    self._model_due_logged = target_date
                    self.log(
                        "模型未就绪，等待后台重训；本次不交易",
                        level="WARNING",
                    )
                return [], {}, {}
        if not is_live and self._should_retrain(target_date):
            train_df = norm_df.filter(pl.col("date") < target_date)
            self._model, self._model_engine = _fit_ml_model(
                train_df,
                train_window=self.train_window,
                horizon=self.future_return_horizon,
                use_lightgbm=self.use_lightgbm,
                feature_cols=feature_cols,
            )
            self._save_model_artifact(
                self._model,
                self._model_engine,
                train_df,
                effective_from=target_date,
            )
        model, engine = self._model, self._model_engine
        if model is None:
            return [], {}, {}
        cross_df = norm_df.filter(pl.col("date") == target_date)
        return _ranked_prediction_result(
            cross_df, model, engine, feature_cols, target_date, self.top_k
        )

    def _refresh_live_rank_model(self, signal_date: datetime.date) -> bool:
        """Refresh the persisted model without retraining in a live decision callback."""
        # 后台任务可能已写入新模型；决策前重新解析一次最新 artifact。
        self._load_model_from_store(signal_date)
        if self._model is None:
            self._model_pending = True
            if self._model_due_logged != signal_date:
                self._model_due_logged = signal_date
                self.log(
                    "模型未就绪，等待后台重训；本次不交易",
                    level="WARNING",
                )
            return False
        if self._model_due(signal_date) and self._model_due_logged != signal_date:
            self._model_due_logged = signal_date
            self.log(
                "模型已到重训周期，继续使用当前模型直至后台更新",
                level="WARNING",
            )
        return True

    def _missing_rank_data(self, day: datetime.date, message: str, severity: str) -> bool:
        self._data_missing = True
        if self._last_data_missing_log != day:
            self._last_data_missing_log = day
            self.log(message, level=severity)
        return False

    def _live_panel_ready(
        self, hist_slice: pl.DataFrame, target_date: datetime.date, today: datetime.date
    ) -> bool:
        """Require today's bars for holdings and the configured universe coverage."""
        if target_date != today:
            return self._missing_rank_data(
                today, f"实盘行情缺失：今日({today}) 无行情，最新 {target_date}，不交易", "WARNING"
            )
        rows = hist_slice.filter(pl.col("date") == today)
        held = {
            asset
            for asset, position in self.broker.positions.items()
            if float(getattr(position, "shares", 0) or 0) > 0
        }
        present = set(rows["asset"].to_list())
        missing = sorted(asset for asset in held if asset not in present)
        if missing:
            return self._missing_rank_data(
                today, f"实盘行情缺失：持仓 {missing} 今日无行情，不交易", "ERROR"
            )
        coverage = len(present) / max(1, len(self._live_universe_assets or []))
        if coverage < self.live_min_quote_coverage:
            return self._missing_rank_data(
                today,
                f"实盘行情覆盖不足：{coverage:.1%} < {self.live_min_quote_coverage:.0%}，不交易",
                "ERROR",
            )
        return True

    def _rank_for_bar(
        self, tm: datetime.datetime
    ) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, int]]:
        """Compute ranked stock candidates, latest close map, and full rank map."""
        is_live = self._is_live_mode()
        use_pull_bars = not getattr(daily_bars, "_initialized", False) or (
            self.custom_assets is not None and len(self.custom_assets) <= 10
        )

        if use_pull_bars:
            return self._rank_small_universe(tm, is_live)

        signal_date = self._resolve_signal_date(tm)
        self._ensure_backtest_panel(signal_date)
        if self._cached_norm_panel is None or self._cached_norm_panel.is_empty():
            return [], {}, {}

        hist_slice = self._cached_norm_panel.filter(pl.col("date") <= signal_date)
        if hist_slice.is_empty():
            return [], {}, {}

        target_date = cast(datetime.date, hist_slice["date"].max())
        if is_live and not self._live_panel_ready(hist_slice, target_date, signal_date):
            return [], {}, {}
        if is_live and not self._refresh_live_rank_model(signal_date):
            return [], {}, {}
        _retrain_replay_model(hist_slice, is_live, self, signal_date)

        cross_df = hist_slice.filter(
            (pl.col("date") == target_date)
            & (~pl.col("is_st"))
            & (pl.col("volume") > 0)
            & (pl.col("close") > 0)
        )
        if cross_df.is_empty():
            return [], {}, {}

        return _ranked_prediction_result(
            cross_df,
            self._model,
            self._model_engine,
            self.selected_features or FEATURE_COLS,
            target_date,
            self.top_k,
        )

    async def on_bar(self, tm: datetime.datetime) -> None:
        """Rebalance to today's top-K selection.

        实盘/模拟盘每个交易日只决策一次：策略按**信号日**去重，
        避免运行时高频轮询导致重复下单。实盘在 14:57 之后才决策
        （收盘集合竞价）；若 15:00 后仍在运行则继续算（不回退 T+1）。

        Today's top-K is the complete portfolio target: selected holdings are
        kept, every other available holding is fully sold, and every selected
        asset that was not held is bought.  The supervised forward-return
        horizon is unrelated to this execution policy.
        """
        self._data_missing = False
        if not self._in_decision_window(tm):
            return
        signal_date = self._resolve_signal_date(tm)
        if self._last_executed_signal_date == signal_date:
            return
        ranked, _, _ = self._rank_for_bar(tm)
        if self._data_missing:
            self._data_missing = False
            return
        self._last_executed_signal_date = signal_date

        current_positions = dict(self.broker.positions)

        if not ranked and not current_positions:
            return

        target_assets = {str(item["asset"]) for item in ranked[: self.top_k]}
        sold_assets = await self._sell_non_targets(current_positions, target_assets, tm)
        await self._buy_target_candidates(ranked, sold_assets, tm)


def _load_selection_bars(options: SelectionOptions) -> pl.DataFrame:
    """Load only the lookback visible at the requested signal date."""
    if not _ensure_data_connected():
        return pl.DataFrame()
    store_end = (
        getattr(daily_bars, "max_date", None)
        or getattr(daily_bars, "end", None)
        or getattr(calendar, "end", None)
        or datetime.date(2024, 12, 31)
    )
    end = options.as_of or store_end
    if isinstance(store_end, datetime.date):
        end = min(end, store_end)
    frame = daily_bars.get_bars(
        n=max(options.train_window + 30, 75),
        end=end,
        assets=options.custom_assets,
        adjust=None,
        eager_mode=True,
    )
    assert isinstance(frame, pl.DataFrame)
    return frame


def _rank_selection_panel(
    panel: pl.DataFrame,
    target_date: datetime.date,
    options: SelectionOptions,
    selected_features: list[str] | None,
) -> list[dict[str, Any]]:
    """Compute, fit and rank a fixed candidate panel."""
    stock_meta = stock_list.data if stock_list.size > 0 else None
    features = resolve_feature_selection(selected_features) or FEATURE_COLS
    normalized = standardize_features(
        compute_alpha_features(panel, stock_meta=stock_meta), features
    )
    model, engine = _fit_ml_model(
        normalized,
        train_window=options.train_window,
        horizon=options.horizon,
        use_lightgbm=options.use_lightgbm,
        feature_cols=features,
    )
    cross = normalized.filter(pl.col("date") == target_date)
    if cross.is_empty():
        return []
    scores = _score_cross_section(cross, model, engine, features)
    scored = cross.with_columns(pl.Series("ml_score", scores))
    return _format_candidate_rows(scored, target_date, engine, options.top_k)
