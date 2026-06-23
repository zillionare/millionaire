import datetime
from enum import IntEnum


class WebErrors(IntEnum):
    """错误码"""

    BAD_PARAMS = 400  # 无效参数
    UNAUTHORIZED = 401  # 未授权
    FORBIDDEN = 403  # 禁止访问
    NOT_FOUND = 404  # 资源不存在
    METHOD_NOT_ALLOWED = 405  # 方法不允许
    INTERNAL_SERVER_ERROR = 500  # 内部服务器错误


class TradeErrors(IntEnum):
    """交易处理错误码"""

    NO_ERROR = 0
    ERROR_UNKNOWN = 1
    ERROR_NOT_LOGIN = 2
    ERROR_BAD_PARAMS = 3
    ERROR_ORDER_FAIL = 4
    ERROR_ORDER_TIMEOUT = 5
    ERROR_DUP_PORTFOLIO = 6
    ERROR_INSUF_CASH = 7
    ERROR_INSUF_AMOUNT = 8          # 委托时，金额不足一手
    ERROR_NONMULTIPLEOFLOTSIZE = 9  # 委托时，share 数量不是一手的整数倍

    ERROR_INSUF_POSITION = 11       # 委卖时，持仓不足或者没有持仓
    ERROR_LIMIT_PRICE = 12          # 委托时，价格超出涨跌停
    ERROR_PRICE_NOT_MET = 13        # 委托时，价格不满足要求
    ERROR_HALT = 14                # 委托时，标的停牌（数据缺失或成交量为 0）
    ERROR_NO_DATA = 14              # 撮合时缺少数据
    ERROR_BAD_PERCENT = 15          # 委托时，percent 不在 (0, 1] 范围内

    # backtest onlly
    ERROR_CLOCK_REWIND = 1001       # 回测时，发生时钟倒退
    ERROR_CLOCK_BEFORE_START = 1002 # 回测时，时钟早于回测开始时间
    ERROR_CLOCK_AFTER_END = 1003    # 回测时，时钟晚于回测结束时间


class BaseTradeError(Exception):
    """基础错误处理基类"""

    def __init__(self, code: TradeErrors, msg: str, *args):
        self.code = code
        self.msg = msg
        self.args = args

    def __str__(self):
        return f"({self.code.value} | {self.msg % self.args})"


class WebError(BaseTradeError):
    """web API 中的错误处理基类"""

    ...


class TradeError(BaseTradeError):
    """交易处理错误"""

    ...


class NoDataForMatch(TradeError):
    """回测撮合时缺少数据"""

    def __init__(
        self,
        security: str,
        dt: datetime.date | datetime.datetime
    ):
        super().__init__(
            TradeErrors.ERROR_BAD_PARAMS,
            "failed to match %s, no data at %s",
            security,
            dt,
        )

class InsufficientCash(TradeError):
    """委托时，现金不足"""

    def __init__(self, security: str, amount: float, cash: float):
        super().__init__(
            TradeErrors.ERROR_INSUF_CASH,
            "Insufficient cash for %s, required: %s, got cash: %s",
            security,
            amount,
            cash
        )
class InsufficientAmount(TradeError):
    """委托时，金额不足一手"""

    def __init__(self, security: str, amount: float):
        super().__init__(
            TradeErrors.ERROR_INSUF_AMOUNT,
            "Insufficient amount for %s at %s",
            security,
            amount,
        )

class LimitPrice(TradeError):
    """委托时，价格超出涨跌停"""

    def __init__(self, security: str, price: float):
        super().__init__(
            TradeErrors.ERROR_LIMIT_PRICE,
            "Limit price reached for %s at %s",
            security,
            price
        )

class PriceNotMeet(TradeError):
    """委托时，价格不满足要求"""

    def __init__(self, security: str, price: float, required_price: float):
        super().__init__(
            TradeErrors.ERROR_PRICE_NOT_MET,
            "Price not meet for %s, required: %s, got: %s",
            security,
            required_price,
            price
        )

