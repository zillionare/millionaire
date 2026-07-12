"""测试 fixture 生成器 — 按 test-plan §1.1 要求构造

为什么需要这个:
- 现有 tests/assets 仅 2024 全市场数据,缺少 test-plan §1.2 要求的
  边界场景(新 IPO / 退市 / 停牌 / ST / 创科 / 分红除权)
- test-plan 要求数据范围 2023-01-01 ~ 2025-12-31,现有只覆盖 2024
- 30m/tick 在 tushare 不易全量拉取,先用合成数据占位

设计原则:
- 所有数据**确定性合成**(固定 seed),确保可重现
- 边界场景手工构造,使其行为可预测(例如 ST 必涨跌停 ±5%)
- 价格序列单调 + 已知,便于手算 ground truth
- 不依赖网络

合成数据 ≠ 真实数据。当前仅供框架功能验证;**真实数据接入**
是后续工作(用 tushare 替换 synthetic 即可)。
"""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl


# ───────────────────── 资产清单(105 个,按 test-plan §1.2 类别) ─────────────────────


def build_asset_universe() -> pd.DataFrame:
    """构造 105 个测试资产;返回 DataFrame 含类别标记

    类别(test-plan §1.2):
        ordinary (50), st (10), ipo (10), delisted (10),
        chinext_star (10), suspended (10), dividend_adjust (5)
    """
    rng = np.random.default_rng(seed=42)
    rows = []

    def base(symbol, name, category, exchange, list_date, delist_date=None,
             chinext=False, is_st=False):
        return {
            "asset": symbol,
            "name": name,
            "pinyin": "".join(p[0] for p in name.split())[:8].upper(),
            "category": category,
            "exchange": exchange,
            "list_date": list_date,
            "delist_date": delist_date,
            "is_chinext_star": chinext,
            "is_st": is_st,
        }

    # 50 普通活跃股(沪深各 25)
    for i in range(50):
        ex = "SSE" if i % 2 == 0 else "SZSE"
        rows.append(
            base(
                symbol=f"{(i*100 + 1):06d}.{'SH' if ex == 'SSE' else 'SZ'}",
                name=f"ORD{i:03d}",
                category="ordinary",
                exchange=ex,
                list_date=datetime.date(2010, 1, 1),
            )
        )

    # 10 ST(沪深各 5)
    for i in range(10):
        ex = "SSE" if i % 2 == 0 else "SZSE"
        rows.append(
            base(
                symbol=f"{(i + 1):06d}.{'SH' if ex == 'SSE' else 'SZ'}",
                name=f"ST{i:02d}",
                category="st",
                exchange=ex,
                list_date=datetime.date(2015, 6, 1),
                is_st=True,
            )
        )

    # 10 新 IPO(2023-2025 上市,跨测试区间)
    for i in range(10):
        year_offset = 2023 + (i % 3)
        rows.append(
            base(
                symbol=f"{(90 + i):06d}.SH" if i % 2 == 0 else f"{(90 + i):06d}.SZ",
                name=f"IPO{i:02d}",
                category="ipo",
                exchange="SSE" if i % 2 == 0 else "SZSE",
                list_date=datetime.date(year_offset, 3 + i, 15),
            )
        )

    # 10 已退市(2023-2025 退市)
    for i in range(10):
        year_offset = 2023 + (i % 3)
        # 散布在 1~12 月
        month = (i % 12) + 1
        rows.append(
            base(
                symbol=f"{(80 + i):06d}.SH" if i % 2 == 0 else f"{(80 + i):06d}.SZ",
                name=f"DEL{i:02d}",
                category="delisted",
                exchange="SSE" if i % 2 == 0 else "SZSE",
                list_date=datetime.date(2010, 1, 1),
                delist_date=datetime.date(year_offset, month, 15),
            )
        )

    # 10 创业板/科创板(±20% 涨跌停)
    for i in range(10):
        rows.append(
            base(
                symbol=f"{(70 + i):06d}.SZ" if i < 5 else f"{(70 + i):06d}.SH",
                name=f"GROWTH{i:02d}" if i < 5 else f"STAR{i:02d}",
                category="chinext_star",
                exchange="SZSE" if i < 5 else "SSE",
                list_date=datetime.date(2020, 9, 1),
                chinext=True,
            )
        )

    # 10 长期停牌
    for i in range(10):
        rows.append(
            base(
                symbol=f"{(60 + i):06d}.SZ" if i % 2 == 0 else f"{(60 + i):06d}.SH",
                name=f"SUSP{i:02d}",
                category="suspended",
                exchange="SZSE" if i % 2 == 0 else "SSE",
                list_date=datetime.date(2012, 1, 1),
            )
        )

    # 5 分红除权(2023-2025 内分红送股)
    for i in range(5):
        rows.append(
            base(
                symbol=f"{(50 + i):06d}.SZ" if i % 2 == 0 else f"{(50 + i):06d}.SH",
                name=f"DIV{i:02d}",
                category="dividend_adjust",
                exchange="SZSE" if i % 2 == 0 else "SSE",
                list_date=datetime.date(2015, 1, 1),
            )
        )

    return pd.DataFrame(rows)


