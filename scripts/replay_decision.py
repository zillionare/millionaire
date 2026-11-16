#!/usr/bin/env python
"""离线重放某个策略在某日 14:57 的选股决策（不交易）。

用法示例：
  python scripts/replay_decision.py --date 2026-10-27 --time 14:57
  python scripts/replay_decision.py --quotes /tmp/quotes.json --json

用途：不用等到当天 14:57，随时用当前/历史保存的行情快照跑同一套
universe → 特征 → 模型打分 → 候选过滤链路，提前发现选股/数据/过滤错误。
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantide.config.output_paths import external_runtime_path  # noqa: E402
from quantide.config.paths import get_strategy_runtime_state_path  # noqa: E402
from quantide.data import init_data  # noqa: E402
from quantide.data.fetchers.tencent import TencentDataFetcher  # noqa: E402
from quantide.data.models.daily_bars import daily_bars  # noqa: E402
from quantide.data.models.stocks import stock_list  # noqa: E402
from quantide.service.bar_views import LiveBarView  # noqa: E402
from quantide.service.model_store import model_store  # noqa: E402
from quantide.strategies.example import ml_momentum_reversal as ml  # noqa: E402


def _load_runtime_config(path: Path | None, runtime_id: str | None) -> tuple[dict, str]:
    if path is None or not path.exists():
        return {}, ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    specs = list(payload.get("strategy_runtimes") or [])
    if runtime_id:
        specs = [s for s in specs if s.get("runtime_id") == runtime_id]
    else:
        specs = [s for s in specs if s.get("mode") in {"paper", "live"}]
    if not specs:
        return {}, ""
    spec = specs[0]
    return dict(spec.get("config") or {}), str(spec.get("runtime_id") or "")


def _normalize_quotes(quotes: dict[str, dict]) -> dict[str, dict]:
    for quote in quotes.values():
        ts = quote.get("ts")
        if isinstance(ts, str):
            try:
                quote["ts"] = datetime.datetime.fromisoformat(ts)
            except ValueError:
                quote.pop("ts", None)
    return quotes


def _load_quotes(args: argparse.Namespace) -> tuple[dict[str, dict], str]:
    if args.quotes:
        data = _normalize_quotes(json.loads(Path(args.quotes).read_text(encoding="utf-8")))
        return data, f"file:{args.quotes}"
    symbols = []
    try:
        if stock_list.size > 0:
            symbols = [str(a) for a in stock_list.data["asset"].to_list()]
    except Exception:
        symbols = []
    quotes = TencentDataFetcher().fetch_quote_snapshot(symbols)
    if args.save_quotes:
        Path(args.save_quotes).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_quotes).write_text(
            json.dumps(quotes, ensure_ascii=False, default=str), encoding="utf-8"
        )
    return quotes, "tencent"


class _MarketData:
    def __init__(self, quotes: dict[str, dict]) -> None:
        self.quotes = quotes

    def snapshot(self, symbols: list[str]) -> dict[str, dict]:
        return {symbol: self.quotes[symbol] for symbol in symbols if symbol in self.quotes}

    def get_limits(self, asset: str) -> tuple[float, float]:
        quote = self.quotes.get(asset) or {}
        return (
            float(quote.get("down_limit") or 0),
            float(quote.get("up_limit") or 0),
        )


class _Broker:
    portfolio_id = "replay-decision"
    positions: dict[str, Any] = {}
    cash = 1_000_000.0

    def __init__(self, market_data: _MarketData, today: datetime.date) -> None:
        self.view = LiveBarView(daily_bars, market_data=market_data, today_func=lambda: today)

    def get_bars_range(self, assets, start, end=None, adjust=None, include_forming_bar=True):
        return self.view.get_bars_range(
            assets, start, end, adjust=adjust, include_forming_bar=include_forming_bar
        )

    def get_history(self, asset, count, end_dt=None, frame_type="1d", include_forming_bar=True):
        return self.view.get_history(
            asset, count, end_dt, frame_type, include_forming_bar=include_forming_bar
        )


def build_report(
    day: datetime.date,
    tm: datetime.time,
    config: dict,
    quotes: dict[str, dict],
    source: str,
) -> dict:
    market_data = _MarketData(quotes)
    broker = _Broker(market_data, day)
    strategy = ml.MLMomentumReversalStrategy(broker, config)
    model, meta = model_store.load(strategy._model_key)
    if model is not None and meta is not None:
        strategy._model = model
        strategy._model_engine = meta.engine or strategy._model_engine
        strategy._model_train_end = datetime.date.fromisoformat(meta.train_end)
        strategy._model_effective_from = datetime.date.fromisoformat(meta.effective_from)

    strategy._ensure_backtest_panel(day)
    panel = strategy._cached_norm_panel
    ranked, _prices, _ranks = strategy._rank_for_bar(datetime.datetime.combine(day, tm))
    report: dict[str, Any] = {
        "date": day.isoformat(),
        "time": tm.isoformat(),
        "quote_source": source,
        "quotes": len(quotes),
        "symbols": int(stock_list.size or 0),
        "model_key": strategy._model_key,
        "model_train_end": str(strategy._model_train_end or ""),
        "model_effective_from": str(strategy._model_effective_from or ""),
        "model_engine": strategy._model_engine,
        "panel_rows": None if panel is None else panel.height,
        "universe": len(getattr(strategy, "_live_universe_assets", []) or []),
        "ranked": [
            {
                "rank": item.get("rank"),
                "asset": item.get("asset"),
                "name": item.get("name"),
                "score": round(float(item.get("ml_score", 0) or 0), 4),
            }
            for item in ranked[:15]
        ],
        "buy_candidates": [
            item["asset"]
            for item in ranked[: strategy.top_k]
            if float(item.get("ml_score", 0) or 0)
            > (0.0 if strategy.custom_assets and len(strategy.custom_assets) == 1 else -0.25)
        ],
    }
    _add_panel_diagnostics(panel, day, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-home", default=None, help="行情目录；默认读取配置")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--time", default="14:57")
    parser.add_argument("--runtime-id", default="")
    parser.add_argument("--runtime-state", default=None, help="运行规格文件；默认读取配置目录")
    parser.add_argument("--quotes", default="", help="JSON quote snapshot; omit to fetch Tencent")
    parser.add_argument(
        "--save-quotes",
        type=external_runtime_path,
        default=None,
        help="save fetched quotes outside the source checkout",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    day = datetime.date.fromisoformat(args.date)
    hour, minute = (int(x) for x in args.time.split(":", 1))
    tm = datetime.time(hour, minute)
    init_data(args.data_home)
    ml._ensure_data_connected()
    config, runtime_id = _load_runtime_config(
        Path(args.runtime_state).expanduser()
        if args.runtime_state
        else get_strategy_runtime_state_path(),
        args.runtime_id or None,
    )
    quotes, source = _load_quotes(args)
    report = build_report(day, tm, config, quotes, source)
    report["runtime_id"] = runtime_id
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"runtime: {runtime_id or 'default'}  date: {day} {tm}")
        print(
            f"quotes: {report['quotes']}/{report['symbols']}  "
            f"panel: {report['panel_rows']}  universe: {report['universe']}  "
            f"cross: {report.get('cross_rows')}"
        )
        print(
            f"model: {report['model_key']} train_end={report['model_train_end']} "
            f"effective={report['model_effective_from']} {report['model_engine']}"
        )
        print(
            f"invalid_limit_order: {report.get('invalid_limit_order')}  "
            f"close_above_up_limit: {report.get('close_above_up_limit')}"
        )
        print("ranked:")
        for item in report["ranked"]:
            print(
                f"  #{item['rank']:<2} {item['asset']:<10} {item['name'] or '':<10} "
                f"{item['score']:+.4f}"
            )
        print(f"buy_candidates: {report['buy_candidates']}")
    if report.get("invalid_limit_order") or report.get("close_above_up_limit"):
        print(
            "ALARM: invalid forming-bar limit order detected "
            f"(invalid_order={report.get('invalid_limit_order')}, "
            f"close_above_up={report.get('close_above_up_limit')})"
        )
        return 3
    if not report["ranked"]:
        print("ALARM: no ranked candidates")
        return 2
    return 0


def _add_panel_diagnostics(panel, day, report):
    """Add source-coverage and limit consistency diagnostics for the replay date."""
    if panel is not None:
        cross = panel.filter(
            (pl.col("date") == day)
            & (~pl.col("is_st"))
            & (pl.col("volume") > 0)
            & (pl.col("close") > 0)
        )
        report["cross_rows"] = cross.height
        report["is_st_null"] = cross.filter(pl.col("is_st").is_null()).height
        if not cross.is_empty() and {"up_limit", "down_limit"}.issubset(cross.columns):
            report["invalid_limit_order"] = cross.filter(
                (pl.col("up_limit") > 0)
                & (pl.col("down_limit") > 0)
                & (pl.col("up_limit") < pl.col("down_limit"))
            ).height
            report["close_above_up_limit"] = cross.filter(
                (pl.col("up_limit") > 0) & (pl.col("close") > pl.col("up_limit") * 1.02)
            ).height


if __name__ == "__main__":
    raise SystemExit(main())
