"""Run a built-in factor audit from a local panel and write a JSON report."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import polars as pl

from quantide.audit.factor import audit_factor
from quantide.audit.models import AuditStatus


def _read_panel(path: Path) -> pl.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pl.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pl.read_csv(path, try_parse_dates=True)
    raise ValueError(f"unsupported panel format: {path.suffix}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("factor", help="registered factor id, e.g. ma20_slope")
    parser.add_argument("--panel", required=True, type=Path, help="raw daily panel CSV/Parquet")
    parser.add_argument(
        "--cutoff",
        action="append",
        type=dt.date.fromisoformat,
        help="truncation date; repeat for multiple cutoffs",
    )
    parser.add_argument("--output", required=True, type=Path, help="JSON report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        frame = _read_panel(args.panel)
        report = audit_factor(frame, args.factor, cutoffs=args.cutoff)
    except Exception as exc:
        print(f"audit failed to run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.to_json() + "\n", encoding="utf-8")
    print(f"{report.status.value} {args.factor} -> {args.output}")
    if report.status is AuditStatus.PASS:
        return 0
    if report.status is AuditStatus.FAIL:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
