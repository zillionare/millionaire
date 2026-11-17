"""Optional OpenAI-compatible assistant configuration and credential masking."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import httpx
from loguru import logger

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import write_json

ProviderPreset = Literal["deepseek", "dashscope", "openai", "ollama", "custom"]
PROVIDER_PRESETS: dict[ProviderPreset, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_required": True,
    },
    "dashscope": {
        "label": "通义千问 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "api_key_required": True,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_required": True,
    },
    "ollama": {
        "label": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "llama3.1",
        "api_key_required": False,
    },
    "custom": {
        "label": "自定义 OpenAI 兼容端点",
        "base_url": "",
        "model": "",
        "api_key_required": False,
    },
}
PROVIDER_CHOICES: tuple[ProviderPreset, ...] = (
    "deepseek",
    "dashscope",
    "openai",
    "ollama",
    "custom",
)
DEFAULT_PROVIDER: ProviderPreset = "deepseek"
CONFIG_FILENAME = "ai_assistant.json"
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{6,}")
_BEARER_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+")


def default_base_url(provider: str) -> str:
    """Return the recommended base URL for a provider preset."""
    return str(PROVIDER_PRESETS.get(_provider(provider), {}).get("base_url") or "")


def default_model(provider: str) -> str:
    """Return the recommended model name for a provider preset."""
    return str(PROVIDER_PRESETS.get(_provider(provider), {}).get("model") or "")


def _provider(value: str) -> ProviderPreset:
    normalized = str(value or DEFAULT_PROVIDER).strip().lower()
    return normalized if normalized in PROVIDER_CHOICES else DEFAULT_PROVIDER


def mask_api_key(api_key: str) -> str:
    """Return a display-safe key mask that never contains the full secret."""
    key = str(api_key or "").strip()
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    prefix = "sk-" if key.startswith("sk-") else ""
    return f"{prefix}****{key[-4:]}"


def redact_secrets(text: object, *secrets: str) -> str:
    """Redact configured keys and generic OpenAI-style tokens from text."""
    redacted = str(text or "")
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, mask_api_key(secret))
    redacted = _KEY_PATTERN.sub(lambda match: mask_api_key(match.group(0)), redacted)
    return _BEARER_PATTERN.sub(r"\1****", redacted)


@dataclass(frozen=True)
class AIAssistantConfig:
    """Durable assistant settings; ``api_key`` is never logged by repr."""

    provider_preset: ProviderPreset = DEFAULT_PROVIDER
    base_url: str = field(default_factory=lambda: default_base_url(DEFAULT_PROVIDER))
    model: str = field(default_factory=lambda: default_model(DEFAULT_PROVIDER))
    api_key: str = field(default="", repr=False)
    timeout_seconds: int = 60
    max_repair_rounds: int = 3
    max_tool_steps: int = 12

    def __post_init__(self) -> None:
        provider = _provider(self.provider_preset)
        base_url = str(self.base_url or default_base_url(provider)).strip().rstrip("/")
        model = str(self.model or default_model(provider)).strip()
        if not base_url:
            raise ValueError("AI 助手 base_url 不能为空")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("AI 助手 base_url 必须以 http:// 或 https:// 开头")
        if not model:
            raise ValueError("AI 助手模型名不能为空")
        if not 1 <= int(self.timeout_seconds) <= 600:
            raise ValueError("AI 助手 timeout_seconds 必须在 1~600 秒之间")
        if not 1 <= int(self.max_repair_rounds) <= 10:
            raise ValueError("AI 助手 max_repair_rounds 必须在 1~10 之间")
        if not 1 <= int(self.max_tool_steps) <= 64:
            raise ValueError("AI 助手 max_tool_steps 必须在 1~64 之间")
        object.__setattr__(self, "provider_preset", provider)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "api_key", str(self.api_key or "").strip())
        object.__setattr__(self, "timeout_seconds", int(self.timeout_seconds))
        object.__setattr__(self, "max_repair_rounds", int(self.max_repair_rounds))
        object.__setattr__(self, "max_tool_steps", int(self.max_tool_steps))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AIAssistantConfig:
        provider = _provider(str(payload.get("provider_preset") or DEFAULT_PROVIDER))
        return cls(
            provider_preset=provider,
            base_url=str(payload.get("base_url") or default_base_url(provider)),
            model=str(payload.get("model") or default_model(provider)),
            api_key=str(payload.get("api_key") or ""),
            timeout_seconds=int(payload.get("timeout_seconds") or 60),
            max_repair_rounds=int(payload.get("max_repair_rounds") or 3),
            max_tool_steps=int(payload.get("max_tool_steps") or 12),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return the durable payload, including the key for persistence only."""
        return asdict(self)

    def public_view(self) -> AIAssistantPublicView:
        return AIAssistantPublicView(
            configured=bool(self.api_key or self.provider_preset == "ollama"),
            provider_preset=self.provider_preset,
            base_url=self.base_url,
            model=self.model,
            api_key_masked=mask_api_key(self.api_key),
            timeout_seconds=self.timeout_seconds,
            max_repair_rounds=self.max_repair_rounds,
            max_tool_steps=self.max_tool_steps,
        )

    def with_api_key(self, api_key: str) -> AIAssistantConfig:
        return replace(self, api_key=str(api_key or "").strip())


