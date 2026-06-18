#!/usr/bin/env python3
"""Build the unit test environment per test plan §2.4 / §2.5.

Pulls 2022 data for 105 hand-picked assets (NOT overlapping with e2e universe)
from Tushare, then writes parquet fixtures + env_manifest.json.

Universe selection criteria (test plan §2.4.2):
  - 50 ordinary active stocks
  - 10 ST / *ST (at some point in 2022)
  - 10 newly IPO'd in 2022
  - 10 delisted in 2022
  - 10 创业板/科创板 (±20% limit)
  - 10 长期停牌 (>=5 trading days suspended in 2022)
  - 5  分红/除权 (had dividend events in 2022)

Usage:
    TUSHARE_TOKEN=xxx python build_env.py
    TUSHARE_TOKEN=xxx python build_env.py --dry-run   # show plan, do not write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import polars as pl
import tushare as ts

# -- Config --------------------------------------------------------------

TOKEN_ENV = "TUSHARE_TOKEN"
START_DATE = "20220101"
END_DATE = "20221231"
EXPECTED_TRADING_DAYS = 242  # 2022 SSE trading days; SZSE has 242 too

# Categories with target counts (test plan §2.4.2 unit version)
CATEGORY_TARGETS = {
    "ordinary": 50,
    "st": 10,
    "ipo": 10,
    "delisted": 10,
    "chinext_star": 10,
    "suspended": 10,
    "dividend_adjust": 5,
}
TOTAL = sum(CATEGORY_TARGETS.values())

# -- Paths ---------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
UNIT_ROOT = SCRIPT_DIR.parent
FIXTURES = UNIT_ROOT / "fixtures" / "data"
FIXTURES.mkdir(parents=True, exist_ok=True)
MANIFEST = UNIT_ROOT / "env_manifest.json"
UNIVERSE_FILE = UNIT_ROOT / "universe.json"

# -- Helpers -------------------------------------------------------------

def get_pro():
    token = os.environ.get(TOKEN_ENV)
    if not token:
        sys.exit(f"ERROR: ${TOKEN_ENV} not set. Export Tushare token first.")
    return ts.pro_api(token)


def _rate_limit():
    time.sleep(0.3)  # Tushare rate limit: 3 calls/sec


def fetch_with_retry(pro, fn_name, **kwargs):
    """Call pro.<fn>(**kwargs); retry on rate limit; raise otherwise."""
    _rate_limit()
    fn = getattr(pro, fn_name)
    return fn(**kwargs)


# -- Universe selection --------------------------------------------------

E2E_UNIVERSE_PARQUET = Path("tests/assets/real/real_universe.parquet")


def load_e2e_excluded() -> set[str]:
    """Load assets used by the e2e universe; unit universe must not reuse them."""
    if not E2E_UNIVERSE_PARQUET.exists():
        return set()
    df = pl.read_parquet(E2E_UNIVERSE_PARQUET, columns=["asset"])
    return set(df["asset"].to_list())


def select_universe(pro) -> pl.DataFrame:
    """Return a DataFrame of 105 assets with category column."""
    excluded = load_e2e_excluded()
    print(f"[universe] e2e excluded: {len(excluded)} assets")

    # 1. All stocks listed (L) or delisted (D) that touch 2022
    basic = fetch_with_retry(
        pro, "stock_basic",
        list_status="L,D",
        fields="ts_code,name,list_date,delist_date,exchange,industry",
    )
    basic["list_date"] = pd.to_numeric(basic["list_date"], errors="coerce")
    basic["delist_date"] = pd.to_numeric(basic["delist_date"], errors="coerce")
    basic = basic.dropna(subset=["list_date"])
    # Active in 2022: listed before/at 2022-end, and (no delist or delist in 2022+)
    in_2022 = basic[
        (basic["list_date"] <= 20221231)
        & ((basic["delist_date"].isna()) | (basic["delist_date"] >= 20220101))
    ].copy()
    print(f"[universe] active in 2022: {len(in_2022)}")

    # Filter out e2e
    in_2022 = in_2022[~in_2022["ts_code"].isin(excluded)]
    print(f"[universe] active in 2022 (excl. e2e): {len(in_2022)}")

    # 2. ST: any point in 2022 was ST
    st_df = fetch_with_retry(pro, "stock_st", start_date=START_DATE, end_date=END_DATE)
    st_codes = set(st_df["ts_code"].unique())
    st_in_2022 = in_2022[in_2022["ts_code"].isin(st_codes) & (in_2022["ts_code"].isin(st_codes))]
    print(f"[universe] ST candidates: {len(st_in_2022)}")
    st_pick = st_in_2022.sample(
        n=min(CATEGORY_TARGETS["st"], len(st_in_2022)), random_state=2022
    )

    # 3. IPO in 2022
    ipo_in_2022 = in_2022[(in_2022["list_date"] >= 20220101) & (in_2022["list_date"] <= 20221231)]
    print(f"[universe] IPO 2022 candidates: {len(ipo_in_2022)}")
    ipo_pick = ipo_in_2022.sample(
        n=min(CATEGORY_TARGETS["ipo"], len(ipo_in_2022)), random_state=2022
    )

    # 4. Delisted in 2022
    delisted_in_2022 = in_2022[
        (in_2022["delist_date"] >= 20220101) & (in_2022["delist_date"] <= 20221231)
    ]
    print(f"[universe] delisted 2022 candidates: {len(delisted_in_2022)}")
    delisted_pick = delisted_in_2022.sample(
        n=min(CATEGORY_TARGETS["delisted"], len(delisted_in_2022)), random_state=2022
    )

    # 5. 创业板 (30x.xx, SZSE) + 科创板 (688xxx, SSE)
    chinext_star = in_2022[
        in_2022["ts_code"].str.match(r"^30\d{4}\.SZ$|^688\d{3}\.SH$")
    ]
    chinext_pick = chinext_star.sample(
        n=min(CATEGORY_TARGETS["chinext_star"], len(chinext_star)), random_state=2022
    )
    print(f"[universe] chinext+star candidates: {len(chinext_star)}")

    # 6. 长期停牌: pull suspend_d for all 2022 trading days, count per asset
    print("[universe] fetching suspend_d for 2022 (242 days)...")
    suspend_dfs = []
    # batch by month
    for m in range(1, 13):
        m_start = f"2022{m:02d}01"
        m_end = f"2022{m:02d}31"
        sd = fetch_with_retry(pro, "suspend_d", start_date=m_start, end_date=m_end)
        if not sd.empty:
            suspend_dfs.append(sd)
    suspend_all = pd.concat(suspend_dfs, ignore_index=True) if suspend_dfs else pd.DataFrame()
    suspend_counts = (
        suspend_all.groupby("ts_code").size().reset_index(name="suspend_days")
    )
    suspended_assets = set(
        suspend_counts[suspend_counts["suspend_days"] >= 5]["ts_code"]
    )
    suspended_in_2022 = in_2022[in_2022["ts_code"].isin(suspended_assets)]
    print(f"[universe] suspended >=5 days candidates: {len(suspended_in_2022)}")
    suspended_pick = suspended_in_2022.sample(
        n=min(CATEGORY_TARGETS["suspended"], len(suspended_in_2022)), random_state=2022
    )

    # 7. 分红/除权: pull dividend for 2022
    div_df = fetch_with_retry(pro, "dividend", start_date=START_DATE, end_date=END_DATE)
    div_assets = set(div_df["ts_code"].unique())
    div_in_2022 = in_2022[in_2022["ts_code"].isin(div_assets)]
    print(f"[universe] dividend candidates: {len(div_in_2022)}")
    div_pick = div_in_2022.sample(
        n=min(CATEGORY_TARGETS["dividend_adjust"], len(div_in_2022)), random_state=2022
    )

    # 8. Ordinary: remaining (excl. picked)
    picked_so_far = set()
    for pick_df in (st_pick, ipo_pick, delisted_pick, chinext_pick, suspended_pick, div_pick):
        picked_so_far.update(pick_df["ts_code"].tolist())
    ordinary_pool = in_2022[~in_2022["ts_code"].isin(picked_so_far)]
    ordinary_pick = ordinary_pool.sample(
        n=min(CATEGORY_TARGETS["ordinary"], len(ordinary_pool)), random_state=2022
    )
    print(f"[universe] ordinary candidates: {len(ordinary_pool)}")

    # Assemble
    rows = []
    for cat, df in [
        ("ordinary", ordinary_pick), ("st", st_pick), ("ipo", ipo_pick),
        ("delisted", delisted_pick), ("chinext_star", chinext_pick),
        ("suspended", suspended_pick), ("dividend_adjust", div_pick),
    ]:
        for _, r in df.iterrows():
            rows.append({
                "asset": r["ts_code"],
                "name": r["name"],
                "category": cat,
                "list_date": r["list_date"],
                "delist_date": r["delist_date"] if pd.notna(r["delist_date"]) else None,
                "exchange": r["exchange"],
            })

    universe = pl.DataFrame(rows)
    if universe.height != universe["asset"].n_unique():
        dup_count = universe.height - universe["asset"].n_unique()
        print(f"[universe] WARN: {dup_count} duplicate assets across categories; deduping (keep first)")
        universe = universe.unique(subset=["asset"], keep="first")

    print(f"[universe] pre-data-fetch: {universe.height} assets")

    return universe


# -- Data fetching -------------------------------------------------------

def fetch_daily(pro, ts_codes: list[str]) -> pl.DataFrame:
    """Fetch daily bars (ohlcv + amount) for all assets."""
    print(f"[daily] fetching for {len(ts_codes)} assets...")
    frames = []
    for i, code in enumerate(ts_codes, 1):
        df = fetch_with_retry(pro, "daily", ts_code=code,
                              start_date=START_DATE, end_date=END_DATE)
        if not df.empty:
            frames.append(df)
        if i % 10 == 0:
            print(f"[daily] {i}/{len(ts_codes)}")
    if not frames:
        return pl.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.rename(columns={"ts_code": "asset", "trade_date": "date", "vol": "volume"})
    return pl.from_pandas(full[["asset", "date", "open", "high", "low", "close", "volume", "amount"]])


def fetch_adj_factor(pro, ts_codes: list[str]) -> pl.DataFrame:
    """Fetch adjustment factors for all assets."""
    print(f"[adj_factor] fetching for {len(ts_codes)} assets...")
    frames = []
    for i, code in enumerate(ts_codes, 1):
        df = fetch_with_retry(pro, "adj_factor", ts_code=code,
                              start_date=START_DATE, end_date=END_DATE)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.rename(columns={"ts_code": "asset", "trade_date": "date"})
    return pl.from_pandas(full[["asset", "date", "adj_factor"]])


def fetch_st_info(pro, ts_codes: list[str]) -> pl.DataFrame:
    """Fetch daily ST status (re-derive is_st from stock_st)."""
    print("[st_info] fetching stock_st 2022...")
    st_df = fetch_with_retry(pro, "stock_st", start_date=START_DATE, end_date=END_DATE)
    if st_df.empty:
        return pl.DataFrame()
    st_df["is_st"] = (st_df["type"].str.contains("ST", na=False)).astype(int)
    st_df = st_df.rename(columns={"ts_code": "asset", "trade_date": "date"})
    out = st_df[["asset", "date", "is_st"]].copy()
    out = out[out["asset"].isin(ts_codes)]
    return pl.from_pandas(out)


def fetch_limit(pro, ts_codes: list[str]) -> pl.DataFrame:
    """Fetch limit prices (up_limit, down_limit) via stk_limit."""
    print(f"[limit] fetching stk_limit for {len(ts_codes)} assets...")
    frames = []
    for i, code in enumerate(ts_codes, 1):
        df = fetch_with_retry(pro, "stk_limit", ts_code=code,
                              start_date=START_DATE, end_date=END_DATE)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    full = pd.concat(frames, ignore_index=True)
    full = full.rename(columns={"ts_code": "asset", "trade_date": "date"})
    keep = [c for c in ["asset", "date", "up_limit", "down_limit"] if c in full.columns]
    return pl.from_pandas(full[keep])


def fetch_calendar(pro) -> pl.DataFrame:
    """Fetch 2022 trade calendar (SSE)."""
    print("[calendar] fetching 2022 SSE trade calendar...")
    df = fetch_with_retry(pro, "trade_cal", exchange="SSE",
                          start_date=START_DATE, end_date=END_DATE)
    df["is_open"] = df["is_open"].astype(int)
    df = df.rename(columns={"cal_date": "date"})
    return pl.from_pandas(df[["exchange", "date", "is_open", "pretrade_date"]])


# -- Write ---------------------------------------------------------------

def write_manifest(universe: pl.DataFrame, daily: pl.DataFrame, n_rows: dict):
    manifest = {
        "version": 1,
        "kind": "unit",
        "data_source": "tushare",
        "date_range": [START_DATE, END_DATE],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "asset_count": universe.height,
        "categories": dict(universe.group_by("category").len().iter_rows()),
        "row_counts": n_rows,
        "expected_trading_days": EXPECTED_TRADING_DAYS,
        "tushare_token": os.environ.get(TOKEN_ENV, "")[:8] + "***",
        "excludes_e2e_universe": True,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[manifest] {MANIFEST}")


# -- Main ----------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="select universe, do not fetch data")
    p.add_argument("--skip-fetch", action="store_true", help="use cached parquet, no tushare")
    args = p.parse_args()

    if args.dry_run:
        pro = get_pro()
        universe = select_universe(pro)
        print(f"[dry-run] would fetch: daily + adj + st + limit for {universe.height} assets")
        return

    pro = get_pro()
    universe = select_universe(pro)

    universe.write_json(UNIVERSE_FILE)
    print(f"[universe.json] {UNIVERSE_FILE}")

    if not args.skip_fetch:
        ts_codes = universe["asset"].to_list()
        daily = fetch_daily(pro, ts_codes)

        fetched_assets = daily["asset"].unique().to_list()
        missing = set(ts_codes) - set(fetched_assets)
        if missing:
            print(f"[daily] WARN: {len(missing)} assets returned 0 daily rows; removing from universe: {missing}")
            universe = universe.filter(~pl.col("asset").is_in(list(missing)))
            universe.write_json(UNIVERSE_FILE)
            print(f"[universe.json] updated to {universe.height} assets")
            ts_codes = universe["asset"].to_list()

        daily.write_parquet(FIXTURES / "daily_bars.parquet")
        print(f"[daily] {FIXTURES / 'daily_bars.parquet'} rows={daily.height}")

        adj = fetch_adj_factor(pro, ts_codes)
        adj.write_parquet(FIXTURES / "adj_factor.parquet")
        print(f"[adj_factor] {FIXTURES / 'adj_factor.parquet'} rows={adj.height}")

        st_info = fetch_st_info(pro, ts_codes)
        st_info.write_parquet(FIXTURES / "st_info.parquet")
        print(f"[st_info] {FIXTURES / 'st_info.parquet'} rows={st_info.height}")

        limit = fetch_limit(pro, ts_codes)
        limit.write_parquet(FIXTURES / "limit_price.parquet")
        print(f"[limit_price] {FIXTURES / 'limit_price.parquet'} rows={limit.height}")

        calendar = fetch_calendar(pro)
        calendar.write_parquet(FIXTURES / "calendar.parquet")
        print(f"[calendar] {FIXTURES / 'calendar.parquet'} rows={calendar.height}")

        n_rows = {
            "daily": daily.height, "adj_factor": adj.height,
            "st_info": st_info.height, "limit_price": limit.height,
            "calendar": calendar.height,
        }
    else:
        daily = pl.read_parquet(FIXTURES / "daily_bars.parquet")
        n_rows = {"daily": daily.height}

    write_manifest(universe, daily, n_rows)
    print(f"\nDONE. Universe: {universe.height} assets.")


if __name__ == "__main__":
    main()
