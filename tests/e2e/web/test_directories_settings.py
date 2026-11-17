"""Administrators can persist and probe the three workspace directories."""

import pytest

from quantide.service.init_wizard import init_wizard
from tests.e2e.support.system_settings_session import system_settings_e2e_session

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]


def test_directories_page_persists_and_probes_paths(tmp_path):
    with system_settings_e2e_session() as session:
        response = session.client.get("/system/directories/", follow_redirects=True)
        assert response.status_code == 200
        assert "数据存储目录" in response.text
        assert "用户因子目录" in response.text
        assert "用户策略目录" in response.text

        factor_dir = tmp_path / "factors"
        strategy_dir = tmp_path / "strategies"
        response = session.client.post(
            "/system/directories/save",
            data={
                "data_home": str(session.market_home),
                "factor_dir": str(factor_dir),
                "strategy_dir": str(strategy_dir),
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        state = init_wizard.get_state(force_refresh=True)
        assert state.factor_dir == str(factor_dir.resolve())
        assert state.strategy_dir == str(strategy_dir.resolve())
        assert factor_dir.is_dir()
        assert strategy_dir.is_dir()
