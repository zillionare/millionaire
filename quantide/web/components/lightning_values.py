"""Lightning order display values shared by forms and handlers."""

from quantide.data.models.stocks import stock_list

PRICE_REFERENCE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("最新价", "current"),
    ("现价+1%", "current_p1"),
    ("现价+2%", "current_p2"),
    ("现价+3%", "current_p3"),
    ("5日均线", "ma5"),
    ("10日均线", "ma10"),
    ("20日均线", "ma20"),
    ("30日均线", "ma30"),
    ("60日均线", "ma60"),
)


PRICE_REFERENCE_LABELS = {key: label for label, key in PRICE_REFERENCE_OPTIONS}


PRICE_REFERENCE_CURRENT_PREMIUMS: dict[str, float] = {
    "current_p1": 0.01,
    "current_p2": 0.02,
    "current_p3": 0.03,
}


def _asset_symbol(asset: str) -> str:
    """返回不带市场后缀的股票代码。"""
    return asset.split(".")[0]


def _asset_profile(asset: str) -> tuple[str, str]:
    """解析股票名称与拼音。

    Args:
        asset: 股票代码。

    Returns:
        ``(name, pinyin)``。
    """
    try:
        return stock_list.get_name(asset), stock_list.get_pinyin(asset)
    except Exception:
        return asset, ""


def _format_amount_wan(amount_wan: float) -> str:
    """格式化万元金额显示。"""
    return f"{amount_wan:g}万"


def _price_reference_label(price_ref: str) -> str:
    """返回价格参考的展示名称。"""
    return PRICE_REFERENCE_LABELS.get(price_ref, PRICE_REFERENCE_LABELS["current"])


def _is_valid_price_ref(price_ref: str) -> bool:
    """判断价格参考键是否合法。"""
    return price_ref in PRICE_REFERENCE_LABELS
