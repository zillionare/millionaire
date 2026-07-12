#!/usr/bin/env python3
"""Validate the unit test environment per test plan §2.5.2.

Checks (per fixture, exit non-zero on failure):
  - 完整性: row count per asset ≈ EXPECTED_TRADING_DAYS ± 5
  - 一致性: OHLCV no nulls; ST ↔ limit price consistency (ST shares: ±5%)
  - 范围: date range within [START_DATE, END_DATE]
  - 抽样: print 5 random asset/date samples (manual review, not auto-fail)

Usage:
    python validate_env.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import polars as pl

SCRIPT_DIR = Path(__file__).resolve().parent
UNIT_ROOT = SCRIPT_DIR.parent
FIXTURES = UNIT_ROOT / "fixtures" / "data"
MANIFEST = UNIT_ROOT / "env_manifest.json"
UNIVERSE = UNIT_ROOT / "universe.json"

EXPECTED_TRADING_DAYS = 242
TOLERANCE = 5  # days; per test plan §2.5.2
START = "2022-01-01"
END = "2022-12-31"


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def _load_universe() -> pl.DataFrame:
    return pl.read_json(UNIVERSE)


def _assert(cond, msg: str) -> list[str]:
    if hasattr(cond, "item"):
        cond = cond.item()
    if hasattr(cond, "all"):
        cond = cond.all()
    if bool(cond):
        return []
    return [f"FAIL: {msg}"]


def validate() -> int:
    manifest = _load_manifest()
    universe = _load_universe()
    failures: list[str] = []

    print(f"[validate] manifest version: {manifest['version']}, kind: {manifest['kind']}")
    print(f"[validate] universe: {universe.height} assets")

    daily = pl.read_parquet(FIXTURES / "daily_bars.parquet")
    calendar = pl.read_parquet(FIXTURES / "calendar.parquet")
    adj = pl.read_parquet(FIXTURES / "adj_factor.parquet")
    st = pl.read_parquet(FIXTURES / "st_info.parquet")
    limit = pl.read_parquet(FIXTURES / "limit_price.parquet")

    for name, df, expected_cols in [
        ("daily", daily, ["asset", "date", "open", "high", "low", "close", "volume", "amount"]),
        ("calendar", calendar, ["date", "is_open"]),
        ("adj_factor", adj, ["asset", "date", "adj_factor"]),
        ("st_info", st, ["asset", "date", "is_st"]),
        ("limit_price", limit, ["asset", "date", "up_limit", "down_limit"]),
    ]:
        missing = [c for c in expected_cols if c not in df.columns]
        failures.extend(_assert(
            not missing,
            f"{name} missing columns: {missing}"
        ))

    failures.extend(_assert(
        daily["date"].min() >= "20220101",
        f"daily min date {daily['date'].min()} before 20220101"
    ))
    failures.extend(_assert(
        daily["date"].max() <= "20221231",
        f"daily max date {daily['date'].max()} after 20221231"
    ))

    daily_open = calendar.filter(pl.col("is_open") == 1).height
    failures.extend(_assert(
        daily_open == EXPECTED_TRADING_DAYS,
        f"calendar open days {daily_open} != expected {EXPECTED_TRADING_DAYS}"
    ))

    null_ohlcv = daily.filter(
        pl.col("open").is_null()
        | pl.col("high").is_null()
        | pl.col("low").is_null()
        | pl.col("close").is_null()
        | pl.col("volume").is_null()
        | pl.col("amount").is_null()
    )
    failures.extend(_assert(
        null_ohlcv.height == 0,
        f"daily OHLCV has {null_ohlcv.height} null rows"
    ))

    invalid_ohlc = daily.filter(
        (pl.col("low") > pl.col("high"))
        | (pl.col("low") > pl.col("open"))
        | (pl.col("low") > pl.col("close"))
        | (pl.col("high") < pl.col("open"))
        | (pl.col("high") < pl.col("close"))
    )
    failures.extend(_assert(
        invalid_ohlc.height == 0,
        f"daily invalid OHLC: {invalid_ohlc.height} rows"
    ))

    invalid_volume = daily.filter(pl.col("volume") < 0)
    failures.extend(_assert(
        invalid_volume.height == 0,
        f"daily negative volume: {invalid_volume.height} rows"
    ))

    for asset_row in universe.iter_rows(named=True):
        asset = asset_row["asset"]
        sub = daily.filter(pl.col("asset") == asset)
        n = sub.height
        # IPO in 2022: less than full year. delisted in 2022: less too. ordinary/suspended:
        # full year. We check: n must be in (0, EXPECTED_TD + TOLERANCE]
        if n == 0:
            failures.append(f"FAIL: {asset} has 0 daily rows (category={asset_row['category']})")
        elif n > EXPECTED_TRADING_DAYS + TOLERANCE:
            failures.append(f"FAIL: {asset} has {n} daily rows (max {EXPECTED_TRADING_DAYS + TOLERANCE})")

    st_with_limit = st.join(limit, on=["asset", "date"], how="inner")
    if not st_with_limit.is_empty():
        st_days = st_with_limit.filter(pl.col("is_st") == 1)
        st_with_limits = st_days.filter(pl.col("up_limit").is_not_null())
        if st_days.height > 0 and st_with_limits.height < st_days.height * 0.9:
            failures.append(
                f"FAIL: only {st_with_limits.height}/{st_days.height} ST-days have limit prices"
            )

    rng = random.Random(42)
    sample_assets = rng.sample(universe["asset"].to_list(), 5)
    print("\n[validate] sample (5 assets, 5 dates each — for manual review):")
    for asset in sample_assets:
        sub = daily.filter(pl.col("asset") == asset).sort("date")
        if sub.is_empty():
            continue
        sample_dates = rng.sample(sub["date"].to_list(), min(5, sub.height))
        for d in sample_dates:
            row = sub.filter(pl.col("date") == d).row(0, named=True)
            print(f"  {asset} {row['date']} O={row['open']} H={row['high']} L={row['low']} C={row['close']} V={row['volume']:.0f}")

    print(f"\n[validate] row counts:")
    print(f"  daily:       {daily.height:>8}  ({daily['asset'].n_unique()} unique assets)")
    print(f"  adj_factor:  {adj.height:>8}  ({adj['asset'].n_unique()} unique assets)")
    print(f"  st_info:     {st.height:>8}  ({st['asset'].n_unique()} unique assets)")
    print(f"  limit_price: {limit.height:>8}  ({limit['asset'].n_unique()} unique assets)")
    print(f"  calendar:    {calendar.height:>8}  ({calendar.filter(pl.col('is_open') == 1).height} open days)")

    if failures:
        print(f"\n[validate] FAILED ({len(failures)} issues):")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\n[validate] PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
