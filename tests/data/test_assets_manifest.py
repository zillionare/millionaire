from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import polars as pl
import yaml


ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets"
MANIFEST_PATH = ASSETS_ROOT / "manifest.yml"


def _load_manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_manifest_tracks_existing_asset_files() -> None:
    manifest = _load_manifest()

    assert manifest["version"] == 1
    assert len(manifest["datasets"]) == 7

    for dataset in manifest["datasets"]:
        path = Path("/Users/aaronyang/workspace/quantide") / dataset["file"]
        assert path.exists(), dataset["file"]
        assert _sha256(path) == dataset["sha256"], dataset["file"]


def test_extended_daily_bars_fixture_matches_contract() -> None:
    frame = pl.read_parquet(ASSETS_ROOT / "2024_bars_ext_cols.parquet")

    assert frame.columns == [
        "date",
        "asset",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjust",
        "is_st",
        "up_limit",
        "down_limit",
    ]

    assert frame.select(pl.len()).item() == frame.select(pl.struct(["asset", "date"]).n_unique()).item()

    invalid_ohlc = frame.filter(
        (pl.col("low") > pl.col("high"))
        | (pl.col("low") > pl.min_horizontal("open", "close"))
        | (pl.col("high") < pl.max_horizontal("open", "close"))
    )
    invalid_limits = frame.filter(
        (pl.col("volume") < 0)
        | (pl.col("amount") < 0)
        | (pl.col("up_limit") < pl.col("down_limit"))
    )

    assert invalid_ohlc.is_empty()
    assert invalid_limits.is_empty()


def test_dual_ma_demo_slice_is_stable() -> None:
    manifest = _load_manifest()
    scenario = manifest["scenario_slices"][0]
    frame = pl.read_parquet(ASSETS_ROOT / "2024_bars_ext_cols.parquet").filter(
        (pl.col("asset") == scenario["asset"])
        & (pl.col("date") >= pl.datetime(2024, 1, 2))
        & (pl.col("date") <= pl.datetime(2024, 5, 31))
    )
    calendar = pl.read_parquet(ASSETS_ROOT / "baseline_calendar.parquet").filter(
        (pl.col("date") >= pl.date(2024, 1, 2))
        & (pl.col("date") <= pl.date(2024, 5, 31))
        & (pl.col("is_open") == 1)
    )

    assert scenario["name"] == "dual_ma_2024_demo"
    assert set(scenario["required_fields"]) <= set(frame.columns)
    assert frame.height == scenario["rows"] == 98
    assert str(frame.select(pl.col("date").min()).item()) == scenario["date_range"]["start"]
    assert str(frame.select(pl.col("date").max()).item()) == scenario["date_range"]["end"]
    assert frame.select("adjust").unique().drop_nulls().to_series().to_list() == scenario["fixed_facts"]["adjust_values"]
    assert frame.select("is_st").unique().drop_nulls().to_series().to_list() == scenario["fixed_facts"]["is_st_values"]
    assert calendar.select(pl.col("date").min()).item().isoformat() <= "2024-01-02"
    assert calendar.select(pl.col("date").max()).item().isoformat() >= "2024-05-31"