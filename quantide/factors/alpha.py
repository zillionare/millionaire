"""A股 alpha 因子库。

与策略解耦：因子只负责「原始 K 线 → 因子表」，不含任何交易规则；
策略负责「因子 → 训练 → 选股 → 下单」。每个因子的计算方法、含义与示例
见 :data:`FEATURE_DOCS`，因子清单见 :data:`FEATURE_GROUPS`。

复权口径：因子层内部统一做**后复权**换算（``调整后价 = 原始价 × 绝对累计复权
因子``），输入应为原始价日线；该口径与抓取窗口无关，因子可增量计算并入库复用。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import polars as pl

#: 因子计算版本（因子模块源码哈希）：因子公式变化时缓存自动失效
FACTOR_VERSION: str = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:12]

#: 因子分组（顺序即 :data:`FEATURE_COLS` 的顺序），供 UI 分组展示。
FEATURE_GROUPS: dict[str, list[str]] = {
    "相对强弱": [
        "rs_board_5d",
        "rs_board_20d",
        "rs_market_rank",
        "downside_resilience",
    ],
    "短线形态": [
        "upper_shadow",
        "lower_shadow",
        "upper_shadow_atr",
        "lower_shadow_atr",
        "upper_shadow_limit",
        "lower_shadow_limit",
        "overnight_gap",
        "intraday_ret",
        "vol_ratio_5_20",
        "high_open_bear",
        "low_open_bull",
        "intraday_vs_overnight_5d",
        "ma20_support_bounce",
    ],
    "资金推动": [
        "clv_money_flow",
        "pv_sync_10d",
        "limit_up_gene",
    ],
    "动量与反转": [
        "ma10_slope",
        "ma20_slope",
        "ma_alignment",
        "bias_5",
        "bias_20",
        "sharpe_mom_20d",
        "rev_5d_shrink_vol",
        "shadow_bias_reversal",
    ],
}

#: 全部因子名（按分组顺序）。
FEATURE_COLS: list[str] = [name for group in FEATURE_GROUPS.values() for name in group]

#: 每个特征的「计算方法 / 含义 / 示例」说明，键与 :data:`FEATURE_COLS` 一一对应。
#: 计算口径里的公共中间量：
#: - ``prev_close``：上一交易日收盘价（``close.shift(1).over("asset")``）。
#: - ``true_range``：``max(最高-最低, |最高-昨收|, |最低-昨收|)``。
#: - ``atr20``：``true_range`` 的 20 日均值（min_samples=5），个股自身波动尺度。
#: - ``limit_pct``：``(涨停价 - 昨收) / 昨收 * 100``，ST/板块不同则不同
#:   （ST≈5%、主板≈10%、创业板/科创板≈20%）。
FEATURE_DOCS: dict[str, str] = {
    "rs_board_5d": (
        "计算：ret_5d − 同日同板块 ret_5d 均值。\n"
        "含义：个股相对本板块的 5 日超额收益（板块口径按代码前缀划分）。\n"
        "示例：个股 5 日 +2.0%、板块均值 −5.0% → +7.0%。"
    ),
    "rs_board_20d": (
        "计算：ret_20d − 同日同板块 ret_20d 均值。\n"
        "含义：个股相对本板块的 20 日超额收益。\n"
        "示例：个股 20 日 +4.0%、板块均值 −13.9% → +17.9%。"
    ),
    "rs_market_rank": (
        "计算：当日截面 ret_10d 升序名次 / 当日资产数。\n"
        "含义：10 日收益在全市场的百分位（序数，丢失幅度）。\n"
        "示例：5344 只中排第 400 → 400/5344 ≈ 0.075。"
    ),
    "downside_resilience": (
        "计算：近 10 日 (个股日收益 − 市场日收益) 的均值；市场下跌的日子权重 1.0，"
        "上涨的日子权重 0.3。\n"
        "含义：市场走弱时能否相对抗跌。\n"
        "示例：市场连跌 5 日，个股每天都少跌 1% → 约 +1.0。"
    ),
    "upper_shadow": (
        "计算：(最高 − max(开,收)) / (最高 − 最低)。\n"
        "含义：上影线占当日振幅的比例（形态，分母为当日振幅，安静日噪声大）。\n"
        "示例：开 10.00、收 10.20、高 11.00、低 10.00 → (11.00-10.20)/1.00 = 0.80。"
    ),
    "lower_shadow": (
        "计算：(min(开,收) − 最低) / (最高 − 最低)。\n"
        "含义：下影线占当日振幅的比例。\n"
        "示例：开 10.00、收 10.20、高 11.00、低 10.00 → (10.00-10.00)/1.00 = 0.00。"
    ),
    "upper_shadow_atr": (
        "计算：(最高 − max(开,收)) / atr20。\n"
        "含义：上影线相当于该股近 20 日常态波动的多少倍（自身波动归一）。\n"
        "示例：上影 0.80 元、atr20 = 2.00 元 → 0.40。"
    ),
    "lower_shadow_atr": (
        "计算：(min(开,收) − 最低) / atr20。\n"
        "含义：下影线相当于该股近 20 日常态波动的多少倍。\n"
        "示例：下影 0.40 元、atr20 = 2.00 元 → 0.20。"
    ),
    "upper_shadow_limit": (
        "计算：((最高 − max(开,收)) / 昨收 × 100) / limit_pct。\n"
        "含义：上影线占当日允许涨跌空间的比例（ST/板块口径统一，跨股票可比）。\n"
        "示例：昨收 10.00、上影 0.30 元(3%)；ST 限 5% → 3/5 = 0.60；"
        "创业板限 20% → 3/20 = 0.15。"
    ),
    "lower_shadow_limit": (
        "计算：((min(开,收) − 最低) / 昨收 × 100) / limit_pct。\n"
        "含义：下影线占当日允许涨跌空间的比例。\n"
        "示例：昨收 10.00、下影 0.50 元(5%)、主板限 10% → 5/10 = 0.50。"
    ),
    "overnight_gap": (
        "计算：开盘 / 昨收 − 1。\n"
        "含义：隔夜跳空幅度（前复权价，除权日无跳空）。\n"
        "示例：昨收 10.00、今开 10.30 → +3.0%。"
    ),
    "intraday_ret": (
        "计算：收盘 / 开盘 − 1。\n"
        "含义：当日开盘到收盘的盘中涨跌。\n"
        "示例：开 10.00、收 10.50 → +5.0%。"
    ),
    "vol_ratio_5_20": (
        "计算：5 日平均成交额 / 20 日平均成交额。\n"
        "含义：近期量能相对常态的放大倍数。\n"
        "示例：5 日均额 2 亿、20 日均额 1 亿 → 2.00。"
    ),
    "high_open_bear": (
        "计算：max(隔夜跳空, 0) × max(−盘中收益, 0) × vol_ratio_5_20。\n"
        "含义：高开低走的形态强度（高开幅度 × 低走幅度 × 放量）。\n"
        "示例：高开 +3%、盘中 −2%、量比 2 → 0.03×0.02×2 = 0.0012。"
    ),
    "low_open_bull": (
        "计算：max(−隔夜跳空, 0) × max(盘中收益, 0) × vol_ratio_5_20。\n"
        "含义：低开高走的形态强度。\n"
        "示例：低开 −2%、盘中 +4%、量比 1.5 → 0.02×0.04×1.5 = 0.0012。"
    ),
    "intraday_vs_overnight_5d": (
        "计算：近 5 日 (盘中收益 − 隔夜跳空) 之和。\n"
        "含义：近 5 日的收益是来自盘中还是隔夜。\n"
        "示例：5 日盘中累计 +6%、隔夜累计 +1% → +5%。"
    ),
    "ma10_slope": (
        "计算：MA10 / MA10[5日前] − 1。\n"
        "含义：10 日均线的 5 日斜率。\n"
        "示例：MA10 从 10.0 升到 10.5 → +5.0%。"
    ),
    "ma20_slope": (
        "计算：MA20 / MA20[5日前] − 1。\n"
        "含义：20 日均线的 5 日斜率。\n"
        "示例：MA20 从 20.0 升到 21.0 → +5.0%。"
    ),
    "ma_alignment": (
        "计算：(收 > MA5 + MA5 > MA10 + MA10 > MA20) / 3。\n"
        "含义：均线多头排列程度。\n"
        "示例：三条条件全满足 → 1.00；全不满足 → 0.00。"
    ),
    "bias_5": (
        "计算：收盘 / MA5 − 1。\n"
        "含义：短期乖离率（相对 5 日线）。\n"
        "示例：收 11.0、MA5 10.0 → +10.0%。"
    ),
    "bias_20": (
        "计算：收盘 / MA20 − 1。\n"
        "含义：中期乖离率（相对 20 日线）。\n"
        "示例：收 22.0、MA20 20.0 → +10.0%。"
    ),
    "ma20_support_bounce": (
        "计算：当 ma20_slope > 0 且 最低 ≤ MA20×1.02 且 收盘 ≥ MA20×0.995 时，"
        "取 (下影线/atr20 + max(盘中收益/atr20, 0) + 0.5)，否则取 0。\n"
        "含义：回踩 20 日线后获支撑并反弹的强度（0 表示未触发该形态）。\n"
        "示例：下影 0.20/atr20 2.0 = 0.10，盘中 +1% = 0.50 → 0.10+0.50+0.5 = 1.10。"
    ),
    "clv_money_flow": (
        "计算：近 5 日 ((2×收盘 − 最高 − 最低) / atr20 × vol_ratio_5_20) 的均值。\n"
        "含义：收盘位置（CLV）与量能配合的资金流强度。\n"
        "示例：某日收在当日区间上沿 → CLV/atr20 = 1.0，量比 2 → 当日 2.0。"
    ),
    "pv_sync_10d": (
        "计算：近 10 日 sign(日收益) × (成交额 / 20 日均额 − 1) 的均值。\n"
        "含义：量价是否同步（涨时放量、跌时缩量为正）。\n"
        "示例：涨日成交额为均额 2 倍 → sign=+1、倍数 1.0 → +1.0。"
    ),
    "limit_up_gene": (
        "计算：近 20 日中「收盘达到涨停价×0.992 以上或日涨幅 ≥ 9.5%」的天数。\n"
        "含义：涨停基因（游资/题材属性）。\n"
        "示例：近 20 日涨停 3 次 → 3。"
    ),
    "sharpe_mom_20d": (
        "计算：ret_20d / (20 日收益波动率 × √20)。\n"
        "含义：20 日动量的风险调整强度。\n"
        "示例：20 日 +10%、波动率 2% → 10/(2×4.47) ≈ 1.12。"
    ),
    "rev_5d_shrink_vol": (
        "计算：−ret_5d / (vol_ratio_5_20 + 0.5)。\n"
        "含义：5 日回撤且缩量的反转特征。\n"
        "示例：5 日 −3%、量比 0.8 → 0.03/1.3 ≈ 0.023。"
    ),
    "shadow_bias_reversal": (
        "计算：−(上影线/atr20) × max(bias_20, 0) × vol_ratio_5_20 "
        "+ (下影线/atr20) × max(−bias_5, 0)。\n"
        "含义：高位长上影（负）与低位长下影（正）的反转交互。\n"
        "示例：高位上影 0.4/atr20、bias_20=+5%、量比 2 → −0.4×0.05×2 = −0.04。"
    ),
}


def compute_alpha_features(
    df: pl.DataFrame,
    stock_meta: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Compute 5 groups of momentum, reversal, and microstructure features.

    特征分组（与 :data:`FEATURE_COLS` 一一对应，每个特征的「计算方法 / 含义 /
    示例」见 :data:`FEATURE_DOCS`）：

    1. 相对强弱：``rs_board_5d`` ``rs_board_20d`` ``rs_market_rank``
       ``downside_resilience``
    2. 短线形态：``upper_shadow`` ``lower_shadow``（当日振幅比例口径）
       ``upper_shadow_atr`` ``lower_shadow_atr``（ATR 归一）
       ``upper_shadow_limit`` ``lower_shadow_limit``（涨跌停限归一）
       ``overnight_gap`` ``intraday_ret`` ``vol_ratio_5_20`` ``high_open_bear``
       ``low_open_bull`` ``intraday_vs_overnight_5d`` ``ma20_support_bounce``
    3. 资金推动：``clv_money_flow`` ``pv_sync_10d`` ``limit_up_gene``
    4. 动量与反转：``ma10_slope`` ``ma20_slope`` ``ma_alignment`` ``bias_5``
       ``bias_20`` ``sharpe_mom_20d`` ``rev_5d_shrink_vol``
       ``shadow_bias_reversal``

    影线族的三种口径（同一根 K 线同时给出，便于模型区分「形态」与「量级」）：

    - 比例口径 ``upper_shadow``/``lower_shadow``：影线 ÷ 当日振幅，取值 [0,1]，
      但分母是当日振幅，安静日容易被小分母放大成噪声。
    - ATR 口径 ``*_shadow_atr``：影线 ÷ ``atr20``（个股近 20 日真实波动的均值），
      表示"相当于自身常态波动的多少倍"，跨股票跨日期可比。
    - 涨跌停限口径 ``*_shadow_limit``：影线占昨收的百分比 ÷ 当日涨停幅度，
      自动适配 ST(5%)、主板(10%)、创业板/科创板(20%)，跨股票横向可比。

    ``clv`` 的分母同样从 ``bar_range`` 换成 ``atr20``（``clv_atr``），
    ``ma20_support_bounce`` / ``shadow_bias_reversal`` / ``clv_money_flow``
    一并改用 ATR 归一后的影线与 CLV。

    复权口径：输入应为**原始价**（不复权）日线，因子层内部按
    ``调整后价 = 原始价 × 绝对累计复权因子``（后复权）换算；累计因子与抓取
    窗口无关，故同一日期的因子取值稳定、可增量入库复用。调用方不要再做前复权。

    Args:
        df: Daily bar DataFrame containing at least
            ``[date, asset, open, high, low, close, volume]``.  ``up_limit`` /
            ``down_limit`` 可选，提供时才能计算涨跌停限口径的影线；``adjust``
            为累计复权因子（缺省视为 1）。
        stock_meta: Optional metadata DataFrame with ``[asset, industry]``.

    Returns:
        Polars DataFrame sorted by ``[asset, date]`` with all feature columns.
    """
    if df.is_empty():
        return df

    cols = set(df.columns)
    # 因子层统一用「后复权」口径：调整后价格 = 原始价 × 绝对累计复权因子。
    # 累计因子由数据源给出、与抓取窗口无关，因此同一日期的因子取值在任何
    # 窗口下都一致（可增量计算并入库复用）；而所有因子都是比例/收益口径，
    # 与整体缩放无关，切换口径不改变因子取值。
    adjust_expr = (
        pl.col("adjust").cast(pl.Float64).fill_null(1.0) if "adjust" in cols else pl.lit(1.0)
    )
    norm_exprs: list[pl.Expr] = [
        pl.col("date").cast(pl.Date).alias("date"),
        pl.col("asset").cast(pl.Utf8).alias("asset"),
        (pl.col("open").cast(pl.Float64) * adjust_expr).alias("open"),
        (pl.col("high").cast(pl.Float64) * adjust_expr).alias("high"),
        (pl.col("low").cast(pl.Float64) * adjust_expr).alias("low"),
        (pl.col("close").cast(pl.Float64) * adjust_expr).alias("close"),
        pl.col("volume").cast(pl.Float64).fill_null(0.0).alias("volume"),
    ]
    if "amount" in cols:
        norm_exprs.append(
            pl.when(pl.col("amount").is_not_null() & (pl.col("amount") > 0))
            .then(pl.col("amount").cast(pl.Float64))
            .otherwise(pl.col("volume").cast(pl.Float64) * pl.col("close").cast(pl.Float64))
            .alias("amount")
        )
    else:
        norm_exprs.append(
            (pl.col("volume").cast(pl.Float64) * pl.col("close").cast(pl.Float64)).alias("amount")
        )

    if "adjust" in cols:
        norm_exprs.append(pl.col("adjust").cast(pl.Float64).fill_null(1.0).alias("adjust"))
    else:
        norm_exprs.append(pl.lit(1.0).alias("adjust"))

    if "is_st" in cols:
        norm_exprs.append(pl.col("is_st").cast(pl.Boolean).fill_null(False).alias("is_st"))
    else:
        norm_exprs.append(pl.lit(False).alias("is_st"))

    if "up_limit" in cols:
        norm_exprs.append(
            (pl.col("up_limit").cast(pl.Float64).fill_null(0.0) * adjust_expr).alias("up_limit")
        )
    else:
        norm_exprs.append(pl.lit(0.0).alias("up_limit"))

    if "down_limit" in cols:
        norm_exprs.append(
            (pl.col("down_limit").cast(pl.Float64).fill_null(0.0) * adjust_expr).alias("down_limit")
        )
    else:
        norm_exprs.append(pl.lit(0.0).alias("down_limit"))

    out = df.with_columns(norm_exprs).sort(["asset", "date"])

    prefix_board = (
        pl.when(pl.col("asset").str.starts_with("688"))
        .then(pl.lit("科创板"))
        .when(
            pl.col("asset").str.starts_with("300")
            | pl.col("asset").str.starts_with("301")
            | pl.col("asset").str.starts_with("302")
        )
        .then(pl.lit("创业板"))
        .when(pl.col("asset").str.starts_with("002"))
        .then(pl.lit("深市中小"))
        .when(pl.col("asset").str.starts_with("60") | pl.col("asset").str.starts_with("00"))
        .then(pl.lit("主板"))
        .otherwise(pl.lit("其他"))
    )

    if (
        stock_meta is not None
        and not stock_meta.is_empty()
        and "asset" in stock_meta.columns
        and "industry" in stock_meta.columns
        and stock_meta["industry"].drop_nulls().len() > 0
    ):
        meta_clean = stock_meta.select(
            [
                pl.col("asset").cast(pl.Utf8),
                pl.col("industry").cast(pl.Utf8).alias("_meta_board"),
            ]
        ).unique(subset=["asset"], keep="first")
        out = (
            out.join(meta_clean, on="asset", how="left")
            .with_columns(
                pl.when(
                    pl.col("_meta_board").is_not_null()
                    & (pl.col("_meta_board").str.len_chars() > 0)
                )
                .then(pl.col("_meta_board"))
                .otherwise(prefix_board)
                .alias("board")
            )
            .drop("_meta_board")
        )
    else:
        out = out.with_columns(prefix_board.alias("board"))

    # Basic returns & moving averages per asset
    out = out.with_columns(
        [
            (pl.col("close") / pl.col("close").shift(1).over("asset") - 1.0).alias("ret_1d"),
            (pl.col("close") / pl.col("close").shift(3).over("asset") - 1.0).alias("ret_3d"),
            (pl.col("close") / pl.col("close").shift(5).over("asset") - 1.0).alias("ret_5d"),
            (pl.col("close") / pl.col("close").shift(10).over("asset") - 1.0).alias("ret_10d"),
            (pl.col("close") / pl.col("close").shift(20).over("asset") - 1.0).alias("ret_20d"),
            pl.col("close").rolling_mean(window_size=5, min_samples=2).over("asset").alias("ma5"),
            pl.col("close").rolling_mean(window_size=10, min_samples=2).over("asset").alias("ma10"),
            pl.col("close").rolling_mean(window_size=20, min_samples=2).over("asset").alias("ma20"),
            pl.col("close").rolling_mean(window_size=60, min_samples=2).over("asset").alias("ma60"),
            pl.col("amount")
            .rolling_mean(window_size=5, min_samples=2)
            .over("asset")
            .alias("vol_ma5"),
            pl.col("amount")
            .rolling_mean(window_size=20, min_samples=2)
            .over("asset")
            .alias("vol_ma20"),
            (pl.col("high") - pl.col("low")).clip(lower_bound=1e-6).alias("bar_range"),
            pl.max_horizontal("open", "close").alias("body_top"),
            pl.min_horizontal("open", "close").alias("body_bot"),
            (pl.col("open") / pl.col("close").shift(1).over("asset") - 1.0).alias("overnight_gap"),
            (pl.col("close") / pl.col("open").clip(lower_bound=1e-6) - 1.0).alias("intraday_ret"),
        ]
    )

    # Intermediate cross-sectional & candlestick columns
    out = out.with_columns(
        [
            pl.col("ret_5d").mean().over(["date", "board"]).alias("board_ret_5d"),
            pl.col("ret_20d").mean().over(["date", "board"]).alias("board_ret_20d"),
            pl.col("ret_1d").mean().over("date").alias("mkt_ret_1d"),
            ((pl.col("high") - pl.col("body_top")) / pl.col("bar_range")).alias("upper_shadow"),
            ((pl.col("body_bot") - pl.col("low")) / pl.col("bar_range")).alias("lower_shadow"),
            (pl.col("vol_ma5") / (pl.col("vol_ma20") + 1e-6)).alias("vol_ratio_5_20"),
            (pl.col("ma10") / pl.col("ma10").shift(5).over("asset") - 1.0).alias("ma10_slope"),
            (pl.col("ma20") / pl.col("ma20").shift(5).over("asset") - 1.0).alias("ma20_slope"),
            (
                (
                    (pl.col("close") > pl.col("ma5")).cast(pl.Float64)
                    + (pl.col("ma5") > pl.col("ma10")).cast(pl.Float64)
                    + (pl.col("ma10") > pl.col("ma20")).cast(pl.Float64)
                )
                / 3.0
            ).alias("ma_alignment"),
            (pl.col("close") / (pl.col("ma5") + 1e-6) - 1.0).alias("bias_5"),
            (pl.col("close") / (pl.col("ma20") + 1e-6) - 1.0).alias("bias_20"),
            ((2.0 * pl.col("close") - pl.col("high") - pl.col("low")) / pl.col("bar_range")).alias(
                "clv"
            ),
            pl.col("ret_1d")
            .rolling_std(window_size=20, min_samples=3)
            .over("asset")
            .fill_null(0.02)
            .clip(lower_bound=0.005)
            .alias("volatility_20d"),
        ]
    )

    # Volatility / price-limit normalization basis for the shadow family.
    # ``bar_range`` (today's range) is a noisy denominator: on a quiet day the
    # ratio form explodes (a 0.8% range with a 0.2% body reads as a 0.8 shadow),
    # so the shadows are also expressed in ATR units and in units of the daily
    # price limit (which is ST/board aware).
    out = out.with_columns(
        [
            pl.col("close").shift(1).over("asset").alias("prev_close"),
            (pl.col("high") - pl.col("body_top")).alias("upper_wick"),
            (pl.col("body_bot") - pl.col("low")).alias("lower_wick"),
        ]
    )
    out = out.with_columns(
        pl.max_horizontal(
            (pl.col("high") - pl.col("low")),
            (pl.col("high") - pl.col("prev_close")).abs(),
            (pl.col("low") - pl.col("prev_close")).abs(),
        ).alias("true_range")
    )
    out = out.with_columns(
        pl.col("true_range")
        .rolling_mean(window_size=20, min_samples=5)
        .over("asset")
        .alias("atr20")
    )
    out = out.with_columns(
        pl.when(pl.col("up_limit") > 0)
        .then((pl.col("up_limit") - pl.col("prev_close")) / pl.col("prev_close") * 100.0)
        .otherwise(None)
        .alias("limit_pct")
    )
    out = out.with_columns(
        [
            (pl.col("upper_wick") / pl.col("atr20")).alias("upper_shadow_atr"),
            (pl.col("lower_wick") / pl.col("atr20")).alias("lower_shadow_atr"),
            ((pl.col("upper_wick") / pl.col("prev_close") * 100.0) / pl.col("limit_pct")).alias(
                "upper_shadow_limit"
            ),
            ((pl.col("lower_wick") / pl.col("prev_close") * 100.0) / pl.col("limit_pct")).alias(
                "lower_shadow_limit"
            ),
            ((2.0 * pl.col("close") - pl.col("high") - pl.col("low")) / pl.col("atr20")).alias(
                "clv_atr"
            ),
            (pl.col("intraday_ret") * pl.col("prev_close") / pl.col("atr20")).alias(
                "intraday_ret_atr"
            ),
        ]
    )

    # All 5 feature groups
    out = out.with_columns(
        [
            # Group 1: Relative Strength
            (pl.col("ret_5d") - pl.col("board_ret_5d")).alias("rs_board_5d"),
            (pl.col("ret_20d") - pl.col("board_ret_20d")).alias("rs_board_20d"),
            (
                pl.col("ret_10d").rank().over("date") / pl.len().over("date").clip(lower_bound=1)
            ).alias("rs_market_rank"),
            (
                (pl.col("ret_1d") - pl.col("mkt_ret_1d"))
                * pl.when(pl.col("mkt_ret_1d") < 0).then(1.0).otherwise(0.3)
            )
            .rolling_mean(window_size=10, min_samples=1)
            .over("asset")
            .alias("downside_resilience"),
            # Group 2: Short-term Candlestick Patterns
            (
                pl.max_horizontal(pl.col("overnight_gap"), pl.lit(0.0))
                * pl.max_horizontal(-pl.col("intraday_ret"), pl.lit(0.0))
                * pl.col("vol_ratio_5_20")
            ).alias("high_open_bear"),
            (
                pl.max_horizontal(-pl.col("overnight_gap"), pl.lit(0.0))
                * pl.max_horizontal(pl.col("intraday_ret"), pl.lit(0.0))
                * pl.col("vol_ratio_5_20")
            ).alias("low_open_bull"),
            (pl.col("intraday_ret") - pl.col("overnight_gap"))
            .rolling_sum(window_size=5, min_samples=1)
            .over("asset")
            .alias("intraday_vs_overnight_5d"),
            # Group 3: MA Slope & Support
            pl.when(
                (pl.col("ma20_slope") > 0)
                & (pl.col("low") <= pl.col("ma20") * 1.02)
                & (pl.col("close") >= pl.col("ma20") * 0.995)
            )
            .then(
                pl.col("lower_shadow_atr")
                + pl.max_horizontal(pl.col("intraday_ret_atr"), pl.lit(0.0))
                + 0.5
            )
            .otherwise(0.0)
            .alias("ma20_support_bounce"),
            # Group 4: Money Flow & Volume-Price
            (pl.col("clv_atr") * pl.col("vol_ratio_5_20"))
            .rolling_mean(window_size=5, min_samples=1)
            .over("asset")
            .alias("clv_money_flow"),
            (pl.col("ret_1d").sign() * (pl.col("amount") / (pl.col("vol_ma20") + 1e-6) - 1.0))
            .rolling_mean(window_size=10, min_samples=1)
            .over("asset")
            .alias("pv_sync_10d"),
            (
                ((pl.col("up_limit") > 0) & (pl.col("close") >= pl.col("up_limit") * 0.992))
                | (pl.col("ret_1d") >= 0.095)
            )
            .cast(pl.Float64)
            .rolling_sum(window_size=20, min_samples=1)
            .over("asset")
            .alias("limit_up_gene"),
            # Group 5: Momentum-Reversal Interactions
            (pl.col("ret_20d") / (pl.col("volatility_20d") * (20.0**0.5))).alias("sharpe_mom_20d"),
            (-pl.col("ret_5d") / (pl.col("vol_ratio_5_20") + 0.5)).alias("rev_5d_shrink_vol"),
            (
                -pl.col("upper_shadow_atr")
                * pl.max_horizontal(pl.col("bias_20"), pl.lit(0.0))
                * pl.col("vol_ratio_5_20")
                + pl.col("lower_shadow_atr") * pl.max_horizontal(-pl.col("bias_5"), pl.lit(0.0))
            ).alias("shadow_bias_reversal"),
        ]
    )

    return out


