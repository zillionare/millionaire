"""Minimal asset fixtures for e2e tests (不依赖真实数据 / 网络).

为 v0.2-001 paper e2e tests 提供:
- baseline_calendar.parquet: 1 个交易日 (2024-06-03) 标记为交易日
- 2024_bars_ext_cols.parquet: 1 只股票 (000001.SZ) 1 天 OHLCV
- 2024_limit_price.parquet: 1 只股票 1 天 up_limit / down_limit

按 spec §FR-180 默认 commission + stamp_tax + slippage=0 + min_lot=100
跑策略只需 1 只股票 1 天即可验证全链路.

不动 quantide.data.models.* — fixtures 是测试支持文件.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import polars as pl


ASSETS_ROOT_LOCAL = Path(__file__).resolve().parent / "minimal_assets"

# 1 股票: 000001.SZ 平安银行
TEST_ASSET = "000001.SZ"
# 1 交易日: 2024-06-03
TEST_DATE = datetime.date(2024, 6, 3)
# OHLCV 价格
TEST_OPEN = 10.0
TEST_HIGH = 10.5
TEST_LOW = 9.5
TEST_CLOSE = 10.2
TEST_VOLUME = 10000  # 1万手
TEST_UP_LIMIT = 11.0
TEST_DOWN_LIMIT = 9.0


def generate() -> None:
    """生成 minimal fixture 数据. 已生成会跳过."""
    ASSETS_ROOT_LOCAL.mkdir(parents=True, exist_ok=True)

    # Calendar: 1 天 (字段: date + is_open + prev)
    cal_path = ASSETS_ROOT_LOCAL / "baseline_calendar.parquet"
    if not cal_path.exists():
        cal = pl.DataFrame({
            "date": [TEST_DATE],
            "is_open": [1],
            "prev": [TEST_DATE - datetime.timedelta(days=1)],
        })
        cal.write_parquet(cal_path)

    # Daily bars: 1 股票 1 天
    bars_path = ASSETS_ROOT_LOCAL / "2024_bars_ext_cols.parquet"
    if not bars_path.exists():
        bars = pl.DataFrame({
            "asset": [TEST_ASSET],
            "date": [TEST_DATE],
            "open": [TEST_OPEN],
            "high": [TEST_HIGH],
            "low": [TEST_LOW],
            "close": [TEST_CLOSE],
            "volume": [TEST_VOLUME],
            "amount": [TEST_CLOSE * TEST_VOLUME * 100],  # 成交额
            "up_limit": [TEST_UP_LIMIT],
            "down_limit": [TEST_DOWN_LIMIT],
            "is_st": [False],
            "adjust_factor": [1.0],
        })
        bars.write_parquet(bars_path)

    # Limit price: 1 股票 1 天
    limit_path = ASSETS_ROOT_LOCAL / "2024_limit_price.parquet"
    if not limit_path.exists():
        limit = pl.DataFrame({
            "asset": [TEST_ASSET],
            "date": [TEST_DATE],
            "up_limit": [TEST_UP_LIMIT],
            "down_limit": [TEST_DOWN_LIMIT],
        })
        limit.write_parquet(limit_path)

    print(f"Generated minimal fixtures in {ASSETS_ROOT_LOCAL}")


def assets_root() -> Path:
    """获取 minimal assets 目录, 必要时自动生成."""
    if not (ASSETS_ROOT_LOCAL / "baseline_calendar.parquet").exists():
        generate()
    return ASSETS_ROOT_LOCAL


if __name__ == "__main__":
    generate()
