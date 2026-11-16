"""策略模型持久化（每个策略只保留最新模型）。"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pickle
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from quantide.config.output_paths import external_runtime_path
from quantide.config.paths import get_model_store_dir

MODEL_CONFIG_KEYS = (
    "train_window",
    "future_return_horizon",
    "retrain_days",
    "use_lightgbm",
    "features",
    "universe_size",
    "universe_mode",
    "market_cap_trim_pct",
    "universe_rebalance_days",
    "index_pool_codes",
    "top_k",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def model_config_payload(config: dict[str, Any]) -> dict[str, Any]:
    """返回参与模型版本计算的配置子集。"""
    return {key: config.get(key) for key in MODEL_CONFIG_KEYS if key in config}


def model_key(strategy_name: str, config: dict[str, Any]) -> str:
    """策略名 + 模型相关配置的稳定键。"""
    payload = json.dumps(model_config_payload(config), sort_keys=True, default=_json_default)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{strategy_name}-{digest}"


@dataclass
class ModelArtifact:
    """模型元数据。"""

    model_key: str
    strategy_name: str
    config_hash: str
    train_end: str
    effective_from: str
    engine: str = "LightGBM"
    feature_version: str = ""
    pipeline_version: str = ""
    model_hash: str = ""
    data_fingerprint: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds")
    )
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelArtifact:
        fields = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in fields})


class ModelStore:
    """文件系统模型仓库：最新模型二进制 + JSON 元数据。"""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = external_runtime_path(root) if root else get_model_store_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def rebind(self, root: Path | str) -> None:
        """Move the process-wide store after the app config override is set."""
        self.root = external_runtime_path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, key: str) -> Path:
        path = self.root / key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _paths(self, key: str) -> tuple[Path, Path, Path]:
        directory = self._dir(key)
        return directory, directory / "latest.pkl", directory / "latest.json"

    @staticmethod
    def _lock_path(directory: Path) -> Path:
        return directory / ".lock"

    def save(
        self,
        *,
        key: str,
        model: Any,
        metadata: ModelArtifact,
    ) -> ModelArtifact:
        """原子保存最新模型与元数据。"""
        directory, model_path, meta_path = self._paths(key)
        directory.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(directory)
        lock_file = open(lock_path, "a+")
        try:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            fd, tmp_model = tempfile.mkstemp(dir=directory, suffix=".pkl.tmp")
            os.close(fd)
            try:
                with open(tmp_model, "wb") as handle:
                    pickle.dump(model, handle, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp_model, model_path)
            finally:
                if os.path.exists(tmp_model):
                    os.unlink(tmp_model)

            payload = metadata.to_dict()
            fd, tmp_meta = tempfile.mkstemp(dir=directory, suffix=".json.tmp")
            os.close(fd)
            try:
                with open(tmp_meta, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, default=_json_default)
                os.replace(tmp_meta, meta_path)
            finally:
                if os.path.exists(tmp_meta):
                    os.unlink(tmp_meta)
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_file.close()
        return metadata

    def metadata(self, key: str) -> ModelArtifact | None:
        _, _, meta_path = self._paths(key)
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return ModelArtifact.from_dict(data)
        except Exception as exc:
            logger.warning("读取模型元数据失败 {}: {}", meta_path, exc)
            return None

    def load(self, key: str) -> tuple[Any | None, ModelArtifact | None]:
        _, model_path, _ = self._paths(key)
        meta = self.metadata(key)
        if not model_path.exists() or meta is None:
            return None, meta
        try:
            with open(model_path, "rb") as handle:
                return pickle.load(handle), meta
        except Exception as exc:
            logger.warning("加载模型失败 {}: {}", model_path, exc)
            return None, meta

    def clear(self, key: str) -> None:
        directory, model_path, meta_path = self._paths(key)
        for path in (model_path, meta_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


model_store = ModelStore()

__all__ = [
    "MODEL_CONFIG_KEYS",
    "ModelArtifact",
    "ModelStore",
    "model_config_payload",
    "model_key",
    "model_store",
]
