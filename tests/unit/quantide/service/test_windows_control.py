"""The installed Windows CLI opens the native tray without owning its service."""

from unittest.mock import Mock

from quantide.service import desktop_control, host_service


def test_control_opens_bundled_tray_and_returns_without_waiting(tmp_path, monkeypatch):
    tray = tmp_path / "MillionaireTray.exe"
    tray.touch()
    spawn = Mock()
    monkeypatch.setattr(desktop_control.sys, "platform", "win32")
    monkeypatch.setattr(host_service, "install_root", lambda: tmp_path)
    monkeypatch.setattr(desktop_control.subprocess, "Popen", spawn)
    assert desktop_control.main() == 0
    spawn.assert_called_once_with([str(tray)])


def test_source_windows_control_can_still_use_window_controller(tmp_path, monkeypatch):
    window = Mock()
    monkeypatch.setattr(desktop_control.sys, "platform", "win32")
    monkeypatch.setattr(host_service, "install_root", lambda: tmp_path)
    monkeypatch.setattr(desktop_control, "create_controller", lambda: window)
    assert desktop_control.main() == 0
    window.mainloop.assert_called_once()
