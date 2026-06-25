"""数据实体定义。

从 sqlite.py 迁移而来，包含 7 个 ORM 实体 dataclass。
sqlite.py 通过 re-export 保持向后兼容。
"""

import datetime
from dataclasses import dataclass, field

from quantide.core.enums import BidType, BrokerKind, OrderSide, OrderStatus
from quantide.data.models.base import Entity, new_uuid_id


@dataclass
class Order(Entity):
    __table_name__ = "orders"
    __pk__ = "qtoid"
    __indexes__ = (["qtoid", "tm"], True)

    portfolio_id: str
    asset: str  # 资产代码
    side: OrderSide
    shares: float | int  # 委托数量。调用者需要保证符合交易要求
    bid_type: BidType  # 委托类型，比如限价单、市价单
    tm: datetime.datetime = field(default_factory=datetime.datetime.now)
    price: float = 0
    filled: float = 0.0

    foid: str | None = None  # 代理(比如QMT)指定的 id，透传，一般用以查错
    cid: str | None = None  # 券商柜台合约 id
    status: OrderStatus = (
        OrderStatus.UNREPORTED
    )  # 委托状态，比如未报、待报、已报、部成等
    status_msg: str = ""  # 委托状态描述，比如废单原因

    # 本委托 ID, pk
    qtoid: str = field(default_factory=new_uuid_id)
    error: str = ""  # 报单错误信息，包括错误码和错误信息,以:分隔
    extra: str = ""  # 额外信息，json 格式

    def __post_init__(self):
        if isinstance(self.tm, str):
            self.tm = datetime.datetime.fromisoformat(self.tm)
        if isinstance(self.status, int):
            self.status = OrderStatus(self.status)
        if isinstance(self.side, int):
            self.side = OrderSide(self.side)
        if isinstance(self.bid_type, int):
            self.bid_type = BidType(self.bid_type)


@dataclass
class Trade(Entity):
    __table_name__ = "trades"
    __pk__ = "tid"
    __indexes__ = (["tid", "tm"], True)
    __foreign_keys__ = [("qtoid", "orders", "qtoid")]

    portfolio_id: str
    tid: str  # 成交 id，pk。可使用代理（比如 qmt）返回值
    qtoid: str  # 对应的 Order id (quantide order id) - 外键引用 orders 表的 qtoid
    foid: str  # 代理（比如qmt）给出的 order id
    asset: str  # 资产代码
    shares: float | int  # 成交数量
    price: float  # 成交价格
    amount: float  # 成交金额 = 成交数量 * 成交价格
    tm: datetime.datetime  # 成交时间
    side: OrderSide  # 成交方向

    cid: str  # 柜台合同编号，应与同 qtoid 中的 cid 相一致

    fee: float = 0  # 本笔交易手续费

    def __post_init__(self):
        if isinstance(self.tm, str):
            self.tm = datetime.datetime.fromisoformat(self.tm)
        if isinstance(self.side, int):
            self.side = OrderSide(self.side)


@dataclass
class Position(Entity):
    __table_name__ = "positions"
    __pk__ = ["portfolio_id", "dt", "asset"]
    __indexes__ = (["portfolio_id", "asset", "dt"], False)

    portfolio_id: str
    dt: datetime.date
    asset: str
    shares: float
    avail: float  # 可用数量
    price: float  # 持仓成本
    profit: float  # 盈亏比，本字段主要供实盘快速查询使用，在回测、模拟时都不使用。
    mv: float  # 市值

    def __post_init__(self):
        if isinstance(self.dt, str):
            # 处理可能包含时间的ISO格式字符串
            if self.dt.find("T") != -1:
                self.dt = datetime.datetime.fromisoformat(self.dt).date()
            else:
                self.dt = datetime.datetime.strptime(self.dt, "%Y-%m-%d").date()
        elif isinstance(self.dt, datetime.datetime):
            self.dt = self.dt.date()


@dataclass
class Asset(Entity):
    __table_name__ = "assets"
    __pk__ = ["portfolio_id", "dt"]
    __indexes__ = (["portfolio_id", "dt"], True)

    portfolio_id: str
    dt: datetime.date
    principal: float
    cash: float
    frozen_cash: float
    market_value: float
    total: float

    def __post_init__(self):
        if isinstance(self.dt, str):
            # 处理可能包含时间的ISO格式字符串
            if self.dt.find("T") != -1:
                self.dt = datetime.datetime.fromisoformat(self.dt).date()
            else:
                self.dt = datetime.datetime.strptime(self.dt, "%Y-%m-%d").date()
        elif isinstance(self.dt, datetime.datetime):
            self.dt = self.dt.date()


@dataclass
class Portfolio(Entity):
    __table_name__ = "portfolios"
    __pk__ = "portfolio_id"
    __indexes__ = (["portfolio_id"], True)

    portfolio_id: str
    kind: BrokerKind
    start: datetime.date
    name: str = ""
    info: str = ""
    end: datetime.date | None = None
    status: bool = True

    def __post_init__(self):
        if isinstance(self.start, str):
            self.start = datetime.datetime.strptime(self.start, "%Y-%m-%d").date()

        if self.end is not None and isinstance(self.end, str):
            self.end = datetime.datetime.strptime(self.end, "%Y-%m-%d").date()

        if isinstance(self.kind, str):
            self.kind = BrokerKind(self.kind)

        if not isinstance(self.status, bool):
            self.status = bool(self.status)


@dataclass
class StrategyLog(Entity):
    __table_name__ = "strategy_logs"
    __pk__ = ["portfolio_id", "dt", "key"]
    __indexes__ = (["portfolio_id", "dt", "key"], True)
    __foreign_keys__ = [("portfolio_id", "portfolios", "portfolio_id")]

    portfolio_id: str
    dt: datetime.datetime
    key: str
    value: float
    extra: str = ""

    def __post_init__(self):
        if isinstance(self.dt, str):
            if self.dt.find("T") != -1:
                self.dt = datetime.datetime.fromisoformat(self.dt)
            else:
                self.dt = datetime.datetime.strptime(self.dt, "%Y-%m-%d")


@dataclass
class BacktestLogEntry(Entity):
    """回测文本日志。"""

    __table_name__ = "backtest_logs"
    __pk__ = "event_id"
    __indexes__ = (["portfolio_id", "dt"], False)
    __foreign_keys__ = [("portfolio_id", "portfolios", "portfolio_id")]

    event_id: str
    portfolio_id: str
    dt: datetime.datetime
    level: str
    source: str
    message: str
    extra: str = ""

    def __post_init__(self):
        if isinstance(self.dt, str):
            self.dt = datetime.datetime.fromisoformat(self.dt)
