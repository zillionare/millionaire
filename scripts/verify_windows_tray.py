"""Exercise the shipped Windows tray assembly against the isolated native service."""

import ctypes
import json
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from quantide.service.host_service import SERVICE_NAME, install_root
from scripts.artifact_paths import artifact_root
from scripts.build_windows_controller import compile_controller
from scripts.verify_installer import health


def _wait_for_local_tray():
    """Wait for the instance in this session, independently of the login desktop."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        handle = kernel.OpenMutexW(0x100000, False, f"Local\\Millionaire.{SERVICE_NAME}")
        if handle:
            kernel.CloseHandle(handle)
            return
        time.sleep(0.05)
    raise TimeoutError("Tray instance did not register in the current Windows session")


def verify_tray():
    """Drive the installed NotifyIcon menu and assert independent service lifetime."""
    root = install_root()
    executable = root / "MillionaireTray.exe"
    startup = Path(os.environ["PROGRAMDATA"]) / (
        "Microsoft/Windows/Start Menu/Programs/StartUp/Millionaire.lnk"
    )
    assert startup.exists(), "Installer did not register the login tray shortcut"
    work = artifact_root() / "work/tray-acceptance"
    work.mkdir(parents=True, exist_ok=True)
    assembly = work / executable.name
    shutil.copy2(executable, assembly)
    driver = Path(__file__).resolve().parents[1] / "tests/assets/windows_tray/TraySmoke.cs"
    smoke = work / "verify-tray.exe"
    compile_controller(smoke, [driver], reference=assembly)
    report = work / "menu.json"
    result = subprocess.run([str(smoke), str(root), str(report)], check=False, timeout=90)
    if result.returncode:
        raise RuntimeError(report.read_text(encoding="utf-8"))
    # Inno can launch into the user's desktop while CI/SSH runs in session zero.
    primary = subprocess.Popen([str(executable)])
    _wait_for_local_tray()
    subprocess.run([str(executable)], check=True, timeout=10)
    before = health()
    subprocess.run([str(executable), "--quit"], check=True, timeout=10)
    primary.wait(timeout=10)
    after = health()
    assert before["pid"] == after["pid"], "Quitting the tray restarted the service"
    evidence = json.loads(report.read_text(encoding="utf-8"))
    evidence.update(login_shortcut=True, single_instance=True, service_pid_unchanged_on_quit=True)
    return evidence
