"""Kernel-backed single-instance ownership that survives stale PID files and process crashes."""

import atexit
import contextlib
import os
from pathlib import Path

from filelock import FileLock, Timeout

from quantide.core.atomic_files import atomic_path


def acquire_instance_guard(pid_path: Path, product_name: str) -> None:
    """Retain the OS lock until process exit; treat the PID file as diagnostic information."""
    pid_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    guard = FileLock(str(pid_path) + ".lock", timeout=0)
    try:
        guard.acquire()
    except Timeout as exc:
        raise RuntimeError(f"{product_name} 已经在运行，请先停止已有服务。") from exc
    try:
        with atomic_path(pid_path) as temporary:
            temporary.write_text(str(os.getpid()), encoding="utf-8")
    except BaseException:
        guard.release()
        raise

    def release() -> None:
        with contextlib.suppress(FileNotFoundError):
            pid_path.unlink()
        guard.release()

    # The callback retains a strong reference to the lock. SIGKILL/reboot releases
    # the kernel handle even though this callback cannot run, allowing recovery.
    atexit.register(release)
