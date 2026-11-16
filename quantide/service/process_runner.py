"""Terminable subprocess execution for long factor computations."""

from __future__ import annotations

import multiprocessing
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.process import BaseProcess
from typing import Any

SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
TIMEOUT = "timeout"


@dataclass(frozen=True)
class ProcessOutcome:
    status: str
    value: Any = None
    error: str = ""


def _child(
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    messages: Any,
) -> None:
    try:
        messages.put((True, target(*args, **kwargs)))
    except BaseException as exc:
        messages.put((False, f"{type(exc).__name__}: {exc}"))


def _terminate(process: BaseProcess) -> None:
    if process.is_alive():
        process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)


def _await_result(
    process: BaseProcess,
    messages: Any,
    deadline: float | None,
    cancel: threading.Event | None,
) -> ProcessOutcome:
    while True:
        if cancel is not None and cancel.is_set():
            return ProcessOutcome(CANCELLED)
        if deadline is not None and time.monotonic() >= deadline:
            return ProcessOutcome(TIMEOUT, error="computation exceeded its time budget")
        try:
            ok, payload = messages.get(timeout=0.05)
        except queue.Empty:
            if not process.is_alive():
                return ProcessOutcome(FAILED, error="worker exited without a result")
            continue
        process.join(timeout=2)
        if ok:
            return ProcessOutcome(SUCCEEDED, payload)
        return ProcessOutcome(FAILED, error=str(payload))


def run_isolated(
    target: Callable[..., Any],
    *args: Any,
    timeout: float | None = None,
    cancel: threading.Event | None = None,
    kwargs: dict[str, Any] | None = None,
) -> ProcessOutcome:
    """Run one picklable target in a child process and terminate it on budget expiry."""
    context = multiprocessing.get_context("spawn")
    messages = context.Queue()
    process = context.Process(
        target=_child,
        args=(target, args, kwargs or {}, messages),
        daemon=True,
    )
    process.start()
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        return _await_result(process, messages, deadline, cancel)
    finally:
        _terminate(process)
        messages.close()
        messages.join_thread()
