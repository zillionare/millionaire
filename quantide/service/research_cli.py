"""Shared service layer for the AI-oriented research CLI."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import textwrap
from pathlib import Path
from typing import Any, cast

from quantide.config.paths import normalize_factor_dir
from quantide.config.settings import get_data_source, get_settings
from quantide.factors.alpha import FEATURE_COLS
from quantide.factors.plugins import (
    FactorPlugin,
    clear_plugin_cache,
    discover_factor_plugins,
    load_factor_plugin,
)
from quantide.factors.registry import all_factor_ids, factor_metadata, factor_version
from quantide.service.factor_audit import factor_wind_tunnel_badge
from quantide.service.factor_study import run_custom_study
from quantide.service.factor_wind_tunnel import load_wind_tunnel_frame, run_factor_wind_tunnel

_FACTOR_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def json_safe(value: Any) -> Any:
    """Convert runtime values into strict JSON without NaN or Infinity."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def envelope(
    command: str,
    *,
    ok: bool,
    status: str,
    exit_code: int,
    data: Any = None,
    fingerprints: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the stable JSON envelope shared by every research subcommand."""
    payload = {
        "schema_version": "1.0",
        "command": command,
        "ok": ok,
        "status": status,
        "exit_code": exit_code,
        "fingerprints": fingerprints or {},
        "data": data if data is not None else {},
        "diagnostics": diagnostics or [],
    }
    return cast(dict[str, Any], json_safe(payload))


def envelope_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def _ensure_data() -> None:
    from quantide.data import init_data
    from quantide.data.models.daily_bars import daily_bars

    if not getattr(daily_bars, "_initialized", False):
        init_data()


def _bar_dates() -> list[dt.date]:
    _ensure_data()
    from quantide.data.models.daily_bars import daily_bars

    return list(daily_bars.available_dates)


def _dataset_columns(path: Path) -> list[str]:
    import polars as pl

    files = [path] if path.is_file() else sorted(path.rglob("*.parquet"))
    if not files:
        return []
    try:
        return list(pl.scan_parquet(files[0]).collect_schema().names())
    except Exception:
        return []


def _dataset_entry(name: str, path: Path, *, start: Any = None, end: Any = None) -> dict[str, Any]:
    exists = path.exists()
    return {
        "name": name,
        "status": "available" if exists else "missing",
        "path": str(path),
        "columns": _dataset_columns(path) if exists else [],
        "start": start,
        "end": end,
    }


def data_status() -> dict[str, Any]:
    """Return active mode, local coverage, dataset schemas and gap risks."""
    dates = _bar_dates()
    settings = get_settings()
    data_home = Path(settings.app_home)
    from quantide.data.models.daily_bars import daily_bars

    bars_path = Path(getattr(daily_bars, "_store_path", data_home / "data/bars/daily"))
    datasets = [
        _dataset_entry(
            "daily_bars",
            bars_path,
            start=dates[0].isoformat() if dates else None,
            end=dates[-1].isoformat() if dates else None,
        ),
        _dataset_entry("calendar", data_home / "data/calendar.parquet"),
        _dataset_entry("stock_list", data_home / "data/stock_list.parquet"),
        _dataset_entry("daily_basic", data_home / "data/daily_basic.parquet"),
        _dataset_entry("index_bars", data_home / "data/bars/index"),
        _dataset_entry("limit_price", data_home / "data/limit_price"),
        _dataset_entry("minute_bars", data_home / "data/bars/minute30"),
    ]
    risks = []
    if not dates:
        risks.append({"code": "daily_bars_empty", "message": "本地日线为空，无法运行因子研究。"})
    if any(item["status"] == "missing" for item in datasets):
        risks.append(
            {
                "code": "optional_dataset_missing",
                "message": "部分可选数据集尚未落库，相关研究能力可能受限。",
            }
        )
    return {
        "mode": "standard",
        "data_source": get_data_source(),
        "data_home": str(data_home),
        "coverage": {
            "start": dates[0].isoformat() if dates else None,
            "end": dates[-1].isoformat() if dates else None,
            "sessions": len(dates),
        },
        "datasets": datasets,
        "gap_risks": risks,
    }


def list_factors() -> dict[str, Any]:
    """List built-in and external factors plus tolerant discovery diagnostics."""
    definitions = factor_metadata()
    discovery = discover_factor_plugins()
    external_ids = {plugin.factor_id for plugin in discovery.plugins}
    factors = []
    for factor_id in all_factor_ids():
        definition = definitions[factor_id]
        badge = factor_wind_tunnel_badge(factor_id)
        factors.append(
            {
                "factor_id": factor_id,
                "display_name": definition.display_name,
                "group": definition.group,
                "source": "external" if factor_id in external_ids else "builtin",
                "source_hash": factor_version(factor_id),
                "wind_tunnel_status": badge.badge_status,
            }
        )
    skipped = [
        {
            "file_path": entry.file_path,
            "reason": entry.reason.value,
            "detail": entry.detail,
            "factor_id": entry.factor_id,
        }
        for entry in discovery.skipped
    ]
    return {"factor_dir": discovery.factor_dir, "factors": factors, "skipped": skipped}


def _template(factor_id: str, group: str) -> str:
    group_literal = json.dumps(group, ensure_ascii=False)
    return textwrap.dedent(
        f'''\
        """User-authored factor plugin generated by `millionaire factor init`."""

        import polars as pl

        from quantide.factors.plugins import FactorPlugin, GoldenCase

        # 必须在整个面板上按证券分组计算；禁止 shift(-n) 或读取未来行。
        # 预热期请返回 None，不要返回 NaN 或 Inf。
        def compute(panel: pl.DataFrame) -> pl.Series:
            previous = pl.col("close").shift(1).over("asset")
            return panel.select(
                (pl.col("close") - previous).alias("{factor_id}")
            ).to_series()


        # 可选：提供独立手算的小样本，风洞会逐行核对。
        GOLDEN_CASES = [
            # GoldenCase(
            #     name="example",
            #     bars=[{{"date": "2025-01-02", "asset": "000001.SZ", "close": 10.0}}],
            #     expected=[None],
            # ),
        ]

        FACTOR_PLUGIN = FactorPlugin(
            factor_id="{factor_id}",
            display_name="{factor_id}",
            group={group_literal},
            compute=compute,
            bar_interval="1d",
            scope="time_series",
            price_adjustment="hfq",
            required_columns=("close",),
            warmup_bars=1,
            availability="bar_close",
            direction="positive",
            principle="TODO: 说明经济含义。",
            formula="TODO: 写明公式。",
            example="TODO: 给出手算示例。",
            caveats="TODO: 写明边界与风险。",
            golden_cases=tuple(GOLDEN_CASES),
        )
        '''
    )


def init_factor(
    factor_id: str, *, group: str = "自定义因子", directory: str | None = None
) -> dict[str, Any]:
    """Create a metadata-rich plugin template inside the configured factor directory."""
    if not _FACTOR_ID.fullmatch(factor_id):
        raise ValueError("factor_id 必须匹配 ^[a-z][a-z0-9_]{2,63}$")
    if factor_id in FEATURE_COLS:
        raise ValueError(f"factor_id 与内置因子重名: {factor_id}")
    from quantide.config.settings import get_factor_dir

    target_dir = Path(normalize_factor_dir(directory or get_factor_dir()))
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{factor_id}.py"
    if path.exists():
        raise FileExistsError(str(path))
    path.write_text(_template(factor_id, group), encoding="utf-8")
    clear_plugin_cache()
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return {"factor_id": factor_id, "path": str(path), "source_hash": source_hash}


def _resolve_target(target: str) -> tuple[str, FactorPlugin | None]:
    path = Path(target).expanduser()
    if target.endswith(".py") or path.is_file():
        plugin = load_factor_plugin(path)
        return plugin.factor_id, plugin
    if target in all_factor_ids():
        return target, None
    raise KeyError(target)


def _check_window(start: dt.date | None, end: dt.date | None) -> tuple[dt.date, dt.date, Any]:
    dates = _bar_dates()
    if not dates:
        raise ValueError("本地日线为空，无法运行因子风洞。")
    resolved_start = start or dates[0]
    resolved_end = end or dates[-1]
    if resolved_start > resolved_end:
        raise ValueError("开始日期不能晚于结束日期")
    frame = load_wind_tunnel_frame(resolved_start, resolved_end)
    return resolved_start, resolved_end, frame


def _inconclusive_payload(factor_id: str, code: str, message: str) -> tuple[dict[str, Any], int]:
    return (
        envelope(
            "factor.check",
            ok=False,
            status="INCONCLUSIVE",
            exit_code=4,
            fingerprints={"source_hash": factor_version(factor_id)},
            diagnostics=[{"code": code, "message": message}],
        ),
        4,
    )


def _check_frame(
    factor_id: str, start: dt.date | None, end: dt.date | None
) -> tuple[Any, tuple[dict[str, Any], int] | None]:
    try:
        _, _, frame = _check_window(start, end)
    except ValueError as exc:
        if "没有可用行情" not in str(exc) and "日线为空" not in str(exc):
            raise
        return None, _inconclusive_payload(factor_id, "INSUFFICIENT_DATA", str(exc))
    return frame, None


def check_factor(
    target: str,
    *,
    cutoffs: list[dt.date] | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> tuple[dict[str, Any], int]:
    """Run the shared wind tunnel and return the CLI envelope plus exit code."""
    factor_id, plugin = _resolve_target(target)
    if cutoffs is not None and len(cutoffs) < 3:
        return _inconclusive_payload(
            factor_id, "INSUFFICIENT_CUTOFFS", "至少需要 3 个未来截断点才能形成风洞证据。"
        )
    frame, error = _check_frame(factor_id, start, end)
    if error is not None:
        return error
    result = run_factor_wind_tunnel(
        factor_id,
        frame=frame,
        cutoffs=tuple(cutoffs) if cutoffs else None,
        plugin=plugin,
        save=True,
    )
    status = result.status
    exit_code = 0 if status == "PASS" else (3 if status == "FAIL" else 4)
    diagnostics = []
    for check in result.report.checks:
        if check.status.value not in {"FAIL", "INCONCLUSIVE"}:
            continue
        difference = check.first_difference.as_dict() if check.first_difference else None
        if difference is not None:
            difference.setdefault("date", difference.get("time"))
        diagnostics.append(
            {"code": check.check_id, "message": check.message, "first_difference": difference}
        )
    payload = envelope(
        "factor.check",
        ok=status == "PASS",
        status=status,
        exit_code=exit_code,
        fingerprints={
            "source_hash": result.report.spec.source_hash,
            "data_hash": result.report.spec.data_hash,
            "config_hash": result.report.spec.config_hash,
        },
        data=result.as_dict(),
        diagnostics=diagnostics,
    )
    return payload, exit_code


def run_study(
    factor_id: str,
    *,
    start: dt.date,
    end: dt.date,
    holdings: list[int],
    price_field: str,
) -> tuple[dict[str, Any], int]:
    """Run the shared factor study and expose the requested statistics."""
    study = run_custom_study(factor_id, start, end, holdings, price_field)
    rows: list[dict[str, Any]] = []
    for result in study.results:
        rows.append(
            {
                "holding_days": result.holding_days,
                "as_of_date": result.diagnostics.as_of_date,
                "rank_ic": result.rank_ic.as_dict(),
                "pearson_ic": result.pearson_ic.as_dict(),
                "deciles": result.deciles.as_dict(),
            }
        )
    valid = any(row["rank_ic"].get("n_days", 0) > 0 for row in rows)
    status = "OK" if valid else "INCONCLUSIVE"
    exit_code = 0 if valid else 4
    payload = envelope(
        "factor.study",
        ok=valid,
        status=status,
        exit_code=exit_code,
        fingerprints={
            "source_hash": factor_version(factor_id),
            "data_hash": "",
            "config_hash": study.calendar_version,
        },
        data={
            "study_id": study.study_id,
            "factor_id": factor_id,
            "start": study.start,
            "end": study.end,
            "price_field": study.price_field,
            "data_cutoff": study.data_cutoff,
            "results": rows,
            "common_cohort": study.cohort.as_dict(),
        },
        diagnostics=[]
        if valid
        else [{"code": "INSUFFICIENT_DATA", "message": "样本不足以形成统计结论。"}],
    )
    return payload, exit_code


__all__ = [
    "check_factor",
    "data_status",
    "envelope",
    "envelope_json",
    "init_factor",
    "json_safe",
    "list_factors",
    "run_study",
]