# ───────────────────── 交易日历(2023-01-01 ~ 2025-12-31) ─────────────────────


def build_trade_calendar(start: datetime.date, end: datetime.date) -> pd.DataFrame:
    """构造交易日历;排除周末 + 已知法定节假日"""
    # 三年间已知的法定节假日(简化)
    holidays = set()
    for year in range(start.year, end.year + 1):
        # 春节:除夕到初六(简化)
        holidays.add(datetime.date(year, 2, 10))  # 占位
        # 国庆:10/1 ~ 10/7
        for d in range(1, 8):
            holidays.add(datetime.date(year, 10, d))
        # 劳动节:5/1 ~ 5/3
        for d in range(1, 4):
            holidays.add(datetime.date(year, 5, d))

    rows = []
    cur = start
    while cur <= end:
        is_trade = cur.weekday() < 5 and cur not in holidays
        rows.append({"date": cur, "is_open": 1 if is_trade else 0, "prev": cur})
        cur += datetime.timedelta(days=1)

    return pd.DataFrame(rows)


# ───────────────────── 日线行情(确定性合成) ─────────────────────


def build_daily_bars(
    assets: pd.DataFrame,
    trade_dates: list[datetime.date],
    base_price: float = 10.0,
) -> pd.DataFrame:
    """为每个 (asset, date) 合成 OHLCV;价格序列确定性,便于手算

    价格规则:
      - 普通股:close 在 [9, 11] 间小幅波动(±5% 噪声)
      - ST:close 在 [4, 5] 间(已折价,±5% 限制)
      - 创业板/科创板:close 在 [19, 21] 间(已涨到 20% 限制附近)
      - 停牌股:停牌日 volume=0,open=high=low=close=前日 close
      - 退市股:仅在 list_date ~ delist_date 区间有数据
      - 新 IPO:仅 list_date 起有数据
      - 分红除权:每年 6 月有一天除权(close 除以 1.1)
    """
    rng = np.random.default_rng(seed=42)
    rows = []

    for _, asset in assets.iterrows():
        symbol = asset["asset"]
        list_date = asset["list_date"]
        delist_date = asset.get("delist_date")
        category = asset["category"]
        is_st = asset["is_st"]
        is_chinext = asset["is_chinext_star"]

        # 确定有效日期范围
        valid_start = list_date
        valid_end = delist_date or trade_dates[-1]

        # 确定价格区间
        if is_st:
            price_lo, price_hi = 4.0, 5.0
        elif is_chinext:
            price_lo, price_hi = 19.0, 21.0
        else:
            price_lo, price_hi = 9.0, 11.0

        # 停牌日期集合(仅对 suspended 类)
        suspended_dates = set()
        if category == "suspended":
            # 选 2024 年一个连续 20 交易日窗口为停牌期
            if trade_dates:
                idx = len(trade_dates) // 2
                suspended_dates = set(trade_dates[idx:idx + 20])

        # 分红除权日(每年 6 月 15 日左右)
        dividend_dates = set()
        if category == "dividend_adjust":
            for year in range(2023, 2026):
                dividend_dates.add(datetime.date(year, 6, 15))

        prev_close = base_price
        for dt in trade_dates:
            if dt < valid_start or dt > valid_end:
                continue
            if dt in suspended_dates:
                # 停牌日:open=high=low=close=前日 close, volume=0
                o = h = l = c = prev_close
                v = 0.0
                adj = 1.0
            else:
                # 正常日:close 在 [price_lo, price_hi] 间小幅波动
                noise = rng.normal(0, 0.01)
                c = prev_close * (1 + noise)
                c = max(price_lo, min(price_hi, c))
                # OHLC 围绕 close
                spread = abs(rng.normal(0, 0.005))
                o = c * (1 - spread)
                h = max(o, c) * (1 + abs(rng.normal(0, 0.003)))
                l = min(o, c) * (1 - abs(rng.normal(0, 0.003)))
                v = rng.uniform(1e6, 1e7)

                # 除权日调整
                if dt in dividend_dates:
                    c = c / 1.1
                    adj = 1.1
                else:
                    adj = 1.0

                prev_close = c

            # 涨跌停(由 close 推 limits)
            if is_st:
                limit_pct = 0.05
            elif is_chinext:
                limit_pct = 0.20
            else:
                limit_pct = 0.10
            up_limit = c * (1 + limit_pct) if dt not in suspended_dates else c
            down_limit = c * (1 - limit_pct) if dt not in suspended_dates else c

            rows.append(
                {
                    "date": dt,
                    "asset": symbol,
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(l, 4),
                    "close": round(c, 4),
                    "volume": round(v, 2),
                    "amount": round(v * c, 2),
                    "adjust": round(adj, 4),
                    "is_st": is_st,
                    "up_limit": round(up_limit, 4),
                    "down_limit": round(down_limit, 4),
                }
            )

    return pd.DataFrame(rows)


