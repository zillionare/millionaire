"""Own UI background jobs and wait for blocking workers before storage shutdown."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger

_tasks: set[asyncio.Task[Any]] = set()


def start_background[T](coroutine: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    task = asyncio.create_task(coroutine)
    if task is not None:
        _tasks.add(task)
        task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Task[Any]) -> None:
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("后台任务失败: {}", task.exception())


async def stop_background() -> None:
    tasks = tuple(_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_blocking[T](
    function: Callable[..., T], *args: Any, on_cancel: Callable[[], object] | None = None
) -> T:
    """Shield the actual thread; cancellation waits until it releases its resources."""
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        if on_cancel is not None:
            on_cancel()
        await asyncio.shield(worker)
        raise
