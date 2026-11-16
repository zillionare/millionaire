from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from quantide.config.settings import get_timezone
from quantide.core.singleton import singleton


@singleton
class SchedulerManager:
    def __init__(self) -> None:
        self._scheduler = None
        self._is_running = False

    def init(self, timezone: Any = None) -> None:
        if self._scheduler is not None:
            return

        tz = timezone or get_timezone()
        # 默认使用 BackgroundScheduler，因项目多为同步/混合调用
        self._scheduler = BackgroundScheduler(timezone=tz)
        logger.info(f"Scheduler initialized with timezone: {tz}")

    @property
    def scheduler(self) -> Any:
        if self._scheduler is None:
            self.init()
        return self._scheduler

    def start(self) -> None:
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Scheduler started")

    def pause(self) -> None:
        """Prevent new scheduled work before shutdown signals existing workers."""
        if self._scheduler and self._is_running:
            self._scheduler.pause()

    def stop(self, wait: bool = False) -> None:
        if self._scheduler and self._is_running:
            self._scheduler.shutdown(wait=wait)
            self._is_running = False
            self._scheduler = None
            logger.info("Scheduler stopped")

    def add_job(
        self,
        func: Callable[..., Any],
        trigger: Any = None,
        args: Any = None,
        kwargs: Any = None,
        id: str | None = None,
        name: str | None = None,
        **trigger_args: Any,
    ) -> Any:
        """代理 add_job 方法"""
        return self.scheduler.add_job(
            func, trigger=trigger, args=args, kwargs=kwargs, id=id, name=name, **trigger_args
        )

    def remove_job(self, job_id: str) -> None:
        """Remove an owned job without starting a new scheduler during shutdown."""
        if self._scheduler is not None and self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)

    def add_listener(self, callback: Callable[..., Any], mask: int | None = None) -> Any:
        """代理 add_listener 方法"""
        return self.scheduler.add_listener(callback, mask)


scheduler = SchedulerManager()
