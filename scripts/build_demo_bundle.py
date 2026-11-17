"""Build and validate the deterministic offline Demo Bundle.

This is a development fixture generator, so writing the committed
``quantide/assets/demo_bundle`` path is an explicit, reviewed exception to the
normal rule that generated output must stay outside the source checkout.
All other output paths are rejected unless they resolve outside the checkout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from quantide.config.output_paths import external_runtime_path
from quantide.core.bar_schema import OHLCV_COLUMNS
from quantide.service.demo_bundle import REQUIRED_FILES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "quantide" / "assets" / "demo_bundle"
CALENDAR_SOURCE = ROOT / "tests" / "assets" / "baseline_calendar.parquet"
START = dt.date(2022, 1, 1)
END = dt.date(2024, 12, 31)
BUNDLE_VERSION = "2026.11.1"
SEED = 20261117
ASSET_COUNT = 150
MAX_BUNDLE_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class Asset:
    code: str
    name: str
    pinyin: str
    board: str
    list_date: dt.date
    delist_date: dt.date | None
    st_periods: tuple[tuple[dt.date, dt.date], ...] = ()


def _asset_definitions() -> list[Asset]:
    assets: list[Asset] = []
    prefixes = (
        ("600{:03d}", "SH", "主板"),
        ("000{:03d}", "SZ", "主板"),
        ("300{:03d}", "SZ", "创业板"),
        ("688{:03d}", "SH", "科创板"),
    )
    counts = (60, 40, 30, 20)
    index = 0
    for (pattern, exchange, board), count in zip(prefixes, counts, strict=True):
        for number in range(1, count + 1):
            index += 1
            code = f"{pattern.format(number)}.{exchange}"
            list_date = dt.date(2018, 1, 2)
            delist = None
            if index < 1000 and 121 <= index <= 125:
                list_date = dt.date(2022, 12, 1)
            if index in {71, 72, 73, 74, 75}:
                delist = dt.date(2024, 9, 30)
            periods = _st_periods(index)
            assets.append(
                Asset(
                    code=code,
                    name=f"演示{board}{number:03d}",
                    pinyin=f"YS{board[0]}{number:03d}",
                    board=board,
                    list_date=list_date,
                    delist_date=delist,
                    st_periods=periods,
                )
            )
    return assets[:ASSET_COUNT]


def _st_periods(index: int) -> tuple[tuple[dt.date, dt.date], ...]:
    if 11 <= index <= 15:
        return ((dt.date(2023, 1, 3), dt.date(2023, 12, 29)),)
    if 16 <= index <= 20:
        return ((dt.date(2023, 7, 3), dt.date(2024, 12, 31)),)
    if index == 21:
        return ((dt.date(2022, 7, 1), dt.date(2022, 12, 30)),)
    return ()


def _trading_sessions() -> list[dt.date]:
    frame = pl.read_parquet(CALENDAR_SOURCE)
    rows = frame.filter((pl.col("date") >= pl.lit(START)) & (pl.col("date") <= pl.lit(END))).sort(
        "date"
    )
    return rows.filter(pl.col("is_open") == 1)["date"].to_list()


def _calendar_frame() -> pl.DataFrame:
    frame = pl.read_parquet(CALENDAR_SOURCE)
    return (
        frame.filter((pl.col("date") >= pl.lit(START)) & (pl.col("date") <= pl.lit(END)))
        .select(
            pl.col("date").cast(pl.Date),
            pl.col("is_open").cast(pl.Int64),
            pl.col("prev").cast(pl.Date),
        )
        .sort("date")
    )


def _is_st(asset: Asset, day: dt.date) -> bool:
    return any(start <= day <= end for start, end in asset.st_periods)


def _limit_pct(asset: Asset, day: dt.date) -> float:
    if _is_st(asset, day):
        return 0.05
    if asset.board in {"创业板", "科创板"}:
        return 0.20
    return 0.10


def _listed(asset: Asset, day: dt.date) -> bool:
    return asset.list_date <= day and (asset.delist_date is None or day <= asset.delist_date)


def _daily_ohlcv(
    asset: Asset, day: dt.date, rng: random.Random, price: float
) -> tuple[float, float, float, float, float]:
    suspended = (asset.code.endswith("7") and day.day in {8, 9}) or rng.random() < 0.003
    if suspended:
        return price, price, price, price, 0.0
    move = max(-0.035, min(0.035, rng.gauss(0.0004, 0.014)))
    open_ = round(max(0.5, price * (1.0 + rng.uniform(-0.008, 0.008))), 2)
    close = round(max(0.5, price * (1.0 + move)), 2)
    high = round(max(open_, close) * (1.0 + rng.uniform(0.001, 0.012)), 2)
    low = round(min(open_, close) * (1.0 - rng.uniform(0.001, 0.012)), 2)
    return open_, high, low, close, float(rng.randint(2_000, 300_000))


def _daily_bar(
    asset: Asset, day: dt.date, rng: random.Random, price: float, adjust: float
) -> tuple[dict[str, Any], float]:
    open_, high, low, close, volume = _daily_ohlcv(asset, day, rng, price)
    pct = _limit_pct(asset, day)
    up_limit = round(price * (1.0 + pct), 2)
    down_limit = round(price * (1.0 - pct), 2)
    high = min(high, up_limit)
    low = max(low, down_limit)
    amount = round(volume * close / 10.0, 2)
    bar = {
        "date": day,
        "asset": asset.code,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amount,
        "adjust": adjust,
        "is_st": _is_st(asset, day),
        "up_limit": up_limit,
        "down_limit": down_limit,
    }
    return bar, close


def _asset_rows(
    asset: Asset, sessions: list[dt.date]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(f"{SEED}:{asset.code}")
    price = round(rng.uniform(4.0, 60.0), 2)
    base_mv = rng.uniform(80_000, 8_000_000)
    adjust = 1.0
    bars: list[dict[str, Any]] = []
    limits: list[dict[str, Any]] = []
    basics: list[dict[str, Any]] = []
    for day in sessions:
        if not _listed(asset, day):
            continue
        if day in {dt.date(2023, 6, 15), dt.date(2024, 6, 17)}:
            adjust = round(adjust * 1.2, 6)
        bar, close = _daily_bar(asset, day, rng, price, adjust)
        bars.append(bar)
        limits.append(
            {
                "date": day,
                "asset": asset.code,
                "up_limit": bar["up_limit"],
                "down_limit": bar["down_limit"],
            }
        )
        total_mv = round(base_mv * (close / max(price, 0.01)), 2)
        basics.append(
            {
                "date": day,
                "asset": asset.code,
                "total_mv": total_mv,
                "circ_mv": round(total_mv * 0.62, 2),
            }
        )
        price = close
    return bars, limits, basics


def _stock_frame(assets: list[Asset]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "asset": [asset.code for asset in assets],
            "name": [asset.name for asset in assets],
            "pinyin": [asset.pinyin for asset in assets],
            "list_date": [asset.list_date for asset in assets],
            "delist_date": [asset.delist_date for asset in assets],
        },
        schema={
            "asset": pl.Utf8,
            "name": pl.Utf8,
            "pinyin": pl.Utf8,
            "list_date": pl.Date,
            "delist_date": pl.Date,
        },
    )


def _market_rows(
    assets: list[Asset], sessions: list[dt.date]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    bar_rows: list[dict[str, Any]] = []
    limit_rows: list[dict[str, Any]] = []
    basic_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    for asset in assets:
        bars, limits, basics = _asset_rows(asset, sessions)
        bar_rows.extend(bars)
        limit_rows.extend(limits)
        basic_rows.extend(basics)
        status_rows.extend(
            {"date": row["date"], "asset": asset.code, "is_st": row["is_st"]} for row in bars
        )
    return bar_rows, limit_rows, basic_rows, status_rows


def _generate_frames() -> dict[str, pl.DataFrame]:
    assets = _asset_definitions()
    bar_rows, limit_rows, basic_rows, status_rows = _market_rows(assets, _trading_sessions())
    return {
        "calendar.parquet": _calendar_frame(),
        "stocks.parquet": _stock_frame(assets).sort("asset"),
        "daily_bars.parquet": pl.DataFrame(bar_rows).sort(["asset", "date"]),
        "limit_prices.parquet": pl.DataFrame(limit_rows).sort(["asset", "date"]),
        "daily_basic.parquet": pl.DataFrame(basic_rows).sort(["asset", "date"]),
        "stock_status_pit.parquet": pl.DataFrame(status_rows).sort(["asset", "date"]),
    }


def _write_parquet(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp.parquet")
    frame.write_parquet(
        temp,
        compression="zstd",
        compression_level=9,
        statistics=True,
        row_group_size=50_000,
    )
    temp.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_text(frame: pl.DataFrame) -> dict[str, str]:
    return {name: str(dtype) for name, dtype in frame.schema.items()}


def _manifest(output: Path, frames: dict[str, pl.DataFrame]) -> dict[str, Any]:
    files = []
    for name in REQUIRED_FILES:
        path = output / name
        frame = frames[name]
        files.append(
            {
                "name": name,
                "sha256": _sha256(path),
                "rows": frame.height,
                "columns": list(frame.columns),
                "schema": _schema_text(frame),
            }
        )
    digest = hashlib.sha256(
        "\n".join(f"{item['name']}:{item['sha256']}" for item in files).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "kind": "demo_bundle",
        "bundle_version": BUNDLE_VERSION,
        "data_origin": "constructed_synthetic",
        "start_date": START.isoformat(),
        "end_date": END.isoformat(),
        "asset_count": ASSET_COUNT,
        "trading_days": _calendar_frame().filter(pl.col("is_open") == 1).height,
        "seed": SEED,
        "units": {
            "prices": "CNY raw",
            "volume": "lots (100 shares)",
            "amount": "thousand CNY",
            "market_cap": "10k CNY",
            "timezone": "Asia/Shanghai trading date",
        },
        "files": files,
        "bundle_digest": digest,
        "assumptions": [
            "Synthetic but deterministic A-share-like data for functional demos only.",
            "ST state is supplied as point-in-time daily snapshots, never current names.",
            "Prices are raw CNY; adjust is cumulative.",
        ],
    }


def _write_manifest(output: Path, manifest: dict[str, Any]) -> None:
    target = output / "manifest.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)


def build(output: Path) -> None:
    frames = _generate_frames()
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        _write_parquet(frame, output / name)
    _write_manifest(output, _manifest(output, frames))


def _bundle_size(output: Path) -> int:
    return sum((output / name).stat().st_size for name in (*REQUIRED_FILES, "manifest.json"))


def validate(output: Path = DEFAULT_OUTPUT) -> list[str]:
    errors: list[str] = []
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in REQUIRED_FILES:
        path = output / name
        if not path.is_file():
            errors.append(f"{name} missing")
            continue
        item = next((row for row in manifest.get("files", []) if row.get("name") == name), None)
        if item is None:
            errors.append(f"{name} absent from manifest")
            continue
        if item.get("sha256") != _sha256(path):
            errors.append(f"{name} sha256 mismatch")
    if not 100 <= int(manifest.get("asset_count", 0)) <= 200:
        errors.append("asset_count must be 100..200")
    if int(manifest.get("trading_days", 0)) < 500:
        errors.append("trading_days must be >= 500")
    size = _bundle_size(output)
    if size > MAX_BUNDLE_BYTES:
        errors.append(f"bundle size {size} exceeds {MAX_BUNDLE_BYTES}")
    try:
        frames = {name: pl.read_parquet(output / name) for name in REQUIRED_FILES}
        errors.extend(_validate_frames(frames))
    except Exception as exc:
        errors.append(f"parquet read failed: {exc}")
    return errors


def _validate_frames(frames: dict[str, pl.DataFrame]) -> list[str]:
    errors: list[str] = []
    required = {
        "calendar.parquet": {"date", "is_open", "prev"},
        "stocks.parquet": {"asset", "name", "pinyin", "list_date", "delist_date"},
        "daily_bars.parquet": (
            {"date", "asset", *OHLCV_COLUMNS} | {"adjust", "is_st", "up_limit", "down_limit"}
        ),
        "limit_prices.parquet": {"date", "asset", "up_limit", "down_limit"},
        "daily_basic.parquet": {"date", "asset", "total_mv", "circ_mv"},
        "stock_status_pit.parquet": {"date", "asset", "is_st"},
    }
    for name, columns in required.items():
        missing = columns.difference(frames[name].columns)
        if missing:
            errors.append(f"{name} missing columns: {sorted(missing)}")
    bars = frames["daily_bars.parquet"]
    if bars.select(["date", "asset"]).is_duplicated().any():
        errors.append("daily_bars duplicate date/asset")
    if bars.filter(
        (pl.col("low") > pl.col("open"))
        | (pl.col("low") > pl.col("close"))
        | (pl.col("high") < pl.col("open"))
        | (pl.col("high") < pl.col("close"))
        | (pl.col("volume") < 0)
        | (pl.col("amount") < 0)
    ).height:
        errors.append("daily_bars invalid OHLCV")
    if bars.filter((pl.col("up_limit") > 0) & (pl.col("up_limit") < pl.col("down_limit"))).height:
        errors.append("daily_bars invalid limits")
    basics = frames["daily_basic.parquet"]
    if basics.filter((pl.col("total_mv") <= 0) | (pl.col("circ_mv") > pl.col("total_mv"))).height:
        errors.append("daily_basic invalid market cap")
    return errors


def _resolve_output(value: str | None) -> Path:
    if value is None:
        return DEFAULT_OUTPUT
    return Path(external_runtime_path(value))


def _verify_determinism() -> list[str]:
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        build(Path(first))
        build(Path(second))
        for name in (*REQUIRED_FILES, "manifest.json"):
            if _sha256(Path(first) / name) != _sha256(Path(second) / name):
                return [f"non-deterministic output: {name}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build/validate the offline Demo Bundle")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="validate the committed bundle")
    action.add_argument("--write", action="store_true", help="regenerate the bundle")
    action.add_argument("--verify-determinism", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    output = _resolve_output(args.output)
    if args.verify_determinism:
        errors = _verify_determinism()
    else:
        if args.write:
            build(output)
        errors = validate(output)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"demo bundle OK: {output} ({_bundle_size(output)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
