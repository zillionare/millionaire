import importlib
import runpy
import sys

import fasthtml.common as fasthtml_common

import quantide.app_factory as app_factory


def test_module_entrypoint_defers_app_creation_until_server_import(monkeypatch):
    """Ensure `python -m quantide.app` does not build the app in the parent process."""
    created: list[dict[str, object]] = []
    sentinel_app = object()
    original_app_module = sys.modules.pop("quantide.app", None)
    original_main_module = sys.modules.get("__main__")

    def fake_create_app(*args, **kwargs):
        created.append({"args": args, "kwargs": kwargs})
        return sentinel_app

    def fake_serve(*, appname=None, **kwargs):
        assert appname == "quantide.app"
        assert kwargs == {}
        assert created == []

        module = importlib.import_module(appname)

        assert module.app is sentinel_app
        assert created == [
            {
                "args": (),
                "kwargs": {
                    "app_config_dir": None,
                    "enforce_single_instance": True,
                },
            }
        ]

    monkeypatch.setattr(app_factory, "create_app", fake_create_app)
    monkeypatch.setattr(fasthtml_common, "serve", fake_serve)

    try:
        runpy.run_module("quantide.app", run_name="__main__")
    finally:
        sys.modules.pop("quantide.app", None)
        if original_app_module is not None:
            sys.modules["quantide.app"] = original_app_module
        if original_main_module is not None:
            sys.modules["__main__"] = original_main_module
