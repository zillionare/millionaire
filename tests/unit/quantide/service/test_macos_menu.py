"""The login menu has its own lifetime, owned shortcut and service profile."""

import json
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quantide.service import macos_menu


class MacOSMenuTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="millionaire-menu-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = self.root / "version with spaces"
        self.app = self.payload / "Millionaire.app"
        (self.app / "Contents").mkdir(parents=True)
        (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({}))
        self.agent = self.root / "agent.plist"
        self.link = self.root / "Applications/Millionaire.app"
        service = self.root / "service.plist"
        service.write_bytes(plistlib.dumps({"StandardOutPath": str(self.root / "logs/service.log")}))
        for name, value in (("install_root", self.payload), ("_launchd_path", service),
                            ("_agent_path", self.agent), ("_application_link", self.link)):
            mocked = patch.object(macos_menu, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.command = patch.object(macos_menu, "_run").start()
        self.addCleanup(patch.stopall)
        patch.object(macos_menu, "_quit_menu").start()
        patch.object(os, "getuid", return_value=12345, create=True).start()

    def test_install_registers_separate_login_job_and_actual_log_path(self):
        macos_menu.install_menu()
        self.assertEqual(self.link.resolve(), self.app.resolve())
        profile = json.loads((self.payload / "controller.json").read_text())
        self.assertEqual(profile["launcher"], str(self.payload / "millionaire"))
        self.assertEqual(profile["logs"], str(self.root / "logs"))
        self.assertEqual(profile["domain"], "gui/12345")
        agent = plistlib.loads(self.agent.read_bytes())
        self.assertEqual(agent["Label"], f"{macos_menu.LABEL}.controller")
        self.assertTrue(agent["RunAtLoad"])
        self.assertNotIn("KeepAlive", agent)
        self.assertEqual(agent["ProgramArguments"], [str(self.app / "Contents/MacOS/MillionaireMenu")])
        self.command.assert_any_call(["launchctl", "bootstrap", "gui/12345", str(self.agent)])

    def test_menu_uninstall_does_not_stop_web_service_or_remove_data(self):
        macos_menu.install_menu()
        self.command.reset_mock()
        macos_menu.uninstall_menu()
        self.assertFalse(self.agent.exists())
        self.assertFalse(self.link.is_symlink())
        self.assertTrue(self.app.exists())
        self.assertEqual(self.command.call_args.args[0],
                         ["launchctl", "bootout", f"gui/12345/{macos_menu.LABEL}.controller"])

    def test_existing_unrelated_application_is_never_replaced(self):
        self.link.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            macos_menu.install_menu()
        self.assertTrue(self.link.is_dir())
        self.assertFalse(self.agent.exists())

    def test_system_install_has_app_entry_without_a_root_gui_job(self):
        macos_menu.install_menu(system=True)
        profile = json.loads((self.payload / "controller.json").read_text())
        self.assertEqual(profile["domain"], "system")
        self.assertTrue(profile["system"])
        self.assertFalse(self.agent.exists())

    def test_bootstrap_failure_is_reported_to_installer(self):
        def fail_bootstrap(command, **kwargs):
            if "bootstrap" in command:
                raise RuntimeError("no GUI session")

        self.command.side_effect = fail_bootstrap
        with self.assertRaisesRegex(RuntimeError, "no GUI session"):
            macos_menu.install_menu()
