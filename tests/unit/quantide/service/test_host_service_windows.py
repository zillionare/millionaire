"""Regress WinSW returning before a stopping service actually exits."""

import ctypes
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from quantide.service import host_service


@pytest.fixture
def service_runtime(monkeypatch, tmp_path):
    """Use an observable SCM sequence without invoking the local OS service."""
    runtime = SimpleNamespace(events=[], states=iter([]))

    def command(arguments, check=True):
        runtime.events.append(arguments[-1])
        return subprocess.CompletedProcess(arguments, 0, "ok", "")

    def state():
        value = next(runtime.states)
        runtime.events.append(value)
        return value

    monkeypatch.setattr(host_service, "install_root", lambda: tmp_path)
    monkeypatch.setattr(host_service, "_run", command)
    monkeypatch.setattr(host_service, "_windows_service_state", state)
    monkeypatch.setattr(
        host_service,
        "time",
        SimpleNamespace(monotonic=lambda: 0, sleep=lambda _seconds: None),
    )
    return runtime


def test_stop_waits_for_service_stopped(service_runtime):
    service_runtime.states = iter([3, 3, 1])
    result = host_service._windows_action("stop")
    assert result.returncode == 0
    assert service_runtime.events == ["stop", 3, 3, 1]


def test_start_waits_for_pending_stop(service_runtime):
    service_runtime.states = iter([3, 3, 1])
    host_service._windows_action("start")
    assert service_runtime.events == [3, 3, 1, "start"]


def test_uninstall_happens_after_actual_stop(service_runtime):
    service_runtime.states = iter([3, 1])
    host_service._windows_action("uninstall")
    assert service_runtime.events == ["stop", 3, 1, "uninstall"]


def test_failed_stop_does_not_uninstall(monkeypatch):
    command = Mock(return_value=subprocess.CompletedProcess([], 5, "", "Access denied"))
    state = Mock()
    monkeypatch.setattr(host_service, "_run", command)
    monkeypatch.setattr(host_service, "_windows_service_state", state)
    result = host_service._windows_action("uninstall")
    assert result.returncode == 5
    assert command.call_count == 1
    assert command.call_args.args[0][-1] == "stop"
    state.assert_not_called()


def test_stop_timeout_is_reported(monkeypatch):
    ticks = iter([0, 0.1, 0.6])
    monkeypatch.setattr(host_service, "_windows_service_state", lambda: 3)
    monkeypatch.setattr(
        host_service,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _seconds: None),
    )
    with pytest.raises(TimeoutError, match="did not finish stopping"):
        host_service._wait_windows_service_stopped(timeout=0.5)


@pytest.mark.parametrize("failure", [None, "manager", "service", "query"])
def test_native_scm_handles_are_closed(monkeypatch, failure):
    closed = []

    def query(_handle, status):
        status._obj.current_state = 3
        return failure != "query"

    api = SimpleNamespace(
        OpenSCManagerW=lambda *_args: 0 if failure == "manager" else 10,
        OpenServiceW=lambda *_args: 0 if failure == "service" else 20,
        QueryServiceStatus=query,
        CloseServiceHandle=lambda handle: closed.append(handle),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(ctypes, "WinError", lambda code: OSError(code, "denied"), raising=False)
    if failure:
        with pytest.raises(OSError, match="denied"):
            host_service._windows_service_state()
    else:
        assert host_service._windows_service_state() == 3
    expected = [] if failure == "manager" else [10] if failure == "service" else [20, 10]
    assert closed == expected
