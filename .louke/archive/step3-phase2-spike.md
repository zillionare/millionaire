# Spike Report: Phase 2.1 / 2.5 Feasibility

> Issue: #120 [step3-Phase2-spike]
> Date: 2026-06-26
> Author: qwen3.7

---

## Spike 1: Phase 2.1 — Merge DailyBarsStore into DailyBars

### 1.1 `daily_bars.store.*` Complete Access Points

| # | File | Line | Access | Type |
|---|------|------|--------|------|
| 1 | web/pages/system/market.py | 292 | `daily_bars.store.update` | method call (async via `asyncio.to_thread`) |
| 2 | web/pages/system/datasource.py | 68 | `daily_bars.store._data` | **private attr access (BUG: `_data` does not exist on ParquetStorage)** |
| 3 | web/pages/system/datasource.py | 417 | `daily_bars.store.update` | method call (async via `asyncio.to_thread`) |
| 4 | web/pages/system/jobs.py | 217 | `daily_bars.store.update()` | method call (sync) |
| 5 | web/pages/init_wizard.py | 1651 | `daily_bars.store` → `StockSyncService(stock_list, daily_bars.store, calendar)` | pass as arg |
| 6 | web/pages/init_wizard.py | 1704 | `daily_bars.store` → `StockSyncService(...)` | pass as arg |
| 7 | web/pages/data_market.py | 324 | `daily_bars.store` → `StockSyncService(...)` | pass as arg |

Total: 7 access points (matches Sage §4.2.1 count).

### 1.2 Compatibility Analysis

**Current architecture:**
- `DailyBars` (singleton, extends `Bars`) holds `self._store: DailyBarsStore | None`
- `.store` property returns `self._store` (the DailyBarsStore instance)
- `DailyBarsStore` extends `ParquetStorage`, adds `_fetch_bars_ext` callback and `rec_counts_per_date()`

**Proposed architecture (Phase 2.1):**
- `DailyBars` directly extends `ParquetStorage` (or composition with delegation)
- `.store` property returns `self` (backward compat)

**Per-access-point analysis:**

| # | Access | Compatible? | Notes |
|---|--------|-------------|-------|
| 1 | `.store.update` | YES | `ParquetStorage.update()` exists, identical signature |
| 2 | `.store._data` | **NO** | `_data` does NOT exist on `ParquetStorage`. This is a **pre-existing bug** — would raise `AttributeError` at runtime today. Needs fix: replace with `daily_bars.total_dates > 0` or similar check |
| 3 | `.store.update` | YES | Same as #1 |
| 4 | `.store.update()` | YES | Same as #1 |
| 5-7 | `daily_bars.store` passed to `StockSyncService` | Depends on 2.5 | If 2.5 deletes StockSyncService, these 3 access points disappear entirely |

**Additional concern:** `DailyBarsStore.rec_counts_per_date()` is a DailyBarsStore-specific method not on ParquetStorage. Must be moved to DailyBars. Grep shows no callers in production code — only potentially in tests.

### 1.3 Conclusion: Phase 2.1

**Recommendation: DO (with 1 prerequisite fix)**

- 4 of 7 access points are `.store.update` — directly compatible
- Access #2 (`.store._data`) is a pre-existing bug — must fix regardless
- Access #5-7 go through `StockSyncService` — if Phase 2.5 deletes it, these vanish
- `.store` property returning `self` provides clean backward compat

**Prerequisite:**
- Fix `datasource.py:68` — replace `daily_bars.store._data is not None` with `daily_bars.total_dates > 0`

**Implementation approach:**
```python
@singleton
class DailyBars(Bars, ParquetStorage):
    # or composition: DailyBars holds ParquetStorage internally

    @property
    def store(self) -> "DailyBars":
        return self  # backward compat
```

---

## Spike 2: Phase 2.5 — Delete StockSyncService

### 2.1 StockSyncService Call Sites