def standardize_features(
    df: pl.DataFrame,
    feature_cols: list[str] | None = None,
) -> pl.DataFrame:
    """Standardize feature columns via winsorized cross-sectional Z-score per date.

    Falls back to rolling time-series standardization when a panel only contains
    a single asset per date.
    """
    if df.is_empty():
        return df

    cols = feature_cols or FEATURE_COLS
    n_assets = df["asset"].n_unique()

    z_exprs: list[pl.Expr] = []
    if n_assets > 1:
        for col in cols:
            raw = pl.col(col).cast(pl.Float64).fill_nan(None)
            mean = raw.mean().over("date")
            std = raw.std().over("date").fill_null(0.0)
            clipped = raw.clip(
                lower_bound=mean - 3.0 * std,
                upper_bound=mean + 3.0 * std,
            )
            z = ((clipped - mean) / (std + 1e-6)).fill_null(0.0).fill_nan(0.0)
            z_exprs.append(z.alias(f"{col}_z"))
    else:
        for col in cols:
            raw = pl.col(col).cast(pl.Float64).fill_nan(None)
            mean = raw.rolling_mean(window_size=20, min_samples=2).over("asset")
            std = raw.rolling_std(window_size=20, min_samples=2).over("asset").fill_null(0.0)
            clipped = raw.clip(
                lower_bound=mean - 3.0 * std,
                upper_bound=mean + 3.0 * std,
            )
            z = ((clipped - mean) / (std + 1e-6)).fill_null(0.0).fill_nan(0.0)
            z_exprs.append(z.alias(f"{col}_z"))

    return df.with_columns(z_exprs)


def _zscore_1d(arr: np.ndarray) -> np.ndarray:
    """Normalize a 1D numpy array to zero mean and unit variance."""
    clean = np.nan_to_num(arr.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    if clean.size <= 1:
        return np.clip(clean, -3.0, 3.0)
    std = float(np.std(clean))
    if std < 1e-8:
        return np.zeros_like(clean)
    return (clean - float(np.mean(clean))) / (std + 1e-6)
