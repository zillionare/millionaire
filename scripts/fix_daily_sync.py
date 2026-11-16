#!/usr/bin/env python3
"""
QuantIDE Daily Data Sync Fix Script

Usage:
    python scripts/fix_daily_sync.py --token YOUR_TUSHARE_TOKEN

This script will:
1. Initialize app_state with the provided Tushare token
2. Sync stock list
3. Sync calendar
4. Backfill daily bars from last available date to present
5. Verify data completeness

Requires: tushare, polars, arrow, loguru, sqlite-utils
"""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from quantide.config.paths import get_app_db_path, normalize_data_home


def init_app_state(token: str, db_path: str | None = None, data_home: str | None = None) -> None:
    """Bind configured stores, updating the token without resetting saved settings."""
    from quantide.data import init_data
    from quantide.data.models.app_state import AppState
    from quantide.data.sqlite import db

    db.init(db_path or get_app_db_path())
    rows = list(db["app_state"].rows_where("id = ?", (1,)))
    state = AppState.from_dict(rows[0]) if rows else AppState()
    state.app_home = normalize_data_home(str(data_home or "").strip() or state.app_home)
    state.data_source = "tushare"
    state.tushare_token = token
    db["app_state"].upsert(state.to_dict(), pk="id")
    init_data(state.app_home, init_db=False)
    logger.info("app_state initialized with Tushare token")


def sync_stock_list() -> int:
    """Sync stock list."""
    from quantide.data.models.stocks import stock_list

    logger.info("Syncing stock list...")
    try:
        stock_list.update()
        count = stock_list.size
        logger.info(f"Stock list synced: {count} records")
        return count
    except Exception as e:
        logger.error(f"Stock list sync failed: {e}")
        return 0


def sync_calendar() -> int:
    """Sync calendar."""
    from quantide.data.models.calendar import calendar as trade_calendar

    logger.info("Syncing calendar...")
    try:
        trade_calendar.update()
        count = len(trade_calendar._data) if trade_calendar._data is not None else 0
        logger.info(f"Calendar synced: {count} records")
        return count
    except Exception as e:
        logger.error(f"Calendar sync failed: {e}")
        return 0


def sync_daily_bars() -> dict:
    """Sync daily bars from last available date to present."""
    from quantide.data.models.calendar import calendar as trade_calendar
    from quantide.data.models.daily_bars import daily_bars

    logger.info("Syncing daily bars...")

    # Determine start date
    if daily_bars.end:
        start = daily_bars.end + datetime.timedelta(days=1)
    else:
        start = datetime.date(2025, 4, 22)

    end = trade_calendar.last_trade_date()
    if not end:
        end = datetime.date.today()

    if start > end:
        logger.info(f"Daily bars already up to date (last: {daily_bars.end})")
        return {"status": "up_to_date", "start": start, "end": end, "count": 0}

    logger.info(f"Backfilling daily bars: {start} ~ {end}")
    try:
        count = daily_bars.store.update()
        logger.info(f"Daily bars synced: {count} records")
        return {"status": "synced", "start": start, "end": end, "count": count}
    except Exception as e:
        logger.error(f"Daily bars sync failed: {e}")
        return {"status": "error", "error": str(e)}


def verify_data(data_home: str | None = None) -> dict:
    """Verify data completeness after sync."""
    import polars as pl

    from quantide.config.settings import get_data_home

    results = {}

    # Daily bars
    home = Path(normalize_data_home(str(data_home or "").strip() or get_data_home()))
    daily_path = home / "data/bars/daily"
    if daily_path.exists():
        daily = pl.read_parquet(str(daily_path))
        unique_dates = daily["date"].dt.date().unique().sort()
        results["daily_bars"] = {
            "total_rows": len(daily),
            "unique_dates": len(unique_dates),
            "latest_date": str(unique_dates[-1]) if len(unique_dates) > 0 else None,
            "nulls_in_core_cols": {
                col: daily.filter(pl.col(col).is_null()).shape[0]
                for col in ["open", "high", "low", "close", "volume", "amount", "adjust"]
            },
        }
    else:
        results["daily_bars"] = {"error": "daily bars path not found"}

    # Stock list
    stock_path = home / "data/stock_list.parquet"
    if stock_path.exists():
        stocks = pl.read_parquet(str(stock_path))
        results["stock_list"] = {
            "total_rows": len(stocks),
        }
    else:
        results["stock_list"] = {"error": "stock list not found"}

    return results


def main():
    parser = argparse.ArgumentParser(description="Fix QuantIDE daily data sync")
    parser.add_argument("--token", required=True, help="Tushare Pro API token")
    parser.add_argument("--db", default=None, help="Path to quantide.db (optional)")
    parser.add_argument("--data-home", default=None, help="Persistent market-data home")
    args = parser.parse_args()

    logger.info("=== QuantIDE Daily Sync Fix ===")

    # Step 1: Initialize
    init_app_state(args.token, args.db, args.data_home)

    # Step 2: Sync
    stock_count = sync_stock_list()
    cal_count = sync_calendar()
    bar_result = sync_daily_bars()

    # Step 3: Verify
    verification = verify_data(args.data_home)

    logger.info("=== Sync Results ===")
    logger.info(f"Stock list: {stock_count} records")
    logger.info(f"Calendar: {cal_count} records")
    logger.info(f"Daily bars: {bar_result}")
    logger.info(f"Verification: {verification}")

    print("\n" + "=" * 50)
    print("FIX COMPLETE")
    print("=" * 50)
    print(f"Stock list: {stock_count} records")
    print(f"Calendar: {cal_count} records")
    print(f"Daily bars: {bar_result.get('count', 0)} records")
    if "daily_bars" in verification:
        db_result = verification["daily_bars"]
        print(f"Latest daily bar date: {db_result.get('latest_date')}")
        print(f"Unique trading days: {db_result.get('unique_dates')}")


if __name__ == "__main__":
    main()