class DupPortfolio(TradeError):
    """重复创建账户"""

    def __init__(self, portfolio_id: str):
        super().__init__(
            TradeErrors.ERROR_DUP_PORTFOLIO,
            "Duplicate portfolio id: %s",
            portfolio_id
        )

class ClockRewind(TradeError):
    """回测时，发生时钟倒退"""

    def __init__(self, dt: datetime.datetime, clock: datetime.datetime):
        super().__init__(
            TradeErrors.ERROR_CLOCK_REWIND,
            "Clock rewind to %s, current is %s",
            dt,
            clock
        )

class ClockBeforeStart(TradeError):
    """回测时，时钟早于回测开始时间"""

    def __init__(self, dt: datetime.datetime, bt_start: datetime.datetime):
        super().__init__(
            TradeErrors.ERROR_CLOCK_BEFORE_START,
            "Clock %s is before bt_start %s",
            dt,
            bt_start
        )

class ClockAfterEnd(TradeError):
    """回测时，时钟晚于回测结束时间"""

    def __init__(self, dt: datetime.datetime, bt_end: datetime.datetime):
        super().__init__(
            TradeErrors.ERROR_CLOCK_AFTER_END,
            "Clock %s is after bt_end %s",
            dt,
            bt_end
        )

class NonMultipleOfLotSize(TradeError):
    """委托时，share 数量不是一手的整数倍，或者不足一手。"""

    def __init__(self, security: str, shares: float):
        super().__init__(
            TradeErrors.ERROR_NONMULTIPLEOFLOTSIZE,
            "Non multiple of lot size for %s at %s",
            security,
            shares
        )

class BadPercent(TradeError):
    """委托时，percent 不在 (0, 1] 范围内"""

    def __init__(self, percent: float):
        super().__init__(
            TradeErrors.ERROR_BAD_PERCENT,
            "Percent %s is not in (0, 1]",
            percent
        )

class InsufficientPosition(TradeError):
    """卖出委托时，持仓不足"""

    def __init__(self, security: str, amount: float):
        super().__init__(
            TradeErrors.ERROR_INSUF_POSITION,
            "Insufficient position for %s at %s",
            security,
            amount
        )


class PriceOutOfLimit(TradeError):
    """限价单价格超出涨跌停范围 (FR-140).

    限价单指定价必须落在 [down_limit, up_limit] 内, 否则下单直接拒绝.
    市价单 (price == 0) 不受此校验.
    """

    def __init__(self, security: str, price: float, down_limit: float, up_limit: float):
        self.security = security
        self.price = price
        self.down_limit = down_limit
        self.up_limit = up_limit
        super().__init__(
            TradeErrors.ERROR_LIMIT_PRICE,
            "限价单价格 %s 超出涨跌停范围 [%s, %s] for %s",
            price, down_limit, up_limit, security,
        )


class TradingHaltedError(TradeError):
    """停牌标的不可下单 (FR-170).

    停牌判定: 数据缺失 (quote 为空) 或 volume == 0.
    持仓中的停牌标的按停牌前最后收盘价估值, 不阻止卖单 (但实际业务中可能拒绝).
    """

    def __init__(self, security: str, reason: str = "数据缺失或成交量为 0"):
        self.security = security
        self.reason = reason
        super().__init__(
            TradeErrors.ERROR_HALT,
            "停牌标的 %s 不可下单: %s",
            security, reason,
        )


class UnsupportedFrameTypeForBacktest(RuntimeError):
    def __init__(self, frame_type: str):
        super().__init__(f"Unsupported frame_type '{frame_type}' for backtest")
        self.frame_type = frame_type


class RiskStrategyNotBacktestable(RuntimeError):
    def __init__(self, strategy_id: str = ""):
        msg = f"RiskStrategy '{strategy_id}' is not backtestable" if strategy_id else "RiskStrategy is not backtestable"
        super().__init__(msg)
        self.strategy_id = strategy_id
