"""Credential masking, persistence and connectivity probes for WP-4."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx
import pytest

from quantide.config.paths import set_app_config_dir_override
from quantide.service.ai_assistant import (
    AIAssistantConfig,
    config_from_form,
    get_ai_assistant_config_path,
    load_ai_assistant_config,
    mask_api_key,
    public_view,
    redact_secrets,
    save_ai_assistant_config,
    test_ai_connection as probe_ai_connection,
)


@pytest.fixture
def config_home(tmp_path: Path):
    previous = set_app_config_dir_override(tmp_path / "config")
    yield tmp_path / "config"
    set_app_config_dir_override(previous)


@pytest.mark.parametrize(
    ("key", "expected"),
    [("", ""), ("abcd", "****"), ("sk-abcdefghijkl9a1f", "sk-****9a1f"), ("plainsecret", "****cret")],
)
def test_mask_api_key_never_returns_the_full_secret(key: str, expected: str) -> None:
    masked = mask_api_key(key)
    assert masked == expected
    if key:
        assert key not in masked


def test_config_public_view_and_repr_hide_key(config_home: Path) -> None:
    config = AIAssistantConfig(
        provider_preset="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="sk-super-secret-1234",
    )
    view = config.public_view()

    assert view.api_key_masked == "sk-****1234"
    assert "sk-super-secret-1234" not in repr(config)
    assert "api_key" not in view.as_dict()
    assert "sk-super-secret-1234" not in json.dumps(view.as_dict(), ensure_ascii=False)


def test_config_persists_with_owner_only_permissions(config_home: Path) -> None:
    config = AIAssistantConfig(api_key="sk-secret-9876")
    save_ai_assistant_config(config)

    path = get_ai_assistant_config_path()
    assert path.is_file()
    assert path.read_text(encoding="utf-8").find("sk-secret-9876") >= 0
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    loaded = load_ai_assistant_config()
    assert loaded is not None
    assert loaded.api_key == "sk-secret-9876"
    assert public_view(loaded).api_key_masked == "sk-****9876"


def test_blank_form_key_keeps_existing_secret(config_home: Path) -> None:
    save_ai_assistant_config(AIAssistantConfig(api_key="sk-existing-9999"))

    config = config_from_form(
        {
            "provider_preset": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "",
            "timeout_seconds": "30",
            "max_repair_rounds": "2",
            "max_tool_steps": "9",
        },
        existing=load_ai_assistant_config(),
    )

    assert config.api_key == "sk-existing-9999"
    assert config.timeout_seconds == 30
    assert config.max_repair_rounds == 2
    assert config.max_tool_steps == 9


def test_redact_secrets_handles_bearer_and_generic_tokens() -> None:
    text = "Authorization: Bearer sk-abcdefghijkl and key sk-super-secret-1234"
    redacted = redact_secrets(text, "sk-super-secret-1234")

    assert "sk-super-secret-1234" not in redacted
    assert "sk-abcdefghijkl" not in redacted


def _config() -> AIAssistantConfig:
    return AIAssistantConfig(
        provider_preset="openai",
        base_url="http://127.0.0.1:9/v1",
        model="mock-model",
        api_key="sk-test-secret-9999",
        timeout_seconds=5,
    )


@pytest.mark.parametrize(
    ("status_code", "code"),
    [(401, "auth_failed"), (403, "auth_failed"), (404, "model_not_found"), (429, "rate_limited"), (500, "http_error")],
)
def test_connectivity_classifies_http_failures_without_leaking_key(
    status_code: int, code: str
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "bad sk-test-secret-9999"}})

    result = probe_ai_connection(_config(), transport=httpx.MockTransport(handler))

    assert result.ok is False
    assert result.code == code
    assert "sk-test-secret-9999" not in result.message
    assert "sk-test-secret-9999" not in result.message


def test_connectivity_distinguishes_network_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot connect sk-test-secret-9999")

    result = probe_ai_connection(_config(), transport=httpx.MockTransport(handler))

    assert result.ok is False
    assert result.code == "unreachable"
    assert "sk-test-secret-9999" not in result.message


def test_connectivity_rejects_incompatible_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    result = probe_ai_connection(_config(), transport=httpx.MockTransport(handler))

    assert result.ok is False
    assert result.code == "incompatible"


def test_connectivity_accepts_openai_compatible_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    result = probe_ai_connection(_config(), transport=httpx.MockTransport(handler))

    assert result.ok is True
    assert result.code == "ok"