| # | File | Line | Method | What it does |
|---|------|------|--------|--------------|
| 1 | web/pages/init_wizard.py | 1653 | `sync_stock_list()` | Fetch stock list + save to parquet |
| 2 | web/pages/init_wizard.py | 1659 | `sync_daily_bars(start, end)` | Fetch daily bars with progress |
| 3 | web/pages/init_wizard.py | 1718 | `sync_stock_list()` | Same as #1 (async) |
| 4 | web/pages/init_wizard.py | 1789 | `sync_daily_bars` | Passed as callback (async) |
| 5 | web/pages/data_market.py | 340 | `sync_daily_bars(start, end)` | Fetch daily bars (async) |

Tests: `test_fr_310_sync.py`, `test_stock_sync.py`, `test_init_wizard.py` (mocked), `test_init_wizard_flow.py` (mocked)

### 2.2 Replacement API Analysis

**`sync_stock_list()` internals:**
```python
def sync_stock_list(self) -> int:
    df = self.fetcher.fetch_stock_list()
    if df is None or df.empty:
        return 0
    self.stock_list.update(df)
    return len(df)
```

**`stock_list.update()` already has a default:**
```python
def update(self, df: pd.DataFrame | None = None) -> None:
    df = df if df is not None else get_data_fetcher().fetch_stock_list()
    if df is None or df.empty:
        return
    self.save(df)
```

**Conclusion:** `stock_list.update()` (no args) is functionally equivalent to `sync_stock_list()`. The only difference is `sync_stock_list()` returns the count — callers can use `len(stock_list)` if needed.

**`sync_daily_bars(start, end)` internals:**
```python
def sync_daily_bars(self, start=None, end=None, progress_callback=None) -> int:
    if start is None:
        start = self._epoch
    if end is None:
        end = calendar.last_trade_date()
    return self.daily_store.fetch_with_daily_progress(start, end, progress_callback)
```

**`ParquetStorage.fetch_with_daily_progress()` is already a public method** on DailyBarsStore/DailyBars. Direct equivalent.

### 2.3 Replacement Mapping

| StockSyncService method | Replacement | Notes |
|------------------------|-------------|-------|
| `sync_stock_list()` | `stock_list.update()` | Direct equivalent, no return value |
| `sync_daily_bars(start, end, cb)` | `daily_bars.fetch_with_daily_progress(start, end, cb)` | Direct equivalent (after 2.1 merge) |
| `sync_daily()` | Inline: `stock_list.update()` + `daily_bars.fetch_with_daily_progress(...)` | No callers in production |
| `sync_full_history(start)` | Inline: `stock_list.update()` + `daily_bars.fetch_with_daily_progress(start, ...)` | No callers in production |

### 2.4 Conclusion: Phase 2.5

**Recommendation: DO**

- `sync_stock_list()` → `stock_list.update()` is a clean 1:1 replacement
- `sync_daily_bars()` → `daily_bars.fetch_with_daily_progress()` is a clean 1:1 replacement
- StockSyncService is a thin pass-through layer (3 methods, each ~5 lines of real logic)
- No callers of `sync_daily()` or `sync_full_history()` in production code

**Prerequisite:** Phase 2.1 must be done first (so `daily_bars.fetch_with_daily_progress` exists directly)

**Test impact:** `test_fr_310_sync.py` and `test_stock_sync.py` can be deleted. `test_init_wizard.py` and `test_init_wizard_flow.py` mock `StockSyncService` — need to update mocks to target `stock_list.update` and `daily_bars.fetch_with_daily_progress`.

---

## Summary

| Phase | Verdict | Rationale |
|-------|---------|-----------|
| 2.1 Merge DailyBarsStore | **DO** (fix `._data` bug first) | 6/7 access points compatible; 1 is a pre-existing bug |
| 2.5 Delete StockSyncService | **DO** (after 2.1) | Clean 1:1 replacement APIs exist on stock_list / ParquetStorage |

**Recommended execution order:**
1. Fix `datasource.py:68` `._data` → `daily_bars.total_dates > 0`
2. Phase 2.1: Merge DailyBarsStore into DailyBars
3. Phase 2.5: Delete StockSyncService, update 3 call sites + 4 test files
