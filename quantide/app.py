#!/usr/bin/env python3

"""Main application entry point for the Quantide system."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fasthtml.common import serve

from quantide.app_factory import create_app

APP_IMPORT_PATH = f"{Path(__file__).resolve().parent.name}.app"


def init(
    app_config_dir: str | Path | None = None,
    enforce_single_instance: bool = True,
) -> Any:
    """Create the Quantide ASGI application.

    Args:
        app_config_dir: Optional runtime config directory override.
        enforce_single_instance: Whether to enforce the single-instance guard.

    Returns:
        The initialized ASGI application.
    """
    return create_app(
        app_config_dir=app_config_dir,
        enforce_single_instance=enforce_single_instance,
    )


def main() -> None:
    """Run the development server using the importable app module path.

    The `python -m quantide.app` entry point executes this file as `__main__`.
    FastHTML's default app-name inference would reduce that to plain `app`, which is
    not importable from the repository root. More importantly, constructing the ASGI
    app in the `__main__` process would trigger the single-instance check before the
    Uvicorn reloader imports the real `quantide.app` module, causing a false
    self-collision. Delegating app construction to the importable module path keeps
    the singleton check in the actual server process only.
    """
    serve(appname=APP_IMPORT_PATH)


if __name__ == "__main__":
    main()
else:
    app = init()
