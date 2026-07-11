"""v0.2-003 FR-0703 AC-FR-0703-3 app factory isolation contract."""

from __future__ import annotations

import pytest

pytest.importorskip("fasthtml", reason="app factory dependency is unavailable")

from quantide.app_factory import create_app


def test_create_app_uses_given_config_directory_without_singleton(tmp_path):
    """AC-FR-0703-3: database and state are placed under the supplied tmp_path."""
    config_dir = tmp_path / "quantide-config"

    app = create_app(app_config_dir=config_dir, enforce_single_instance=False)

    assert app.state.app_config_dir == config_dir
    assert (config_dir / "quantide.db").exists()
    assert not (config_dir / ".quantide.pid").exists()
