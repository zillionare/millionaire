"""单因子检验：因子与前瞻收益的截面相关性研究。

用途：独立于策略与训练目标，检验"某个因子在前瞻 N 日是否真的有预测力"，
用来判断模型学到的方向是数据规律还是实现缺陷。

口径（默认 ``price="open"``）：

- ``t0``：计算因子的交易日；
- ``t1``：以 ``t1`` 开盘价买入；
- ``t2 ... t(N+1)``：以 ``t(N+1)`` 开盘价卖出，``N = holding_days``；
  即 ``holding_days=1`` → t1 开盘买、t2 开盘卖（持有 1 个交易日）。

只有当买入日、卖出日与 ``t0`` 在交易日历上**相邻**（无停牌跳日）时该样本才有效。

用法::

    from quantide.factors.alphatest import load_factor_panel, study_single_factor

    panel = load_factor_panel(datetime.date(2022, 6, 1), datetime.date(2026, 10, 19))
    result = study_single_factor(panel, "ma20_slope", holding_days=1)
    print(result.rank_ic.mean, result.rank_ic.t_stat)

命令行::

    python -m quantide.factors.alphatest --factors ma20_slope --holdings 1 3 5 10 20
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

DEFAULT_FACTOR = "ma20_slope"
DEFAULT_HOLDING_DAYS = (1, 2, 3, 5, 10, 20)
MIN_CROSS_SECTION = 100


def _append_decile_summaries(
    buckets: int, totals: dict[int, list[float]], result: list[DecileBucket]
) -> None:
    """Append decile summaries."""
    for bucket in range(1, buckets + 1):
        values = totals[bucket]
        mean = float(np.mean(values)) if values else float("nan")
        result.append(
            DecileBucket(
                bucket=bucket,
                n_samples=len(values),
                mean_forward=mean,
            )
        )


@dataclass(frozen=True)
class RankIcSummary:
    """截面 RankIC 汇总。"""

    mean: float
    t_stat: float
    n_days: int

    def as_row(self) -> dict[str, Any]:
        """转为可序列化的字典。"""
        return {
            "mean": round(self.mean, 6),
            "t_stat": round(self.t_stat, 4),
            "n_days": self.n_days,
        }


@dataclass(frozen=True)
class DecileBucket:
    """因子十分位分组的平均前瞻收益。"""

    bucket: int
    n_samples: int
    mean_forward: float

    def as_row(self) -> dict[str, Any]:
        """转为可序列化的字典。"""
        return {
            "bucket": self.bucket,
            "n_samples": self.n_samples,
            "mean_forward": round(self.mean_forward, 8),
        }


@dataclass(frozen=True)
class SingleFactorResult:
    """单因子检验结果。"""

    factor: str
    holding_days: int
    price: str
    rank_ic: RankIcSummary
    deciles: list[DecileBucket] = field(default_factory=list)
    by_year: dict[int, RankIcSummary] = field(default_factory=dict)
    n_rows: int = 0

    def as_dict(self) -> dict[str, Any]:
        """转为可序列化的字典。"""
        return {
            "factor": self.factor,
            "holding_days": self.holding_days,
            "price": self.price,
            "rank_ic": self.rank_ic.as_row(),
            "deciles": [d.as_row() for d in self.deciles],
            "by_year": {str(y): v.as_row() for y, v in sorted(self.by_year.items())},
            "n_rows": self.n_rows,
        }


def ensure_trading_index(panel: pl.DataFrame) -> pl.DataFrame:
    """确保面板带有交易日序号列 ``di``。

    Args:
        panel: 含 ``date`` 列的面板。

    Returns:
        pl.DataFrame: 带 ``di`` 的面板。
    """
    if "di" in panel.columns:
        return panel
    days = sorted(panel["date"].unique().to_list())
    mapping = {day: index for index, day in enumerate(days)}
    return panel.with_columns(pl.col("date").replace_strict(mapping).alias("di"))


def forward_return_expr(holding_days: int, price: str = "open") -> pl.Expr:
    """构造前瞻收益表达式（t1 开盘买入，t(N+1) 开盘卖出）。

    Args:
        holding_days: 持有交易日数 N（1 表示 t1 买、t2 卖）。
        price: 使用哪个价格字段（``open`` / ``close`` / ``high`` / ``low``）。

    Returns:
        pl.Expr: 前瞻收益表达式。
    """
    if holding_days < 1:
        raise ValueError("holding_days 必须 >= 1")
    entry = pl.col(price).shift(-1).over("asset")
    exit_price = pl.col(price).shift(-(holding_days + 1)).over("asset")
    return exit_price / entry - 1.0


def adjacent_trading_day_expr(holding_days: int) -> pl.Expr:
    """构造"买卖日与 t0 相邻"的校验表达式。

    Args:
        holding_days: 持有交易日数 N。

    Returns:
        pl.Expr: 布尔表达式。
    """
    di = pl.col("di")
    return (di.shift(-1).over("asset") == di + 1) & (
        di.shift(-(holding_days + 1)).over("asset") == di + (holding_days + 1)
    )


def prepare_forward_returns(
    panel: pl.DataFrame,
    holding_days: int,
    price: str = "open",
) -> pl.DataFrame:
    """给面板加上前瞻收益与有效性标记。

    Args:
        panel: 因子面板（需含 ``date``/``asset`` 与因子列）。
        holding_days: 持有交易日数 N。
        price: 价格字段。

    Returns:
        pl.DataFrame: 含 ``forward`` 与 ``valid`` 的面板。
    """
    panel = ensure_trading_index(panel)
    return panel.with_columns(
        [
            forward_return_expr(holding_days, price).alias("forward"),
            adjacent_trading_day_expr(holding_days).alias("valid"),
        ]
    )


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Assign equal values their average zero-based rank, preserving ties."""
    return pl.Series(values).rank(method="average").to_numpy() - 1.0


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """两组数值的 Spearman 秩相关。"""
    if x.size < MIN_CROSS_SECTION:
        return float("nan")
    rx = _average_ranks(x)
    ry = _average_ranks(y)
    if rx.std() < 1e-9 or ry.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def daily_rank_ic(
    df: pl.DataFrame,
    factor: str,
    forward: str = "forward",
) -> list[float]:
    """逐交易日的截面 RankIC。

    Args:
        df: 含 ``date``/因子/前瞻收益的表。
        factor: 因子列名。
        forward: 前瞻收益列名。

    Returns:
        list[float]: 每个交易日的 RankIC。
    """
    ics: list[float] = []
    for _, group in df.group_by("date"):
        if group.height < MIN_CROSS_SECTION:
            continue
        x = group[factor].to_numpy().astype(float)
        y = group[forward].to_numpy().astype(float)
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() < MIN_CROSS_SECTION:
            continue
        value = _spearman(x[mask], y[mask])
        if not math.isnan(value):
            ics.append(value)
    return ics


