"""qmt-gateway 交易端口适配器."""

import datetime
from typing import Any
from uuid import uuid4

from quantide.core.enums import OrderSide
from quantide.core.ports import (
    AssetView,
    BrokerPort,
    CancelAck,
    ExecutionResult,
    OrderAck,
    OrderRequest,
    OrderView,
    PositionView,
)
from quantide.core.runtime.gateway_client import GatewayClient
from quantide.core.runtime.gateway_legacy import GatewayBrokerWrapper as GatewayBrokerWrapper
from quantide.core.runtime.gateway_mapping import (
    GatewayTradeStateConsistencyError as GatewayTradeStateConsistencyError,
)
from quantide.core.runtime.gateway_mapping import (
    _coerce_order_side as _coerce_order_side,
)
from quantide.core.runtime.gateway_mapping import (
    _coerce_order_status as _coerce_order_status,
)
from quantide.core.runtime.order_convenience import (
    OrderConvenience,
    execution_request,
    target_order_side,
)
from quantide.data.models import Trade
from quantide.service.market_data_hub import market_data_hub


class GatewayBrokerAdapter(OrderConvenience, BrokerPort):
    """基于 qmt-gateway REST 的交易适配器."""

    def __init__(self, client: GatewayClient) -> None:
        """初始化适配器.

        Args:
            client: gateway 客户端。
        """
        self._client = client
        self._qtoid_to_external_order_id: dict[str, str] = {}
        self._external_order_id_to_qtoid: dict[str, str] = {}

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录策略运行数据.

        gateway 当前仅提供交易与查询能力，不在此端口持久化指标。
        """

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time: datetime.datetime | None = None,
        timeout: float = 0.5,
        **kwargs: Any,
    ) -> ExecutionResult:
        """调整目标仓位占比."""
        asset_view = self.query_assets()
        if asset_view is None or asset_view.total <= 0:
            return ExecutionResult.empty()
        side = target_order_side(asset, target_pct, asset_view.total, self.query_positions())
        return await self._submit_execution(
            asset, side, target_pct, "target_pct", price, order_time, timeout, kwargs
        )

    async def submit(self, request: OrderRequest) -> OrderAck:
        """提交订单."""
        price = self._resolve_price(request)
        sizing_price = self._resolve_sizing_price(request, price)
        shares = self._resolve_shares(request, sizing_price)
        qtoid = str(request.extra.get("qtoid") or uuid4())
        strategy_id = str(request.extra.get("strategy_id") or "")
        if shares <= 0:
            return OrderAck(qt_oid=None, status="rejected", message="invalid shares")
        if request.side == OrderSide.BUY:
            payload = {
                "symbol": request.asset,
                "price": price,
                "shares": int(shares),
                "strategy_id": strategy_id,
                "qtoid": qtoid,
            }
            result = self._client.post_form("/api/trade/buy", payload) or {}
        else:
            payload = {
                "symbol": request.asset,
                "price": price,
                "shares": int(shares),
                "strategy_id": strategy_id,
                "qtoid": qtoid,
            }
            result = self._client.post_form("/api/trade/sell", payload) or {}
        if result.get("success"):
            response_qtoid = self._read_text(result, "qtoid")
            external_order_id = self._read_text(result, "order_id", "foid", "external_order_id")
            if response_qtoid and response_qtoid != qtoid:
                raise GatewayTradeStateConsistencyError(
                    "gateway submit returned mismatched qtoid; treat as block candidate"
                )
            self._remember_order_mapping(qtoid=qtoid, external_order_id=external_order_id)
            return OrderAck(
                qt_oid=qtoid,
                status="submitted",
                message="ok",
            )
        return OrderAck(
            qt_oid=None,
            status="rejected",
            message=str(result.get("error") or "gateway submit failed"),
        )

    async def cancel(self, order_id: str) -> CancelAck:
        """撤销订单."""
        result = self._client.post_form("/api/trade/cancel", {"qtoid": order_id}) or {}
        return CancelAck(
            success=bool(result.get("success", False)),
            message=str(result.get("error") or ""),
        )

    async def _submit_execution(
        self,
        asset: str,
        side: OrderSide,
        value: int | float,
        style: str,
        price: float,
        order_time: datetime.datetime | None,
        timeout: float,
        extra: dict[str, Any],
    ) -> ExecutionResult:
        """提交高阶交易请求并返回正式结果对象."""
        ack = await self.submit(
            execution_request(asset, side, value, style, price, order_time, timeout, extra)
        )
        return ExecutionResult(
            qt_oid=ack.qt_oid,
            trades=list(ack.trades or []),
            status=ack.status,
            message=ack.message,
        )

    async def cancel_all(self, side: OrderSide | None = None) -> int:
        """撤销全部订单."""
        orders = self.query_orders()
        count = 0
        for order in orders:
            if side and not self._side_matches(order.side, side):
                continue
            if order.order_id:
                ack = await self.cancel(order.order_id)
                if ack.success:
                    count += 1
        return count

    def query_positions(self) -> list[PositionView]:
        """查询持仓."""
        rows = self._client.get_json("/api/trade/positions") or []
        result: list[PositionView] = []
        today = datetime.date.today()
        for row in rows:
            result.append(
                PositionView(
                    asset=str(row.get("symbol") or ""),
                    shares=float(row.get("shares") or 0),
                    avail=float(row.get("avail") or 0),
                    price=float(row.get("cost") or 0),
                    mv=float(row.get("market_value") or 0),
                    dt=today,
                )
            )
        return result

    def query_assets(self) -> AssetView | None:
        """查询资产."""
        row = self._client.get_json("/api/trade/asset") or {}
        if not row:
            return None
        today = datetime.date.today()
        return AssetView(
            cash=float(row.get("cash") or 0),
            total=float(row.get("total") or 0),
            market_value=float(row.get("market_value") or 0),
            frozen_cash=float(row.get("frozen_cash") or 0),
            principal=float(row.get("principal") or 0),
            dt=today,
        )

    def query_orders(self, status: str | None = None) -> list[OrderView]:
        """查询订单."""
        params = {"status": status} if status else None
        rows = self._client.get_json("/api/trade/orders", params=params) or []
        result: list[OrderView] = []
        for row in rows:
            qtoid = self._resolve_qtoid(row, context="query_orders")
            result.append(
                OrderView(
                    order_id=qtoid,
                    asset=str(row.get("symbol") or ""),
                    side=str(row.get("side") or ""),
                    shares=float(row.get("shares") or 0),
                    price=float(row.get("price") or 0),
                    status=str(row.get("status") or ""),
                    tm=self._parse_time_text(str(row.get("time") or "")),
                    filled=float(row.get("filled") or 0),
                    error="",
                )
            )
        return result

    def query_trades(self, order_id: str | None = None) -> list[Trade]:
        """查询成交."""
        rows = self._client.get_json("/api/trade/trades") or []
        result: list[Trade] = []
        for idx, row in enumerate(rows):
            trade_id = str(row.get("tid") or f"gw-{idx}")
            qtoid = self._resolve_qtoid(
                row,
                requested_qtoid=order_id,
                context="query_trades",
            )
            result.append(
                Trade(
                    portfolio_id="",
                    tid=trade_id,
                    qtoid=qtoid,
                    foid="",
                    asset=str(row.get("symbol") or ""),
                    shares=float(row.get("shares") or 0),
                    price=float(row.get("price") or 0),
                    amount=float(row.get("amount") or 0),
                    tm=self._parse_time_text(str(row.get("time") or "")),
                    side=_coerce_order_side(str(row.get("side") or "")),
                    cid="",
                )
            )
        return result

    def _resolve_price(self, request: OrderRequest) -> float:
        """解析正式下单价格，优先使用显式价格，其次回退到 MarketDataHub。"""
        if request.price > 0:
            return float(request.price)
        try:
            quote = market_data_hub.get_quote(request.asset)
        except Exception:
            return 0.0
        if not quote:
            return 0.0
        for key in ("price", "open", "high", "low"):
            value = quote.get(key)
            if value and value > 0:
                return float(value)
        return 0.0

    def _resolve_sizing_price(self, request: OrderRequest, execution_price: float) -> float:
        """解析金额类下单的数量估算价格，优先使用涨跌停保护价。"""
        try:
            down_limit, up_limit = market_data_hub.get_price_limits(request.asset)
        except Exception:
            return execution_price
        try:
            down_limit_value = float(down_limit or 0)
            up_limit_value = float(up_limit or 0)
        except (TypeError, ValueError):
            return execution_price
        if request.side == OrderSide.BUY and up_limit_value > 0:
            return up_limit_value
        if request.side == OrderSide.SELL and down_limit_value > 0:
            return down_limit_value
        return execution_price

    def _resolve_shares(self, request: OrderRequest, price: float) -> int:
        """Resolve order sizing through a single board-lot rounding rule."""
        if request.style == "shares":
            return int(request.value // 100 * 100)
        if price <= 0:
            return 0
        if request.style == "amount":
            return int((request.value / price) // 100 * 100)
        if request.style not in {"percent", "target_pct"}:
            return 0
        asset = self.query_assets()
        if asset is None:
            return 0
        amount = asset.total * request.value
        if request.style == "target_pct":
            amount = self._target_order_amount(request, price, amount)
        return int((amount / price) // 100 * 100)

    def _target_order_amount(self, request: OrderRequest, price: float, target: float) -> float:
        current = next(
            (
                position.shares * price
                for position in self.query_positions()
                if position.asset == request.asset
            ),
            0.0,
        )
        delta = target - current
        return max(0.0, delta if request.side == OrderSide.BUY else -delta)

    def _side_matches(self, text: str, side: OrderSide) -> bool:
        """判断订单方向是否匹配."""
        raw = str(text).strip().lower()
        if side == OrderSide.BUY:
            return raw in {"buy", "1", "买入"}
        if side == OrderSide.SELL:
            return raw in {"sell", "-1", "卖出"}
        return False

    def _remember_order_mapping(self, qtoid: str, external_order_id: str | None) -> None:
        """Record gateway external order-id mapping without replacing qtoid."""
        if not external_order_id or external_order_id == qtoid:
            return
        existing_qtoid = self._external_order_id_to_qtoid.get(external_order_id)
        if existing_qtoid and existing_qtoid != qtoid:
            raise GatewayTradeStateConsistencyError(
                "gateway external order id remapped to another qtoid; treat as block candidate"
            )
        existing_external = self._qtoid_to_external_order_id.get(qtoid)
        if existing_external and existing_external != external_order_id:
            raise GatewayTradeStateConsistencyError(
                "gateway qtoid remapped to another external order id; treat as block candidate"
            )
        self._qtoid_to_external_order_id[qtoid] = external_order_id
        self._external_order_id_to_qtoid[external_order_id] = qtoid

    def _resolve_qtoid(
        self,
        payload: dict[str, Any],
        requested_qtoid: str | None = None,
        *,
        context: str,
    ) -> str:
        """Resolve the canonical qtoid for gateway payloads."""
        qtoid = self._read_text(payload, "qtoid")
        external_order_id = self._read_text(payload, "order_id", "foid", "external_order_id")
        mapped_qtoid = self._external_order_id_to_qtoid.get(external_order_id or "")

        if qtoid and external_order_id:
            self._remember_order_mapping(qtoid=qtoid, external_order_id=external_order_id)
            return qtoid

        if qtoid:
            if requested_qtoid and requested_qtoid != qtoid:
                raise GatewayTradeStateConsistencyError(
                    f"{context}"
                    " returned qtoid different from requested qtoid; treat as block "
                    "candidate"
                )
            return qtoid

        if mapped_qtoid:
            return mapped_qtoid

        if requested_qtoid:
            if external_order_id:
                self._remember_order_mapping(
                    qtoid=requested_qtoid, external_order_id=external_order_id
                )
            return requested_qtoid

        raise GatewayTradeStateConsistencyError(
            f"{context} missing qtoid and known external mapping; treat as block candidate"
        )

    def _read_text(self, payload: dict[str, Any], *keys: str) -> str | None:
        """Read the first non-empty string value from a payload."""
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _parse_time_text(self, text: str) -> datetime.datetime:
        """解析时间字符串."""
        if not text:
            return datetime.datetime.now()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
            try:
                parsed = datetime.datetime.strptime(text, fmt)
                if fmt == "%H:%M:%S":
                    today = datetime.date.today()
                    return datetime.datetime.combine(today, parsed.time())
                return parsed
            except ValueError:
                continue
        return datetime.datetime.now()
