"""Read the saved web listener before the application database is initialized."""

import ipaddress
import os
import sqlite3
import sys
from pathlib import Path

from quantide.config.output_paths import external_runtime_path
from quantide.config.paths import get_app_config_dir
from quantide.core.atomic_files import atomic_path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8130


def validate_address(host: object, port: str | int | float | None) -> tuple[str, int]:
    """Accept explicit IP listeners and a usable TCP port."""
    try:
        text = str(host).strip()
        address = str(ipaddress.ip_address("127.0.0.1" if text == "localhost" else text))
        if port is None:
            raise ValueError("invalid port")
        number = int(port)
        if not 1 <= number <= 65535:
            raise ValueError("invalid port")
    except (TypeError, ValueError) as exc:
        raise ValueError("监听地址或端口无效；端口必须介于 1 和 65535。") from exc
    return address, number


def saved_address(config_dir: str | Path | None = None) -> tuple[str, int]:
    """Read only the listener fields without creating or modifying a profile."""
    directory = Path(config_dir) if config_dir is not None else get_app_config_dir()
    database = directory / "quantide.db"
    if not database.is_file():
        return DEFAULT_HOST, DEFAULT_PORT
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as conn:
            row = conn.execute("SELECT app_host, app_port FROM app_state WHERE id=1").fetchone()
        if row:
            return validate_address(row[0], row[1])
    except (OSError, sqlite3.Error, ValueError):
        pass
    return DEFAULT_HOST, DEFAULT_PORT


def effective_address(host: str | None = None, port: int | str | None = None) -> tuple[str, int]:
    """Use explicit arguments, environment, then persisted settings, in that order."""
    saved_host, saved_port = saved_address()
    selected_host = host if host is not None else os.getenv("QUANTIDE_HOST") or saved_host
    selected_port = port if port is not None else os.getenv("QUANTIDE_PORT") or saved_port
    _, validated_port = validate_address(DEFAULT_HOST, selected_port)
    return str(selected_host).strip(), validated_port


def local_url(config_dir: str | Path | None = None) -> str:
    """Use loopback for the foreground controller, including wildcard listeners."""
    _, port = saved_address(config_dir)
    return f"http://127.0.0.1:{port}"


def publish_port(port: int | str) -> None:
    """Publish only the listening port when the native service provides a public path."""
    path = os.getenv("QUANTIDE_PUBLIC_WEB_PORT", "").strip()
    if not path:
        return
    _, port = validate_address(DEFAULT_HOST, port)
    with atomic_path(external_runtime_path(path)) as temporary:
        temporary.write_text(str(port), encoding="ascii")
        temporary.chmod(0o644)


def controller_url() -> str:
    """Let non-privileged desktop controls read the service's non-secret port."""
    public = os.getenv("QUANTIDE_PUBLIC_WEB_PORT", "").strip()
    if not public and sys.platform.startswith("linux"):
        name = os.getenv("MILLIONAIRE_SERVICE_NAME", "millionaire-ce")
        public = str(Path("/run") / name / "web-port")
    if public:
        try:
            _, port = validate_address(DEFAULT_HOST, Path(public).read_text(encoding="ascii"))
            return f"http://127.0.0.1:{port}"
        except (OSError, UnicodeError, ValueError):
            pass
    return local_url()