@dataclass(frozen=True)
class AIAssistantPublicView:
    """Front-end safe assistant settings without plaintext credentials."""

    configured: bool
    provider_preset: ProviderPreset
    base_url: str
    model: str
    api_key_masked: str
    timeout_seconds: int = 60
    max_repair_rounds: int = 3
    max_tool_steps: int = 12

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AIConnectivityResult:
    """Typed, credential-safe connectivity probe result."""

    ok: bool
    code: str
    message: str
    status_code: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def empty_ai_assistant_config(provider: str = DEFAULT_PROVIDER) -> AIAssistantConfig:
    preset = _provider(provider)
    return AIAssistantConfig(
        provider_preset=preset,
        base_url=default_base_url(preset),
        model=default_model(preset),
    )


def get_ai_assistant_config_path() -> Path:
    """Return the durable, user-private assistant config path."""
    return ensure_app_config_dir() / CONFIG_FILENAME


def load_ai_assistant_config() -> AIAssistantConfig | None:
    """Load persisted settings; malformed or absent files are treated as unconfigured."""
    path = get_ai_assistant_config_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return AIAssistantConfig.from_dict(payload)
    except (OSError, ValueError, TypeError):
        logger.warning("AI 助手配置读取失败；请重新填写。")
        return None


def save_ai_assistant_config(config: AIAssistantConfig) -> AIAssistantPublicView:
    """Persist settings atomically with owner-only permissions on POSIX."""
    path = get_ai_assistant_config_path()
    write_json(path, config.as_dict())
    if os.name != "nt":
        os.chmod(path, 0o600)
    return config.public_view()


def save_ai_assistant_settings(
    *,
    provider_preset: str,
    base_url: str,
    model: str,
    api_key: str = "",
    timeout_seconds: int = 60,
    max_repair_rounds: int = 3,
    max_tool_steps: int = 12,
) -> AIAssistantPublicView:
    """Validate and persist one settings form submission."""
    config = AIAssistantConfig(
        provider_preset=_provider(provider_preset),
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        max_repair_rounds=max_repair_rounds,
        max_tool_steps=max_tool_steps,
    )
    return save_ai_assistant_config(config)


