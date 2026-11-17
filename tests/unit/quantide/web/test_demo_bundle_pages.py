"""Demo-mode banner and system data-source activation routes."""

from __future__ import annotations

from pathlib import Path

from quantide.config.settings import get_data_home
from quantide.data.models.daily_bars import daily_bars
from quantide.data.sqlite import db
from quantide.service.demo_bundle import demo_status
from quantide.service.init_wizard import init_wizard
from tests.e2e.support.sqlite_state import capture_sqlite_state, restore_sqlite_state
from tests.e2e.support.system_settings_session import system_settings_e2e_session


def test_system_datasource_can_activate_and_exit_demo_mode() -> None:
    with system_settings_e2e_session() as session:
        formal = Path(init_wizard.get_state().app_home)
        before = sorted(path.relative_to(formal) for path in formal.rglob("*"))

        response = session.client.post(
            "/system/datasource/demo/activate", follow_redirects=True
        )
        assert response.status_code == 200
        assert "体验数据包已启用" in response.text
        assert demo_status()["active"]
        assert get_data_home() == demo_status()["demo_home"]
        assert Path(daily_bars._store_path) == Path(demo_status()["demo_home"]) / "data/bars/daily"

        page = session.client.get("/system/datasource/")
        assert "体验数据模式（数据截至" in page.text
        assert "切换正式数据源" in page.text
        assert "退出体验模式" in page.text
        after = sorted(path.relative_to(formal) for path in formal.rglob("*"))
        assert after == before

        response = session.client.post(
            "/system/datasource/demo/deactivate", follow_redirects=True
        )
        assert response.status_code == 200
        assert "已切换回正式数据源" in response.text
        assert demo_status()["mode"] == "standard"
        assert get_data_home() == str(formal)
        assert Path(daily_bars._store_path) == formal / "data/bars/daily"
        assert "体验数据模式" not in session.client.get("/system/datasource/").text


def test_system_settings_session_restores_outer_database(tmp_path: Path) -> None:
    before = capture_sqlite_state()
    outer = tmp_path / "outer.db"
    db.init(outer)
    try:
        with system_settings_e2e_session():
            assert Path(db.db_path).name == "quantide.db"
        assert Path(db.db_path) == outer
        assert db["app_state"].count >= 0
    finally:
        restore_sqlite_state(before)
