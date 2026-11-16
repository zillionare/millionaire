"""Canonical coercion for persisted and external order states."""

from quantide.core.enums import OrderSide, OrderStatus


def coerce_order_side(value: object) -> OrderSide:
    """Read order-side enums, numeric codes, and common external labels."""
    if isinstance(value, OrderSide):
        return value
    text = str(value).strip().upper().removeprefix("ORDERSIDE.")
    aliases = {
        "B": OrderSide.BUY,
        "买入": OrderSide.BUY,
        "S": OrderSide.SELL,
        "卖出": OrderSide.SELL,
    }
    if text in aliases:
        return aliases[text]
    try:
        return OrderSide(int(text))
    except ValueError:
        return OrderSide.__members__.get(text, OrderSide.UNKNOWN)


_STATUS_ALIASES = {
    "未报": OrderStatus.UNREPORTED,
    "待报": OrderStatus.WAIT_REPORTING,
    "已报": OrderStatus.REPORTED,
    "已报待撤": OrderStatus.REPORTED_CANCEL,
    "部成待撤": OrderStatus.PARTSUCC_CANCEL,
    "部成已撤": OrderStatus.PART_CANCEL,
    "已撤": OrderStatus.CANCELED,
    "部成": OrderStatus.PART_SUCC,
    "已成": OrderStatus.SUCCEEDED,
    "已成交": OrderStatus.SUCCEEDED,
    "废单": OrderStatus.JUNK,
    "已拒绝": OrderStatus.JUNK,
    "SUBMITTED": OrderStatus.REPORTED,
    "REJECTED": OrderStatus.JUNK,
    "CANCELLED": OrderStatus.CANCELED,
    "PARTIAL": OrderStatus.PART_SUCC,
    "FILLED": OrderStatus.SUCCEEDED,
}


def coerce_order_status(value: object) -> OrderStatus:
    """Read enums, integer codes, enum names/prefixes, and documented aliases."""
    if isinstance(value, OrderStatus):
        return value
    text = str(value).strip().upper().removeprefix("ORDERSTATUS.")
    if text.isdigit():
        try:
            return OrderStatus(int(text))
        except ValueError:
            return OrderStatus.UNKNOWN
    return _STATUS_ALIASES.get(text, OrderStatus.__members__.get(text, OrderStatus.UNKNOWN))
