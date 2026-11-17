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
from quantide.core.atomic_files import write_json

MODEL_CONFIG_KEYS = (
    "train_window",
    "future_return_horizon",
    "label_kind",
    "retrain_days",
    "use_lightgbm",
    "features",
    "factor_catalog_version",
    "universe_size",
    "universe_mode",
    "market_cap_trim_pct",
    "universe_rebalance_days",
    "index_pool_codes",
    "top_k",
    "fill_timing",
    "universe_filter",
    "pipeline_version",
    "seed",
    "symbols",
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

    def _version_dir(self, key: str) -> Path:
        path = self._dir(key) / "versions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _atomic_pickle(path: Path, model: Any, directory: Path) -> None:
        fd, temporary = tempfile.mkstemp(dir=directory, suffix=".pkl.tmp")
        os.close(fd)
        try:
            with open(temporary, "wb") as handle:
                pickle.dump(model, handle, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _artifact_hash(model: Any, metadata: ModelArtifact) -> str:
        payload = metadata.to_dict()
        extra = dict(payload.get("extra") or {})
        for key in ("model_ref", "artifact_hash"):
            extra.pop(key, None)
        payload["extra"] = extra
        payload.pop("created_at", None)
        digest = hashlib.sha256()
        digest.update(pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL))
        digest.update(json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8"))
        return digest.hexdigest()[:20]

    def _migrate_legacy_latest(self, key: str, model_path: Path, meta_path: Path) -> None:
        if not model_path.is_file() or not meta_path.is_file():
            return
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if (data.get("extra") or {}).get("model_ref"):
                return
            model = pickle.loads(model_path.read_bytes())
            metadata = ModelArtifact.from_dict(data)
        except Exception:
            return
        artifact_hash = self._artifact_hash(model, metadata)
        metadata.extra = {
            **dict(metadata.extra or {}),
            "artifact_hash": artifact_hash,
            "model_ref": f"{key}/{artifact_hash}",
        }
        payload = metadata.to_dict()
        self._save_version(key, model, metadata, payload)
        write_json(meta_path, payload)

    def _save_version(
        self, key: str, model: Any, metadata: ModelArtifact, payload: dict[str, Any]
    ) -> None:
        versions = self._version_dir(key)
        artifact_hash = str(metadata.extra.get("artifact_hash") or metadata.model_hash)
        version_model = versions / f"{artifact_hash}.pkl"
        version_meta = versions / f"{artifact_hash}.json"
        if not version_model.exists():
            self._atomic_pickle(version_model, model, versions)
        if not version_meta.exists():
            write_json(version_meta, payload)

    def save_version(self, *, key: str, model: Any, metadata: ModelArtifact) -> ModelArtifact:
        """Publish an immutable experiment artifact without moving latest."""
        directory, _, _ = self._paths(key)
        directory.mkdir(parents=True, exist_ok=True)
        if not metadata.model_hash:
            metadata.model_hash = hashlib.sha1(pickle.dumps(model)).hexdigest()[:16]
        artifact_hash = self._artifact_hash(model, metadata)
        metadata.extra = {
            **dict(metadata.extra or {}),
            "artifact_hash": artifact_hash,
            "model_ref": f"{key}/{artifact_hash}",
        }
        self._save_version(key, model, metadata, metadata.to_dict())
        return metadata

    def save(
        self,
        *,
        key: str,
        model: Any,
        metadata: ModelArtifact,
    ) -> ModelArtifact:
        """Atomically save latest plus an immutable content-addressed version."""
        directory, model_path, meta_path = self._paths(key)
        directory.mkdir(parents=True, exist_ok=True)
        if not metadata.model_hash:
            metadata.model_hash = hashlib.sha1(pickle.dumps(model)).hexdigest()[:16]
        artifact_hash = self._artifact_hash(model, metadata)
        metadata.extra = {
            **dict(metadata.extra or {}),
            "artifact_hash": artifact_hash,
            "model_ref": f"{key}/{artifact_hash}",
        }
        lock_path = self._lock_path(directory)
        lock_file = open(lock_path, "a+")
        try:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            self._migrate_legacy_latest(key, model_path, meta_path)
            payload = metadata.to_dict()
            # Publish the immutable artifact first. A crash before latest.json lands
            # leaves the previous latest pointer valid and self-consistent.
            self._save_version(key, model, metadata, payload)
            self._atomic_pickle(model_path, model, directory)
            write_json(meta_path, payload)
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_file.close()
        return metadata

    def _legacy_candidates(self, ref: str, digest: str | None) -> list[Path]:
        if digest is not None:
            key = ref.rsplit("/", 1)[0]
            paths = sorted((self._dir(key) / "versions").glob("*.json"))
            wanted = digest
        else:
            paths = sorted(self.root.glob("*/versions/*.json"))
            wanted = ref
        found: list[Path] = []
        for meta_path in paths:
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(data.get("model_hash") or "") == wanted:
                found.append(meta_path.with_suffix(".pkl"))
        return found

    def load_ref(self, model_ref: str) -> tuple[Any | None, ModelArtifact | None]:
        """Load an immutable model by ``key/hash`` or a bare content hash."""
        ref = str(model_ref or "").strip()
        if not ref:
            return None, None
        candidates: list[Path] = []
        digest: str | None = None
        if "/" in ref:
            key, digest = ref.rsplit("/", 1)
            candidates.append(self._dir(key) / "versions" / f"{digest}.pkl")
        else:
            candidates.extend(sorted(self.root.glob(f"*/versions/{ref}.pkl")))
        candidates.extend(self._legacy_candidates(ref, digest))
        unique = sorted({path.resolve() for path in candidates if path.is_file()})
        if len(unique) > 1:
            logger.warning("模型引用不唯一，拒绝按文件名猜测: {}", ref)
            return None, None
        for model_path in unique:
            meta_path = model_path.with_suffix(".json")
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                metadata = ModelArtifact.from_dict(data)
                with open(model_path, "rb") as handle:
                    return pickle.load(handle), metadata
            except Exception as exc:
                logger.warning("加载不可变模型失败 {}: {}", model_path, exc)
                continue
        return None, None

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
        if meta is None:
            return None, None
        ref = str((meta.extra or {}).get("model_ref") or "")
        if ref:
            return self.load_ref(ref)
        if not model_path.exists():
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
