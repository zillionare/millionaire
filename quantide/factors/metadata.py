"""结构化因子目录；跟踪参数是产品起点，并非最优性结论。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from quantide.factors.alpha import FEATURE_COLS, FEATURE_DOCS, FEATURE_GROUPS

Holding = Literal[1, 2, 3, 5, 10, 20]
Direction = Literal["positive", "negative", "nonlinear"]


@dataclass(frozen=True)
class TrackingDefaults:
    lookback: Literal["1y", "3y", "5y", "all"]
    primary_holding_days: Holding
    comparison_holding_days: tuple[Holding, ...]
    price_field: Literal["open", "close"]
    defaults_version: str


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    display_name: str
    group: str
    direction: Direction
    principle: str
    formula: str
    parameters: tuple[str, ...]
    example: str
    data_requirements: str
    caveats: str
    recommended_tracking: TrackingDefaults | None = None


@dataclass(frozen=True)
class NormalizedTrackingDefaults(TrackingDefaults):
    source: Literal["global", "factor"]


GLOBAL_TRACKING_DEFAULTS = TrackingDefaults("3y", 5, (1, 3, 5), "open", "1")

# 名称、方向、固定参数、最低历史及额外数据、局限。历史长度以交易日计。
_DETAILS: dict[str, tuple[str, Direction, str, str, str]] = {
    "rs_board_5d": (
        "板块五日相对强弱",
        "positive",
        "收益窗口5日",
        "至少6日收盘价及同日板块截面",
        "板块优先采用行业元数据，否则按代码前缀划分",
    ),
    "rs_board_20d": (
        "板块二十日相对强弱",
        "positive",
        "收益窗口20日",
        "至少21日收盘价及同日板块截面",
        "板块优先采用行业元数据，否则按代码前缀划分",
    ),
    "rs_market_rank": (
        "市场收益排名",
        "positive",
        "收益窗口10日",
        "至少11日收盘价及同日市场截面",
        "排名丢失收益幅度，受截面构成影响",
    ),
    "downside_resilience": (
        "下跌抗性",
        "positive",
        "窗口10日；下跌权重1，上涨权重0.3",
        "至少2日收盘价及市场截面",
        "短历史使用部分窗口；受市场截面影响",
    ),
    "upper_shadow": (
        "上影线比例",
        "negative",
        "当日振幅归一",
        "当日开高低收",
        "低振幅日比例噪声较大",
    ),
    "lower_shadow": (
        "下影线比例",
        "positive",
        "当日振幅归一",
        "当日开高低收",
        "低振幅日比例噪声较大",
    ),
    "upper_shadow_atr": (
        "上影线波动倍数",
        "negative",
        "ATR窗口20日，最少5个样本",
        "至少5日日线开高低收",
        "ATR不足时不可用",
    ),
    "lower_shadow_atr": (
        "下影线波动倍数",
        "positive",
        "ATR窗口20日，最少5个样本",
        "至少5日日线开高低收",
        "ATR不足时不可用",
    ),
    "upper_shadow_limit": (
        "上影线涨停空间比例",
        "negative",
        "按涨停幅度归一",
        "至少2日开高低收及当日涨停价",
        "缺少有效涨停价时不可用",
    ),
    "lower_shadow_limit": (
        "下影线涨停空间比例",
        "positive",
        "按涨停幅度归一",
        "至少2日开高低收及当日涨停价",
        "缺少有效涨停价时不可用",
    ),
    "overnight_gap": (
        "隔夜跳空",
        "nonlinear",
        "昨收到今开",
        "至少2日收盘价及当日开盘价",
        "依赖复权因子；方向不代表未来收益",
    ),
    "intraday_ret": (
        "盘中收益",
        "nonlinear",
        "当日开盘到收盘",
        "当日开盘价和收盘价",
        "方向不代表未来收益",
    ),
    "vol_ratio_5_20": (
        "五二十日量比",
        "nonlinear",
        "成交额均值窗口5日和20日，最少2个样本",
        "至少2日成交额或成交量及收盘价",
        "缺成交额时以成交量乘收盘价估算",
    ),
    "high_open_bear": (
        "高开低走强度",
        "negative",
        "量比窗口5日和20日",
        "至少2日开收盘价及成交额或成交量",
        "缺成交额时使用估算值",
    ),
    "low_open_bull": (
        "低开高走强度",
        "positive",
        "量比窗口5日和20日",
        "至少2日开收盘价及成交额或成交量",
        "缺成交额时使用估算值",
    ),
    "intraday_vs_overnight_5d": (
        "盘中隔夜收益差",
        "nonlinear",
        "求和窗口5日，最少1个样本",
        "至少2日开收盘价",
        "短历史使用部分窗口",
    ),
    "ma10_slope": (
        "十日均线斜率",
        "positive",
        "均线10日，回看5日，均线最少2个样本",
        "至少7日收盘价",
        "短历史均线不足完整10日",
    ),
    "ma20_slope": (
        "二十日均线斜率",
        "positive",
        "均线20日，回看5日，均线最少2个样本",
        "至少7日收盘价",
        "短历史均线不足完整20日",
    ),
    "ma_alignment": (
        "均线多头排列",
        "positive",
        "均线5、10、20日，最少2个样本",
        "至少2日收盘价",
        "短历史均线不足完整窗口",
    ),
    "bias_5": (
        "五日乖离率",
        "nonlinear",
        "均线5日，最少2个样本",
        "至少2日收盘价",
        "乖离方向不代表未来收益",
    ),
    "bias_20": (
        "二十日乖离率",
        "nonlinear",
        "均线20日，最少2个样本",
        "至少2日收盘价",
        "乖离方向不代表未来收益",
    ),
    "ma20_support_bounce": (
        "二十日线支撑反弹",
        "positive",
        "均线20日；斜率回看5日；阈值1.02和0.995；ATR20",
        "至少7日开高低收",
        "零值表示未触发；短历史均线可能不完整",
    ),
    "clv_money_flow": (
        "量价资金流",
        "positive",
        "均值5日；ATR20最少5个样本；量比5日和20日",
        "至少5日开高低收及成交额或成交量",
        "资金流为价格和量能代理，并非实际资金流",
    ),
    "pv_sync_10d": (
        "十日量价同步",
        "positive",
        "均值10日；成交额均值20日",
        "至少2日收盘价及成交额或成交量",
        "短历史使用部分窗口；成交额可为估算值",
    ),
    "limit_up_gene": (
        "涨停基因",
        "positive",
        "窗口20日；涨停价系数0.992或涨幅9.5%",
        "至少2日收盘价；涨停价可选",
        "固定9.5%替代条件不适用于所有涨跌停制度",
    ),
    "sharpe_mom_20d": (
        "风险调整二十日动量",
        "positive",
        "收益和波动率窗口20日；波动率下限0.005",
        "至少21日收盘价",
        "波动率不足时使用默认值0.02",
    ),
    "rev_5d_shrink_vol": (
        "五日缩量反转",
        "positive",
        "收益5日；量比5日和20日；分母加0.5",
        "至少6日收盘价及成交额或成交量",
        "成交额可为估算值；反转并非收益保证",
    ),
    "shadow_bias_reversal": (
        "影线乖离反转",
        "positive",
        "ATR20；乖离5日和20日；量比5日和20日",
        "至少5日开高低收及成交额或成交量",
        "高位上影和低位下影交互，反转并非收益保证",
    ),
}


def _make_definition(factor_id: str, group: str) -> FactorDefinition:
    name, direction, parameter, requirements, caveat = _DETAILS[factor_id]
    parts = FEATURE_DOCS[factor_id].splitlines()
    formula, principle, example = (part.split("：", 1)[1] for part in parts)
    return FactorDefinition(
        factor_id,
        name,
        group,
        direction,
        principle,
        formula,
        (parameter, "原始日线按累计复权因子后复权；缺省因子为1"),
        example,
        requirements,
        caveat,
    )


FACTOR_METADATA: dict[str, FactorDefinition] = {
    factor_id: _make_definition(factor_id, group)
    for group, ids in FEATURE_GROUPS.items()
    for factor_id in ids
}


def factor_definition(factor_id: str) -> FactorDefinition:
    return FACTOR_METADATA[factor_id]


def list_factor_definitions() -> list[FactorDefinition]:
    return [factor_definition(factor_id) for factor_id in FEATURE_COLS]


def normalized_tracking_defaults(factor_id: str) -> NormalizedTrackingDefaults:
    recommendation = factor_definition(factor_id).recommended_tracking
    defaults = recommendation or GLOBAL_TRACKING_DEFAULTS
    return NormalizedTrackingDefaults(
        defaults.lookback,
        defaults.primary_holding_days,
        defaults.comparison_holding_days,
        defaults.price_field,
        defaults.defaults_version,
        "factor" if recommendation else "global",
    )


def validate_factor_metadata(metadata: Mapping[str, FactorDefinition] | None = None) -> None:
    """检查覆盖与必需字段，报告所有缺失项。"""
    entries = FACTOR_METADATA if metadata is None else metadata
    errors = [f"missing factor: {key}" for key in FEATURE_COLS if key not in entries]
    required = (
        "factor_id",
        "display_name",
        "group",
        "direction",
        "principle",
        "formula",
        "parameters",
        "example",
        "data_requirements",
        "caveats",
    )
    for key, definition in entries.items():
        for field in required:
            value = getattr(definition, field)
            if (
                not value
                or (isinstance(value, str) and not value.strip())
                or (field == "parameters" and any(not item.strip() for item in value))
            ):
                errors.append(f"{key}: missing {field}")
        if definition.factor_id != key:
            errors.append(f"{key}: factor_id mismatch")
        if definition.direction not in ("positive", "negative", "nonlinear"):
            errors.append(f"{key}: invalid direction")
    if errors:
        raise ValueError("; ".join(errors))
