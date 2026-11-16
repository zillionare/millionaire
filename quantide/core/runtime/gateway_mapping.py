"""Gateway order identity and protocol value coercions."""

from quantide.core.enums import OrderSide, OrderStatus
from quantide.core.order_values import coerce_order_side


class GatewayTradeStateConsistencyError(RuntimeError):
    """Raised when gateway payloads break qtoid/external-id consistency."""


def _coerce_order_side(value: str) -> OrderSide:
    """把网关归一化后的委托方向字符串转回 ``OrderSide`` 枚举.

    网关 ``_normalize_order_status`` 不会触碰 ``side``，但客户端代码
    历史上既见过 ``"buy"`` / ``"sell"``，也见过 ``"BUY"`` / ``"SELL"``，
    甚至下单回报里可能带 ``OrderSide`` 整数值。统一在这里收敛。
    """
    return coerce_order_side(value)


def _coerce_order_status(value: str) -> OrderStatus:
    """把网关 ``_normalize_order_status`` 归一化后的字符串映射回 ``OrderStatus`` 枚举.

    网关归一化结果（参考 ``qmt_gateway/apis/trade.py::`` ``_normalize_order_status``）：

    ``"unreported"`` / ``"pending"`` / ``"reported"`` / ``"canceling"`` /
    ``"partial_canceling"`` / ``"partial_cancelled"`` / ``"cancelled"`` /
    ``"partial"`` / ``"filled"`` / ``"rejected"`` / ``"unknown"``

    下游 ``TodayOrdersTable`` 的 ``status_map`` 直接用 ``OrderStatus`` 枚举查找，
    所以必须返回枚举成员本身；任何未识别的字符串都映射成 ``OrderStatus.UNKNOWN``。
    """
    text = str(value or "").strip().lower()
    mapping: dict[str, OrderStatus] = {
        "unreported": OrderStatus.UNREPORTED,
        "pending": OrderStatus.WAIT_REPORTING,
        "reported": OrderStatus.REPORTED,
        "canceling": OrderStatus.REPORTED_CANCEL,
        "partial_canceling": OrderStatus.PARTSUCC_CANCEL,
        "partial_cancelled": OrderStatus.PART_CANCEL,
        "cancelled": OrderStatus.CANCELED,
        "canceled": OrderStatus.CANCELED,
        "partial": OrderStatus.PART_SUCC,
        "filled": OrderStatus.SUCCEEDED,
        "rejected": OrderStatus.JUNK,
    }
    return mapping.get(text, OrderStatus.UNKNOWN)
