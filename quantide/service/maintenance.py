"""Daily maintenance orchestration shared by scheduled and catch-up runs."""

import asyncio
import datetime
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from loguru import logger

from quantide.config.paths import get_app_config_dir
from quantide.config.settings import get_settings
from quantide.core.atomic_files import write_json
from quantide.core.market_time import market_today
from quantide.data.coverage import trading_sessions
from quantide.data.models.calendar import calendar
from quantide.service.data_backfill import BackfillWindow
from quantide.service.data_sync import SyncParams, data_sync_service

if TYPE_CHECKING:
    from quantide.data.fetchers.budget import DataSourceBudget

MAJOR_INDICES = ["000001.SH", "000300.SH", "000905.SH", "399001.SZ", "399006.SZ"]


MAX_BACKFILL_WINDOWS_PER_RUN = 12


def maintain_data() -> str:
    """Fill the tail first, then walk historical gaps backward from ``epoch``."""
    from quantide.service.minute_backfill import _minute_history_end

    settings = get_settings()
    end = _minute_history_end(market_today())
    if end is None:
        raise RuntimeError("无法确定已收盘的数据维护日期，请检查交易日历")
    windows = _backfill_windows(settings.epoch, end)
    if not windows:
        _trigger_factor_refresh()
        return "数据已完整，无需补全"

    completed = 0
    skipped = 0
    paused = ""
    for window in windows[:MAX_BACKFILL_WINDOWS_PER_RUN]:
        outcome = _run_backfill_window(window)
        if outcome == "ok":
            completed += 1
            continue
        if outcome == "skip":
            skipped += 1
            continue
        paused = outcome
        break
    if completed:
        _trigger_factor_refresh()
    processed = completed + skipped
    remaining = max(0, len(windows) - processed)
    suffix = f"，剩余 {remaining} 个窗口" if remaining else ""
    pause_text = f"，已暂停：{paused}" if paused else ""
    return f"数据维护完成 {completed} 个窗口{suffix}{pause_text}"


def _current_dataset_dates() -> dict[str, set[datetime.date]]:
    from quantide.data import get_index_bars_store
    from quantide.data.models.daily_bars import daily_bars
    from quantide.data.models.daily_basic import daily_basic

    daily_basic.load()
    basic_dates = (
        set(daily_basic.data["date"].to_list()) if not daily_basic.data.is_empty() else set()
    )
    candidates = {
        "daily_bars": set(daily_bars.available_dates),
        "daily_basic": basic_dates,
    }
    try:
        candidates["index_bars"] = set(get_index_bars_store().available_dates)
    except Exception:
        pass
    return candidates


def _missing_by_dataset(
    epoch: datetime.date,
    end: datetime.date,
    sessions: set[datetime.date],
    candidates: Mapping[str, set[datetime.date]],
    store: Any,
) -> dict[str, set[datetime.date]]:
    datasets: dict[str, set[datetime.date]] = {}
    for dataset, available in candidates.items():
        missing = sessions - available
        blocked: set[datetime.date] = set()
        for record in store.blocking(dataset, epoch, end):
            blocked.update(day for day in sessions if record.start <= day <= record.end)
        missing -= blocked
        if missing:
            datasets[dataset] = missing
    return datasets


def _backfill_windows(
    epoch: datetime.date,
    end: datetime.date,
) -> tuple[BackfillWindow, ...]:
    from quantide.data.models.daily_bars import daily_bars
    from quantide.service.data_backfill import plan_backfill
    from quantide.service.data_gaps import DataGapStore

    sessions = set(trading_sessions(calendar, epoch, end))
    datasets = _missing_by_dataset(epoch, end, sessions, _current_dataset_dates(), DataGapStore())
    return plan_backfill(
        epoch,
        end,
        datasets,
        available_end=getattr(daily_bars, "end", None),
    )


def _source_budget() -> "DataSourceBudget":
    from quantide.data.fetchers.budget import NoQuotaBudget, budget_for_fetcher
    from quantide.data.fetchers.registry import get_data_fetcher

    try:
        return budget_for_fetcher(get_data_fetcher())
    except Exception:
        return NoQuotaBudget(get_settings().data_source)


def _run_backfill_window(window: BackfillWindow) -> str:
    from quantide.data.fetchers.budget import BudgetDecision, DataSourceErrorKind, retryable
    from quantide.service.data_gaps import record_data_gap, resolve_data_gap

    budget = _source_budget()
    decision = budget.acquire()
    if decision is BudgetDecision.EXHAUSTED:
        return "quota_exhausted"
    if decision is BudgetDecision.DELAY:
        return "rate_limited"
    params = SyncParams(
        window.start,
        window.end,
        index_codes=MAJOR_INDICES,
        include_minute=window.phase == "tail",
    )
    task = data_sync_service.create_task(params)
    if data_sync_service.run(task.task_id):
        for dataset in window.datasets:
            resolve_data_gap(dataset=dataset, start=window.start, end=window.end)
        return "ok"
    result = data_sync_service.get_task(task.task_id)
    error = str(result.error or result.message) if result else "数据维护失败"
    kind = budget.classify(error)
    budget.observe(RuntimeError(error))
    for dataset in window.datasets:
        record_data_gap(
            dataset=dataset,
            start=window.start,
            end=window.end,
            reason_code=kind.value,
            source=get_settings().data_source,
            retryable=retryable(kind),
        )
    if kind in {DataSourceErrorKind.AUTH_ERROR, DataSourceErrorKind.PERMISSION_DENIED}:
        return f"{kind.value}: {error}"
    if retryable(kind):
        return f"{kind.value}: {error}"
    return "skip"


