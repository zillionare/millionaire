"""Durable audit report storage with fingerprint invalidation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantide.audit.models import AuditReport, AuditSpec
from quantide.config.paths import get_app_config_dir
from quantide.core.atomic_files import write_json


class ReportStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (get_app_config_dir() / "audit-reports")

    def _path(self, run_id: str) -> Path:
        if not run_id or "/" in run_id or "\\" in run_id:
            raise ValueError("invalid run id")
        return self.root / f"{run_id}.json"

    def save(self, report: AuditReport) -> Path:
        path = self._path(report.run_id)
        write_json(path, report.as_dict())
        return path

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("audit report is not an object")
        return payload

    def list_reports(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        reports = []
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                reports.append(
                    {
                        "run_id": payload.get("run_id", path.stem),
                        "spec_id": payload.get("spec_id", ""),
                        "status": payload.get("status", ""),
                        "source_hash": payload.get("source_hash", ""),
                        "generated_at": payload.get("generated_at", ""),
                    }
                )
        return reports

    def is_current(self, run_id: str, spec: AuditSpec) -> bool:
        payload = self.load(run_id)
        return (
            payload.get("spec_fingerprint") == spec.fingerprint
            and payload.get("source_hash") == spec.source_hash
            and payload.get("config_hash") == spec.config_hash
            and payload.get("data_hash") == spec.data_hash
        )
