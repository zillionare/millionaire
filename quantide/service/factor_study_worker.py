"""Durable, process-isolated custom factor study tasks."""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

from quantide.service.factor_runs import (
    CANCELLED,
    FactorRun,
    FactorRunStore,
    FactorRunWorker,
    RunBudget,
)
from quantide.service.factor_study import (
    CustomStudy,
    run_custom_study,
    validate_study_request,
)
from quantide.service.factor_tracking_worker import run_store
from quantide.service.process_runner import (
    CANCELLED as PROCESS_CANCELLED,
)
from quantide.service.process_runner import (
    FAILED as PROCESS_FAILED,
)
from quantide.service.process_runner import (
    TIMEOUT as PROCESS_TIMEOUT,
)
from quantide.service.process_runner import run_isolated
from quantide.service.worker_slot import WorkerSlot

STUDY_SCOPE = "study"
BUDGET = RunBudget(max_seconds=120.0, lease_seconds=30.0, max_attempts=1, max_factors=1)
WORKER_BUDGET = RunBudget(max_seconds=130.0, lease_seconds=30.0, max_attempts=1, max_factors=1)


def _study_target(payload: dict[str, Any]) -> dict[str, Any]:
    data_home = str(payload.get("data_home") or "")
    if data_home:
        from quantide.data import init_data

        init_data(data_home, init_db=False)
    study = run_custom_study(
        str(payload["factor_id"]),
        dt.date.fromisoformat(str(payload["start"])),
        dt.date.fromisoformat(str(payload["end"])),
        [int(value) for value in payload["holding_days"]],
        str(payload["price_field"]),
    )
    return study.as_dict()


def _execute_run(
    run: FactorRun,
    cancel: threading.Event,
    checkpoint: Any,
) -> str:
    if cancel.is_set():
        return CANCELLED
    if callable(checkpoint):
        checkpoint("start", {"factor_ids": list(run.factor_ids), "payload": run.payload})
    outcome = run_isolated(
        _study_target,
        run.payload,
        timeout=BUDGET.max_seconds,
        cancel=cancel,
    )
    if outcome.status == PROCESS_TIMEOUT:
        raise TimeoutError(outcome.error or "custom study exceeded its time budget")
    if outcome.status == PROCESS_FAILED:
        raise RuntimeError(outcome.error or "custom study failed")
    if outcome.status == PROCESS_CANCELLED or cancel.is_set():
        return CANCELLED
    if not isinstance(outcome.value, dict):
        raise RuntimeError("custom study returned no result")
    if cancel.is_set():
        return CANCELLED
    if not run_store().set_result(run.run_id, outcome.value, owner=run.owner):
        raise RuntimeError("study result rejected: run ownership or lease changed")
    if callable(checkpoint):
        checkpoint("published", {"study_id": outcome.value.get("study_id", "")})
    return "succeeded"


_SLOT = WorkerSlot(
    lambda: run_store().path,
    lambda: FactorRunWorker(
        run_store(),
        _execute_run,
        budget=WORKER_BUDGET,
        scopes=(STUDY_SCOPE,),
    ),
)


def ensure_worker() -> FactorRunWorker:
    return _SLOT.ensure()


def stop_worker() -> None:
    _SLOT.stop()


def submit_study(
    factor_id: str,
    start: dt.date,
    end: dt.date,
    holding_days: list[int] | tuple[int, ...],
    price_field: str = "open",
    *,
    data_home: str | None = None,
) -> str:
    from quantide.config.settings import get_data_home

    holdings = validate_study_request(factor_id, start, end, holding_days, price_field)
    payload = {
        "factor_id": factor_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "holding_days": list(holdings),
        "price_field": price_field,
        "data_home": data_home or get_data_home(),
    }
    run_id = run_store().enqueue_task(
        scope=STUDY_SCOPE,
        factor_ids=[factor_id],
        lookback="custom",
        payload=payload,
        budget=BUDGET,
    )
    ensure_worker()
    return run_id


def study_run(run_id: str) -> FactorRun | None:
    return run_store().get(run_id)


def load_study(run_id: str) -> CustomStudy | None:
    run = study_run(run_id)
    if run is None or not run.result:
        return None
    payload = run.result
    if payload.get("kind") != "custom_study":
        return None
    return CustomStudy.from_dict(payload)


def cancel_study(run_id: str) -> bool:
    return run_store().request_cancel(run_id)


def start_study_worker() -> FactorRunStore:
    return ensure_worker().store


def stop_study_worker() -> None:
    stop_worker()
