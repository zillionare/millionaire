"""Observe one durable pipeline task, isolated from other jobs' event messages."""

import asyncio
from collections.abc import Callable

from quantide.data.models.sync_task import DataSyncTask
from quantide.service.background import run_blocking
from quantide.service.data_sync import DataSyncService


async def wait_for_sync(
    task_id: str, on_progress: Callable[[DataSyncTask | None], None], service: DataSyncService
) -> None:
    worker = asyncio.create_task(run_blocking(service.run, task_id))
    try:
        while not worker.done():
            on_progress(service.get_task(task_id))
            await asyncio.sleep(0.2)
        success = await worker
        result = service.get_task(task_id)
        if not success or result is None or result.status != "done":
            raise RuntimeError(result.error or result.message if result else "数据同步未完成")
    except asyncio.CancelledError:
        service.cancel()
        await asyncio.shield(worker)
        raise
