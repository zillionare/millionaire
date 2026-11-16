"""Shared lifecycle for lazily created background worker pools."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from quantide.service.factor_runs import FactorRunWorker


class WorkerSlot:
    """Create one worker per store path and restart it after root changes."""

    def __init__(
        self,
        path: Callable[[], Path],
        factory: Callable[[], FactorRunWorker],
    ) -> None:
        self._path = path
        self._factory = factory
        self._lock = threading.RLock()
        self._worker: FactorRunWorker | None = None

    def ensure(self) -> FactorRunWorker:
        with self._lock:
            path = self._path()
            if self._worker is None or self._worker.store.path != path:
                self._worker = self._factory()
            self._worker.start()
            return self._worker

    def stop(self) -> None:
        with self._lock:
            worker = self._worker
            self._worker = None
        if worker is not None:
            worker.stop()
