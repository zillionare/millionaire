"""Native service management for the installed standalone application."""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast
from xml.etree.ElementTree import Element, SubElement, tostring

from quantide.config.output_paths import external_runtime_path
from quantide.config.paths import get_app_config_dir, normalize_data_home
from quantide.core.atomic_files import atomic_path

if TYPE_CHECKING:
    import pwd

SERVICE_NAME = os.environ.get("MILLIONAIRE_SERVICE_NAME", "millionaire-ce")
LABEL = f"ai.quantide.{SERVICE_NAME}"


class _WindowsCtypes(Protocol):
    WinDLL: Callable[..., Any]
    WinError: Callable[[int], OSError]
    get_last_error: Callable[[], int]


def install_root() -> Path:
    """Resolve the bundled runtime's parent, retaining relocatable paths."""
    return Path(sys.prefix).resolve().parent


def _run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True)


def _launchd_path(system: bool = False) -> Path:
    directory = Path("/Library/LaunchDaemons") if system else Path.home() / "Library/LaunchAgents"
    return directory / f"{LABEL}.plist"


def _launchd_profile(
    system: bool, user: str | None
) -> tuple[dict[str, str], pwd.struct_passwd | None]:
    if not system:
        return _environment(), None
    if not user or user == "root":
        raise ValueError("A system service requires --user with an existing non-root account")
    import pwd

    owner = pwd.getpwnam(user)
    base = Path("/Library/Application Support/MillionaireCE")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(base, owner.pw_uid, owner.pw_gid)
    environment = {
        name: str(external_runtime_path(os.environ.get(name, "").strip() or base / folder))
        for name, folder in (("QUANTIDE_CONFIG_HOME", "config"), ("QUANTIDE_DATA_HOME", "data"))
    }
    for directory in [
        *map(Path, environment.values()),
        Path(environment["QUANTIDE_CONFIG_HOME"]) / "logs",
    ]:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chown(directory, owner.pw_uid, owner.pw_gid)
    environment.update(HOME=owner.pw_dir, USER=owner.pw_name, LOGNAME=owner.pw_name)
    status = base.parent / "MillionaireCE-Status"
    status.mkdir(mode=0o755, parents=True, exist_ok=True)
    status.chmod(0o755)
    os.chown(status, owner.pw_uid, owner.pw_gid)
    environment["QUANTIDE_PUBLIC_WEB_PORT"] = str(status / "web-port")
    return environment, owner


def _environment() -> dict[str, str]:
    return {
        "QUANTIDE_CONFIG_HOME": str(get_app_config_dir()),
        "QUANTIDE_DATA_HOME": normalize_data_home(),
    }


def _install_launchd(system: bool = False, user: str | None = None) -> None:
    environment, owner = _launchd_profile(system, user)
    Path(environment["QUANTIDE_CONFIG_HOME"]).mkdir(mode=0o700, parents=True, exist_ok=True)
    logs = Path(environment["QUANTIDE_CONFIG_HOME"]) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "quantide.cli"],
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ExitTimeOut": 30,
        "StandardOutPath": str(logs / "service.log"),
        "StandardErrorPath": str(logs / "service-error.log"),
    }
    if owner is not None:
        import grp

        payload["UserName"] = owner.pw_name
        payload["GroupName"] = grp.getgrgid(owner.pw_gid).gr_name
    with atomic_path(_launchd_path(system)) as temporary:
        temporary.write_bytes(plistlib.dumps(payload))
        temporary.chmod(0o644)


