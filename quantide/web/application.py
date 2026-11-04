"""FastHTML applications with a persistent session key outside the working directory."""

import secrets
from typing import Any

from fasthtml.common import fast_app as _fast_app
from filelock import FileLock

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import atomic_path


def session_secret() -> str:
    """Keep service startup independent of a writable current working directory."""
    path = ensure_app_config_dir() / ".session-key"
    with FileLock(str(path) + ".lock", timeout=10):
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if len(value) < 32:
                raise RuntimeError(f"Invalid session key file: {path}")
            return value
        value = secrets.token_urlsafe(48)
        with atomic_path(path) as temporary:
            temporary.chmod(0o600)
            temporary.write_text(value, encoding="utf-8")
        return value


def fast_app(*args: Any, **kwargs: Any) -> Any:
    """Create an application using the installation's durable session secret."""
    kwargs.setdefault("secret_key", session_secret())
    return _fast_app(*args, **kwargs)
