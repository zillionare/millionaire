# QuantIDE Daily Subscription Audit Report
Date: 2026-05-04

## Executive Summary

quantIDE daily data subscription is **completely non-functional**. There is **no evidence** that automated sync has ever run. The daily bars are stale by **240+ trading days** (last data: 2025-04-21). Root cause: the application was never fully initialized (`app_state` empty), so the scheduler was never started.

---

## Source Status Table

| Source | Last Update | Status | Root Cause | Fix Action |
|--------|-------------|--------|------------|------------|
| **日线行情 (Daily Bars)** | 2025-04-21 | FAIL | App never initialized -> scheduler never started -> sync jobs never run | Run init wizard, start app, trigger manual sync |
| **股票列表 (Stock List)** | 2025-05-02 | STALE | Same as above - no scheduled sync running | Same as above |
| **交易日历 (Calendar)** | Pre-loaded | OK | Static file covers through 2026-12-31 | None needed now |
| **日终快照 (Daily Snapshot)** | Never | FAIL | Job is TODO stub (no implementation) | Implement snapshot logic or disable |
| **行情快照 (Market Snapshot)** | Never | FAIL | Job is TODO stub (no implementation) | Implement snapshot logic or disable |

---

## Detailed Findings

### 1. Daily Bars (日线行情) - CRITICAL FAILURE

- **File**: `data/bars/daily/` (partitioned parquet, year=2025)
- **Records**: 37,751 rows across **7 unique trading dates**
- **Date range**: 2025-03-31 to 2025-04-21
- **Missing**: ALL 240+ trading days from 2025-04-22 to present
- **Record count per day**: ~5,391-5,394 (reasonable for full A-share market)
- **dates.pq mismatch**: Tracks 15 dates (2025-03-31 to 2025-04-21) but only **7** have actual parquet data. Missing from parquet: 2025-04-08, 04-09, 04-10, 04-11, 04-14, 04-15, 04-16, 04-17. This suggests a partial write failure or incremental sync that was interrupted.
- **Schema notes**:
  - Has `st` column (bool) instead of standard `is_st`
  - Extra columns `name`, `type`, `type_name` from ST info merge (36,825/37,751 nulls = 97.5%)
  - **Code already handles this**: `daily_bars.py:47-50` transparently renames `st` -> `is_st` on read; extra columns are ignored
  - Core price columns (open/high/low/close/volume/amount/adjust) have **0 nulls**

### 2. Stock List (股票列表) - STALE

- **File**: `data/stock_list.parquet`
- **Records**: 5,814
- **Last modified**: ~2025-05-02
- **Completeness**: OK - has asset, name, pinyin, list_date, delist_date
- **Freshness**: STALE - missing ~1 year of IPOs/delistings

### 3. Calendar (交易日历) - OK

- **File**: `data/calendar.parquet`
- **Records**: 8,035
- **Coverage**: 2005-01-01 to 2026-12-31
- **Today (2026-05-04)**: correctly marked as closed (holiday)
- **Next trading day**: 2026-05-06

### 4. Job Scheduler - NEVER INITIALIZED

- **job_history table**: Does not exist in SQLite (created lazily on first access)
- **app_state table**: 0 rows (init wizard never completed)
- **quantIDE process**: Not running
- **InitCheckMiddleware**: Blocks ALL non-init-wizard requests when uninitialized (`middleware_init.py:53`)
- **Predefined jobs** (`quantide/web/pages/system/jobs.py`):
  - `daily_bars_sync` (15:35 Mon-Fri) - no evidence of execution
  - `stock_list_sync` (16:00 daily) - no evidence of execution
  - `calendar_sync` (09:00 Mon weekly) - no evidence of execution
  - `daily_snapshot` (15:05 Mon-Fri) - TODO stub (no implementation)
  - `market_snapshot` (every 5min 9-15 Mon-Fri) - TODO stub (no implementation)

### 5. Database State

- Tables with data: `user` (1 row), `sqlite_stat1` (1 row)
- Tables with schema but **0 rows**: `orders`, `trades`, `assets`, `positions`, `portfolios`, `strategy_logs`, `strategy_config`, `strategy_info`
- `app_state`: 0 rows (never initialized)

---

## Root Cause Chain

```
App never initialized (app_state empty)
    -> InitCheckMiddleware blocks all non-wizard pages
    -> No Tushare token configured
    -> RuntimeBootstrap never called (init_wizard.is_initialized() returns False)
    -> Scheduler never started
    -> Sync jobs never registered/executed
    -> Daily bars stale for 1 year
    -> Stock list stale for 1 year
```

**Additional nuance**: The `dates.pq` tracks 15 dates but parquet only contains 7. This indicates an initial sync attempt was partially successful — some dates were tracked in `dates.pq` but not persisted to parquet, suggesting the sync was interrupted or failed silently during the initial data load.

---

## Fix Plan

### Phase 1: Initialize Application (Required)
1. Start quantIDE web application (`python -m quantide` or via entry point)
2. Complete init wizard with valid Tushare token
3. Verify `app_state` is persisted to SQLite with `tushare_token`, `data_source`, `epoch`

### Phase 2: Backfill Data (Required)
1. Trigger manual sync from `/system/datasource` page, OR
2. Run data sync via script/API to backfill 2025-04-22 to present
3. Run `stock_list.update()` to refresh stock list
4. Verify `dates.pq` and parquet are consistent after sync
5. **Expected time**: ~240 trading days of data; at Tushare's rate limits this may take hours

### Phase 3: Verify Scheduler (Required)
1. Confirm `RuntimeBootstrap.bootstrap()` starts scheduler automatically on app init
2. Verify jobs appear in `/system/jobs` page
3. Trigger one manual job execution to verify end-to-end pipeline
4. Verify `job_history` table is created and records executions

### Phase 4: Implement TODO Jobs (Optional)
- `daily_snapshot`: implement holdings snapshot logic
- `market_snapshot`: implement quote snapshot logic
- Or disable these jobs in `PREDEFINED_JOBS` until implemented

---

## Preventive Measures

1. **Add startup health check**: Verify scheduler is running on app start; alert if not
2. **Add data freshness monitor**: Check daily bars latest date vs last trade date on startup; warn if stale > 2 days
3. **Persist job_history eagerly**: Create table on app init, not lazily on first job execution
4. **Add CLI sync command**: Allow `python -m quantide sync` for manual recovery without UI
5. **Consider cron-based sync**: As alternative to in-app scheduler for reliability
6. **Verify dates.pq/parquet consistency**: Add check that all tracked dates have corresponding parquet data
