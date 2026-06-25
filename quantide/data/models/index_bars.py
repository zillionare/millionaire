"""指数行情数据模型

纯数据类 / schema marker。
存储逻辑由 IndexBarsStore (quantide.data.stores.index_bars) 承担。
"""

import polars as pl


class IndexBars:
    """指数行情 schema marker。

    与 DailyBars 对称保留文件，但不含存储/加载逻辑。
    字段定义: symbol, date, open, high, low, close, volume, amount
    """

    SCHEMA: dict[str, pl.DataType] = {
        "symbol": pl.Utf8,
        "date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    }
