"""Point-in-time A-share universe filtering shared by research and strategies."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

_ST_COLUMNS = ("status", "name", "stock_name")
_DATE_COLUMNS = ("date", "trade_date", "dt")


@dataclass(frozen=True)
class UniverseFilterConfig:
    """Auditable PIT universe rules."""

    exclude_st: bool = True
    min_listing_days: int = 60
    exclude_suspended: bool = True
    exclude_limit_locked_on_close: bool = True
    max_universe_size: int | None = 2000

    @classmethod
    def from_mapping(
        cls, values: dict[str, Any] | None, *, max_universe_size: int | None = None
    ) -> UniverseFilterConfig:
        values = values or {}
        raw_size = values.get("max_universe_size", max_universe_size)
        size = int(str(raw_size)) if raw_size not in (None, "") else None
        return cls(
            exclude_st=bool(values.get("exclude_st", True)),
            min_listing_days=max(0, int(values.get("min_listing_days", 60))),
            exclude_suspended=bool(values.get("exclude_suspended", True)),
            exclude_limit_locked_on_close=bool(values.get("exclude_limit_locked_on_close", True)),
            max_universe_size=size if size is None or size > 0 else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "exclude_st": self.exclude_st,
            "min_listing_days": self.min_listing_days,
            "exclude_suspended": self.exclude_suspended,
            "exclude_limit_locked_on_close": self.exclude_limit_locked_on_close,
            "max_universe_size": self.max_universe_size,
        }


@dataclass(frozen=True)
class UniverseFilterResult:
    """Selected assets plus every exclusion count and warning."""

    assets: tuple[str, ...]
    exclusion_counts: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    size_basis: str = "none"
    max_universe_size: int | None = None

    @property
    def capped(self) -> bool:
        return self.size_basis != "none"

    def as_dict(self) -> dict[str, Any]:
        return {
            "assets": list(self.assets),
            "exclusion_counts": dict(self.exclusion_counts),
            "warnings": list(self.warnings),
            "size_basis": self.size_basis,
            "max_universe_size": self.max_universe_size,
            "capped": self.capped,
        }


def _date_column(frame: pl.DataFrame) -> str | None:
    return next((column for column in _DATE_COLUMNS if column in frame.columns), None)


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_st_status_frame(path: str | Path | None = None) -> pl.DataFrame | None:
    """Load optional historical ST/status snapshots; never fall back to current names."""
    from quantide.config.settings import get_data_home

    default = Path(get_data_home()) / "data/stock_status_pit.parquet"
    target = Path(path) if path is not None else default
    if not target.exists():
        return None
    try:
        frame = pl.read_parquet(target)
    except Exception:
        return None
    if frame.is_empty():
        return None
    return _normalize_status_frame(frame)


def _normalize_status_frame(frame: pl.DataFrame) -> pl.DataFrame:
    date_col = _date_column(frame)
    if date_col is None or "asset" not in frame.columns:
        return pl.DataFrame()
    frame = frame.rename({date_col: "date"})
    frame = frame.with_columns(pl.col("date").cast(pl.Date), pl.col("asset").cast(pl.Utf8))
    if "is_st" in frame.columns:
        return frame.with_columns(pl.col("is_st").cast(pl.Boolean))
    for column in _ST_COLUMNS:
        if column in frame.columns:
            values = pl.col(column).cast(pl.Utf8).fill_null("")
            return frame.with_columns(
                (values.str.to_uppercase().str.contains("ST") | values.str.contains("退")).alias(
                    "is_st"
                )
            )
    return pl.DataFrame()


def _attach_stock_meta(frame: pl.DataFrame, stock_meta: pl.DataFrame | None) -> pl.DataFrame:
    if stock_meta is None or stock_meta.is_empty() or "asset" not in stock_meta.columns:
        return frame
    columns = [
        column for column in ("asset", "list_date", "delist_date") if column in stock_meta.columns
    ]
    if "asset" not in columns:
        return frame
    drop = [column for column in ("list_date", "delist_date") if column in frame.columns]
    left = frame.drop(drop)
    return left.join(stock_meta.select(columns), on="asset", how="left")


def _record_status_count(
    warnings: list[str], counts: dict[str, int] | None, name: str, value: int
) -> None:
    if value <= 0:
        return
    warnings.append(name)
    if counts is not None:
        counts[name] = counts.get(name, 0) + value


def _combine_status_columns(joined: pl.DataFrame) -> pl.DataFrame:
    return joined.with_columns(
        (pl.col("is_st").fill_null(False) | pl.col("_status_st").fill_null(False)).alias("is_st")
    )


def _status_input(frame: pl.DataFrame) -> tuple[pl.DataFrame, bool, int]:
    if "is_st" not in frame.columns:
        return frame, False, 0
    frame = frame.with_columns(pl.col("is_st").cast(pl.Boolean))
    return frame, True, frame.filter(pl.col("is_st").is_null()).height


def _status_without_history(
    frame: pl.DataFrame,
    has_input: bool,
    unknown_input: int,
    warnings: list[str],
    counts: dict[str, int] | None,
) -> pl.DataFrame:
    if unknown_input <= 0 and has_input:
        return frame
    warnings.append("st_history_unavailable")
    _record_status_count(warnings, counts, "st_history_incomplete", unknown_input)
    if not has_input:
        return frame.with_columns(pl.lit(False).alias("is_st"))
    return frame.with_columns(pl.col("is_st").fill_null(False))


def _merge_status(
    joined: pl.DataFrame,
    has_input: bool,
    warnings: list[str],
    counts: dict[str, int] | None,
) -> pl.DataFrame:
    status = pl.col("_status_st")
    unresolved = (
        joined.filter(status.is_null() & pl.col("is_st").is_null()).height
        if has_input
        else joined.filter(status.is_null()).height
    )
    _record_status_count(warnings, counts, "st_history_incomplete", unresolved)
    if not has_input:
        return joined.with_columns(status.fill_null(False).alias("is_st")).drop("_status_st")
    conflicts = joined.filter(
        pl.col("is_st").is_not_null() & status.is_not_null() & (pl.col("is_st") != status)
    ).height
    _record_status_count(warnings, counts, "st_status_conflict", conflicts)
    return _combine_status_columns(joined).drop("_status_st")


def attach_status_contract(
    frame: pl.DataFrame,
    status_frame: pl.DataFrame | None,
    warnings: list[str],
    counts: dict[str, int] | None = None,
) -> pl.DataFrame:
    """Apply one shared ST contract with OR semantics and explicit diagnostics."""
    if frame.is_empty():
        return frame
    frame, has_input, unknown_input = _status_input(frame)
    if status_frame is None or status_frame.is_empty():
        return _status_without_history(frame, has_input, unknown_input, warnings, counts)
    status = (
        status_frame.select(["date", "asset", "is_st"])
        .unique(["date", "asset"])
        .rename({"is_st": "_status_st"})
    )
    joined = frame.join(status, on=["date", "asset"], how="left")
    return _merge_status(joined, has_input, warnings, counts)


def _attach_status(
    frame: pl.DataFrame,
    trade_date: dt.date,
    status_frame: pl.DataFrame | None,
    warnings: list[str],
) -> pl.DataFrame:
    """Compatibility wrapper around the shared multi-date status contract."""
    if "date" not in frame.columns:
        frame = frame.with_columns(pl.lit(trade_date).alias("date"))
    return attach_status_contract(frame, status_frame, warnings)


def _listing_days(list_date: Any, trade_date: dt.date, calendar_obj: Any) -> int | None:
    start = _as_date(list_date)
    if start is None:
        return None
    try:
        return len(tuple(calendar_obj.get_trade_dates(start, trade_date)))
    except Exception:
        return None


def _listing_row_ok(
    list_date: Any,
    delist_date: Any,
    trade_date: dt.date,
    config: UniverseFilterConfig,
    calendar_obj: Any,
) -> tuple[bool, bool]:
    start = _as_date(list_date)
    delisted = _as_date(delist_date)
    listed_ok = start is None or start <= trade_date
    delisted_ok = delisted is None or delisted > trade_date
    days = _listing_days(list_date, trade_date, calendar_obj)
    if days is None:
        return listed_ok and delisted_ok, True
    return listed_ok and days >= config.min_listing_days and delisted_ok, False


def _listing_mask(
    frame: pl.DataFrame,
    trade_date: dt.date,
    config: UniverseFilterConfig,
    calendar_obj: Any,
    counts: dict[str, int],
) -> pl.DataFrame:
    if "list_date" not in frame.columns and "delist_date" not in frame.columns:
        return frame
    delist_dates = (
        frame.get_column("delist_date").to_list()
        if "delist_date" in frame.columns
        else [None] * frame.height
    )
    keep: list[bool] = []
    missing = 0
    for list_date, delist_date in zip(
        frame.get_column("list_date").to_list(), delist_dates, strict=True
    ):
        allowed, unknown = _listing_row_ok(list_date, delist_date, trade_date, config, calendar_obj)
        keep.append(allowed)
        missing += int(unknown)
    if missing:
        counts["calendar_unavailable"] = counts.get("calendar_unavailable", 0) + missing
        counts["list_date_unavailable"] = counts.get("list_date_unavailable", 0) + missing
    if not keep:
        return frame
    return frame.filter(pl.Series(keep))


def _limit_locked(frame: pl.DataFrame) -> pl.Series:
    required = {"close", "high", "low", "up_limit"}
    if not required.issubset(frame.columns):
        return pl.Series([False] * frame.height, dtype=pl.Boolean)
    tolerance = pl.col("up_limit") * 0.001
    one_word = (pl.col("high") - pl.col("low")).abs() <= 1e-12
    at_limit = pl.col("close") >= (pl.col("up_limit") - tolerance)
    return frame.select((one_word & at_limit).fill_null(False)).to_series()


def _amount_cap(
    history: pl.DataFrame,
    frame: pl.DataFrame,
    max_size: int,
    warnings: list[str],
) -> pl.DataFrame:
    amount_column = "amount" if "amount" in history.columns else None
    if amount_column is None and {"volume", "close"}.issubset(history.columns):
        history = history.with_columns((pl.col("volume") * pl.col("close")).alias("amount"))
        amount_column = "amount"
    if amount_column is None:
        warnings.append("amount_unavailable_no_cap")
        return frame
    assets = frame["asset"].unique().to_list()
    dates = history["date"].unique().sort().tail(20).to_list()
    ranked = (
        history.filter(pl.col("date").is_in(dates) & pl.col("asset").is_in(assets))
        .group_by("asset")
        .agg(pl.col(amount_column).cast(pl.Float64).mean().alias("avg_amount"))
        .sort(["avg_amount", "asset"], descending=[True, False])
        .head(max_size)["asset"]
        .to_list()
    )
    return frame.filter(pl.col("asset").is_in(ranked))


def _apply_size_cap(
    frame: pl.DataFrame,
    history: pl.DataFrame,
    config: UniverseFilterConfig,
    warnings: list[str],
) -> tuple[pl.DataFrame, str]:
    max_size = config.max_universe_size
    if max_size is None or frame.height <= max_size:
        return frame, "none"
    cap_column = next(
        (
            column
            for column in ("total_mv", "circ_mv")
            if column in frame.columns and frame[column].is_not_null().any()
        ),
        None,
    )
    if cap_column is not None:
        frame = frame.sort([cap_column, "asset"], descending=[True, False]).head(max_size)
        return frame, "market_cap"
    warnings.append("market_cap_unavailable_amount_20d_cap")
    return _amount_cap(history, frame, max_size, warnings), "amount_20d"


def filter_universe_for_date(
    history: pl.DataFrame,
    trade_date: dt.date,
    config: UniverseFilterConfig | None = None,
    *,
    fill_timing: str = "auction_close",
    status_frame: pl.DataFrame | None = None,
    stock_meta: pl.DataFrame | None = None,
    calendar_obj: Any = None,
) -> UniverseFilterResult:
    """Filter one point-in-time cross-section without touching future rows."""
    config = config or UniverseFilterConfig()
    if calendar_obj is None:
        from quantide.data.models.calendar import calendar as calendar_obj
    warnings: list[str] = []
    history = _attach_stock_meta(history, stock_meta)
    history = history.filter(pl.col("date") <= trade_date)
    on_date = history.filter(pl.col("date") == trade_date)
    if on_date.is_empty():
        return UniverseFilterResult((), {"empty_cross_section": 1}, tuple(warnings))
    counts = {"initial": on_date.height}
    frame = _attach_status(on_date, trade_date, status_frame, warnings)
    before = frame.height
    if config.exclude_st:
        frame = frame.filter(~pl.col("is_st"))
        counts["st"] = before - frame.height
    before = frame.height
    if config.exclude_suspended and "volume" in frame.columns:
        frame = frame.filter(pl.col("volume").fill_null(0) > 0)
        counts["suspended"] = before - frame.height
    before = frame.height
    frame = _listing_mask(frame, trade_date, config, calendar_obj, counts)
    counts["listing_days"] = before - frame.height
    if counts.get("calendar_unavailable"):
        warnings.append("calendar_unavailable")
    if config.exclude_limit_locked_on_close and str(fill_timing).strip().lower() in {
        "auction_close",
        "auction",
        "close",
    }:
        before = frame.height
        frame = frame.filter(~_limit_locked(frame))
        counts["limit_locked_close"] = before - frame.height
    before = frame.height
    frame, basis = _apply_size_cap(frame, history, config, warnings)
    if basis != "none":
        counts["max_universe_size"] = before - frame.height
    assets = tuple(sorted(str(asset) for asset in frame["asset"].to_list()))
    return UniverseFilterResult(
        assets,
        counts,
        tuple(dict.fromkeys(warnings)),
        size_basis=basis,
        max_universe_size=config.max_universe_size,
    )


def _merge_panel_result(
    result: UniverseFilterResult,
    selected: list[str],
    counts: dict[str, int],
    warnings: list[str],
    bases: list[str],
) -> None:
    selected.extend(result.assets)
    warnings.extend(result.warnings)
    if result.capped:
        bases.append(result.size_basis)
    for key, value in result.exclusion_counts.items():
        counts[key] = counts.get(key, 0) + value


def filter_universe_panel(
    frame: pl.DataFrame,
    config: UniverseFilterConfig | None = None,
    *,
    fill_timing: str = "auction_close",
    status_frame: pl.DataFrame | None = None,
    stock_meta: pl.DataFrame | None = None,
    calendar_obj: Any = None,
) -> tuple[pl.DataFrame, UniverseFilterResult]:
    """Apply the PIT rules independently on every date and aggregate diagnostics."""
    if frame.is_empty():
        return frame, UniverseFilterResult(())
    if calendar_obj is None:
        from quantide.data.models.calendar import calendar as calendar_obj
    frame = frame.with_columns(pl.col("date").cast(pl.Date))
    selected: list[str] = []
    pairs: list[tuple[dt.date, str]] = []
    counts: dict[str, int] = {}
    warnings: list[str] = []
    bases: list[str] = []
    for trade_date in sorted(frame["date"].unique().to_list()):
        result = filter_universe_for_date(
            frame.filter(pl.col("date") <= trade_date),
            trade_date,
            config,
            fill_timing=fill_timing,
            status_frame=status_frame,
            stock_meta=stock_meta,
            calendar_obj=calendar_obj,
        )
        _merge_panel_result(result, selected, counts, warnings, bases)
        pairs.extend((trade_date, asset) for asset in result.assets)
    if pairs:
        keep = pl.DataFrame(pairs, schema=["date", "asset"], orient="row").unique()
        filtered = frame.join(keep, on=["date", "asset"], how="semi")
    else:
        filtered = frame.head(0)
    return filtered, UniverseFilterResult(
        tuple(sorted(set(selected))),
        counts,
        tuple(dict.fromkeys(warnings)),
        size_basis=bases[-1] if bases else "none",
        max_universe_size=(config or UniverseFilterConfig()).max_universe_size,
    )


def attach_universe_eligibility(
    frame: pl.DataFrame,
    config: UniverseFilterConfig | None = None,
    *,
    fill_timing: str = "auction_close",
    status_frame: pl.DataFrame | None = None,
    stock_meta: pl.DataFrame | None = None,
    calendar_obj: Any = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Mark signal rows eligible without removing price rows used by labels."""
    config = config or UniverseFilterConfig()
    if frame.is_empty():
        return frame, {"applied": True, "config": config.as_dict(), "by_date": {}}
    if status_frame is None:
        status_frame = load_st_status_frame()
    if stock_meta is None:
        from quantide.data.models.stocks import stock_list

        stock_meta = stock_list.data if stock_list.size > 0 else None
    frame = frame.with_columns(pl.col("date").cast(pl.Date))
    pairs: list[tuple[dt.date, str]] = []
    by_date: dict[str, Any] = {}
    for trade_date in sorted(frame["date"].unique().to_list()):
        result = filter_universe_for_date(
            frame.filter(pl.col("date") <= trade_date),
            trade_date,
            config,
            fill_timing=fill_timing,
            status_frame=status_frame,
            stock_meta=stock_meta,
            calendar_obj=calendar_obj,
        )
        pairs.extend((trade_date, asset) for asset in result.assets)
        by_date[trade_date.isoformat()] = result.as_dict()
    eligible = pl.DataFrame(
        pairs or [(dt.date(1900, 1, 1), "__none__")], schema=["date", "asset"], orient="row"
    ).unique()
    marked = frame.join(
        eligible.with_columns(pl.lit(True).alias("_eligible")), on=["date", "asset"], how="left"
    ).with_columns(pl.col("_eligible").fill_null(False))
    return marked, {"applied": True, "config": config.as_dict(), "by_date": by_date}


__all__ = [
    "UniverseFilterConfig",
    "UniverseFilterResult",
    "attach_status_contract",
    "attach_universe_eligibility",
    "filter_universe_for_date",
    "filter_universe_panel",
    "load_st_status_frame",
]
