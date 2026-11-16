"""Task-local durable order identity shared by runtime and broker extensions."""

from contextvars import ContextVar

client_order_id: ContextVar[str | None] = ContextVar("client_order_id", default=None)
