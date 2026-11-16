"""FastHTML applications with a persistent session key outside the working directory."""

import secrets
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, overload

from fasthtml import common as _fasthtml_common
from fasthtml import core as _fasthtml_core
from fasthtml import fastapp as _fasthtml_fastapp
from fasthtml.common import Link, Script, Style
from fasthtml.common import fast_app as _fast_app
from filelock import FileLock

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import atomic_path
from quantide.web.theme import VENDOR_PREFIX

_Handler = TypeVar("_Handler", bound=Callable[..., Any])


def _use_local_default_headers() -> None:
    """Replace FastHTML's CDN defaults before any application is created."""
    for module in (_fasthtml_core, _fasthtml_common):
        module.htmxsrc = Script(src=f"{VENDOR_PREFIX}/htmx-1.9.12.min.js")
        module.fhjsscr = Script(src=f"{VENDOR_PREFIX}/fasthtml-1.0.12.js")
        module.surrsrc = Script(src=f"{VENDOR_PREFIX}/surreal.js")
        module.scopesrc = Script(src=f"{VENDOR_PREFIX}/css-scope-inline.js")
    picolink = (
        Link(rel="stylesheet", href=f"{VENDOR_PREFIX}/pico-2.1.1.min.css"),
        Style(":root { --pico-font-size: 100%; }"),
    )
    _fasthtml_common.picolink = picolink
    _fasthtml_fastapp.picolink = picolink


_use_local_default_headers()


class _RouteDecorator(Protocol):
    def __call__(self, handler: _Handler) -> _Handler: ...


class RouteRegistrar(Protocol):
    """FastHTML's route decorator preserves the registered handler."""

    def __call__(self, path: str, *args: Any, **kwargs: Any) -> _RouteDecorator: ...


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


@overload
def fast_app(db_file: None = None, *args: Any, **kwargs: Any) -> tuple[Any, RouteRegistrar]: ...


@overload
def fast_app(db_file: str, *args: Any, **kwargs: Any) -> tuple[Any, ...]: ...


def fast_app(*args: Any, **kwargs: Any) -> Any:
    """Create an application using the installation's durable session secret."""
    kwargs.setdefault("secret_key", session_secret())
    return _fast_app(*args, **kwargs)
