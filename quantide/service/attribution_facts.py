"""Account-fact attribution adapter shared by backtest, Paper and simulations."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import polars as pl

from quantide.audit.performance import (
    AttributionPeriod,
    AuditTrade,
    PeriodAttribution,
    attribute_period,
    link_carino,
)

SourceKind = Literal["backtest", "paper", "counter", "manual"]


@dataclass(frozen=True)
class FactSnapshot:
    date: dt.date
    equity: float
    cash: float
    positions: dict[str, float]
    prices: dict[str, float]


@dataclass(frozen=True)
class TradeFact:
    date: dt.date
    asset: str
    side: Literal["buy", "sell"]
    shares: float
    price: float
    fee: float = 0.0
    tax: float = 0.0
    strategy: str = "unassigned"
    client_order_id: str = ""


@dataclass(frozen=True)
class CashFlowFact:
    date: dt.date
    amount: float
    kind: str = "external"


@dataclass(frozen=True)
class CorporateActionFact:
    date: dt.date
    asset: str
    kind: Literal["dividend", "split"]
    amount: float = 0.0
    ratio: float = 1.0


@dataclass(frozen=True)
class AccountFacts:
    portfolio_id: str
    source: SourceKind
    snapshots: tuple[FactSnapshot, ...]
    trades: tuple[TradeFact, ...] = ()
    flows: tuple[CashFlowFact, ...] = ()
    corporate_actions: tuple[CorporateActionFact, ...] = ()
    benchmark: dict[dt.date, float] = field(default_factory=dict)
    strategy: str = "unassigned"
    warnings: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        payload = {
            "portfolio_id": self.portfolio_id,
            "source": self.source,
            "snapshots": [
                {
                    "date": item.date.isoformat(),
                    "equity": item.equity,
                    "cash": item.cash,
                    "positions": item.positions,
                    "prices": item.prices,
                }
                for item in self.snapshots
            ],
            "trades": [
                {
                    "date": item.date.isoformat(),
                    "asset": item.asset,
                    "side": item.side,
                    "shares": item.shares,
                    "price": item.price,
                    "fee": item.fee,
                    "tax": item.tax,
                    "strategy": item.strategy,
                }
                for item in self.trades
            ],
            "flows": [
                {"date": item.date.isoformat(), "amount": item.amount, "kind": item.kind}
                for item in self.flows
            ],
            "corporate_actions": [
                {
                    "date": item.date.isoformat(),
                    "asset": item.asset,
                    "kind": item.kind,
                    "amount": item.amount,
                    "ratio": item.ratio,
                }
                for item in self.corporate_actions
            ],
            "benchmark": {day.isoformat(): value for day, value in sorted(self.benchmark.items())},
            "strategy": self.strategy,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def _split_adjust(snapshot: FactSnapshot, actions: tuple[CorporateActionFact, ...]) -> FactSnapshot:
    positions = dict(snapshot.positions)
    prices = dict(snapshot.prices)
    for action in actions:
        if action.kind != "split" or action.asset not in positions:
            continue
        ratio = float(action.ratio)
        if ratio <= 0:
            raise ValueError("split ratio must be positive")
        positions[action.asset] *= ratio
        prices[action.asset] /= ratio
    return FactSnapshot(snapshot.date, snapshot.equity, snapshot.cash, positions, prices)


def _period(facts: AccountFacts, start: FactSnapshot, end: FactSnapshot) -> AttributionPeriod:
    actions = tuple(
        action for action in facts.corporate_actions if start.date < action.date <= end.date
    )
    adjusted = _split_adjust(start, actions)
    start_positions = {asset: shares for asset, shares in adjusted.positions.items() if shares > 0}
    dividends: dict[str, float] = {}
    for action in actions:
        if action.kind == "dividend":
            dividends[action.asset] = dividends.get(action.asset, 0.0) + float(action.amount)
    trades = tuple(
        AuditTrade(
            item.asset,
            item.side,
            item.shares,
            item.price,
            item.fee,
            item.tax,
        )
        for item in facts.trades
        if start.date < item.date <= end.date
    )
    flow = sum(item.amount for item in facts.flows if start.date < item.date <= end.date)
    return AttributionPeriod(
        start_equity=adjusted.equity,
        start_positions=start_positions,
        start_prices=adjusted.prices,
        end_prices=end.prices,
        trades=trades,
        external_flow=flow,
        dividends=dividends,
    )


def _reconcile_period(
    period: PeriodAttribution,
    left: FactSnapshot,
    right: FactSnapshot,
) -> PeriodAttribution:
    observed_delta = right.equity - left.equity - period.external_flow
    gap = observed_delta - period.delta_equity
    issues: list[str] = []
    if abs(right.equity - period.end_equity) > 1e-9:
        issues.append(
            f"{right.date}: observed end equity {right.equity} != reconstructed {period.end_equity}"
        )
    if abs(right.cash - period.end_cash) > 1e-9:
        issues.append(
            f"{right.date}: observed end cash {right.cash} != reconstructed {period.end_cash}"
        )
    reconstructed_positions = {
        asset: shares for asset, shares in period.end_positions.items() if abs(shares) > 1e-12
    }
    observed_positions = {
        asset: shares for asset, shares in right.positions.items() if abs(shares) > 1e-12
    }
    if set(reconstructed_positions) != set(observed_positions) or any(
        abs(reconstructed_positions[asset] - observed_positions[asset]) > 1e-9
        for asset in reconstructed_positions.keys() & observed_positions.keys()
    ):
        issues.append(
            f"{right.date}: observed positions {observed_positions} != reconstructed "
            f"{reconstructed_positions}"
        )
    return replace(
        period,
        end_equity=right.equity,
        end_cash=right.cash,
        end_positions=observed_positions,
        delta_equity=observed_delta,
        residual=period.residual + gap,
        start_date=left.date,
        end_date=right.date,
        observed_end_equity=right.equity,
        observed_end_cash=right.cash,
        reconciliation_gap=gap,
        reconciliation_issues=tuple(issues),
    )


def periods_from_facts(
    facts: AccountFacts, *, start: dt.date | None = None, end: dt.date | None = None
) -> list[PeriodAttribution]:
    snapshots = [item for item in facts.snapshots if (start is None or item.date >= start)]
    snapshots = [item for item in snapshots if end is None or item.date <= end]
    if len(snapshots) < 2:
        return []
    return [
        _reconcile_period(attribute_period(_period(facts, left, right)), left, right)
        for left, right in zip(snapshots, snapshots[1:], strict=False)
    ]


def _apply_ownership_trade(lots: dict[str, float], trade: TradeFact) -> None:
    if trade.side == "buy":
        lots[trade.strategy] = lots.get(trade.strategy, 0.0) + trade.shares
        return
    remaining = trade.shares
    if trade.strategy in lots:
        used = min(lots[trade.strategy], remaining)
        lots[trade.strategy] -= used
        remaining -= used
    if remaining > 0 and "unassigned" in lots:
        lots["unassigned"] = max(0.0, lots["unassigned"] - remaining)


def _initial_ownership(
    facts: AccountFacts, asset: str, first: FactSnapshot | None
) -> dict[str, float]:
    lots: dict[str, float] = {}
    for trade in facts.trades:
        if trade.asset == asset and (first is None or trade.date <= first.date):
            _apply_ownership_trade(lots, trade)
    if first is None:
        return lots
    initial = float(first.positions.get(asset, 0.0))
    known = sum(max(value, 0.0) for name, value in lots.items() if name != "unassigned")
    if known > initial > 0:
        scale = initial / known
        lots = {name: value * scale for name, value in lots.items()}
        known = initial
    lots["unassigned"] = lots.get("unassigned", 0.0) + max(0.0, initial - known)
    return lots


def _ownership_events(
    facts: AccountFacts, asset: str, first: FactSnapshot | None, day: dt.date
) -> list[tuple[dt.date, int, int, Any]]:
    events: list[tuple[dt.date, int, int, Any]] = []
    for index, action in enumerate(facts.corporate_actions):
        if action.asset != asset or action.kind != "split" or action.date > day:
            continue
        if first is None or action.date > first.date:
            events.append((action.date, 0, index, action))
    for index, trade in enumerate(facts.trades):
        if trade.asset != asset or trade.date > day:
            continue
        if first is None or trade.date > first.date:
            events.append((trade.date, 1, index, trade))
    return sorted(events, key=lambda event: event[:3])


def _apply_ownership_events(
    lots: dict[str, float], events: list[tuple[dt.date, int, int, Any]]
) -> None:
    for _date, kind, _index, item in events:
        if kind == 0:
            for name in lots:
                lots[name] *= float(item.ratio)
        else:
            _apply_ownership_trade(lots, item)


def _normalize_owners(lots: dict[str, float], target: float) -> dict[str, float]:
    total = sum(max(value, 0.0) for value in lots.values())
    if total <= 0:
        return {"unassigned": target}
    scale = target / total if total > target else 1.0
    result = {
        name: value * scale
        for name, value in lots.items()
        if value > 0 and 0 < value * scale <= target
    }
    assigned = sum(result.values())
    if target - assigned > 1e-9:
        result["unassigned"] = result.get("unassigned", 0.0) + target - assigned
    return result


def _owners_at(facts: AccountFacts, asset: str, day: dt.date, target: float) -> dict[str, float]:
    """Track known-source lots and keep unprovable opening shares unassigned."""
    if target <= 0:
        return {}
    snapshots = [item for item in facts.snapshots if item.date <= day]
    first = snapshots[0] if snapshots else None
    lots = _initial_ownership(facts, asset, first)
    _apply_ownership_events(lots, _ownership_events(facts, asset, first, day))
    return _normalize_owners(lots, target)


def _add_contributions(target: dict[str, float], values: dict[str, float]) -> float:
    for strategy, value in values.items():
        target[strategy] = target.get(strategy, 0.0) + value
    return sum(values.values())


def _trade_contributions(
    facts: AccountFacts, left: FactSnapshot, right: FactSnapshot
) -> dict[str, float]:
    result: dict[str, float] = {}
    for trade in facts.trades:
        if not (left.date < trade.date <= right.date) or trade.asset not in right.prices:
            continue
        end_price = float(right.prices[trade.asset])
        direction = 1.0 if trade.side == "buy" else -1.0
        value = direction * trade.shares * (end_price - trade.price) - trade.fee - trade.tax
        result[trade.strategy] = result.get(trade.strategy, 0.0) + value
    return result


def _start_contributions(
    facts: AccountFacts, left: FactSnapshot, adjusted: FactSnapshot, right: FactSnapshot
) -> dict[str, float]:
    result: dict[str, float] = {}
    for asset, shares in adjusted.positions.items():
        if shares <= 0 or asset not in right.prices:
            continue
        start_price = adjusted.prices.get(asset, 0.0)
        value = shares * (float(right.prices[asset]) - start_price)
        original = float(left.positions.get(asset, 0.0))
        owners = _owners_at(facts, asset, left.date, original or shares)
        denominator = original or shares
        for strategy, owned in owners.items():
            result[strategy] = result.get(strategy, 0.0) + value * owned / denominator
    return result


def _dividend_contributions(
    facts: AccountFacts, adjusted: FactSnapshot, actions: tuple[CorporateActionFact, ...]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for action in actions:
        if action.kind != "dividend" or action.amount == 0:
            continue
        shares = max(adjusted.positions.get(action.asset, 0.0), 0.0)
        if shares <= 0:
            continue
        for strategy, owned in _owners_at(facts, action.asset, action.date, shares).items():
            result[strategy] = result.get(strategy, 0.0) + action.amount * owned / shares
    return result


def _strategy_contributions(
    facts: AccountFacts, periods: list[PeriodAttribution]
) -> dict[str, float]:
    snapshots = {item.date: item for item in facts.snapshots}
    result: dict[str, float] = {}
    for period in periods:
        left = snapshots.get(period.start_date) if period.start_date else None
        right = snapshots.get(period.end_date) if period.end_date else None
        if left is None or right is None:
            continue
        actions = tuple(
            action for action in facts.corporate_actions if left.date < action.date <= right.date
        )
        adjusted = _split_adjust(left, actions)
        allocated = _add_contributions(result, _trade_contributions(facts, left, right))
        allocated += _add_contributions(result, _start_contributions(facts, left, adjusted, right))
        allocated += _add_contributions(result, _dividend_contributions(facts, adjusted, actions))
        gap = sum(period.contributions.values()) - allocated
        if abs(gap) > 1e-9:
            result["unassigned"] = result.get("unassigned", 0.0) + gap
    return result


def _report_fingerprint(facts: AccountFacts, periods: list[PeriodAttribution]) -> str:
    payload = {
        "facts": facts.fingerprint,
        "periods": [
            {
                "start": period.start_date.isoformat() if period.start_date else None,
                "end": period.end_date.isoformat() if period.end_date else None,
                "return": period.return_pct,
            }
            for period in periods
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def attribution_report(
    facts: AccountFacts,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, Any]:
    periods = periods_from_facts(facts, start=start, end=end)
    if not periods:
        return {
            "status": "INSUFFICIENT",
            "reason": "at least two account snapshots are required",
            "portfolio_id": facts.portfolio_id,
            "fingerprint": facts.fingerprint,
        }
    linked = link_carino(periods)
    total_delta = sum(period.delta_equity for period in periods)
    total_cost = sum(period.costs for period in periods)
    total_price = sum(period.price_pnl for period in periods)
    total_execution = sum(period.execution_pnl for period in periods)
    total_dividends = sum(period.dividends for period in periods)
    residual = sum(period.residual for period in periods)
    strategy = _strategy_contributions(facts, periods)
    benchmark = _benchmark_metrics(facts, periods)
    issues = [issue for period in periods for issue in period.reconciliation_issues]
    return {
        "status": "OK" if abs(residual) < 1e-6 and not issues else "OK_WITH_RESIDUAL",
        "portfolio_id": facts.portfolio_id,
        "source": facts.source,
        "strategy": facts.strategy,
        "fingerprint": _report_fingerprint(facts, periods),
        "start_equity": periods[0].start_equity,
        "end_equity": periods[-1].end_equity,
        "delta_equity": total_delta,
        "external_flow": sum(period.external_flow for period in periods),
        "price_pnl": total_price,
        "execution_pnl": total_execution,
        "costs": total_cost,
        "dividends": total_dividends,
        "residual": residual,
        "reconciliation_issues": issues,
        "asset_contributions": linked["linked_contributions"],
        "strategy_contributions": strategy,
        "trade_count": sum(len(period.contributions) for period in periods),
        "periods": [period.as_dict() for period in periods],
        "linked": linked,
        "benchmark": benchmark,
        "warnings": list(facts.warnings),
        "basis": {
            "amounts": "original currency",
            "link": "Carino",
            "external_flows": "event-segmented snapshots",
            "corporate_actions": "split-adjusted start state; dividends in cash",
        },
    }


def _benchmark_metrics(facts: AccountFacts, periods: list[PeriodAttribution]) -> dict[str, Any]:
    if not facts.benchmark:
        return {"status": "NOT_APPLICABLE", "reason": "no benchmark supplied"}
    dates = [period.end_date for period in periods]
    if any(date is None or date not in facts.benchmark for date in dates):
        return {"status": "INSUFFICIENT", "reason": "benchmark dates do not align"}
    strategy_returns = [period.return_pct for period in periods]
    benchmark_returns = [float(facts.benchmark[date]) for date in dates if date is not None]
    excess = [s - b for s, b in zip(strategy_returns, benchmark_returns, strict=True)]
    total_strategy = 1.0
    total_benchmark = 1.0
    for value in strategy_returns:
        total_strategy *= 1 + value
    for value in benchmark_returns:
        total_benchmark *= 1 + value
    return {
        "status": "OK",
        "strategy_total": total_strategy - 1,
        "benchmark_total": total_benchmark - 1,
        "excess_total": (total_strategy - 1) - (total_benchmark - 1),
        "daily_excess": excess,
        "frequency": "snapshot",
    }


def _snapshot_from_row(row: dict[str, Any], positions: pl.DataFrame) -> FactSnapshot:
    day = row["dt"]
    held = positions.filter(pl.col("dt") == day) if not positions.is_empty() else positions
    shares: dict[str, float] = {}
    prices: dict[str, float] = {}
    for position in held.iter_rows(named=True):
        quantity = float(position.get("shares") or 0)
        market_value = float(position.get("mv") or 0)
        if quantity <= 0:
            continue
        shares[position["asset"]] = quantity
        prices[position["asset"]] = market_value / quantity
    return FactSnapshot(day, float(row["total"]), float(row["cash"]), shares, prices)


def _trade_facts(trades: pl.DataFrame) -> tuple[TradeFact, ...]:
    return tuple(
        TradeFact(
            row["tm"].date() if isinstance(row["tm"], dt.datetime) else row["tm"],
            row["asset"],
            "buy" if int(row["side"]) == 1 else "sell",
            float(row["shares"]),
            float(row["price"]),
            float(row.get("fee") or 0),
        )
        for row in trades.iter_rows(named=True)
    )


def facts_from_db(
    portfolio_id: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> AccountFacts:
    from quantide.data.sqlite import db

    assets = db.query_assets(portfolio_id, start=start, end=end)
    if assets.is_empty():
        return AccountFacts(portfolio_id, "backtest", ())
    positions = db.query_positions(portfolio_id, start=start, end=end)
    snapshots = tuple(_snapshot_from_row(row, positions) for row in assets.iter_rows(named=True))
    return AccountFacts(
        portfolio_id,
        "backtest",
        snapshots,
        _trade_facts(db.trades_all(portfolio_id)),
        warnings=("external flows and corporate actions require explicit facts",),
    )


def facts_from_counter_state(portfolio_id: str, state: dict[str, Any]) -> AccountFacts:
    cash = float(state.get("cash") or 0)
    positions = state.get("positions") or {}
    shares = {
        str(asset): float(item.get("shares", item.get("quantity", 0)))
        for asset, item in positions.items()
    }
    prices = {str(asset): float(item.get("price", 0)) for asset, item in positions.items()}
    market_value = sum(shares[asset] * prices[asset] for asset in shares)
    day = dt.date.today()
    snapshot = FactSnapshot(day, cash + market_value, cash, shares, prices)
    trades = tuple(
        TradeFact(
            day,
            str(item.get("asset", "")),
            "buy" if float(item.get("shares", 0)) > 0 else "sell",
            abs(float(item.get("shares", 0))),
            float(item.get("price", 0)),
            float(item.get("fee", 0)),
        )
        for item in state.get("trades", [])
    )
    return AccountFacts(
        portfolio_id,
        "counter",
        (snapshot,),
        trades,
        warnings=("counter snapshot has no daily equity history",),
    )


def attribution_markdown(report: dict[str, Any]) -> str:
    """Render an AI-readable Markdown summary without executing report text."""
    if report.get("status") == "INSUFFICIENT":
        return f"# 收益归因\n\n数据不足：{report.get('reason', '')}\n"
    lines = [
        "# 收益归因",
        "",
        f"- 账户：{report.get('portfolio_id')}",
        f"- 来源：{report.get('source')}",
        f"- 口径：{report.get('basis', {}).get('link', '')}",
        f"- 指纹：`{report.get('fingerprint', '')}`",
        f"- 区间权益：{report.get('start_equity'):.2f} → {report.get('end_equity'):.2f}",
        f"- 已解释：价格 {report.get('price_pnl'):.2f}、执行 {report.get('execution_pnl'):.2f}、"
        f"成本 {report.get('costs'):.2f}、分红 {report.get('dividends'):.2f}",
        f"- 外部净流入：{report.get('external_flow'):.2f}",
        f"- 显式残差：{report.get('residual'):.2f}",
        "",
        "## 资产贡献（Carino 链接）",
        "",
        "| 资产 | 贡献 |",
        "| --- | ---: |",
    ]
    for asset, value in sorted(report.get("asset_contributions", {}).items()):
        lines.append(f"| {asset} | {value:.6f} |")
    lines += ["", "## 策略贡献", "", "| 策略 | 贡献 |", "| --- | ---: |"]
    for strategy, value in sorted(report.get("strategy_contributions", {}).items()):
        lines.append(f"| {strategy} | {value:.6f} |")
    benchmark = report.get("benchmark", {})
    lines += ["", "## 基准", ""]
    if benchmark.get("status") == "OK":
        lines.append(
            f"- 策略总收益 {benchmark.get('strategy_total'):.6f}；"
            f"基准总收益 {benchmark.get('benchmark_total'):.6f}；"
            f"超额 {benchmark.get('excess_total'):.6f}"
        )
    else:
        lines.append(
            f"- {benchmark.get('status', 'NOT_APPLICABLE')}：{benchmark.get('reason', '')}"
        )
    warnings = report.get("warnings") or []
    if warnings:
        lines += ["", "## 数据限制", ""] + [f"- {item}" for item in warnings]
    lines.append("")
    lines.append("收益归因不是盈利保证；缺失事实以残差或数据不足呈现，不猜测补造。")
    return "\n".join(lines)
