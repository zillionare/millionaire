"""Initialization UI backed by the shared durable data pipeline."""

import asyncio
import datetime

from loguru import logger

from quantide.data.models.calendar import calendar
from quantide.service.background import run_blocking
from quantide.service.data_sync import SyncParams, data_sync_service
from quantide.service.init_wizard import init_wizard
from quantide.service.maintenance import MAJOR_INDICES
from quantide.service.sync_jobs import wait_for_sync
from quantide.web.pages import wizard_state
from quantide.web.pages.wizard_state import _set_download_error, _update_sync_status

_background_tasks: set[asyncio.Task] = set()


def start_wizard_sync(start_date):
    """Retain ownership of downloads until completion or ASGI shutdown."""
    task = asyncio.create_task(_run_data_sync(start_date))
    if task is not None:
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)


async def stop_wizard_sync() -> None:
    """Cancel downloads and wait for their worker before closing storage."""
    tasks = tuple(_background_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _show_failure(error):
    text = str(error)
    _set_download_error(f"下载失败：{text}")
    _update_sync_status(
        wizard_state._sync_status["progress"], "同步失败", f"同步失败: {text}", error=text
    )


def _apply_task_progress(task):
    """Display persisted progress without treating a stage event as completion."""
    if task is None:
        return
    if task.error:
        _show_failure(task.error)
        return
    _update_sync_status(min(99, task.progress), "正在同步数据", task.message or "正在同步数据")


async def _wait_for_pipeline(task_id):
    await wait_for_sync(task_id, _apply_task_progress, data_sync_service)


async def _run_data_sync(start_date: datetime.date | None = None) -> None:
    """Use the same stages, failures and checkpoints as daily maintenance."""
    wizard_state._sync_status.update(is_running=True, completed=False, error=None)
    _set_download_error(None)
    try:
        from quantide.data import init_data

        state = init_wizard.get_state(force_refresh=True)
        init_data(state.app_home, init_db=True)
        # Refresh before selecting the endpoint; the pipeline also owns calendar
        # validation for ordinary data-page and scheduled runs.
        await run_blocking(calendar.update)
        end = calendar.last_trade_date()
        start = min(start_date or state.history_start_date or state.epoch, end)
        params = SyncParams(start, end, index_codes=list(MAJOR_INDICES))
        task = data_sync_service.create_task(params)
        wizard_state._sync_status["current_task"] = task.task_id
        await _wait_for_pipeline(task.task_id)
        init_wizard.complete_initialization()
        _set_download_error(None)
        _update_sync_status(100, "初始化数据下载完成", "初始化数据下载完成", completed=True)
    except asyncio.CancelledError:
        _show_failure("服务停止，初始化被中断；可从数据任务继续")
        raise
    except Exception as exc:
        logger.exception("初始化数据同步失败")
        _show_failure(exc)
    finally:
        wizard_state._sync_status["is_running"] = False
