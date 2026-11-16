"""Pre-registered random controls and label permutation for factor audits."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from typing import Any

import polars as pl

from quantide.factors.research import ICSummary, daily_rank_ic, summarize_ic


@dataclass(frozen=True)
class StatisticalProfile:
    alpha: float = 0.05
    power: float = 0.8
    seeds: tuple[int, ...] = (0,)
    permutations: int = 100
    min_cross_section: int = 100

    def __post_init__(self) -> None:
        if not 0 < self.alpha < 1 or not 0 < self.power < 1:
            raise ValueError("alpha and power must be between zero and one")
        if not self.seeds or self.permutations < 1 or self.min_cross_section < 2:
            raise ValueError("invalid statistical profile")

    def as_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "power": self.power,
            "seeds": list(self.seeds),
            "permutations": self.permutations,
            "min_cross_section": self.min_cross_section,
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def random_factor(
    panel: pl.DataFrame,
    *,
    seed: int = 0,
    date_col: str = "date",
    name: str = "random_factor",
) -> pl.DataFrame:
    if date_col not in panel.columns:
        raise ValueError(f"panel missing date column: {date_col}")
    generator = random.Random(seed)
    return panel.with_columns(pl.Series(name, [generator.random() for _ in range(panel.height)]))


def _shuffle_buckets(values: list[Any], dates: list[Any], seed: int) -> list[Any]:
    indices: dict[Any, list[int]] = {}
    for index, day in enumerate(dates):
        indices.setdefault(day, []).append(index)
    generator = random.Random(seed)
    shuffled = list(values)
    for day in sorted(indices, key=str):
        positions = indices[day]
        bucket = [values[index] for index in positions]
        generator.shuffle(bucket)
        for position, value in zip(positions, bucket, strict=True):
            shuffled[position] = value
    return shuffled


def permute_within_date(
    panel: pl.DataFrame,
    value_col: str,
    *,
    seed: int = 0,
    date_col: str = "date",
    name: str | None = None,
) -> pl.DataFrame:
    if value_col not in panel.columns or date_col not in panel.columns:
        raise ValueError("panel missing permutation columns")
    target = name or f"{value_col}_permuted"
    shuffled = _shuffle_buckets(panel[value_col].to_list(), panel[date_col].to_list(), seed)
    return panel.with_columns(pl.Series(target, shuffled, dtype=panel[value_col].dtype))


def rank_ic_summary(
    panel: pl.DataFrame,
    factor: str,
    *,
    forward_col: str = "forward",
    min_cross_section: int = 100,
) -> ICSummary:
    if forward_col not in panel.columns:
        raise ValueError(f"panel missing forward column: {forward_col}")
    points = daily_rank_ic(panel, factor, min_cross_section, forward_col)
    return summarize_ic([point.ic for point in points])


def empirical_p_value(observed: float, null_values: list[float]) -> float:
    if not null_values:
        raise ValueError("null distribution is empty")
    extreme = sum(abs(value) >= abs(observed) for value in null_values)
    return (extreme + 1) / (len(null_values) + 1)


def null_rank_ic_distribution(
    panel: pl.DataFrame,
    factor: str,
    profile: StatisticalProfile,
    *,
    forward_col: str = "forward",
) -> list[ICSummary]:
    results = []
    for seed in profile.seeds:
        for index in range(profile.permutations):
            permuted = permute_within_date(
                panel,
                factor,
                seed=seed * 1_000_003 + index,
                name=f"{factor}_null",
            )
            results.append(
                rank_ic_summary(
                    permuted,
                    f"{factor}_null",
                    forward_col=forward_col,
                    min_cross_section=profile.min_cross_section,
                )
            )
    return results


def summarize_null_distribution(
    observed: ICSummary, nulls: list[ICSummary], profile: StatisticalProfile
) -> dict[str, Any]:
    if observed.mean is None:
        return {
            "status": "INCONCLUSIVE",
            "reason": "observed IC undefined",
            "profile": profile.as_dict(),
        }
    values = [item.mean for item in nulls if item.mean is not None]
    expected = profile.permutations * len(profile.seeds)
    if not values:
        return {
            "status": "INCONCLUSIVE",
            "reason": "null distribution undefined",
            "profile": profile.as_dict(),
        }
    if len(values) < expected:
        return {
            "status": "INCONCLUSIVE",
            "reason": "insufficient null samples",
            "null_count": len(values),
            "expected_count": expected,
            "profile": profile.as_dict(),
        }
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)
    p_value = empirical_p_value(observed.mean, values)
    return {
        "status": "OK",
        "observed_ic": observed.mean,
        "null_mean": mean,
        "null_std": math.sqrt(variance),
        "null_count": len(values),
        "expected_count": expected,
        "p_value": p_value,
        "threshold": profile.alpha,
        "significant": p_value <= profile.alpha,
        "profile": profile.as_dict(),
    }