def summarize(values: list[float]) -> RankIcSummary:
    """把逐日 RankIC 汇总为均值与 t 值。

    Args:
        values: 逐日 RankIC。

    Returns:
        RankIcSummary: 汇总结果。
    """
    if not values:
        return RankIcSummary(mean=float("nan"), t_stat=float("nan"), n_days=0)
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    if arr.size > 1 and arr.std(ddof=1) > 0:
        t_stat = float(mean / (arr.std(ddof=1) / math.sqrt(arr.size)))
    else:
        t_stat = float("nan")
    return RankIcSummary(mean=mean, t_stat=t_stat, n_days=int(arr.size))


def decile_profile(
    df: pl.DataFrame,
    factor: str,
    forward: str = "forward",
    buckets: int = 10,
) -> list[DecileBucket]:
    """因子十分位分组的平均前瞻收益（bucket=1 为因子值最低的一组）。

    Args:
        df: 含 ``date``/因子/前瞻收益的表。
        factor: 因子列名。
        forward: 前瞻收益列名。
        buckets: 分组数。

    Returns:
        list[DecileBucket]: 逐组统计（按 bucket 升序）。
    """
    totals: dict[int, list[float]] = {b: [] for b in range(1, buckets + 1)}
    for _, group in df.group_by("date"):
        if group.height < MIN_CROSS_SECTION:
            continue
        x = group[factor].to_numpy().astype(float)
        y = group[forward].to_numpy().astype(float)
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.sum() < MIN_CROSS_SECTION:
            continue
        x = x[mask]
        y = y[mask]
        order = _average_ranks(x)
        labels = np.floor(order / len(order) * buckets).astype(int) + 1
        for bucket in range(1, buckets + 1):
            picked = y[labels == bucket]
            if picked.size:
                totals[bucket].extend(picked.tolist())
    result: list[DecileBucket] = []
    _append_decile_summaries(buckets, totals, result)
    return result


