"""按 asset 解析证券名称，用于表格中 证券名称 列。"""

from quantide.data.models.stocks import stock_list


def resolve_asset_name(asset: str) -> str:
    """根据 asset 代码查证券名称；查不到时回退到代码本身。

    Args:
        asset: 证券代码（如 ``000001.SZ``、``601398``）。

    Returns:
        证券中文名称（``stock_list`` 命中时），或原代码（未命中、异常、空值）。
    """
    if not asset:
        return ""
    try:
        return stock_list.get_name(asset)
    except Exception:
        return asset
