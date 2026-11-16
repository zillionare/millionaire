"""Versioned audit input and report contracts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum, StrEnum
from typing import Any, cast

AUDIT_SCHEMA_VERSION = "1.0.0"


class AuditStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, float) and not (value == value and abs(value) != float("inf")):
        return None
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditSpec:
    spec_id: str
    object_type: str
    object_id: str
    source_hash: str
    data_hash: str
    config_hash: str
    interval: str
    timezone: str
    availability_contract: str
    seed_set: tuple[int, ...] = ()
    statistical_profile: str = ""
    oracle_version: str = ""
    mutation_version: str = ""
    truncation_points: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], _json_safe(asdict(self)))

    @property
    def fingerprint(self) -> str:
        return canonical_hash(self.as_dict())


@dataclass(frozen=True)
class FirstDifference:
    time: str
    asset: str
    column: str
    expected: Any
    actual: Any
    kind: str
    minimal_input: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], _json_safe(asdict(self)))


@dataclass(frozen=True)
class AuditCheck:
    check_id: str
    required: bool
    status: AuditStatus
    message: str = ""
    duration_ms: int = 0
    sample_size: int | None = None
    first_difference: FirstDifference | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def run(self) -> bool:
        return self.status is not AuditStatus.NOT_APPLICABLE

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        if self.first_difference is not None:
            payload["first_difference"] = self.first_difference.as_dict()
        return cast(dict[str, Any], _json_safe(payload))


def compose_status(checks: list[AuditCheck]) -> AuditStatus:
    if not checks:
        return AuditStatus.INCONCLUSIVE
    if any(check.status is AuditStatus.FAIL for check in checks):
        return AuditStatus.FAIL
    if any(check.required and check.status is not AuditStatus.PASS for check in checks):
        return AuditStatus.INCONCLUSIVE
    return AuditStatus.PASS


@dataclass(frozen=True)
class AuditReport:
    run_id: str
    spec: AuditSpec
    status: AuditStatus
    checks: tuple[AuditCheck, ...]
    generated_at: str
    environment: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    mutations: dict[str, Any] = field(default_factory=dict)
    attribution: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    reproduce: dict[str, Any] = field(default_factory=dict)
    schema_version: str = AUDIT_SCHEMA_VERSION

    @property
    def first_difference(self) -> FirstDifference | None:
        return next(
            (
                check.first_difference
                for check in self.checks
                if check.status is AuditStatus.FAIL and check.first_difference is not None
            ),
            None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "spec_id": self.spec.spec_id,
            "spec_fingerprint": self.spec.fingerprint,
            "source_hash": self.spec.source_hash,
            "config_hash": self.spec.config_hash,
            "data_hash": self.spec.data_hash,
            "environment": _json_safe(self.environment),
            "interval": self.spec.interval,
            "timezone": self.spec.timezone,
            "availability_contract": self.spec.availability_contract,
            "seed_set": list(self.spec.seed_set),
            "statistical_profile": self.spec.statistical_profile,
            "oracle_version": self.spec.oracle_version,
            "mutation_version": self.spec.mutation_version,
            "status": self.status.value,
            "checks": [check.as_dict() for check in self.checks],
            "first_difference": (
                self.first_difference.as_dict() if self.first_difference is not None else None
            ),
            "statistics": _json_safe(self.statistics),
            "mutations": _json_safe(self.mutations),
            "attribution": _json_safe(self.attribution),
            "artifacts": list(self.artifacts),
            "reproduce": _json_safe(self.reproduce),
            "generated_at": self.generated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, allow_nan=False)