def yearly_rank_ic(
    df: pl.DataFrame,
    factor: str,
    forward: str = "forward",
) -> dict[int, RankIcSummary]:
    """按自然年拆分的 RankIC（观察因子有效性的 regime 依赖）。

    Args:
        df: 含 ``date``/因子/前瞻收益的表。
        factor: 因子列名。
        forward: 前瞻收益列名。

    Returns:
        dict[int, RankIcSummary]: 年份 → 汇总。
    """
    if "date" not in df.columns:
        return {}
    years = df.with_columns(pl.col("date").dt.year().alias("year"))
    result: dict[int, RankIcSummary] = {}
    for year, group in years.group_by("year"):
        result[int(year[0])] = summarize(daily_rank_ic(group, factor, forward))
    return dict(sorted(result.items()))


def _batch_stats(
    df: pl.DataFrame,
    factors: list[str],
    buckets: int = 10,
) -> tuple[
    dict[str, list[float]],
    dict[int, dict[str, list[float]]],
    dict[str, list[tuple[int, int, float]]],
]:
    """一次遍历算出多因子的逐日 RankIC、分年 RankIC 与十分位收益。

    Args:
        df: 含 ``date``/因子/前瞻收益的表。
        factors: 因子列名列表。
        buckets: 十分位分组数。

    Returns:
        tuple: (逐日 IC, 分年 IC, 十分位累计（因子 → [(分组, 样本数, 收益和)])。
    """
    batch = _FactorBatch(factors, buckets)
    for _, group in df.group_by("date"):
        batch.add(group)
    return batch.result()


def study_factors(
    panel: pl.DataFrame,
    factors: list[str],
    holding_days: int,
    price: str = "open",
    buckets: int = 10,
) -> list[SingleFactorResult]:
    """批量检验多个因子，共用前瞻收益并独立处理缺失值。

    Args:
        panel: 因子面板（需含 ``date``/``asset``/因子列）。
        factors: 因子列名列表。
        holding_days: 持有交易日数 N。
        price: 价格字段。
        buckets: 十分位分组数。

    Returns:
        list[SingleFactorResult]: 每个因子的检验结果。
    """
    missing = [f for f in factors if f not in panel.columns]
    if missing:
        raise KeyError(f"面板缺少因子列: {', '.join(missing)}")
    prepared = prepare_forward_returns(panel, holding_days, price)
    usable = prepared.filter(pl.col("valid") & pl.col("forward").is_not_null())
    ics, year_ics, deciles = _batch_stats(usable, factors, buckets=buckets)
    results: list[SingleFactorResult] = []
    for factor in factors:
        buckets_out = [
            DecileBucket(bucket=bucket, n_samples=n, mean_forward=total / n)
            for bucket, n, total in deciles[factor]
        ]
        results.append(
            SingleFactorResult(
                factor=factor,
                holding_days=holding_days,
                price=price,
                rank_ic=summarize(ics[factor]),
                deciles=buckets_out,
                by_year={
                    year: summarize(values.get(factor, []))
                    for year, values in sorted(year_ics.items())
                },
                n_rows=usable.height,
            )
        )
    return results


def study_single_factor(
    panel: pl.DataFrame,
    factor: str,
    holding_days: int,
    price: str = "open",
    buckets: int = 10,
) -> SingleFactorResult:
    """对单个因子做前瞻收益检验。

    Args:
        panel: 因子面板（需含 ``date``/``asset``/因子列）。
        factor: 因子列名。
        holding_days: 持有交易日数 N（1 → t1 开盘买、t2 开盘卖）。
        price: 价格字段。
        buckets: 十分位分组数。

    Returns:
        SingleFactorResult: 检验结果。
    """
    if factor not in panel.columns:
        raise KeyError(f"面板缺少因子列: {factor}")
    prepared = prepare_forward_returns(panel, holding_days, price)
    usable = prepared.filter(pl.col("valid") & pl.col("forward").is_not_null())
    ics = daily_rank_ic(usable, factor)
    return SingleFactorResult(
        factor=factor,
        holding_days=holding_days,
        price=price,
        rank_ic=summarize(ics),
        deciles=decile_profile(usable, factor, buckets=buckets),
        by_year=yearly_rank_ic(usable, factor),
        n_rows=usable.height,
    )


def load_factor_panel(
    start: datetime.date,
    end: datetime.date,
    assets: list[str] | None = None,
) -> pl.DataFrame:
    """加载日线并计算因子面板（含交易日序号）。

    Args:
        start: 起始日期。
        end: 结束日期。
        assets: 限定资产；``None`` 表示全市场。

    Returns:
        pl.DataFrame: 因子面板。
    """
    from quantide.data.models.daily_bars import daily_bars
    from quantide.factors.alpha import compute_alpha_features

    raw = daily_bars.get_bars_in_range(start, end, assets=assets, adjust=None, eager_mode=True)
    if isinstance(raw, pl.LazyFrame):
        raw = raw.collect()
    if raw is None or raw.is_empty():
        return pl.DataFrame()
    raw = raw.with_columns(pl.col("date").cast(pl.Date)).sort(["asset", "date"])
    return ensure_trading_index(compute_alpha_features(raw))


