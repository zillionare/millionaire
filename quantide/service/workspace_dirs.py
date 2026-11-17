"""Persistent workspace directories shared by the wizard and system settings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from quantide.config.output_paths import external_runtime_path
from quantide.config.paths import normalize_data_home, normalize_factor_dir, normalize_strategy_dir


@dataclass(frozen=True)
class WorkspaceDirectories:
    """The three durable directories configured during onboarding."""

    data_home: str
    factor_dir: str
    strategy_dir: str


def prepare_workspace_dir(value: str | Path, label: str) -> str:
    """Create a directory and verify the service process can write there.

    ``external_runtime_path`` rejects source-checkout aliases before any
    directory is created or touched.
    """
    path = external_runtime_path(str(value).strip())
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"{label}无法创建：{path}（{exc}）") from exc
    if not path.is_dir():
        raise ValueError(f"{label}不是目录：{path}")
    probe = path / f".millionaire-write-probe-{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"{label}不可写：{path}。请检查后台服务账户权限或改选其他目录。（{exc}）"
        ) from exc
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    return str(path)


def normalize_workspace_directories(
    data_home: str | Path | None,
    factor_dir: str | Path | None,
    strategy_dir: str | Path | None,
) -> WorkspaceDirectories:
    """Normalize, create and probe all three workspace directories."""
    return WorkspaceDirectories(
        data_home=prepare_workspace_dir(normalize_data_home(data_home), "数据存储目录"),
        factor_dir=prepare_workspace_dir(normalize_factor_dir(factor_dir), "用户因子目录"),
        strategy_dir=prepare_workspace_dir(normalize_strategy_dir(strategy_dir), "用户策略目录"),
    )


__all__ = ["WorkspaceDirectories", "normalize_workspace_directories", "prepare_workspace_dir"]