def _install_systemd() -> None:
    destination = Path("/etc/systemd/system") / f"{SERVICE_NAME}.service"
    executable = str(Path(sys.executable).resolve()).replace('"', '\\"')
    content = (
        "[Unit]\nDescription=Millionaire CE\nAfter=network-online.target\n"
        "Wants=network-online.target\n[Service]\nType=simple\n"
        "User=millionaire-ce\nGroup=millionaire-ce\n"
        f'ExecStart="{executable}" -m quantide.cli\n'
        "Environment=QUANTIDE_CONFIG_HOME=/var/lib/millionaire-ce/config\n"
        "Environment=QUANTIDE_DATA_HOME=/var/lib/millionaire-ce/data\n"
        f"Environment=QUANTIDE_PUBLIC_WEB_PORT=/run/{SERVICE_NAME}/web-port\n"
        f"RuntimeDirectory={SERVICE_NAME}\n"
        "RuntimeDirectoryMode=0755\nRuntimeDirectoryPreserve=yes\n"
        "Restart=on-failure\nRestartSec=10\nTimeoutStopSec=30\n"
        "KillSignal=SIGTERM\nUMask=0077\nNoNewPrivileges=true\n"
        "ProtectSystem=strict\nProtectHome=true\n"
        f"ReadWritePaths=/var/lib/millionaire-ce /run/{SERVICE_NAME}\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
    with atomic_path(destination) as temporary:
        temporary.write_text(content, encoding="utf-8")
    _run(["systemctl", "daemon-reload"])
    _run(["systemctl", "enable", SERVICE_NAME])


def _install_windows() -> None:
    root = external_runtime_path(install_root())
    directory = external_runtime_path(
        os.environ.get("MILLIONAIRE_SERVICE_HOME", "").strip()
        or Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "MillionaireCE"
    )
    directory.mkdir(parents=True, exist_ok=True)
    service = Element("service")
    values = {
        "id": SERVICE_NAME,
        "name": "Millionaire CE",
        "description": "CE research service",
        "executable": str(Path(sys.executable)),
        "arguments": "-m quantide.cli",
        "workingdirectory": str(directory),
        "startmode": "Automatic",
        "stoptimeout": "30sec",
        "logpath": str(directory / "logs"),
    }
    for key, value in values.items():
        SubElement(service, key).text = value
    for name, folder in (("QUANTIDE_CONFIG_HOME", "config"), ("QUANTIDE_DATA_HOME", "data")):
        SubElement(service, "env", {"name": name, "value": str(directory / folder)})
    status = directory.parent / f"{directory.name}-Status"
    status.mkdir(parents=True, exist_ok=True)
    SubElement(
        service,
        "env",
        {
            "name": "QUANTIDE_PUBLIC_WEB_PORT",
            "value": str(status / "web-port"),
        },
    )
    SubElement(service, "onfailure", {"action": "restart", "delay": "10 sec"})
    SubElement(service, "log", {"mode": "roll-by-size"})
    config = root / "millionaire-service.xml"
    with atomic_path(config) as temporary:
        temporary.write_bytes(tostring(service, encoding="utf-8", xml_declaration=True))
    wrapper = str(root / "millionaire-service.exe")
    existing = _run(["sc.exe", "query", SERVICE_NAME], check=False)
    if existing.returncode == 0:
        _run(["sc.exe", "config", SERVICE_NAME, "binPath=", f'"{wrapper}"', "start=", "auto"])
    else:
        _run([wrapper, "install"])


def _launchd_action(action: str, system: bool = False) -> subprocess.CompletedProcess[str]:
    domain = "system" if system else f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    current = _run(["launchctl", "print", target], check=False)
    if action == "status":
        return current
    if action == "stop":
        if current.returncode != 0:
            return subprocess.CompletedProcess([], 0, "Service is stopped", "")
        pid = re.search(r"\bpid = (\d+)", current.stdout)
        result = _run(["launchctl", "bootout", target], check=False)
        if pid:
            _wait_for_exit(int(pid.group(1)))
        return result
    if current.returncode == 0:
        return _run(["launchctl", "kickstart", target], check=False)
    for attempt in range(6):
        result = _run(["launchctl", "bootstrap", domain, str(_launchd_path(system))], check=False)
        if result.returncode == 0:
            return result
        time.sleep(min(0.5 * (attempt + 1), 2))
    return result


def _wait_for_exit(pid: int) -> None:
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    raise TimeoutError(f"Service process {pid} did not stop")


def _windows_service_state() -> int:
    """Read the SCM state without depending on localized sc.exe output."""
    import ctypes
    from ctypes import wintypes

    class ServiceStatus(ctypes.Structure):
        """Native SERVICE_STATUS layout, with no locale-dependent text fields."""

        _fields_ = [
            (name, wintypes.DWORD)
            for name in (
                "service_type",
                "current_state",
                "controls",
                "exit_code",
                "specific_exit_code",
                "checkpoint",
                "wait_hint",
            )
        ]

    # These ctypes APIs exist on Windows, while type checking also runs on POSIX.
    windows_ctypes = cast(_WindowsCtypes, ctypes)
    api = windows_ctypes.WinDLL("advapi32", use_last_error=True)
    windows_error = windows_ctypes.WinError
    last_error = windows_ctypes.get_last_error
    api.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenSCManagerW.restype = wintypes.HANDLE
    api.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenServiceW.restype = wintypes.HANDLE
    api.QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(ServiceStatus)]
    api.QueryServiceStatus.restype = wintypes.BOOL
    api.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    api.CloseServiceHandle.restype = wintypes.BOOL
    manager = api.OpenSCManagerW(None, None, 1)
    if not manager:
        raise windows_error(last_error())
    try:
        handle = api.OpenServiceW(manager, SERVICE_NAME, 4)
        if not handle:
            raise windows_error(last_error())
        try:
            status = ServiceStatus()
            if not api.QueryServiceStatus(handle, ctypes.byref(status)):
                raise windows_error(last_error())
            return int(status.current_state)
        finally:
            api.CloseServiceHandle(handle)
    finally:
        api.CloseServiceHandle(manager)


def _wait_windows_service_stopped(timeout: float = 35) -> None:
    """Wait for SCM SERVICE_STOPPED even after a successful WinSW command."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _windows_service_state() == 1:
            return
        time.sleep(0.2)
    raise TimeoutError(f"Windows service {SERVICE_NAME} did not finish stopping")


def _windows_action(action: str) -> subprocess.CompletedProcess[str]:
    """Serialize stop/start and removal against actual service completion."""
    if action == "uninstall":
        stopped = _windows_action("stop")
        if stopped.returncode != 0:
            return stopped
    if action == "start" and _windows_service_state() == 3:
        _wait_windows_service_stopped()
    result = _run([str(install_root() / "millionaire-service.exe"), action], check=False)
    if action == "stop" and result.returncode == 0:
        _wait_windows_service_stopped()
    return result


def manage_service(action: str, *, system: bool = False, user: str | None = None) -> int:
    """Manage a registered OS service; controller exit never stops the service."""
    if action == "install":
        if sys.platform == "darwin":
            _install_launchd(system, user)
        elif sys.platform == "win32":
            _install_windows()
        else:
            _install_systemd()
        return 0
    if sys.platform == "darwin":
        if action == "uninstall":
            _launchd_action("stop", system)
            _launchd_path(system).unlink(missing_ok=True)
            return 0
        result = _launchd_action(action, system)
    elif sys.platform == "win32":
        result = _windows_action(action)
    else:
        if action == "uninstall":
            _run(["systemctl", "disable", "--now", SERVICE_NAME], check=False)
            (Path("/etc/systemd/system") / f"{SERVICE_NAME}.service").unlink(missing_ok=True)
            _run(["systemctl", "daemon-reload"])
            return 0
        result = _run(["systemctl", action, SERVICE_NAME], check=False)
    print(result.stdout or result.stderr)
    return result.returncode