def config_from_form(
    values: Mapping[str, Any], *, existing: AIAssistantConfig | None = None
) -> AIAssistantConfig:
    """Build config from form values, keeping the saved key when the field is blank."""
    saved_key = existing.api_key if existing is not None else ""
    provider = _provider(str(values.get("provider_preset") or DEFAULT_PROVIDER))
    return AIAssistantConfig(
        provider_preset=provider,
        base_url=str(values.get("base_url") or default_base_url(provider)),
        model=str(values.get("model") or default_model(provider)),
        api_key=str(values.get("api_key") or "").strip() or saved_key,
        timeout_seconds=int(str(values.get("timeout_seconds") or 60)),
        max_repair_rounds=int(str(values.get("max_repair_rounds") or 3)),
        max_tool_steps=int(str(values.get("max_tool_steps") or 12)),
    )


def public_view(config: AIAssistantConfig | None = None) -> AIAssistantPublicView:
    """Return a safe view for an explicit config or the persisted config."""
    resolved = config if config is not None else load_ai_assistant_config()
    if resolved is None:
        return empty_ai_assistant_config().public_view()
    return resolved.public_view()


def _chat_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _headers(config: AIAssistantConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _json_message(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("响应不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("响应 JSON 不是对象")
    return payload


def _classify_status(status_code: int) -> tuple[str, str]:
    if status_code in {401, 403}:
        return "auth_failed", "鉴权失败：请检查 API Key 是否有效以及是否有模型权限。"
    if status_code == 404:
        return "model_not_found", "模型名不存在或端点路径错误（404）。"
    if status_code == 429:
        return "rate_limited", "请求被限流（429），请稍后重试或检查额度。"
    return "http_error", f"端点返回 HTTP {status_code}。"


def test_ai_connection(
    config: AIAssistantConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> AIConnectivityResult:
    """Send a minimal Chat Completions probe and classify failures safely."""
    key = config.api_key
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": "只回复 ok"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    try:
        with httpx.Client(
            timeout=float(config.timeout_seconds),
            trust_env=False,
            transport=transport,
        ) as client:
            response = client.post(
                _chat_url(config.base_url), headers=_headers(config), json=payload
            )
    except httpx.TimeoutException:
        return AIConnectivityResult(False, "timeout", "连接超时，请检查网络或端点地址。")
    except httpx.RequestError as exc:
        message = redact_secrets(str(exc), key)
        return AIConnectivityResult(False, "unreachable", f"网络不可达：{message}")
    if response.status_code >= 400:
        code, message = _classify_status(response.status_code)
        return AIConnectivityResult(False, code, message, response.status_code)
    try:
        data = _json_message(response)
    except ValueError as exc:
        return AIConnectivityResult(
            False, "incompatible", f"响应格式不兼容：{exc}", response.status_code
        )
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return AIConnectivityResult(
            False, "incompatible", "响应格式不兼容：缺少 choices。", response.status_code
        )
    return AIConnectivityResult(True, "ok", f"连接成功：{config.model}", response.status_code)


check_ai_connection = test_ai_connection


def test_saved_ai_connection() -> AIConnectivityResult:
    """Probe the persisted assistant settings."""
    config = load_ai_assistant_config()
    if config is None:
        return AIConnectivityResult(False, "not_configured", "尚未配置 AI 助手。")
    return test_ai_connection(config)


__all__ = [
    "AIAssistantConfig",
    "AIAssistantPublicView",
    "AIConnectivityResult",
    "PROVIDER_CHOICES",
    "PROVIDER_PRESETS",
    "check_ai_connection",
    "config_from_form",
    "default_base_url",
    "default_model",
    "empty_ai_assistant_config",
    "get_ai_assistant_config_path",
    "load_ai_assistant_config",
    "mask_api_key",
    "public_view",
    "redact_secrets",
    "save_ai_assistant_config",
    "save_ai_assistant_settings",
    "test_ai_connection",
    "test_saved_ai_connection",
]


# These are library APIs, not pytest test cases when imported into test modules.
test_ai_connection.__test__ = False  # type: ignore[attr-defined]
test_saved_ai_connection.__test__ = False  # type: ignore[attr-defined]