def format_report(results: list[SingleFactorResult]) -> str:
    """把检验结果格式化成可读表格。

    Args:
        results: 检验结果列表。

    Returns:
        str: 文本报告。
    """
    lines: list[str] = []
    for result in results:
        lines.append(
            f"{result.factor} | 持有 {result.holding_days} 日（{result.price}）"
            f" | RankIC {result.rank_ic.mean:+.4f} (t={result.rank_ic.t_stat:+.2f},"
            f" n={result.rank_ic.n_days}日) | 有效样本 {result.n_rows}"
        )
        if result.deciles:
            head = "    十分位(1=最低): " + "  ".join(
                f"D{d.bucket}:{d.mean_forward * 100:+.2f}%" for d in result.deciles
            )
            lines.append(head)
        for year, summary in result.by_year.items():
            lines.append(
                f"    {year} 年: RankIC {summary.mean:+.4f} (t={summary.t_stat:+.2f},"
                f" n={summary.n_days})"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(description="单因子前瞻收益检验")
    parser.add_argument("--factors", nargs="+", default=[DEFAULT_FACTOR])
    parser.add_argument("--holdings", nargs="+", type=int, default=list(DEFAULT_HOLDING_DAYS))
    parser.add_argument("--start", default="2022-06-01")
    parser.add_argument("--end", default="2026-10-19")
    parser.add_argument("--price", default="open")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--data-home", default=None, help="行情目录；默认使用已保存的配置")
    args = parser.parse_args(argv)

    from quantide.data import init_data

    init_data(args.data_home)
    panel = load_factor_panel(
        datetime.date.fromisoformat(args.start), datetime.date.fromisoformat(args.end)
    )
    results: list[SingleFactorResult] = []
    for factor in args.factors:
        for holding in args.holdings:
            try:
                results.append(study_single_factor(panel, factor, holding, price=args.price))
            except KeyError as exc:
                print(f"跳过 {factor}: {exc}")
    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        print(format_report(results))
    return 0


class _FactorBatch:
    """Accumulate per-day IC, yearly IC and bucket returns in a single traversal."""

    def __init__(self, factors: list[str], buckets: int) -> None:
        self.factors, self.buckets = factors, buckets
        self.ics: dict[str, list[float]] = {factor: [] for factor in factors}
        self.year_ics: dict[int, dict[str, list[float]]] = {}
        self.sums = {factor: np.zeros(buckets + 1) for factor in factors}
        self.counts = {factor: np.zeros(buckets + 1) for factor in factors}

    def add(self, group: pl.DataFrame) -> None:
        if group.height < MIN_CROSS_SECTION:
            return
        y = group["forward"].to_numpy().astype(float)
        year = group["date"][0].year if hasattr(group["date"][0], "year") else None
        for factor in self.factors:
            self._add_factor(factor, group[factor].to_numpy().astype(float), y, year)

    def _add_factor(self, factor: str, x: np.ndarray, y: np.ndarray, year: int | None) -> None:
        mask = np.isfinite(x) & np.isfinite(y)
        if int(mask.sum()) < MIN_CROSS_SECTION:
            return
        x, y = x[mask], y[mask]
        value = _spearman(x, y)
        if not math.isnan(value):
            self.ics[factor].append(value)
            if year is not None:
                self.year_ics.setdefault(int(year), {}).setdefault(factor, []).append(value)
        labels = np.floor(_average_ranks(x) / len(x) * self.buckets).astype(int) + 1
        self._add_buckets(factor, labels, y)

    def _add_buckets(self, factor: str, labels: np.ndarray, y: np.ndarray) -> None:
        for bucket in range(1, self.buckets + 1):
            picked = y[labels == bucket]
            if picked.size:
                self.sums[factor][bucket] += float(picked.sum())
                self.counts[factor][bucket] += int(picked.size)

    def result(
        self,
    ) -> tuple[
        dict[str, list[float]],
        dict[int, dict[str, list[float]]],
        dict[str, list[tuple[int, int, float]]],
    ]:
        deciles = {
            factor: [
                (bucket, int(self.counts[factor][bucket]), float(self.sums[factor][bucket]))
                for bucket in range(1, self.buckets + 1)
                if self.counts[factor][bucket]
            ]
            for factor in self.factors
        }
        return self.ics, self.year_ics, deciles


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
