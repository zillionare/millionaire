"""Drive native menu handlers against the installed isolated acceptance service."""

import json
import plistlib
import subprocess
from pathlib import Path

from quantide.service.macos_menu import bundle_path
from scripts.artifact_paths import artifact_root
from scripts.build_macos_controller import SOURCE
from scripts.verify_installer import health


def verify_menu():
    """Compile the shipped controller with a Cocoa event-loop acceptance driver."""
    app = bundle_path()
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert metadata["LSUIElement"], "Menu app must not require a Dock window"
    work = artifact_root() / "work/menu-acceptance"
    work.mkdir(parents=True, exist_ok=True)
    driver = Path(__file__).resolve().parents[1] / "tests/assets/macos_menu/main.swift"
    executable = work / "verify-menu"
    subprocess.run(
        [
            "xcrun",
            "swiftc",
            "-swift-version",
            "5",
            "-framework",
            "Cocoa",
            "-module-cache-path",
            str(work / "swift-cache"),
            str(SOURCE / "MenuController.swift"),
            str(driver),
            "-o",
            str(executable),
        ],
        check=True,
        timeout=120,
    )
    result = subprocess.check_output(
        [str(executable), str(app.parent / "controller.json")], text=True, timeout=80
    )
    # launchd reports "running" before Python has bound the HTTP socket.
    # Wait for readiness, then ensure quitting cannot even restart the service.
    before = health()
    subprocess.run([str(app / "Contents/MacOS/MillionaireMenu"), "--quit"], check=True, timeout=10)
    after = health()
    assert before["pid"] == after["pid"], "Quitting the menu restarted the service"
    evidence = json.loads(result)
    evidence["service_pid_unchanged_on_quit"] = True
    return evidence
