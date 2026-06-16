"""真实 tushare fixture 生成器

按 test-plan §1.1 要求:
- 数据范围 2023-01-01 ~ 2025-12-31
- 105 个标的,覆盖 7 类边界场景
- 数据来源: tushare 真实历史
- 30m/tick 允许合成(tushare 不提供)

用法:
    TUSHARE_TOKEN=<token> python tests/e2e/fixtures/fetch_tushare.py tests/assets/real

注意:
- tushare 限速较严(~50/min);脚本已加 sleep
- 数据量较大(105 标的 × 3 年 ≈ 5-10 万行),需要几分钟
- 中途失败可重跑:已下载的标的不再重复拉
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

import pandas as pd
import tushare as ts


START_DATE = datetime.date(2023, 1, 1)
END_DATE = datetime.date(2025, 12, 31)


# ───────────────────── 资产筛选 ─────────────────────


def _list_all_basic(pro: ts.pro_api) -> pd.DataFrame:
    """全 A 证券列表(含已退市)"""
    frames = []
    for status in ("L", "D", "P"):
        df = pro.stock_basic(
            list_status=status,
            fields="ts_code,name,list_date,delist_date,exchange,industry",
        )
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        raise RuntimeError("no stock_basic data fetched")
    all_df = pd.concat(frames, ignore_index=True)
    all_df["list_date"] = pd.to_datetime(all_df["list_date"], format="%Y%m%d", errors="coerce")
    all_df["delist_date"] = pd.to_datetime(all_df["delist_date"], format="%Y%m%d", errors="coerce")
    return all_df


def select_universe(pro: ts.pro_api, target_count_per_category: dict[str, int]) -> pd.DataFrame:
    """按类别选 105 个标的"""
    print("fetching stock_basic...", flush=True)
    all_basic = _list_all_basic(pro)
    print(f"  total assets: {len(all_basic)}", flush=True)

    picked = []

    # ordinary: 活跃股(交易所 SSE/SZSE),按代码排序前 N
    ordinary_pool = all_basic[
        (all_basic["exchange"].isin(["SSE", "SZSE"]))
        & (all_basic["list_date"] <= pd.Timestamp("2022-12-31"))
        & (all_basic["delist_date"].isna())
    ].sort_values("ts_code").head(200)  # 候选池
    picked.append(("ordinary", ordinary_pool.sample(
        n=min(target_count_per_category["ordinary"], len(ordinary_pool)),
        random_state=42,
    )))

    # ST: 名称含 ST
    st_pool = all_basic[all_basic["name"].str.contains("ST", na=False)]
    picked.append(("st", st_pool.sample(
        n=min(target_count_per_category["st"], len(st_pool)),
        random_state=42,
    )))

    # ipo: 2023-01-01 ~ 2025-12-31 上市
    ipo_pool = all_basic[
        (all_basic["list_date"] >= pd.Timestamp(START_DATE))
        & (all_basic["list_date"] <= pd.Timestamp(END_DATE))
    ]
    picked.append(("ipo", ipo_pool.sample(
        n=min(target_count_per_category["ipo"], len(ipo_pool)),
        random_state=42,
    )))

    # delisted: 2023-01-01 ~ 2025-12-31 退市
    delisted_pool = all_basic[
        (all_basic["delist_date"] >= pd.Timestamp(START_DATE))
        & (all_basic["delist_date"] <= pd.Timestamp(END_DATE))
    ]
    picked.append(("delisted", delisted_pool.sample(
        n=min(target_count_per_category["delisted"], len(delisted_pool)),
        random_state=42,
    )))

    # chinext_star: 创业板(30/301 开头)+ 科创板(688/689 开头)
    cs_pool = all_basic[
        all_basic["ts_code"].str.match(r"(30|301|688|689)\.")
    ]
    picked.append(("chinext_star", cs_pool.sample(
        n=min(target_count_per_category["chinext_star"], len(cs_pool)),
        random_state=42,
    )))

    # suspended: 暂时使用 ordinary 池子;真正停牌判断需日线后再筛
    # 先选若干普通股,后续 fetch_daily 时按"日线连续缺失"筛
    picked.append(("suspended", ordinary_pool.sample(
        n=min(target_count_per_category["suspended"], len(ordinary_pool)),
        random_state=43,  # 不同 seed
    )))

    # dividend_adjust: 占位(从 ordinary 选,后续可换)
    picked.append(("dividend_adjust", ordinary_pool.sample(
        n=min(target_count_per_category["dividend_adjust"], len(ordinary_pool)),
        random_state=44,
    )))

    # 合并 + 标 category
    rows = []
    seen = set()
    for category, df in picked:
        for _, row in df.iterrows():
            if row["ts_code"] in seen:
                continue
            seen.add(row["ts_code"])
            rows.append(
                {
                    "asset": row["ts_code"],
                    "name": row["name"],
                    "category": category,
                    "list_date": row["list_date"].date() if pd.notna(row["list_date"]) else None,
                    "delist_date": row["delist_date"].date() if pd.notna(row["delist_date"]) else None,
                    "exchange": row["exchange"],
                }
            )

    universe = pd.DataFrame(rows)
    print(f"  selected: {len(universe)} (deduplicated from {sum(len(d) for _, d in picked)})", flush=True)
    return universe


# ───────────────────── 日线拉取 ─────────────────────


def fetch_daily(
    pro: ts.pro_api,
    ts_code: str,
    start: datetime.date,
    end: datetime.date,
) -> pd.DataFrame | None:
    """拉单只标的日线"""
    try:
        df = pro.daily(
            ts_code=ts_code,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
    except Exception as e:
        print(f"  [ERROR] {ts_code}: {e}", flush=True)
        return None
    if df is None or df.empty:
        return None
    return df


def fetch_all_daily(
    pro: ts.pro_api,
    universe: pd.DataFrame,
    cache_dir: Path,
    rate_limit_per_min: int = 40,
) -> pd.DataFrame:
    """拉所有标的日线;支持断点续传(已下载的跳过)"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    sleep_between = 60.0 / rate_limit_per_min

    for idx, row in universe.iterrows():
        ts_code = row["asset"]
        cache_file = cache_dir / f"{ts_code.replace('.', '_')}.parquet"

        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                if not df.empty:
                    frames.append(df)
                    continue
            except Exception:
                pass  # 损坏则重拉

        df = fetch_daily(pro, ts_code, START_DATE, END_DATE)
        if df is not None and not df.empty:
            df["asset"] = ts_code  # ensure column
            df.to_parquet(cache_file, index=False)
            frames.append(df)

        time.sleep(sleep_between)

        if (idx + 1) % 20 == 0:
            print(f"  fetched {idx + 1}/{len(universe)}", flush=True)

    if not frames:
        raise RuntimeError("no daily data fetched")
    return pd.concat(frames, ignore_index=True)


