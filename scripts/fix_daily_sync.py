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


def init_app_state(token: str, db_path: str | None = None) -> None:
    """Create app_state record with Tushare token."""
    from quantide.data.sqlite import db
    from quantide.data.models.app_state import AppState

    if db_path:
        db.init(db_path)

    state = AppState(
        id=1,
        init_completed=True,
        init_step=6,
        app_home="/Users/openclaw/workspace/quantIDE/data",
        data_source="tushare",
        tushare_token=token,
        epoch=datetime.date(2005, 1, 1),
        app_host="0.0.0.0",
        app_port=8130,
        app_prefix="/quantide",
    )

    db["app_state"].upsert(state.to_dict(), pk="id")
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
    from quantide.data.models.daily_bars import daily_bars
    from quantide.data.models.calendar import calendar as trade_calendar

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


def verify_data() -> dict:
    """Verify data completeness after sync."""
    import polars as pl

    results = {}

    # Daily bars
    daily_path = Path("/Users/openclaw/workspace/quantIDE/data/bars/daily")
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
    stock_path = Path("/Users/openclaw/workspace/quantIDE/data/stock_list.parquet")
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
    args = parser.parse_args()

    logger.info("=== QuantIDE Daily Sync Fix ===")

    # Step 1: Initialize
    init_app_state(args.token, args.db)

    # Step 2: Sync
    stock_count = sync_stock_list()
    cal_count = sync_calendar()
    bar_result = sync_daily_bars()

    # Step 3: Verify
    verification = verify_data()

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
