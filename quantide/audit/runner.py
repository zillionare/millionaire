"""Run registered audit checks without mutating user accounts or code."""

from __future__ import annotations

import datetime as dt
import os
import platform
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

from quantide.audit.models import (
    AuditCheck,
    AuditReport,
    AuditSpec,
    AuditStatus,
    FirstDifference,
    compose_status,
)

AuditFunction = Callable[[AuditSpec], AuditCheck]
_REGISTRY: dict[str, tuple[AuditFunction, bool]] = {}


def register_check(check_id: str, function: AuditFunction, *, required: bool = True) -> None:
    if not check_id:
        raise ValueError("check_id must not be empty")
    _REGISTRY[check_id] = (function, required)


def clear_checks() -> None:
    _REGISTRY.clear()


def registered_checks() -> dict[str, bool]:
    return {check_id: required for check_id, (_, required) in _REGISTRY.items()}


def _environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pid": os.getpid(),
    }


class AuditRunner:
    def __init__(self, registry: dict[str, tuple[AuditFunction, bool]] | None = None) -> None:
        self._registry = dict(_REGISTRY if registry is None else registry)

    def run(self, spec: AuditSpec) -> AuditReport:
        checks: list[AuditCheck] = []
        for check_id, (function, required) in self._registry.items():
            started = time.monotonic()
            try:
                check = function(spec)
            except Exception as exc:
                check = AuditCheck(
                    check_id=check_id,
                    required=required,
                    status=AuditStatus.FAIL,
                    message=f"{type(exc).__name__}: {exc}",
                )
            else:
                check = AuditCheck(
                    check_id=check.check_id or check_id,
                    required=required,
                    status=check.status,
                    message=check.message,
                    duration_ms=check.duration_ms or int((time.monotonic() - started) * 1000),
                    sample_size=check.sample_size,
                    first_difference=check.first_difference,
                    details=check.details,
                )
            checks.append(check)
        status = compose_status(checks)
        return AuditReport(
            run_id=uuid.uuid4().hex,
            spec=spec,
            status=status,
            checks=tuple(checks),
            generated_at=dt.datetime.now(dt.UTC).isoformat(),
            environment=_environment(),
            reproduce={"spec": spec.as_dict(), "checks": list(self._registry)},
        )


def fail_check(
    check_id: str,
    *,
    message: str,
    expected: Any,
    actual: Any,
    time: str = "",
    asset: str = "",
    column: str = "",
    kind: str = "value_mismatch",
    minimal_input: dict[str, Any] | None = None,
) -> AuditCheck:
    return AuditCheck(
        check_id=check_id,
        required=True,
        status=AuditStatus.FAIL,
        message=message,
        first_difference=FirstDifference(
            time=time,
            asset=asset,
            column=column,
            expected=expected,
            actual=actual,
            kind=kind,
            minimal_input=minimal_input or {},
        ),
    )
