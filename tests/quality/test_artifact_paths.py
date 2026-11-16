"""Keep generated artifacts outside the checkout and out of distributions."""

import contextlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import artifact_paths, validate_release_artifacts


class ArtifactPathsTest(unittest.TestCase):
    def test_configured_checkout_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            with (
                patch.object(artifact_paths, "ROOT", root),
                patch.dict(os.environ, {"MILLIONAIRE_ARTIFACTS_DIR": str(root / "build")}),
                self.assertRaisesRegex(ValueError, "outside"),
            ):
                artifact_paths.artifact_root()

    def test_default_output_is_outside_checkout(self):
        with patch.dict(os.environ, {}, clear=True):
            root = artifact_paths.artifact_root()
        self.assertTrue(root.is_absolute())
        self.assertFalse(root.is_relative_to(artifact_paths.ROOT))
        if os.name != "nt":
            self.assertTrue(root.is_relative_to(Path("/tmp").resolve()))

    def test_child_command_uses_temporary_coverage_and_cache_paths(self):
        with tempfile.TemporaryDirectory(prefix="ce artifacts ") as directory:
            root = Path(directory).resolve()
            code = "import os,pathlib; pathlib.Path(os.environ['COVERAGE_FILE']).write_text('ok')"
            with patch.dict(os.environ, {"MILLIONAIRE_ARTIFACTS_DIR": str(root)}):
                self.assertEqual(artifact_paths.main(["--run", sys.executable, "-c", code]), 0)
                environment = artifact_paths.artifact_environment()
            self.assertEqual((root / "coverage/.coverage").read_text(), "ok")
            self.assertIn(str(root / "pytest-cache"), environment["PYTEST_ADDOPTS"])

    def test_layout_rejects_root_artifacts_but_accepts_package_data_and_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "quantide/data").mkdir(parents=True)
            (root / "scripts/packaging").mkdir(parents=True)
            (root / ".coveragerc").write_text("[run]\nbranch = True\n")
            self.assertEqual(artifact_paths.layout_errors(root), [])
            (root / "site").mkdir()
            (root / ".coverage").touch()
            self.assertEqual(len(artifact_paths.layout_errors(root)), 2)

    def test_layout_command_fails_for_generated_checkout_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dist").mkdir()
            with (
                patch.object(artifact_paths, "ROOT", root),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(artifact_paths.main(["--check-layout"]), 1)

    def test_runtime_and_report_output_are_also_layout_violations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("quantide.db", "quantide.db-wal", "coverage.json", "logs", "models"):
                (root / name).touch()
            self.assertEqual(len(artifact_paths.layout_errors(root)), 5)

    def test_development_or_generated_content_blocks_wheel_and_sdist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / "bad.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("quantide/data/__init__.py", '"""Package data APIs."""')
            self.assertEqual(validate_release_artifacts._validate_artifact(wheel), [])
            with zipfile.ZipFile(wheel, "a") as archive:
                archive.writestr(".louke/project/reviews/internal.md", "private development notes")
            self.assertTrue(validate_release_artifacts._validate_artifact(wheel))
            source = root / "bad.tar.gz"
            with tarfile.open(source, "w:gz") as archive:
                payload = b"generated content"
                member = tarfile.TarInfo("millionaire-0.3.0/site/index.html")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            self.assertTrue(validate_release_artifacts._validate_artifact(source))
