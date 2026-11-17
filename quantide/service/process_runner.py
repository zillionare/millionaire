"""Terminable subprocess execution for long factor computations."""

from __future__ import annotations

import ctypes
import multiprocessing
import os
import pickle
import signal
import subprocess
import sys
import tempfile
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
MEMORY = "memory"


@dataclass(frozen=True)
class ProcessOutcome:
    status: str
    value: Any = None
    error: str = ""


def _limit_child_memory(limit: int | None) -> None:
    """Apply the platform-appropriate child memory ceiling before user code.

    Resident memory is enforced by the parent's native RSS monitor on Linux and
    Windows.  Linux deliberately receives no RLIMIT_AS/RLIMIT_DATA: numeric
    libraries reserve large anonymous address ranges and thread stacks that are
    not resident, so an address-space cap would abort healthy work.  macOS keeps
    its verified RLIMIT_DATA path.
    """
    if not limit or os.name == "nt" or sys.platform.startswith("linux"):
        return
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return
    key = getattr(resource, "RLIMIT_DATA", None)
    if key is None:
        return
    try:
        resource.setrlimit(key, (limit, limit))
    except (OSError, ValueError):
        pass


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobBasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _JobExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _windows_job(pid: int) -> int | None:
    """Assign the spawned process to a kill-on-close Job Object."""
    if os.name != "nt":
        return None
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = _JobExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        handle = kernel32.OpenProcess(0x0200 | 0x1000 | 0x0001, False, int(pid))
        assigned = bool(configured and handle and kernel32.AssignProcessToJobObject(job, handle))
        if handle:
            kernel32.CloseHandle(handle)
        if not assigned:
            kernel32.CloseHandle(job)
            return None
        return int(job)
    except Exception:  # pragma: no cover - non-Windows import
        return None


def _close_windows_job(job: int | None) -> None:
    if not job or os.name != "nt":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(job)
    except Exception:  # pragma: no cover
        pass


def _windows_rss_bytes(pid: int) -> int | None:
    """Read private working set through typed Win32 calls, independent of locale."""
    if os.name != "nt":
        return None
    try:
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        process_vm_read = 0x0010
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        psapi = ctypes.WinDLL("psapi", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            process_query_limited_information | process_vm_read, False, int(pid)
        )
        if not handle:
            return None
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        try:
            ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
            return int(counters.WorkingSetSize) if ok else None
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # pragma: no cover - non-Windows import
        return None


def _rss_bytes(pid: int) -> int | None:
    """Read resident memory without adding a psutil dependency."""
    if os.name == "nt":
        return _windows_rss_bytes(pid)
    try:
        output = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        ).stdout.strip()
        return int(output.split()[0]) * 1024 if output else None
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None


def _write_result(path: str, ok: bool, payload: Any) -> None:
    temporary = f"{path}.tmp"
    with open(temporary, "wb") as handle:
        pickle.dump((ok, payload), handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _child(
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result_path: str,
    memory_bytes: int | None,
) -> None:
    if os.name != "nt":
        if not os.environ.get("QUANTIDE_OWNED_WORKER"):
            try:
                os.setsid()
            except OSError:
                pass
        os.environ["QUANTIDE_OWNED_WORKER"] = "1"
    _limit_child_memory(memory_bytes)
    try:
        _write_result(result_path, True, target(*args, **kwargs))
    except BaseException as exc:
        try:
            _write_result(result_path, False, f"{type(exc).__name__}: {exc}")
        except BaseException:
            pass


def _descendant_pids(root_pid: int) -> list[int]:
    if os.name == "nt":
        return []
    try:
        output = subprocess.run(
            ["ps", "-eo", "pid=,ppid="], capture_output=True, text=True, timeout=2, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            continue
        pid, parent = int(parts[0]), int(parts[1])
        children.setdefault(parent, []).append(pid)
    found: list[int] = []
    stack = [root_pid]
    while stack:
        parent = stack.pop()
        for child in children.get(parent, []):
            found.append(child)
            stack.append(child)
    return found


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except (OSError, ProcessLookupError):
        pass


def _owns_process_group(pid: int, *, exited_hint: bool = False) -> bool:
    try:
        return os.getpgid(pid) == pid
    except ProcessLookupError:
        return exited_hint
    except OSError:
        return False


def _signal_children(pids: list[int], sig: int) -> None:
    for child in reversed(pids):
        try:
            os.kill(child, sig)
        except (OSError, ProcessLookupError):
            pass


def _terminate(process: BaseProcess, owned_group_hint: bool | None = None) -> None:
    pid = process.pid
    if pid is None:
        process.join(timeout=2)
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=3,
            check=False,
        )
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        return
    owned_group = _owns_process_group(pid, exited_hint=bool(owned_group_hint))
    descendants = [] if owned_group else _descendant_pids(pid)
    if owned_group:
        _signal_group(pid, signal.SIGTERM)
    else:
        _signal_children(descendants, signal.SIGTERM)
    if process.is_alive():
        process.terminate()
    process.join(timeout=2)
    if owned_group:
        _signal_group(pid, signal.SIGKILL)
    else:
        _signal_children(descendants, signal.SIGKILL)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)