# ───────────────────── 30 分钟线(2025 最后 2 交易日,1 个代表资产) ─────────────────────


def build_30min_bars(
    base_day: datetime.date,
    asset: str = "000001.SZ",
    base_price: float = 10.0,
) -> pd.DataFrame:
    """合成 1 天的 30 分钟线(8 根 bar:09:30 ~ 15:00)"""
    times = [
        datetime.time(9, 30), datetime.time(10, 0),
        datetime.time(10, 30), datetime.time(11, 0),
        datetime.time(13, 1), datetime.time(13, 30),
        datetime.time(14, 0), datetime.time(14, 30),
        # 最后一根是收盘前(15:00 close 用于 cheat-on-close)
        datetime.time(15, 0),
    ]
    rng = np.random.default_rng(seed=42)
    rows = []
    prev = base_price
    for t in times:
        # 简化:close 围绕 base_price 小幅波动
        c = prev * (1 + rng.normal(0, 0.005))
        o = c * (1 - 0.002)
        h = max(o, c) * 1.001
        l = min(o, c) * 0.999
        rows.append(
            {
                "date": datetime.datetime.combine(base_day, t),
                "asset": asset,
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
                "volume": 100000.0,
                "amount": 100000.0 * c,
            }
        )
        prev = c
    return pd.DataFrame(rows)


# ───────────────────── Tick(2025 最后 2 交易日,1 个代表资产) ─────────────────────


def build_ticks(
    base_day: datetime.date,
    asset: str = "000001.SZ",
    n_ticks: int = 480,
    base_price: float = 10.0,
) -> pd.DataFrame:
    """合成 tick;240 ticks/天 × 2 天"""
    rng = np.random.default_rng(seed=42)
    rows = []
    base_dt = datetime.datetime.combine(base_day, datetime.time(9, 30))
    for i in range(n_ticks):
        ts = base_dt + datetime.timedelta(seconds=i * 30)
        price = base_price * (1 + rng.normal(0, 0.001))
        rows.append(
            {
                "timestamp": ts,
                "asset": asset,
                "price": round(price, 4),
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


# ───────────────────── 入口:生成所有 fixture 到目录 ─────────────────────


def generate_all(
    output_dir: Path,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
) -> dict[str, Path]:
    """生成测试数据,返回 {logical_name: file_path}"""
    output_dir.mkdir(parents=True, exist_ok=True)
    start = start or datetime.date(2023, 1, 1)
    end = end or datetime.date(2025, 12, 31)

    paths: dict[str, Path] = {}

    # 1. 交易日历
    cal = build_trade_calendar(start, end)
    p = output_dir / "synthetic_calendar.parquet"
    cal.to_parquet(p, index=False)
    paths["calendar"] = p

    trade_dates = [d.date() if hasattr(d, "date") else d for d in cal[cal["is_open"] == 1]["date"].tolist()]

    # 2. 资产清单
    universe = build_asset_universe()
    p = output_dir / "synthetic_universe.parquet"
    universe.to_parquet(p, index=False)
    paths["universe"] = p

    # 3. 日线
    bars = build_daily_bars(universe, trade_dates)
    p = output_dir / "synthetic_daily_bars.parquet"
    bars.to_parquet(p, index=False)
    paths["daily_bars"] = p

    # 4. 30m(tushare 占位 — 仅 2025 最后 2 日,1 个资产)
    if trade_dates:
        last2 = trade_dates[-2:]
        b30_frames = [build_30min_bars(d) for d in last2]
        b30 = pd.concat(b30_frames, ignore_index=True)
        p = output_dir / "synthetic_30m_bars.parquet"
        b30.to_parquet(p, index=False)
        paths["30m_bars"] = p

        # 5. tick(占位)
        tick_frames = [build_ticks(d) for d in last2]
        ticks = pd.concat(tick_frames, ignore_index=True)
        p = output_dir / "synthetic_ticks.parquet"
        ticks.to_parquet(p, index=False)
        paths["ticks"] = p

    return paths


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/assets/synthetic")
    paths = generate_all(out)
    print(f"Generated {len(paths)} files in {out}:")
    for name, p in paths.items():
        size_mb = p.stat().st_size / (1024 * 1024)
        print(f"  {name}: {p.name} ({size_mb:.2f} MB)")
