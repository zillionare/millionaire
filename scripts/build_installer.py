"""Build native installers containing a relocatable Python and locked dependencies."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from scripts.artifact_paths import artifact_root, external_path
from scripts.build_macos_controller import build_menu_app
from scripts.build_windows_controller import build_tray_app

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = Path(__file__).resolve().parent / "packaging"
PYTHON_VERSION = "3.13.11"


def run(*command, **kwargs):
    """Fail the build on any unsuccessful tool, preserving its output."""
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def verify_wheel_source(wheel):
    """Refuse stale same-version wheels before spending time building a native installer."""
    paths = [*sorted((ROOT / "quantide").rglob("*.py"))]
    for directory in ("quantide/web/static", "quantide/web/templates", "quantide/assets"):
        paths.extend(path for path in (ROOT / directory).rglob("*") if path.is_file())
    with zipfile.ZipFile(wheel) as archive:
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            if archive.read(relative) != path.read_bytes():
                raise ValueError(f"Wheel differs from current source: {relative}; rebuild it first")


def stage_runtime(payload, wheel):
    """Use python-build-standalone through uv; avoid freezing strategy imports."""
    downloads = payload.parent / "python-download"
    environment = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(downloads), "UV_NATIVE_TLS": "true"}
    run("uv", "python", "install", PYTHON_VERSION, "--no-bin", env=environment)
    python = subprocess.check_output(
        ["uv", "python", "find", "--managed-python", PYTHON_VERSION],
        env=environment,
        text=True,
    ).strip()
    prefix = subprocess.check_output(
        [python, "-c", "import sys; print(sys.base_prefix)"], text=True
    )
    shutil.copytree(prefix.strip(), payload / "runtime", symlinks=True)
    executable = payload / "runtime" / ("python.exe" if os.name == "nt" else "bin/python3.13")
    run(
        "uv",
        "pip",
        "sync",
        "--break-system-packages",
        "--python",
        executable,
        "--require-hashes",
        ROOT / "requirements-runtime.txt",
        env=environment,
    )
    run(
        "uv",
        "pip",
        "install",
        "--break-system-packages",
        "--python",
        executable,
        "--no-deps",
        wheel,
        env=environment,
    )
    return executable


def bundle_openmp(payload):
    """Ship OpenMP with macOS installers so end users do not need Homebrew."""
    prefix = subprocess.check_output(["brew", "--prefix", "libomp"], text=True).strip()
    library = next(
        payload.glob("runtime/lib/python*/site-packages/lightgbm/lib/lib_lightgbm.dylib")
    )
    destination = library.parent / "libomp.dylib"
    destination.unlink(missing_ok=True)
    shutil.copy2(Path(prefix) / "lib/libomp.dylib", destination)
    shutil.copy2(Path(prefix) / "LICENSE.TXT", library.parent / "libomp-LICENSE.txt")
    dependencies = subprocess.check_output(["otool", "-L", str(library)], text=True)
    for line in dependencies.splitlines()[1:]:
        dependency = line.strip().split(" ", 1)[0]
        if dependency.endswith("libomp.dylib"):
            run("install_name_tool", "-change", dependency, "@loader_path/libomp.dylib", library)
    run("codesign", "--force", "--sign", "-", library)


def windows_wrapper(payload):
    """Verify the pinned service wrapper before putting it in a distributable."""
    metadata = json.loads((PACKAGING / "winsw.json").read_text(encoding="utf-8"))
    destination = payload / "millionaire-service.exe"
    shutil.copy2(PACKAGING / "licenses/WinSW.txt", payload / "WinSW-LICENSE.txt")
    with urllib.request.urlopen(metadata["url"], timeout=60) as response:
        destination.write_bytes(response.read())
    if hashlib.sha256(destination.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("WinSW checksum mismatch")


def build_deb(payload, version, output):
    """Produce a systemd package; persistent data is outside /opt."""
    root = payload.parent / "deb"
    destination = root / "opt/millionaire"
    destination.parent.mkdir(parents=True)
    shutil.copytree(payload, destination, symlinks=True)
    entry = root / "usr/bin/millionaire"
    entry.parent.mkdir(parents=True)
    entry.symlink_to("/opt/millionaire/millionaire")
    desktop = root / "usr/share/applications/millionaire.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=Millionaire\n"
        "Exec=/usr/bin/millionaire control\nTerminal=false\nCategories=Office;Finance;\n",
        encoding="utf-8",
    )
    control = root / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: millionaire\nVersion: {version}\nArchitecture: amd64\n"
        "Maintainer: Millionaire contributors\n"
        "Depends: libc6 (>= 2.28), libgomp1, libx11-6, libxext6, libxrender1\n"
        "Description: Millionaire quantitative research service\n",
        encoding="utf-8",
    )
    for name in ("postinst", "prerm", "postrm"):
        shutil.copy2(PACKAGING / f"debian-{name}.sh", control / name)
        (control / name).chmod(0o755)
    run("dpkg-deb", "--root-owner-group", "--build", root, output)


def build_platform(payload, version, output_dir):
    """Build on the target OS, then let CI install the resulting artifact."""
    architecture = platform.machine().lower()
    if os.name == "nt":
        windows_wrapper(payload)
        build_tray_app(payload)
        compiler = shutil.which("ISCC") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        run(
            compiler,
            f"/DPayload={payload}",
            f"/DAppVersion={version}",
            f"/DOutputDir={output_dir}",
            PACKAGING / "windows.iss",
        )
        return
    shutil.copy2(PACKAGING / "launcher.sh", payload / "millionaire")
    (payload / "millionaire").chmod(0o755)
    if sys.platform == "linux":
        if architecture not in {"x86_64", "amd64"}:
            raise ValueError("The first Ubuntu installer supports x86_64")
        build_deb(payload, version, output_dir / f"millionaire-{version}-ubuntu-amd64.deb")
        return
    for filename in ("install.sh", "uninstall.sh"):
        shutil.copy2(PACKAGING / filename, payload / filename)
    shutil.copy2(ROOT / "scripts/wait_for_service.py", payload / "wait-for-service.py")
    (payload / "install.sh").chmod(0o755)
    (payload / "VERSION").write_text(version, encoding="utf-8")
    name = f"millionaire-{version}-macos-{architecture}"
    with tarfile.open(output_dir / f"{name}.tar.gz", "w:gz") as archive:
        archive.add(payload, arcname=name)


def build_installer(wheel, work, output):
    """Stage and package inside a caller-owned temporary workspace."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "poetry"
    ]["version"]
    verify_wheel_source(wheel)
    payload = work.resolve() / "payload"
    payload.mkdir(parents=True)
    python = stage_runtime(payload, wheel.resolve())
    if sys.platform == "darwin":
        bundle_openmp(payload)
        build_menu_app(payload)
    run(
        python,
        "-c",
        "import lightgbm, polars_talib, tkinter; import quantide.cli",
        cwd=work.resolve(),
    )
    output.mkdir(parents=True, exist_ok=True)
    build_platform(payload, version, output)
    for path in sorted(output.iterdir()):
        if not path.name.endswith((".tar.gz", ".deb", ".exe")):
            continue
        path.with_name(path.name + ".sha256").write_text(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


def main():
    """Build outside the checkout; retain only requested packages after staging."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--work", type=external_path)
    parser.add_argument("--output", type=external_path, default=artifact_root() / "installers")
    args = parser.parse_args()
    if args.work:
        return build_installer(args.wheel, args.work, args.output.resolve())
    directory = artifact_root() / "work"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="installer-", dir=directory) as temporary:
        return build_installer(args.wheel, Path(temporary), args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
