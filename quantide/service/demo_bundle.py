"""Read-only offline demo bundle mounting and isolated demo-mode state."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, cast

import polars as pl
from loguru import logger

from quantide.config.output_paths import external_runtime_path
from quantide.config.paths import ensure_app_config_dir
from quantide.config.realtime_source import configure_realtime_source
from quantide.config.settings import get_data_home
from quantide.data.models.app_state import AppState

REQUIRED_FILES = (
    "calendar.parquet",
    "stocks.parquet",
    "daily_bars.parquet",
    "limit_prices.parquet",
    "daily_basic.parquet",
    "stock_status_pit.parquet",
)
MAX_BUNDLE_BYTES = 15 * 1024 * 1024


def bundle_root() -> Path:
    """Return the packaged read-only demo bundle directory."""
    return Path(__file__).resolve().parents[1] / "assets" / "demo_bundle"


def demo_market_dir() -> Path:
    """Return the isolated runtime copy under the durable app config directory."""
    return Path(external_runtime_path(ensure_app_config_dir() / "demo_market"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(root: Path | None = None) -> dict[str, Any]:
    """Validate manifest hashes, file set and size before mounting anything."""
    source = Path(root) if root is not None else bundle_root()
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"体验数据包缺少 manifest.json: {source}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = {
        str(item.get("name")): str(item.get("sha256")) for item in manifest.get("files", [])
    }
    if set(declared) != set(REQUIRED_FILES):
        raise ValueError("体验数据包 manifest 文件清单不完整")
    total = 0
    for name in REQUIRED_FILES:
        path = source / name
        if not path.is_file():
            raise ValueError(f"体验数据包缺少文件: {name}")
        if _sha256(path) != declared[name]:
            raise ValueError(f"体验数据包文件校验失败: {name}")
        total += path.stat().st_size
    total += manifest_path.stat().st_size
    if total > MAX_BUNDLE_BYTES:
        raise ValueError(f"体验数据包超过 {MAX_BUNDLE_BYTES} 字节预算")
    return cast(dict[str, Any], manifest)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _write_partitions(frame: pl.DataFrame, root: Path) -> None:
    frame = frame.with_columns(
        pl.col("date").dt.year().alias("_year"),
        pl.col("date").dt.month().alias("_month"),
    )
    for (year, month), part in frame.group_by(["_year", "_month"], maintain_order=True):
        target = (
            root
            / f"partition_key_year={int(year)}"
            / f"partition_key_month={int(month):02d}"
            / "part-0.parquet"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        part.drop(["_year", "_month"]).sort("date").write_parquet(
            target, compression="zstd", statistics=True
        )


def _materialize(source: Path, destination: Path) -> None:
    data = destination / "data"
    data.mkdir(parents=True, exist_ok=True)
    _copy_file(source / "calendar.parquet", data / "calendar.parquet")
    _copy_file(source / "stocks.parquet", data / "stock_list.parquet")
    _copy_file(source / "daily_basic.parquet", data / "daily_basic.parquet")
    _copy_file(source / "stock_status_pit.parquet", data / "stock_status_pit.parquet")
    _copy_file(source / "manifest.json", destination / "manifest.json")
    for name, target in (
        ("daily_bars.parquet", data / "bars" / "daily"),
        ("limit_prices.parquet", data / "limit_price"),
    ):
        target.mkdir(parents=True, exist_ok=True)
        _write_partitions(pl.read_parquet(source / name), target)
    for empty in (data / "bars" / "index", data / "index_weight", data / "bars" / "minute30"):
        empty.mkdir(parents=True, exist_ok=True)
    (destination / ".bundle_digest").write_text(
        str(json.loads((source / "manifest.json").read_text(encoding="utf-8"))["bundle_digest"]),
        encoding="utf-8",
    )


def _quiesce_external_runtime() -> None:
    """Stop background pullers so demo mode never fetches external history/quotes."""
    for module_name, name in (
        ("quantide.service.limit_price_refresher", "limit_price_refresher"),
        ("quantide.service.minute_bar_aggregator", "minute_bar_aggregator"),
        ("quantide.service.quote_monitor", "quote_monitor"),
    ):
        try:
            module = __import__(module_name, fromlist=[name])
            getattr(module, name).stop()
        except Exception:
            logger.debug("demo mode runtime stop skipped: {}", name)


def activate_demo_bundle(
    *, complete_initialization: bool = True, root: Path | None = None
) -> dict[str, Any]:
    """Mount a verified bundle into the isolated demo home and switch mode."""
    manifest = verify_bundle(root)
    source = Path(root) if root is not None else bundle_root()
    target = demo_market_dir()
    staging = target.parent / f".demo_market-{uuid.uuid4().hex}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        _materialize(source, staging)
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    from quantide.data import init_data
    from quantide.service.init_wizard import init_wizard

    state = init_wizard.get_state()
    state.data_source_mode = "demo_bundle"
    state.demo_home = str(target)
    state.demo_bundle_version = str(manifest.get("bundle_version") or "")
    state.demo_data_end = dt.date.fromisoformat(str(manifest["end_date"]))
    state.demo_activated_at = dt.datetime.now()
    init_wizard.save_state(state)
    configure_realtime_source("none")
    try:
        from quantide.config.tencent_trial import configure_trial

        configure_trial(False)
    except Exception:
        logger.debug("tencent trial disable skipped")
    init_data(str(target), init_db=True)
    from quantide.service.discovery import strategy_loader

    strategy_loader.ensure_builtin_strategies()
    _quiesce_external_runtime()
    if complete_initialization:
        init_wizard.complete_initialization()
    return demo_status(state)


def deactivate_demo_bundle() -> dict[str, Any]:
    """Switch stores back to the formal data home; keep the demo copy on disk."""
    from quantide.data import init_data
    from quantide.service.init_wizard import init_wizard

    state = init_wizard.get_state()
    state.data_source_mode = "standard"
    init_wizard.save_state(state)
    init_data(get_data_home(), init_db=True, fetch_missing=False)
    return demo_status(state)


def demo_status(state: AppState | None = None) -> dict[str, Any]:
    """Return a credential-safe summary used by CLI, pages and tests."""
    from quantide.service.init_wizard import init_wizard

    state = state or init_wizard.get_state()
    active = state.data_source_mode == "demo_bundle" and bool(state.demo_home)
    cutoff = state.demo_data_end.isoformat() if state.demo_data_end else None
    return {
        "mode": "demo_bundle" if active else "standard",
        "active": active,
        "bundle_version": state.demo_bundle_version,
        "data_end": cutoff,
        "demo_home": state.demo_home,
        "formal_data_home": state.app_home,
        "effective_data_home": get_data_home(),
    }


__all__ = [
    "REQUIRED_FILES",
    "activate_demo_bundle",
    "bundle_root",
    "deactivate_demo_bundle",
    "demo_market_dir",
    "demo_status",
    "verify_bundle",
]
