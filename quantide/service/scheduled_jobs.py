"""Lifecycle helpers for application-owned scheduler registrations."""

from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Any, Protocol


class _JobOwner(Protocol):
    _scheduled: bool

    @property
    def _lock(self) -> AbstractContextManager[Any]: ...


class _JobScheduler(Protocol):
    def remove_job(self, job_id: str) -> None: ...


def remove_owned_jobs(owner: _JobOwner, scheduler: _JobScheduler, job_ids: Iterable[str]) -> None:
    """Remove owned jobs under the service lock and allow the next lifespan to start."""
    with owner._lock:
        for job_id in job_ids:
            scheduler.remove_job(job_id)
        owner._scheduled = False
