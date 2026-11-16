"""Compile the macOS menu application without adding Python runtime dependencies."""

import plistlib
import subprocess
from pathlib import Path

SOURCE = Path(__file__).parent / "packaging/macos"


def build_menu_app(payload):
    """Build a menu-only Cocoa application using the macOS CI toolchain."""
    app = payload / "Millionaire.app"
    contents = app / "Contents"
    executable = contents / "MacOS/MillionaireMenu"
    executable.parent.mkdir(parents=True)
    metadata = {
        "CFBundleIdentifier": "ai.quantide.millionaire.controller",
        "CFBundleExecutable": executable.name,
        "CFBundleName": "Millionaire",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    }
    (contents / "Info.plist").write_bytes(plistlib.dumps(metadata))
    subprocess.run(
        [
            "xcrun",
            "swiftc",
            "-swift-version",
            "5",
            "-O",
            "-framework",
            "Cocoa",
            "-target",
            "arm64-apple-macosx13.0",
            "-module-cache-path",
            str(payload.parent / "swift-cache"),
            str(SOURCE / "MenuController.swift"),
            str(SOURCE / "main.swift"),
            "-o",
            str(executable),
        ],
        check=True,
    )
    return app
