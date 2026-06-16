"""后处理:把 limit/ST 数据合并到 daily bars,生成统一 schema 的 fixture

输入:
- tests/assets/real/real_daily_bars.parquet
- tests/assets/real/real_limit.parquet
- tests/assets/real/real_universe.parquet

输出:
- tests/assets/real/real_bars_combined.parquet(与 2024 fixture schema 一致)
- tests/assets/real/real_calendar.parquet(已是此格式,不动)
- tests/assets/real/real_30m_bars.parquet
- tests/assets/real/real_ticks.parquet
"""

from __future__ import annotations

from pathlib import Path

import polars as pl


def combine(output_dir: Path) -> None:
    daily = pl.read_parquet(output_dir / "real_daily_bars.parquet")
    limit = pl.read_parquet(output_dir / "real_limit.parquet")
    universe = pl.read_parquet(output_dir / "real_universe.parquet")

    print(f"daily: {daily.shape}, limit: {limit.shape}, universe: {universe.shape}")

    # 1. 标准化 limit 表(列名大写或小写取决于 fetch 路径)
    date_col = "trade_date" if "trade_date" in limit.columns else "TRADE_DATE"
    code_col = "ts_code" if "ts_code" in limit.columns else "TS_CODE"
    up_col = "up_limit" if "up_limit" in limit.columns else "UP_LIMIT"
    down_col = "down_limit" if "down_limit" in limit.columns else "DOWN_LIMIT"
    limit_norm = limit.select([
        pl.col(date_col).alias("date"),
        pl.col(code_col).alias("asset"),
        pl.col(up_col).alias("up_limit"),
        pl.col(down_col).alias("down_limit"),
    ])
    if "CREATE_TIME" in limit.columns:
        limit_norm = limit_norm.with_columns(pl.col("CREATE_TIME").alias("create_time"))
        limit_norm = limit_norm.sort("create_time", descending=True).unique(subset=["date", "asset"], keep="first").drop("create_time")

    # 2. daily 已有 ts_code + date(asset 已存在)
    if "ts_code" in daily.columns and "asset" not in daily.columns:
        daily = daily.rename({"ts_code": "asset"})
    if "ts_code" in daily.columns and "asset" in daily.columns:
        daily = daily.drop("ts_code")

    # 3. 合并 limit 到 daily
    combined = daily.join(
        limit_norm, on=["date", "asset"], how="left"
    )
    print(f"after limit join: {combined.shape}, missing up_limit: {combined['up_limit'].is_null().sum()}")

    # 4. 计算 is_st: name 含 ST/退市风险警示
    universe_st = universe.select([
        pl.col("asset"),
        pl.col("name").str.contains("ST").alias("is_st"),
    ])
    combined = combined.join(universe_st, on="asset", how="left")
    combined = combined.with_columns(pl.col("is_st").fill_null(False))
    print(f"ST count: {combined.filter(pl.col('is_st')==True)['asset'].n_unique()}")

    # 5. 加 adjust 字段(1.0 占位,tushare 用 adj_factor 单独表;v0.2 不验证复权)
    combined = combined.with_columns(pl.lit(1.0).alias("adjust"))

    # 6. 标准化列顺序(匹配 2024 fixture schema)
    cols = [
        "date", "asset", "open", "high", "low", "close",
        "vol", "amount", "adjust", "is_st", "up_limit", "down_limit",
    ]
    # tushare 列名是 vol,2024 fixture 是 volume;统一
    if "vol" in combined.columns and "volume" not in combined.columns:
        combined = combined.rename({"vol": "volume"})

    final_cols = [
        "date", "asset", "open", "high", "low", "close",
        "volume", "amount", "adjust", "is_st", "up_limit", "down_limit",
    ]
    combined = combined.select(final_cols)
    combined = combined.sort(["date", "asset"])

    out = output_dir / "real_bars_combined.parquet"
    combined.write_parquet(out)
    print(f"combined: {combined.shape} → {out}")
    print(f"  date range: {combined['date'].min()} ~ {combined['date'].max()}")
    print(f"  unique assets: {combined['asset'].n_unique()}")
    print(f"  ST assets: {combined.filter(pl.col('is_st')==True)['asset'].n_unique()}")
    print(f"  has up_limit: {(~combined['up_limit'].is_null()).sum()} / {len(combined)}")


if __name__ == "__main__":
    import sys
    combine(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/assets/real"))
