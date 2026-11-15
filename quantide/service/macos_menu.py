"""Install a login menu application independently of the macOS web service."""

import json
import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any

from quantide.config.output_paths import external_runtime_path
from quantide.core.atomic_files import atomic_path
from quantide.service.host_service import LABEL, _launchd_path, _run, install_root


def bundle_path() -> Path:
    """Return the menu application shipped alongside the bundled Python."""
    return install_root() / "Millionaire.app"


def _agent_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.controller.plist"


def _application_link(system: bool) -> Path:
    directory = os.environ.get("MILLIONAIRE_APPLICATIONS_DIR", "").strip()
    base = Path("/Applications") if system else Path.home() / "Applications"
    return external_runtime_path(Path(directory) if directory else base) / "Millionaire.app"


def _profile(system: bool) -> dict[str, Any]:
    service = plistlib.loads(_launchd_path(system).read_bytes())
    return {
        "launcher": str(install_root() / "millionaire"),
        "label": LABEL,
        "domain": "system" if system else f"gui/{os.getuid()}",
        "logs": str(Path(service["StandardOutPath"]).parent),
        "system": system,
        "portFile": service.get("EnvironmentVariables", {}).get("QUANTIDE_PUBLIC_WEB_PORT"),
    }


def _write_profile(app: Path, profile: dict[str, Any]) -> None:
    with atomic_path(app.parent / "controller.json") as temporary:
        temporary.write_text(json.dumps(profile), encoding="utf-8")
    info = app / "Contents/Info.plist"
    metadata = plistlib.loads(info.read_bytes())
    metadata["CFBundleIdentifier"] = f"{LABEL}.controller"
    with atomic_path(info) as temporary:
        temporary.write_bytes(plistlib.dumps(metadata))
    _run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)])


def _link_application(app: Path, system: bool) -> None:
    link = _application_link(system)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        existing = link.resolve() / "Contents/Info.plist"
        if existing.exists():
            metadata = plistlib.loads(existing.read_bytes())
            if metadata.get("CFBundleIdentifier") != f"{LABEL}.controller":
                raise FileExistsError(f"Another application owns {link}")
        link.unlink()
    if link.exists():
        raise FileExistsError(f"Another application owns {link}")
    link.symlink_to(app, target_is_directory=True)


def install_menu(system: bool = False) -> int:
    """Register the menu for login; system servers only get an Applications entry."""
    app = bundle_path()
    profile = _profile(system)
    _write_profile(app, profile)
    _link_application(app, system)
    if system:
        return 0
    agent = _agent_path()
    agent.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": f"{LABEL}.controller",
        "ProgramArguments": [str(app / "Contents/MacOS/MillionaireMenu")],
        "RunAtLoad": True,
        "StandardOutPath": str(Path(profile["logs"]) / "menu.log"),
        "StandardErrorPath": str(Path(profile["logs"]) / "menu-error.log"),
    }
    _run(["launchctl", "bootout", f"{profile['domain']}/{LABEL}.controller"], check=False)
    _quit_menu(app)
    with atomic_path(agent) as temporary:
        temporary.write_bytes(plistlib.dumps(payload))
        temporary.chmod(0o644)
    _run(["launchctl", "bootstrap", profile["domain"], str(agent)])
    return 0


def _quit_menu(app: Path) -> None:
    executable = app / "Contents/MacOS/MillionaireMenu"
    if executable.exists():
        subprocess.run([str(executable), "--quit"], check=True, timeout=10)


def uninstall_menu(system: bool = False) -> int:
    """Remove the login menu and its owned shortcut; retain application data."""
    if not system:
        _run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}.controller"], check=False)
        _agent_path().unlink(missing_ok=True)
    app = bundle_path()
    _quit_menu(app)
    link = _application_link(system)
    if link.is_symlink() and link.resolve() == app.resolve():
        link.unlink()
    return 0


def open_menu() -> int:
    """Reopen the app after the user has quit its menu."""
    _run(["open", str(bundle_path())])
    return 0
