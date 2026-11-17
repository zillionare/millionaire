"""System-maintenance switch for the explicit user risk extension."""

from __future__ import annotations

import json
from pathlib import Path

from quantide.service.risk_programs import risk_program_registry
from tests.e2e.support.system_settings_session import system_settings_e2e_session


def test_system_page_copies_enables_and_disables_risk_extension() -> None:
    with system_settings_e2e_session() as session:
        assert risk_program_registry.list() == []
        response = session.client.post(
            "/system/datasource/risk-extension/copy-example", follow_redirects=True
        )
        assert response.status_code == 200
        assert "教学风控模板已复制并启用" in response.text
        assert "用户风控扩展（可选）" in response.text
        assert "已启用" in response.text

        extension_dir = Path(session.app_config_dir) / "extensions"
        assert (extension_dir / "risk_extensions.py").is_file()
        state = json.loads((extension_dir / "risk-extensions.json").read_text(encoding="utf-8"))
        assert state == {"enabled": True}

        response = session.client.post(
            "/system/datasource/risk-extension/disable", follow_redirects=True
        )
        assert response.status_code == 200
        assert "用户风控扩展已停用" in response.text
        state = json.loads((extension_dir / "risk-extensions.json").read_text(encoding="utf-8"))
        assert state == {"enabled": False}
        assert (extension_dir / "risk_extensions.py").is_file()
