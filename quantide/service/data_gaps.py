"""Durable records for historical data gaps that cannot be filled automatically."""

from __future__ import annotations

import datetime
import json
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import write_json


@dataclass(frozen=True)
class DataGapRecord:
    """One dataset gap with its latest source-side evidence."""

    dataset: str
    start: datetime.date
    end: datetime.date
    reason_code: str
    source: str = ""
    retryable: bool = False
    attempts: int = 1
    first_seen: datetime.datetime | None = None
    last_attempt: datetime.datetime | None = None
    resolved_at: datetime.datetime | None = None

    def overlaps(self, start: datetime.date, end: datetime.date) -> bool:
        return self.start <= end and start <= self.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "reason_code": self.reason_code,
            "source": self.source,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> DataGapRecord:
        def _date(value: Any) -> datetime.date:
            return datetime.date.fromisoformat(str(value))

        def _datetime(value: Any) -> datetime.datetime | None:
            return datetime.datetime.fromisoformat(str(value)) if value else None

        return DataGapRecord(
            dataset=str(payload["dataset"]),
            start=_date(payload["start"]),
            end=_date(payload["end"]),
            reason_code=str(payload.get("reason_code") or "unknown"),
            source=str(payload.get("source") or ""),
            retryable=bool(payload.get("retryable")),
            attempts=max(1, int(payload.get("attempts") or 1)),
            first_seen=_datetime(payload.get("first_seen")),
            last_attempt=_datetime(payload.get("last_attempt")),
            resolved_at=_datetime(payload.get("resolved_at")),
        )


class DataGapStore:
    """Small JSON-backed registry; it does not replace the risk event center."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else ensure_app_config_dir() / "data-gaps.json"
        self._lock = threading.RLock()

    def _load(self) -> list[DataGapRecord]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        records = payload.get("gaps") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        result: list[DataGapRecord] = []
        for item in records:
            try:
                result.append(DataGapRecord.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def _save(self, records: list[DataGapRecord]) -> None:
        write_json(self.path, {"gaps": [record.to_dict() for record in records]})

    def active(self) -> list[DataGapRecord]:
        with self._lock:
            return [record for record in self._load() if record.resolved_at is None]

    def blocking(
        self,
        dataset: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[DataGapRecord]:
        with self._lock:
            return [
                record
                for record in self._load()
                if record.resolved_at is None
                and not record.retryable
                and record.dataset == dataset
                and record.overlaps(start, end)
            ]

    def record(self, record: DataGapRecord) -> DataGapRecord:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._lock:
            records = self._load()
            for index, existing in enumerate(records):
                if (
                    existing.dataset == record.dataset
                    and existing.start == record.start
                    and existing.end == record.end
                ):
                    updated = replace(
                        existing,
                        reason_code=record.reason_code,
                        source=record.source,
                        retryable=record.retryable,
                        attempts=existing.attempts + 1,
                        last_attempt=datetime.datetime.now(),
                        resolved_at=None,
                    )
                    records[index] = updated
                    self._save(records)
                    return updated
            first_seen = record.first_seen or datetime.datetime.now()
            stored = replace(
                record,
                attempts=max(1, record.attempts),
                first_seen=first_seen,
                last_attempt=record.last_attempt or datetime.datetime.fromisoformat(now),
            )
            records.append(stored)
            self._save(records)
            return stored

    def resolve(self, dataset: str, start: datetime.date, end: datetime.date) -> None:
        with self._lock:
            records = self._load()
            resolved_at = datetime.datetime.now()
            changed = False
            for index, existing in enumerate(records):
                if existing.dataset != dataset or not existing.overlaps(start, end):
                    continue
                if existing.start < start or existing.end > end:
                    continue
                records[index] = replace(existing, resolved_at=resolved_at)
                changed = True
            if changed:
                self._save(records)


def _event_target(record: DataGapRecord) -> str:
    return f"data:gap:{record.dataset}:{record.start.isoformat()}:{record.end.isoformat()}"


def record_data_gap(
    *,
    dataset: str,
    start: datetime.date,
    end: datetime.date,
    reason_code: str,
    source: str = "",
    retryable: bool = False,
    store: DataGapStore | None = None,
) -> DataGapRecord:
    """Persist a gap and mirror unfillable gaps into the risk event center."""
    record = (store or DataGapStore()).record(
        DataGapRecord(
            dataset=dataset,
            start=start,
            end=end,
            reason_code=reason_code,
            source=source,
            retryable=retryable,
        )
    )
    if record.retryable:
        return record
    try:
        from quantide.service.strategy_runtime import strategy_runtime_manager

        strategy_runtime_manager.record_system_event(
            title="历史数据缺口无法补全",
            message=(f"{dataset} {start}~{end} 无法从 {source or '数据源'} 补齐：{reason_code}"),
            severity="warning",
            blocked=False,
            target_id=_event_target(record),
        )
    except Exception:
        pass
    return record


def resolve_data_gap(
    *,
    dataset: str,
    start: datetime.date,
    end: datetime.date,
    store: DataGapStore | None = None,
) -> None:
    """Mark a repaired range resolved and close its mirrored alert."""
    target_store = store or DataGapStore()
    target_store.resolve(dataset, start, end)
    try:
        from quantide.service.strategy_runtime import strategy_runtime_manager

        strategy_runtime_manager.record_system_event(
            title="历史数据缺口已补齐",
            message=f"{dataset} {start}~{end} 已补齐。",
            severity="info",
            blocked=False,
            target_id=f"data:gap:{dataset}:{start.isoformat()}:{end.isoformat()}",
        )
    except Exception:
        pass


__all__ = [
    "DataGapRecord",
    "DataGapStore",
    "record_data_gap",
    "resolve_data_gap",
]
