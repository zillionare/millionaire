"""Lightweight stdlib-only workers for descendant-cleanup process tests."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_DESCENDANT_CODE = """
import os
import signal
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(str(os.getpid()))
while True:
    time.sleep(0.1)
"""


def _start_descendant(path: str) -> None:
    child = subprocess.Popen([sys.executable, "-c", _DESCENDANT_CODE, path])
    deadline = time.monotonic() + 10
    while not Path(path).exists():
        if child.poll() is not None:
            raise RuntimeError("stubborn descendant exited before becoming ready")
        if time.monotonic() >= deadline:
            child.kill()
            raise RuntimeError("stubborn descendant did not become ready")
        time.sleep(0.01)


def _spawn_stubborn_descendant(path: str) -> None:
    _start_descendant(path)
    while True:
        time.sleep(0.1)


def _spawn_leftover_and_return(path: str) -> None:
    _start_descendant(path)


def _nested_inner(path: str) -> None:
    Path(path).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(30)


def _nested_outer(path: str) -> str:
    from quantide.service.process_runner import run_isolated

    return run_isolated(_nested_inner, path, timeout=25).status


def loaded_test_frameworks() -> list[str]:
    """Return heavyweight parent packages visible to the spawned process."""
    return sorted(
        name
        for name in sys.modules
        if name == "pandas"
        or name.startswith("pandas.")
        or name == "tests"
        or name.startswith("tests.")
    )


def process_is_dead(pid: int) -> bool:
    """Query a real OS process state without treating a missing command as death."""
    if os.name == "nt":
        return _windows_process_dead(pid)
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return not state or state.startswith("Z")


def force_kill(pid: int) -> None:
    """Best-effort platform-native tree cleanup for local test evidence."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _windows_process_dead(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    wait_object_0 = 0
    wait_timeout = 258
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(process_query_limited_information | synchronize, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:
            return True
        raise OSError(error, "OpenProcess failed")
    try:
        wait = kernel32.WaitForSingleObject(handle, 0)
        if wait == wait_object_0:
            return True
        if wait != wait_timeout:
            raise OSError(ctypes.get_last_error(), "WaitForSingleObject failed")
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise OSError(ctypes.get_last_error(), "GetExitCodeProcess failed")
        return int(code.value) != still_active
    finally:
        kernel32.CloseHandle(handle)


def _collect_worker_semaphores(path: str) -> None:
    import inspect
    import json

    frame = inspect.currentframe()
    names: list[str] = []
    while frame is not None:
        queue = frame.f_locals.get("messages")
        if queue is not None and all(hasattr(queue, key) for key in ("_rlock", "_wlock", "_sem")):
            for key in ("_rlock", "_wlock", "_sem"):
                lock = getattr(queue, key)._semlock
                if lock.name:
                    names.append(lock.name)
            break
        frame = frame.f_back
    Path(path).write_text(json.dumps(names), encoding="utf-8")
    time.sleep(30)


def _nested_semaphore_outer(path: str) -> str:
    from quantide.service.process_runner import run_isolated

    return run_isolated(_collect_worker_semaphores, path, timeout=25).status