def _trigger_factor_refresh() -> None:
    try:
        from quantide.service.factor_tracking import trigger_refresh_all

        trigger_refresh_all()
    except Exception as exc:
        logger.warning("行情维护完成后触发因子跟踪失败: {}", exc)


def maintenance_start(
    history: datetime.date,
    checkpoints: Iterable[datetime.date | datetime.datetime | None],
) -> datetime.date:
    """Retain the configured history floor and the earliest incomplete dataset."""
    normalized = [
        value.date() if isinstance(value, datetime.datetime) else value for value in checkpoints
    ]
    return max(history, min(value or history for value in normalized))


def _first_missing_session(
    history: datetime.date, end: datetime.date, available: Iterable[datetime.date]
) -> datetime.date:
    from quantide.data.models.calendar import calendar

    missing = set(trading_sessions(calendar, history, end)) - set(available)
    return min(missing) if missing else end


def _maintenance_checkpoints(
    history: datetime.date, end: datetime.date
) -> list[datetime.date | None]:
    from quantide.data import get_index_bars_store, get_index_weight_store, get_minute_bars_store
    from quantide.data.models.daily_bars import daily_bars
    from quantide.data.models.daily_basic import daily_basic

    daily_basic.load()
    basic_dates = (
        daily_basic.data["date"].unique().to_list() if not daily_basic.data.is_empty() else []
    )
    from quantide.service.minute_backfill import MINUTE_HISTORY_START, resolve_minute_assets
    from quantide.service.minute_gaps import coverage_starts

    minutes = coverage_starts(
        get_minute_bars_store(),
        resolve_minute_assets(None),
        max(history, MINUTE_HISTORY_START),
        end,
        "30",
    )
    return [
        _first_missing_session(history, end, daily_bars.available_dates),
        _first_missing_session(history, end, basic_dates),
        _first_missing_session(history, end, get_index_bars_store().available_dates),
        get_index_weight_store().end,
        _oldest_minute_checkpoint(minutes, history, end),
    ]


def _oldest_minute_checkpoint(
    last_dates: Mapping[str, datetime.date | None], history: datetime.date, end: datetime.date
) -> datetime.date:
    from quantide.data.fetchers.capabilities import SOURCE_CAPABILITIES
    from quantide.data.models.stocks import stock_list
    from quantide.service.minute_backfill import MINUTE_HISTORY_START, _date_value

    checkpoints = []
    for row in stock_list.data.to_dicts():
        if not SOURCE_CAPABILITIES["baostock"].supports(row["asset"]):
            continue
        listed = _date_value(row.get("list_date")) or history
        delisted = _date_value(row.get("delist_date")) or end
        if max(history, MINUTE_HISTORY_START, listed) > min(end, delisted):
            continue
        checkpoint = last_dates.get(row["asset"])
        if checkpoint is not None:
            checkpoints.append(checkpoint)
    return min(checkpoints) if checkpoints else end


def snapshot_accounts() -> str:
    """Persist actual account state, including empty portfolios and pending cancels."""
    from quantide.service.registry import BrokerRegistry

    registry = BrokerRegistry()
    count = 0
    for item in registry.list():
        broker = registry.get(item["kind"], item["id"])
        on_day_close = getattr(broker, "on_day_close", None)
        if callable(on_day_close):
            asyncio.run(on_day_close())
            count += 1
    return f"已保存 {count} 个账户的日终快照"


def snapshot_market() -> str:
    """Persist the last received market snapshot; absence is an explicit failure."""
    from quantide.service.quote_monitor import quote_monitor

    rows = quote_monitor.snapshot(limit=10000)
    if not rows:
        raise RuntimeError("未收到行情，无法生成行情快照")
    now = datetime.datetime.now(datetime.UTC)
    # quote timestamps are datetimes; serialize deliberately at this boundary.
    encoded = [
        {
            key: value.isoformat() if isinstance(value, datetime.date) else value
            for key, value in row.items()
        }
        for row in rows
    ]
    destination = get_app_config_dir() / "market-snapshots" / f"{now.date()}.json"
    write_json(destination, {"captured_at": now.isoformat(), "quotes": encoded})
    return f"已保存 {len(rows)} 个标的的行情快照"