# ───────────────────── 涨跌停/ST 历史 ─────────────────────


def fetch_limit_and_st(
    pro: ts.pro_api,
    universe: pd.DataFrame,
    cache_dir: Path,
    rate_limit_per_min: int = 40,
) -> pd.DataFrame:
    """拉涨跌停价 + ST 标志"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    sleep_between = 60.0 / rate_limit_per_min
    frames = []

    for idx, row in universe.iterrows():
        ts_code = row["asset"]
        cache_file = cache_dir / f"limit_{ts_code.replace('.', '_')}.parquet"

        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                if not df.empty:
                    frames.append(df)
                    continue
            except Exception:
                pass

        try:
            # tushare 实际行为:ts_code 参数被忽略,返回所有股票。
            # 因此完整拉取(单次 API 调用覆盖 3 年)→ 本地按 ts_code 过滤
            if not (cache_dir / "_full.parquet").exists():
                full_df = pro.stk_limit(
                    start_date=START_DATE.strftime("%Y%m%d"),
                    end_date=END_DATE.strftime("%Y%m%d"),
                )
                if full_df is not None and not full_df.empty:
                    full_df.to_parquet(cache_dir / "_full.parquet", index=False)
                    df = full_df[full_df["ts_code"] == ts_code]
                else:
                    df = None
            else:
                full_df = pd.read_parquet(cache_dir / "_full.parquet")
                df = full_df[full_df["ts_code"] == ts_code]
        except Exception:
            df = None
        if df is not None and not df.empty:
            df = df.copy()
            df["asset"] = ts_code
            df.to_parquet(cache_file, index=False)
            frames.append(df)

        time.sleep(sleep_between)

        if (idx + 1) % 20 == 0:
            print(f"  fetched limit {idx + 1}/{len(universe)}", flush=True)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ───────────────────── 合成 30m/tick(保留) ─────────────────────


def build_30min_synthetic(base_day: datetime.date, asset: str = "000001.SZ") -> pd.DataFrame:
    """合成 1 天 30m bar(tushare 不提供 30m 历史回溯)"""
    times = [datetime.time(9, 30), datetime.time(10, 0), datetime.time(10, 30),
             datetime.time(11, 0), datetime.time(13, 1), datetime.time(13, 30),
             datetime.time(14, 0), datetime.time(14, 30), datetime.time(15, 0)]
    import numpy as np
    rng = np.random.default_rng(seed=42)
    rows = []
    prev = 10.0
    for t in times:
        c = prev * (1 + rng.normal(0, 0.005))
        o = c * 0.998
        h = max(o, c) * 1.001
        l = min(o, c) * 0.999
        rows.append({
            "date": datetime.datetime.combine(base_day, t),
            "asset": asset,
            "open": round(o, 4), "high": round(h, 4),
            "low": round(l, 4), "close": round(c, 4),
            "volume": 100000.0, "amount": 100000.0 * c,
        })
        prev = c
    return pd.DataFrame(rows)


def build_ticks_synthetic(base_day: datetime.date, asset: str = "000001.SZ", n_ticks: int = 480) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(seed=42)
    base_dt = datetime.datetime.combine(base_day, datetime.time(9, 30))
    rows = []
    for i in range(n_ticks):
        ts = base_dt + datetime.timedelta(seconds=i * 30)
        price = 10.0 * (1 + rng.normal(0, 0.001))
        rows.append({"timestamp": ts, "asset": asset,
                     "price": round(price, 4), "volume": 100.0})
    return pd.DataFrame(rows)


# ───────────────────── 入口 ─────────────────────


def main(output_dir: str) -> None:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        print("ERROR: TUSHARE_TOKEN env var not set", file=sys.stderr)
        sys.exit(1)

    ts.set_token(token)
    pro = ts.pro_api()

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cache_dir = output_path / "_cache"

    target = {
        "ordinary": 50, "st": 10, "ipo": 10, "delisted": 10,
        "chinext_star": 10, "suspended": 10, "dividend_adjust": 5,
    }

    # 1. Universe
    universe_path = output_path / "real_universe.parquet"
    if universe_path.exists():
        print(f"universe exists, loading: {universe_path}", flush=True)
        universe = pd.read_parquet(universe_path)
    else:
        universe = select_universe(pro, target)
        universe.to_parquet(universe_path, index=False)
    print(f"universe size: {len(universe)}", flush=True)

    # Fallback: 不足 105 时,补 ordinary
    if len(universe) < 105:
        need = 105 - len(universe)
        existing_codes = set(universe["asset"])
        all_basic = _list_all_basic(pro)
        candidate = all_basic[
            (all_basic["exchange"].isin(["SSE", "SZSE"]))
            & (~all_basic["ts_code"].isin(existing_codes))
            & (all_basic["list_date"] <= pd.Timestamp("2022-12-31"))
            & (all_basic["delist_date"].isna())
        ]
        extra = candidate.sample(n=min(need, len(candidate)), random_state=99)
        for _, row in extra.iterrows():
            universe = pd.concat([universe, pd.DataFrame([{
                "asset": row["ts_code"],
                "name": row["name"],
                "category": "ordinary",
                "list_date": row["list_date"].date() if pd.notna(row["list_date"]) else None,
                "delist_date": row["delist_date"].date() if pd.notna(row["delist_date"]) else None,
                "exchange": row["exchange"],
            }])], ignore_index=True)
        universe.to_parquet(universe_path, index=False)
        print(f"after fallback: {len(universe)}", flush=True)

    # 2. Daily bars(限速 + 断点续传)
    daily_cache = cache_dir / "daily"
    print("fetching daily bars...", flush=True)
    daily_df = fetch_all_daily(pro, universe, daily_cache, rate_limit_per_min=40)
    daily_df["trade_date"] = pd.to_datetime(daily_df["trade_date"], format="%Y%m%d")
    daily_df = daily_df.rename(columns={"trade_date": "date"})
    daily_df = daily_df.sort_values(["date", "asset"]).reset_index(drop=True)
    daily_path = output_path / "real_daily_bars.parquet"
    daily_df.to_parquet(daily_path, index=False)
    print(f"daily rows: {len(daily_df)} → {daily_path}", flush=True)

    # 3. 涨跌停 / ST
    print("fetching limit/st info...", flush=True)
    limit_cache = cache_dir / "limit"
    limit_df = fetch_limit_and_st(pro, universe, limit_cache, rate_limit_per_min=40)
    if not limit_df.empty:
        # tushare 列名是大写
        date_col = "trade_date" if "trade_date" in limit_df.columns else "TRADE_DATE"
        limit_df[date_col] = pd.to_datetime(limit_df[date_col], format="%Y%m%d")
        limit_path = output_path / "real_limit.parquet"
        limit_df.to_parquet(limit_path, index=False)
        print(f"limit rows: {len(limit_df)} → {limit_path}", flush=True)

    # 4. Calendar(从 daily 推)
    cal_df = daily_df[["date"]].drop_duplicates().sort_values("date").reset_index(drop=True)
    cal_df["is_open"] = 1
    cal_path = output_path / "real_calendar.parquet"
    cal_df.to_parquet(cal_path, index=False)
    print(f"calendar dates: {len(cal_df)} → {cal_path}", flush=True)

    # 5. 30m/tick(synthetic,占位)
    last2_dates = sorted(cal_df["date"].dt.date.tolist())[-2:]
    if last2_dates:
        b30 = pd.concat([build_30min_synthetic(d) for d in last2_dates], ignore_index=True)
        b30.to_parquet(output_path / "real_30m_bars.parquet", index=False)
        ticks = pd.concat([build_ticks_synthetic(d) for d in last2_dates], ignore_index=True)
        ticks.to_parquet(output_path / "real_ticks.parquet", index=False)
        print(f"30m + ticks generated for {last2_dates}", flush=True)

    # 6. 元数据
    meta = {
        "generated_at": datetime.datetime.now().isoformat(),
        "data_source": "tushare",
        "date_range": [START_DATE.isoformat(), END_DATE.isoformat()],
        "asset_count": len(universe),
        "categories": {k: int((universe["category"] == k).sum()) for k in target},
        "daily_rows": len(daily_df),
    }
    import json
    with open(output_path / "manifest.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"manifest: {output_path / 'manifest.json'}", flush=True)
    print("done.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir")
    args = parser.parse_args()
    main(args.output_dir)
