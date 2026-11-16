"""Serialize a store's read/merge/publish operations across writers."""

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Concatenate, Protocol, cast

from filelock import FileLock


class _LockableStore(Protocol):
    _store_path: Path

    def _collect_dates(self) -> None: ...


def locked_store[S, **P, R](
    method: Callable[Concatenate[S, P], R],
) -> Callable[Concatenate[S, P], R]:
    """Keep a stable sibling lock file while data files are atomically replaced."""

    @wraps(method)
    def locked(self: S, *args: P.args, **kwargs: P.kwargs) -> R:
        store = cast(_LockableStore, self)
        path = store._store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=30):
            if method.__name__ == "append_data":
                store._collect_dates()
            return method(self, *args, **kwargs)

    return locked
