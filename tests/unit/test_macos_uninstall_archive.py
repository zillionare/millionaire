"""Archive and installed uninstall entry points share the same ownership checks."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="macOS uses a POSIX shell installer")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/packaging/uninstall.sh"


@pytest.fixture
def installation(tmp_path):
    home = tmp_path / "user home"
    root = home / ".local/share/millionaire"
    binary = root / "versions/0.3.0.test/millionaire"
    binary.parent.mkdir(parents=True)
    log = tmp_path / "service-actions.txt"
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$ACTION_LOG"\n')
    binary.chmod(0o755)
    (root / "current").symlink_to(binary.parent)
    (root / ".millionaire-install").write_text("Millionaire managed installation\n")
    (root / "service-scope").write_text("user\n")
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "millionaire").symlink_to(root / "current/millionaire")
    (root / "bin-dir").write_text(str(bin_dir) + "\n")
    data = home / ".quantide/retained.txt"
    data.parent.mkdir()
    data.write_text("retain market data")
    archive = tmp_path / "extracted archive"
    archive.mkdir()
    shutil.copy2(SCRIPT, archive / "uninstall.sh")
    shutil.copy2(SCRIPT, root / "uninstall.sh")
    env = {"HOME": str(home), "PATH": os.defpath, "ACTION_LOG": str(log)}
    return root, archive, bin_dir, data, log, env


@pytest.mark.parametrize("entry", ["archive", "installed"])
def test_both_entry_points_remove_only_managed_installation(installation, entry):
    root, archive, bin_dir, data, log, env = installation
    script = (archive if entry == "archive" else root) / "uninstall.sh"
    result = subprocess.run([str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not root.exists()
    assert not (bin_dir / "millionaire").is_symlink()
    assert data.read_text() == "retain market data"
    assert (archive / "uninstall.sh").exists()
    assert log.read_text().splitlines() == ["control --uninstall", "service uninstall"]


def test_custom_root_and_system_scope_are_explicit(installation):
    root, archive, _, data, log, env = installation
    (root / "service-scope").write_text("system\n")
    env["MILLIONAIRE_INSTALL_ROOT"] = str(root)
    result = subprocess.run(["sh", str(archive / "uninstall.sh"), "--system"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == ["control --uninstall --system",
                                          "service uninstall --system"]
    assert data.exists()


@pytest.mark.parametrize("damage", ["marker", "scope", "launcher", "scope_mismatch"])
def test_incomplete_or_mismatched_installation_is_not_deleted(installation, damage):
    root, archive, _, data, log, env = installation
    args = []
    if damage == "marker":
        (root / ".millionaire-install").write_text("another application")
    elif damage == "scope":
        (root / "service-scope").write_text("unexpected")
    elif damage == "launcher":
        (root / "current").unlink()
    else:
        env["MILLIONAIRE_INSTALL_ROOT"] = str(root)
        args = ["--system"]
    result = subprocess.run(["sh", str(archive / "uninstall.sh"), *args],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert root.is_dir() and data.is_file()
    assert not log.exists()


def test_missing_installation_has_actionable_error_and_keeps_archive(tmp_path):
    result = subprocess.run(["sh", str(SCRIPT)], env={"HOME": str(tmp_path), "PATH": os.defpath},
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "MILLIONAIRE_INSTALL_ROOT" in result.stderr
    assert "--system" in result.stderr
    assert SCRIPT.is_file()
