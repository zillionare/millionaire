"""Process-isolated custom study task lifecycle."""

from __future__ import annotations

import datetime as dt
import threading
import time
from pathlib import Path

import pytest

from quantide.service import factor_study_worker as worker
from quantide.service.factor_runs import (
    CANCELLED,
    FAILED,
    RUNNING,
    SUCCEEDED,
    FactorRunStore,
    RunBudget,
)
from quantide.service.process_runner import (
    CANCELLED as PROCESS_CANCELLED,
)
from quantide.service.process_runner import (
    TIMEOUT as PROCESS_TIMEOUT,
)
from quantide.service.process_runner import ProcessOutcome, run_isolated


@pytest.fixture(autouse=True)
def _stop_worker_after_test():
    yield
    worker.stop_worker()


def _wait(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_task_ledger_is_idempotent_scoped_and_stores_result(tmp_path) -> None:
    store = FactorRunStore(tmp_path / "runs.sqlite")
    payload = {"factor_id": "bias_5", "start": "2024-01-02"}
    first = store.enqueue_task(
        scope="study",
        factor_ids=["bias_5"],
        lookback="custom",
        payload=payload,
        budget=RunBudget(),
    )
    assert (
        store.enqueue_task(
            scope="study",
            factor_ids=["bias_5"],
            lookback="custom",
            payload=payload,
            budget=RunBudget(),
        )
        == first
    )
    assert store.claim("tracking", budget=RunBudget(), scopes=("factor", "group")) is None
    claimed = store.claim("study", budget=RunBudget(), scopes=("study",))
    assert claimed is not None and claimed.run_id == first
    assert claimed.payload == payload
    assert store.set_result(first, {"kind": "custom_study", "study_id": "s1"}, owner="study")
    assert store.get(first).result == {"kind": "custom_study", "study_id": "s1"}


def test_process_runner_terminates_timeout_cancel_and_failure() -> None:
    started = time.monotonic()
    timed_out = run_isolated(time.sleep, 10, timeout=0.5)
    assert timed_out.status == PROCESS_TIMEOUT
    assert time.monotonic() - started < 5

    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    assert run_isolated(time.sleep, 10, timeout=10, cancel=cancel).status == PROCESS_CANCELLED

    failed = run_isolated(int, "not-a-number", timeout=5)
    assert failed.status != SUCCEEDED and "ValueError" in failed.error


def _patch_worker(monkeypatch, tmp_path, outcome) -> FactorRunStore:
    store = FactorRunStore(tmp_path / "runs.sqlite")
    worker.stop_worker()
    monkeypatch.setattr(worker, "run_store", lambda: store)
    monkeypatch.setattr(worker, "run_isolated", lambda *args, **kwargs: outcome)
    return store


def test_study_task_runs_in_worker_and_keeps_result(monkeypatch, tmp_path) -> None:
    result = {
        "kind": "custom_study",
        "study_id": "study-1",
        "factor_id": "bias_5",
        "start": "2024-01-02",
        "end": "2024-01-08",
        "price_field": "open",
        "data_cutoff": "2024-01-08",
        "holding_days": [1],
        "results": [],
        "common_cohort": {"dates": [], "n_days": 0, "per_horizon": {}, "status": "insufficient"},
        "created_at": "2024-01-08T16:00:00",
    }
    store = _patch_worker(monkeypatch, tmp_path, ProcessOutcome(SUCCEEDED, result))
    run_id = worker.submit_study("bias_5", dt.date(2024, 1, 2), dt.date(2024, 1, 8), [1])
    assert _wait(lambda: store.get(run_id).status == SUCCEEDED)
    run = store.get(run_id)
    assert run.result["study_id"] == "study-1"
    assert worker.load_study(run_id).study_id == "study-1"
    worker.stop_worker()


def test_study_timeout_fails_and_cancel_is_cooperative(monkeypatch, tmp_path) -> None:
    store = _patch_worker(
        monkeypatch, tmp_path, ProcessOutcome(PROCESS_TIMEOUT, error="budget exceeded")
    )
    timeout_id = worker.submit_study("bias_5", dt.date(2024, 1, 2), dt.date(2024, 1, 8), [1])
    assert _wait(lambda: store.get(timeout_id).status == FAILED)
    assert "budget" in store.get(timeout_id).error
    worker.stop_worker()

    store = FactorRunStore(tmp_path / "cancel.sqlite")

    def blocking(*args, **kwargs):
        while not kwargs["cancel"].is_set():
            time.sleep(0.01)
        return ProcessOutcome(PROCESS_CANCELLED)

    worker.stop_worker()
    monkeypatch.setattr(worker, "run_store", lambda: store)
    monkeypatch.setattr(worker, "run_isolated", blocking)
    cancel_id = worker.submit_study("bias_5", dt.date(2024, 1, 2), dt.date(2024, 1, 8), [1])
    assert _wait(lambda: store.get(cancel_id).status == RUNNING)
    assert worker.cancel_study(cancel_id)
    assert _wait(lambda: store.get(cancel_id).status == CANCELLED)
    worker.stop_worker()


def test_real_subprocess_study_initializes_data_home(tmp_path, monkeypatch) -> None:
    import shutil

    import polars as pl

    home = tmp_path / "market"
    data_dir = home / "data"
    bars_dir = data_dir / "bars" / "daily" / "partition_key_year=2024"
    bars_dir.mkdir(parents=True)
    shutil.copy2(
        Path(__file__).parents[3] / "assets" / "baseline_calendar.parquet",
        data_dir / "calendar.parquet",
    )
    shutil.copy2(
        Path(__file__).parents[3] / "assets" / "market_data" / "stock_list.parquet",
        data_dir / "stock_list.parquet",
    )
    raw = pl.read_parquet(Path(__file__).parents[3] / "assets" / "bars_2021_2024.small.parquet")
    raw.filter(pl.col("date").dt.year() == 2024).write_parquet(bars_dir / "data.parquet")
    store = FactorRunStore(tmp_path / "runs.sqlite")
    worker.stop_worker()
    monkeypatch.setattr(worker, "run_store", lambda: store)
    run_id = worker.submit_study(
        "bias_5",
        dt.date(2024, 1, 2),
        dt.date(2024, 3, 29),
        [1],
        data_home=str(home),
    )
    assert _wait(lambda: store.get(run_id).status in {SUCCEEDED, FAILED}, timeout=90)
    run = store.get(run_id)
    assert run.status == SUCCEEDED, run.error
    assert run.result is not None and run.result["results"]
    assert worker.load_study(run_id) is not None
    worker.stop_worker()
