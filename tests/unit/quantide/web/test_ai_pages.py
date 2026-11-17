"""AI assistant settings and AI studio Web entry points."""

from __future__ import annotations

from fasthtml.common import to_xml

from quantide.service.ai_assistant import AIAssistantConfig, save_ai_assistant_config
from quantide.web.pages.ai_config_views import ai_wizard_card
from tests.e2e.support.system_settings_session import system_settings_e2e_session

FORM = {
    "provider_preset": "openai",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "sk-web-secret-4321",
    "timeout_seconds": "45",
    "max_repair_rounds": "2",
    "max_tool_steps": "9",
}


def test_system_ai_page_saves_and_masks_key() -> None:
    with system_settings_e2e_session() as session:
        response = session.client.get("/system/ai/")
        assert response.status_code == 200
        assert "AI 助手配置" in response.text
        assert "测试连接" in response.text

        saved = session.client.post(
            "/system/ai/save", data=FORM, follow_redirects=False
        )
        assert saved.status_code == 303
        assert "sk-web-secret-4321" in (
            session.app_config_dir / "ai_assistant.json"
        ).read_text(encoding="utf-8")

        rendered = session.client.get("/system/ai/?saved=1")
        assert rendered.status_code == 200
        assert "sk-web-secret-4321" not in rendered.text
        assert "sk-****4321" in rendered.text
        assert "gpt-4o-mini" in rendered.text


def test_studio_shows_inline_config_when_ai_is_not_configured() -> None:
    with system_settings_e2e_session() as session:
        response = session.client.get("/factors/studio")
        assert response.status_code == 200
        assert "AI 写因子" in response.text
        assert "保存并开始" in response.text
        assert 'name="api_key"' in response.text
        assert "sk-web-secret" not in response.text


def test_studio_starts_conversation_after_save() -> None:
    with system_settings_e2e_session() as session:
        session.client.post("/system/ai/save", data=FORM, follow_redirects=False)
        response = session.client.get("/factors/studio")
        assert response.status_code == 200
        assert "新建会话" in response.text
        assert "发送" in response.text
        assert "sk-web-secret-4321" not in response.text


def test_wizard_ai_card_is_optional_and_masked(tmp_path) -> None:
    from quantide.config.paths import set_app_config_dir_override

    previous = set_app_config_dir_override(tmp_path / "config")
    try:
        save_ai_assistant_config(
            AIAssistantConfig(
                provider_preset="deepseek",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                api_key="sk-wizard-secret-8765",
            )
        )
        html = to_xml(ai_wizard_card())
    finally:
        set_app_config_dir_override(previous)

    assert "OPTIONAL" in html
    assert "可跳过" in html
    assert "sk-****8765" in html
    assert "sk-wizard-secret-8765" not in html
    assert "/init-wizard/ai/test" in html
