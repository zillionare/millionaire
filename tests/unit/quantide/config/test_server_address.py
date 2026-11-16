"""The listener uses the saved profile and preserves explicit overrides."""

import sqlite3

import pytest

from quantide.config import server_address


def _profile(path, host, port):
    path.mkdir()
    with sqlite3.connect(path / "quantide.db") as db:
        db.execute("CREATE TABLE app_state (id INTEGER PRIMARY KEY, app_host TEXT, app_port INTEGER)")
        db.execute("INSERT INTO app_state VALUES (1, ?, ?)", (host, port))


def test_profile_address_is_read_before_application_initialization(tmp_path, monkeypatch):
    config = tmp_path / "config"
    _profile(config, "0.0.0.0", 9123)
    monkeypatch.setattr(server_address, "get_app_config_dir", lambda: config)
    monkeypatch.delenv("QUANTIDE_HOST", raising=False)
    monkeypatch.delenv("QUANTIDE_PORT", raising=False)
    assert server_address.effective_address() == ("0.0.0.0", 9123)
    assert server_address.local_url() == "http://127.0.0.1:9123"
    monkeypatch.setenv("QUANTIDE_HOST", "127.0.0.1")
    monkeypatch.setenv("QUANTIDE_PORT", "8124")
    assert server_address.effective_address() == ("127.0.0.1", 8124)
    assert server_address.effective_address("0.0.0.0", 9999) == ("0.0.0.0", 9999)


def test_missing_or_invalid_profile_fails_closed_without_creating_a_database(tmp_path):
    missing = tmp_path / "missing"
    assert server_address.saved_address(missing) == ("127.0.0.1", 8130)
    assert not missing.exists()
    invalid = tmp_path / "invalid"
    _profile(invalid, "bad-host", 70000)
    assert server_address.saved_address(invalid) == ("127.0.0.1", 8130)


@pytest.mark.parametrize("port", [0, -1, 65536, "abc", None])
def test_invalid_port_is_rejected(port):
    with pytest.raises(ValueError):
        server_address.validate_address("0.0.0.0", port)


def test_cli_passes_saved_listener_to_uvicorn(tmp_path, monkeypatch):
    from quantide import cli

    config = tmp_path / "config"
    _profile(config, "0.0.0.0", 9123)
    monkeypatch.setattr(server_address, "get_app_config_dir", lambda: config)
    monkeypatch.delenv("QUANTIDE_HOST", raising=False)
    monkeypatch.delenv("QUANTIDE_PORT", raising=False)
    calls = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    assert cli.main(["--no-browser"]) == 0
    assert calls[0]["host"] == "0.0.0.0"
    assert calls[0]["port"] == 9123


def test_public_status_contains_only_the_port_and_needs_no_private_profile(tmp_path, monkeypatch):
    status = tmp_path / "public" / "web-port"
    monkeypatch.setenv("QUANTIDE_PUBLIC_WEB_PORT", str(status))
    server_address.publish_port(9231)
    assert status.read_text() == "9231"
    monkeypatch.setattr(server_address, "saved_address", lambda *args: pytest.fail("private DB read"))
    assert server_address.controller_url() == "http://127.0.0.1:9231"


def test_installed_entrypoint_restarts_on_the_saved_port(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    config = tmp_path / 'config'
    _profile(config, '0.0.0.0', port)
    env = dict(os.environ, QUANTIDE_CONFIG_HOME=str(config), QUANTIDE_DATA_HOME=str(tmp_path / 'data'))
    env.pop('QUANTIDE_HOST', None)
    env.pop('QUANTIDE_PORT', None)
    env.pop('TUSHARE_TOKEN', None)
    env['QUANTIDE_PUBLIC_WEB_PORT'] = str(tmp_path / 'public' / 'web-port')
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[4])
    for host in ('0.0.0.0', '127.0.0.1'):
        with sqlite3.connect(config / 'quantide.db') as db:
            db.execute('UPDATE app_state SET app_host=? WHERE id=1', (host,))
        process = subprocess.Popen([sys.executable, '-m', 'quantide.cli', '--no-browser'],
                                   env=env, cwd=tmp_path, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(f'web service exited early: {process.returncode}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as r:
                        assert r.status == 200
                        assert (tmp_path / 'public' / 'web-port').read_text() == str(port)
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                pytest.fail('web service did not bind the configured port')
        finally:
            process.terminate()
            process.wait(timeout=20)
