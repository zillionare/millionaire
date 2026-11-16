"""Install the built artifact and exercise the native service lifecycle."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from scripts.artifact_paths import artifact_root, external_path


def run(command, environment):
    """Retain installer and service output in the CI log."""
    subprocess.run(list(map(str, command)), check=True, env=environment, timeout=120)


def health(previous_pid=None):
    """Wait for a responsive service, optionally requiring a new process."""
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8130/api/health", timeout=1) as response:
                payload = json.load(response)
            if payload["pid"] != previous_pid:
                return payload
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Native service did not become healthy")


def verify_checksum(artifact):
    """Never install an artifact that differs from its published checksum."""
    expected = artifact.with_name(artifact.name + ".sha256").read_text(encoding="utf-8").split()[0]
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
        raise ValueError("Installer checksum mismatch")


class NativeInstallation:
    """Platform-specific installer commands with one shared acceptance contract."""

    def __init__(self, artifact, directory):
        self.artifact = artifact.resolve()
        self.directory = directory
        self.environment = {
            **os.environ,
            "MILLIONAIRE_SERVICE_NAME": "millionaire-ci",
            "MILLIONAIRE_SERVICE_HOME": str(directory / "service-data"),
            "MILLIONAIRE_INSTALL_ROOT": str(directory / "installed"),
            "MILLIONAIRE_BIN_DIR": str(directory / "bin"),
            "MILLIONAIRE_APPLICATIONS_DIR": str(directory / "Applications"),
            "QUANTIDE_CONFIG_HOME": str(directory / "config"),
            "QUANTIDE_DATA_HOME": str(directory / "data"),
        }
        self.python = None
        self.config = directory / "config"
        self.source = directory / "extracted"

    def install(self):
        """Install or upgrade, using the exact same distributable twice."""
        if sys.platform == "darwin":
            if not self.source.exists():
                self.source.mkdir()
                with tarfile.open(self.artifact) as archive:
                    archive.extractall(self.source, filter="data")
            script = next(self.source.glob("*/install.sh"))
            run(["sh", script], self.environment)
            self.python = self.directory / "installed/current/runtime/bin/python3.13"
        elif os.name == "nt":
            run(
                [
                    self.artifact,
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                    f"/DIR={self.directory / 'installed'}",
                    f"/LOG={self.directory / 'setup.log'}",
                ],
                self.environment,
            )
            self.python = self.directory / "installed/runtime/python.exe"
            self.config = self.directory / "service-data/config"
        else:
            run(["dpkg", "-i", self.artifact], self.environment)
            self.python = Path("/opt/millionaire/runtime/bin/python3.13")
            self.config = Path("/var/lib/millionaire/config")

    def command(self):
        """Exercise the public symlink, not just the internal runtime executable."""
        if os.name == "nt":
            return [self.python, "-m", "quantide.cli"]
        entry = (
            self.directory / "bin/millionaire"
            if sys.platform == "darwin"
            else Path("/usr/bin/millionaire")
        )
        return [entry]

    def service(self, action):
        run([*self.command(), "service", action], self.environment)

    def uninstall(self):
        """Default uninstall retains data; test cleanup is explicitly separate."""
        if os.name == "nt":
            run(
                [
                    self.directory / "installed/unins000.exe",
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                ],
                self.environment,
            )
        elif sys.platform == "darwin":
            # End users may run the archive's script from their extraction folder.
            run(["sh", next(self.source.glob("*/uninstall.sh"))], self.environment)
        else:
            run(["dpkg", "--remove", "millionaire"], self.environment)


def verify(installation):
    """Assert persistence and recovery, rather than only successful installer exits."""
    # Refuse to operate if another application already owns the production port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8130))
    installation.install()
    first = health()
    run([*installation.command(), "--help"], installation.environment)
    controller = subprocess.check_output(
        [str(installation.python), str(Path(__file__).with_name("verify_controller.py"))],
        env=installation.environment,
        text=True,
        timeout=180,
    )
    marker = installation.config / "installation-persistence.txt"
    marker.write_text("must survive restart, upgrade and default uninstall", encoding="utf-8")
    extension = installation.config / "extensions/quote_provider.py"
    extension.parent.mkdir(exist_ok=True)
    extension.write_text("# retained user extension\n", encoding="utf-8")
    installation.service("stop")
    installation.service("start")
    restarted = health(first["pid"])
    if os.name == "nt":
        run(["taskkill", "/PID", str(restarted["pid"]), "/F"], installation.environment)
    else:
        import signal

        os.kill(restarted["pid"], signal.SIGKILL)
    recovered = health(restarted["pid"])
    installation.install()
    upgraded = health(recovered["pid"])
    assert marker.read_text(encoding="utf-8").startswith("must survive")
    installation.uninstall()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 8130)) != 0, "Service still listens after uninstall"
    assert marker.exists(), "Default uninstall deleted persistent user data"
    assert extension.read_text(encoding="utf-8") == "# retained user extension\n"
    return {
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "installer_sha256": hashlib.sha256(installation.artifact.read_bytes()).hexdigest(),
        "controller": json.loads(controller),
        "fresh": first,
        "restart": restarted,
        "crash_recovery": recovered,
        "upgrade": upgraded,
        "data_retained_on_uninstall": True,
        "extension_retained_on_upgrade_uninstall": True,
    }


def main():
    """Publish evidence only for actual native installation checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=artifact_root() / "installers")
    parser.add_argument(
        "--report-dir", type=external_path, default=artifact_root() / "quality/installers"
    )
    args = parser.parse_args()
    artifacts = [
        path for path in args.directory.iterdir() if path.name.endswith((".tar.gz", ".deb", ".exe"))
    ]
    if len(artifacts) != 1:
        raise ValueError("Expected exactly one native installer for this platform")
    verify_checksum(artifacts[0])
    evidence = args.report_dir
    evidence.mkdir(parents=True, exist_ok=True)
    work = artifact_root() / "work"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="millionaire-installer-", dir=work) as temporary:
        installation = NativeInstallation(artifacts[0], Path(temporary))
        try:
            result = verify(installation)
            (evidence / "verified.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        finally:
            if os.name == "nt" and (Path(temporary) / "installed/unins000.exe").exists():
                installation.uninstall()
            if installation.python is not None and installation.python.exists():
                if sys.platform == "darwin":
                    subprocess.run(
                        [str(installation.python), "-m", "quantide.cli", "control", "--uninstall"],
                        env=installation.environment,
                        check=False,
                        timeout=15,
                    )
                subprocess.run(
                    [str(installation.python), "-m", "quantide.cli", "service", "uninstall"],
                    env=installation.environment,
                    check=False,
                    timeout=60,
                )
            for log in Path(temporary).rglob("*.log"):
                shutil.copy2(log, evidence / log.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