def _budget_outcome(
    process: BaseProcess,
    deadline: float | None,
    cancel: threading.Event | None,
) -> ProcessOutcome | None:
    if cancel is not None and cancel.is_set():
        return ProcessOutcome(CANCELLED)
    if deadline is not None and time.monotonic() >= deadline:
        return ProcessOutcome(TIMEOUT, error="computation exceeded its time budget")
    return None


def _memory_outcome(
    pid: int | None, memory_bytes: int | None, failures: int
) -> tuple[ProcessOutcome | None, int]:
    if memory_bytes is None or pid is None:
        return None, 0
    rss = _rss_bytes(pid)
    if rss is None:
        failures += 1
        if failures >= 20:
            return ProcessOutcome(FAILED, error="memory budget could not be measured"), failures
        return None, failures
    if rss > memory_bytes:
        return (
            ProcessOutcome(
                MEMORY,
                error=f"computation exceeded its memory budget ({rss} > {memory_bytes})",
            ),
            0,
        )
    return None, 0


def _read_result(path: str) -> tuple[bool, Any]:
    with open(path, "rb") as handle:
        ok, payload = pickle.load(handle)
    return bool(ok), payload


def _ready_result(process: BaseProcess, result_path: str) -> ProcessOutcome | None:
    if not os.path.exists(result_path):
        return None
    try:
        ok, payload = _read_result(result_path)
    except (EOFError, OSError, pickle.UnpicklingError):
        if process.is_alive():
            return None
        return ProcessOutcome(FAILED, error="worker result was not readable")
    # Keep the worker unreaped until _terminate can inspect its process group;
    # an exited leader must still be able to kill descendants in that group.
    if ok:
        return ProcessOutcome(SUCCEEDED, payload)
    return ProcessOutcome(FAILED, error=str(payload))


def _await_result(
    process: BaseProcess,
    result_path: str,
    deadline: float | None,
    cancel: threading.Event | None,
    memory_bytes: int | None,
) -> ProcessOutcome:
    rss_failures = 0
    while True:
        budget = _budget_outcome(process, deadline, cancel)
        if budget is not None:
            return budget
        memory_outcome, rss_failures = _memory_outcome(process.pid, memory_bytes, rss_failures)
        if memory_outcome is not None:
            return memory_outcome
        ready = _ready_result(process, result_path)
        if ready is not None:
            return ready
        if not process.is_alive():
            return ProcessOutcome(FAILED, error="worker exited without a result")
        time.sleep(0.05)


def run_isolated(
    target: Callable[..., Any],
    *args: Any,
    timeout: float | None = None,
    memory_bytes: int | None = None,
    cancel: threading.Event | None = None,
    kwargs: dict[str, Any] | None = None,
) -> ProcessOutcome:
    """Run one picklable target in a child process and terminate it on budget expiry."""
    context = multiprocessing.get_context("spawn")
    descriptor, result_path = tempfile.mkstemp(prefix="quantide-worker-", suffix=".result")
    os.close(descriptor)
    os.unlink(result_path)
    owned_group_hint = not os.environ.get("QUANTIDE_OWNED_WORKER")
    process = context.Process(
        target=_child,
        args=(target, args, kwargs or {}, result_path, memory_bytes),
        daemon=False,
    )
    process.start()
    job = _windows_job(process.pid) if process.pid is not None else None
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        return _await_result(process, result_path, deadline, cancel, memory_bytes)
    finally:
        _terminate(process, owned_group_hint)
        _close_windows_job(job)
        for path in (result_path, f"{result_path}.tmp"):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
