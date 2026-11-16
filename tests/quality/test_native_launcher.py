"""The installed CLI must resolve launcher file symlinks as well as directory links."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class NativeLauncherTests(unittest.TestCase):
    def test_absolute_and_relative_symlinks_use_the_installed_runtime(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="ce-cli-") as directory:
            base = Path(directory)
            payload = base / "app with spaces"
            runtime = payload / "runtime/bin"
            runtime.mkdir(parents=True)
            python = runtime / "python3.13"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
            python.chmod(0o755)
            launcher = payload / "millionaire"
            shutil.copy2(root / "scripts/packaging/launcher.sh", launcher)
            link = base / "millionaire"
            link.symlink_to(launcher)
            relative = base / "relative"
            relative.symlink_to(link.name)
            for entry in (launcher, link, relative):
                result = subprocess.run(["sh", str(entry), "--help"], capture_output=True,
                                        text=True, check=True)
                self.assertEqual(result.stdout.splitlines(), ["-m", "quantide.cli", "--help"])
