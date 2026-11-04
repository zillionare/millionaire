"""Persist the user's realtime-data choice separately from historical credentials."""

import json

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import write_json

SOURCES = {"tushare", "tencent", "extension", "none"}


def realtime_source() -> str:
    """Preserve existing extension/trial configurations when no selection exists."""
    path = ensure_app_config_dir() / "realtime-source.json"
    if not path.is_file():
        return ""
    source = json.loads(path.read_text(encoding="utf-8"))["source"]
    if not isinstance(source, str) or source not in SOURCES:
        raise ValueError("未知实时行情配置，请重新配置数据源")
    return source


def configure_realtime_source(source: str) -> None:
    """Save a deliberate selection; switching sources cannot renew the Tencent trial."""
    if source not in SOURCES:
        raise ValueError("请选择有效的实时行情数据源")
    write_json(ensure_app_config_dir() / "realtime-source.json", {"source": source})
