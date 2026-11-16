"""Compile a native Windows notification-area controller using the OS toolchain."""

import os
import subprocess
from pathlib import Path

SOURCE = Path(__file__).parent / "packaging/windows"


def compile_controller(output, sources, *, reference=None, target="winexe"):
    """Use the inbox .NET Framework compiler; end users need no build tools."""
    compiler = Path(os.environ.get("WINDIR", r"C:\Windows")) / (
        "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler),
        "/nologo",
        "/codepage:65001",
        "/platform:x64",
        f"/target:{target}",
        f"/out:{output}",
        "/r:System.Windows.Forms.dll",
        "/r:System.Drawing.dll",
        "/r:System.ServiceProcess.dll",
        "/r:System.Xml.Linq.dll",
        f"/win32manifest:{SOURCE / 'app.manifest'}",
    ]
    if reference:
        command.append(f"/r:{reference}")
    subprocess.run([*command, *map(str, sources)], check=True, timeout=120)


def build_tray_app(payload):
    """Put the tray executable beside the service configuration it controls."""
    output = payload / "MillionaireTray.exe"
    compile_controller(output, sorted(SOURCE.glob("*.cs")))
    return output
