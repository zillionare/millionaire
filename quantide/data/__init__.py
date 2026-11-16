from pathlib import Path

from quantide.config.paths import get_app_db_path, normalize_data_home
from quantide.data.models.calendar import calendar
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.daily_basic import daily_basic
from quantide.data.models.minute_bars import minute_bars
from quantide.data.models.stocks import stock_list
from quantide.data.sqlite import db
from quantide.data.stores.index_bars import IndexBarsStore
from quantide.data.stores.index_weight import IndexWeightStore
from quantide.data.stores.limit_price import LimitPriceStore
from quantide.data.stores.minute_bars import MinuteBarsStore

_index_bars_store: IndexBarsStore | None = None
_index_weight_store: IndexWeightStore | None = None
_limit_price_store: LimitPriceStore | None = None
_minute_bars_store: MinuteBarsStore | None = None


def get_index_bars_store() -> IndexBarsStore:
    """返回 IndexBarsStore 单例。"""
    if _index_bars_store is None:
        raise RuntimeError("IndexBarsStore 未初始化，请先调用 init_data()")
    return _index_bars_store


def get_index_weight_store() -> IndexWeightStore:
    """返回 IndexWeightStore 单例（指数成分 PIT）。"""
    if _index_weight_store is None:
        raise RuntimeError("IndexWeightStore 未初始化，请先调用 init_data()")
    return _index_weight_store


def get_limit_price_store() -> LimitPriceStore:
    """返回 LimitPriceStore 单例（涨跌停限价）。"""
    if _limit_price_store is None:
        raise RuntimeError("LimitPriceStore 未初始化，请先调用 init_data()")
    return _limit_price_store


def get_minute_bars_store() -> MinuteBarsStore:
    """返回 MinuteBarsStore 单例（日线级别分钟行情，不含复权因子与涨跌停，读取时关联）。"""
    if _minute_bars_store is None:
        raise RuntimeError("MinuteBarsStore 未初始化，请先调用 init_data()")
    return _minute_bars_store


def init_data(
    home: str | Path | None = None,
    init_db: bool = True,
    db_path: str | Path | None = None,
) -> None:
    """初始化数据层对象：stocklist、calendar、daily_bars、index_bars、index_weight、limit_price。

    Args:
        home (str | Path | None): 指定行情目录；留空读取配置，再退回系统临时目录。
        init_db (bool): 是否初始化数据库。默认为True。
        db_path (str | Path | None): sqlite 数据库路径。未指定时使用固定配置目录。

    Returns:
        None
    """
    global _index_bars_store, _index_weight_store, _limit_price_store, _minute_bars_store

    if init_db:
        target = Path(db_path).expanduser() if db_path is not None else get_app_db_path()
        if not db.is_initialized_for(target):
            db.init(target)

    if not str(home or "").strip():
        from quantide.config.settings import get_data_home

        home = get_data_home()
    home_dir = Path(normalize_data_home(home))
    home_dir.mkdir(parents=True, exist_ok=True)
    calendar_path = home_dir / "data/calendar.parquet"
    stocklist_path = home_dir / "data/stock_list.parquet"
    daily_bars_path = home_dir / "data/bars/daily"
    index_bars_path = home_dir / "data/bars/index"
    index_weight_path = home_dir / "data/index_weight"
    limit_price_path = home_dir / "data/limit_price"
    minute_bars_path = home_dir / "data/bars/minute30"

    daily_bars_path.mkdir(parents=True, exist_ok=True)
    index_bars_path.mkdir(parents=True, exist_ok=True)
    index_weight_path.mkdir(parents=True, exist_ok=True)
    limit_price_path.mkdir(parents=True, exist_ok=True)
    minute_bars_path.mkdir(parents=True, exist_ok=True)

    calendar.load(calendar_path)
    stock_list.load(stocklist_path)
    daily_basic.connect(home_dir / "data/daily_basic.parquet").load()

    daily_bars.connect(str(daily_bars_path), str(calendar_path))
    _index_bars_store = IndexBarsStore(str(index_bars_path), calendar)
    _index_weight_store = IndexWeightStore(str(index_weight_path), calendar)
    _limit_price_store = LimitPriceStore(str(limit_price_path), calendar)
    _minute_bars_store = MinuteBarsStore(str(minute_bars_path), calendar)
    minute_bars.connect(_minute_bars_store)
