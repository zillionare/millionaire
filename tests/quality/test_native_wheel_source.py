"""Reject native packaging of stale or incomplete wheels, including same-version builds."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import build_installer


class NativeWheelSourceTest(unittest.TestCase):
    def test_current_wheel_passes_and_source_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "quantide/module.py"
            source.parent.mkdir()
            source.write_text("VALUE = 1\n", encoding="utf-8")
            wheel = root / "same-version.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.write(source, "quantide/module.py")
            with patch.object(build_installer, "ROOT", root):
                build_installer.verify_wheel_source(wheel)
                source.write_text("VALUE = 2\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "differs from current source"):
                    build_installer.verify_wheel_source(wheel)

    def test_missing_required_static_asset_blocks_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "quantide/web/static/app.js"
            asset.parent.mkdir(parents=True)
            asset.write_text("window.test = true;", encoding="utf-8")
            wheel = root / "incomplete.whl"
            with zipfile.ZipFile(wheel, "w"):
                pass
            with patch.object(build_installer, "ROOT", root), self.assertRaises(KeyError):
                build_installer.verify_wheel_source(wheel)
