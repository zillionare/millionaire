"""Daily maintenance orchestration shared by scheduled and catch-up runs."""

import asyncio
import datetime
from collections.abc import Iterable, Mapping

from loguru import logger

from quantide.config.paths import get_app_config_dir
from quantide.config.settings import get_settings
from quantide.core.atomic_files import write_json
from quantide.core.market_time import market_today
from quantide.data.coverage import trading_sessions
from quantide.service.data_sync import SyncParams, data_sync_service

MAJOR_INDICES = ["000001.SH", "000300.SH", "000905.SH", "399001.SZ", "399006.SZ"]


def maintain_data() -> str:
    """Backfill missed days through the same durable pipeline as the data page."""
    from quantide.service.init_wizard import init_wizard
    from quantide.service.minute_backfill import _minute_history_end

    settings = get_settings()
    history = max(settings.epoch, init_wizard.get_state().history_start_date or settings.epoch)
    end = _minute_history_end(market_today())
    if end is None:
        raise RuntimeError("无法确定已收盘的数据维护日期，请检查交易日历")
    start = maintenance_start(history, _maintenance_checkpoints(history, end))
    params = SyncParams(min(start, end), end, index_codes=MAJOR_INDICES)
    task = data_sync_service.create_task(params)
    if not data_sync_service.run(task.task_id):
        result = data_sync_service.get_task(task.task_id)
        raise RuntimeError(result.error or result.message if result else "数据维护失败")
    try:
        from quantide.service.factor_tracking import trigger_refresh_all

        trigger_refresh_all()
    except Exception as exc:
        logger.warning("行情维护完成后触发因子跟踪失败: {}", exc)
    return f"完整数据维护完成，task={task.task_id}"


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
