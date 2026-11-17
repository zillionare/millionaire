"""Process-isolated custom study task lifecycle."""

from __future__ import annotations

import datetime as dt
import importlib
import sys
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
    MEMORY,
    ProcessOutcome,
    run_isolated,
)
from quantide.service.process_runner import (
    TIMEOUT as PROCESS_TIMEOUT,
)

_SERVICE_TEST_DIR = Path(__file__).resolve().parent
if str(_SERVICE_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_TEST_DIR))
_process_descendant_worker = importlib.import_module("_process_descendant_worker")
_process_memory_worker = importlib.import_module("_process_memory_worker")
if getattr(_process_memory_worker, "_RESERVED", None) is not None:
    _process_memory_worker._RESERVED.close()


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


def test_process_runner_enforces_memory_budget(tmp_path) -> None:
    marker = tmp_path / "worker-entered"
    outcome = run_isolated(
        _process_memory_worker.allocate_beyond_budget,
        str(marker),
        timeout=15,
        memory_bytes=64 * 1024 * 1024,
    )

    assert marker.read_text(encoding="utf-8") == "entered"
    assert outcome.status != SUCCEEDED
    if sys.platform.startswith("linux") or sys.platform == "win32":
        assert outcome.status == MEMORY
    else:
        assert outcome.status in {MEMORY, FAILED}


def test_bare_spawn_helper_does_not_import_tests_or_pandas() -> None:
    outcome = run_isolated(_process_descendant_worker.loaded_test_frameworks, timeout=30)

    assert outcome.status == SUCCEEDED, outcome.error
    assert outcome.value == []


def test_rss_budget_allows_healthy_polars_with_large_virtual_mapping() -> None:
    outcome = run_isolated(
        _process_memory_worker.healthy_polars_sum,
        timeout=30,
        memory_bytes=512 * 1024 * 1024,
    )

    assert outcome.status == SUCCEEDED, outcome.error
    assert outcome.value == sum(range(20_000)) * 2


def _large_result(size: int) -> bytes:
    return b"x" * size


def _assert_dead(pid: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if _process_descendant_worker.process_is_dead(pid):
            return
        time.sleep(0.05)
    assert _process_descendant_worker.process_is_dead(pid)


def test_runner_kills_nested_worker_group_after_outer_timeout(tmp_path) -> None:
    pid_file = tmp_path / "nested-inner.pid"
    outcome = run_isolated(_process_descendant_worker._nested_outer, str(pid_file), timeout=3)
    assert outcome.status == PROCESS_TIMEOUT
    assert pid_file.exists()
    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        _assert_dead(pid)
    finally:
        _process_descendant_worker.force_kill(pid)


def test_runner_kills_leftover_child_after_normal_return(tmp_path) -> None:
    pid_file = tmp_path / "leftover.pid"
    outcome = run_isolated(
        _process_descendant_worker._spawn_leftover_and_return, str(pid_file), timeout=5
    )
    assert outcome.status == SUCCEEDED
    assert pid_file.exists()
    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        _assert_dead(pid)
    finally:
        _process_descendant_worker.force_kill(pid)


def test_runner_kills_term_ignoring_descendants_after_timeout(tmp_path) -> None:
    pid_file = tmp_path / "descendant.pid"
    outcome = run_isolated(
        _process_descendant_worker._spawn_stubborn_descendant, str(pid_file), timeout=5
    )
    assert outcome.status == PROCESS_TIMEOUT
    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        _assert_dead(pid)
    finally:
        _process_descendant_worker.force_kill(pid)


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


def test_nested_timeout_leaves_no_named_semaphores_in_live_service(tmp_path) -> None:
    import json

    for index in range(3):
        path = tmp_path / f"semaphores-{index}.json"
        outcome = run_isolated(
            _process_descendant_worker._nested_semaphore_outer, str(path), timeout=3
        )
        assert outcome.status == PROCESS_TIMEOUT
        assert json.loads(path.read_text(encoding="utf-8")) == []


def test_isolated_result_file_handles_large_payload() -> None:
    outcome = run_isolated(_large_result, 4 * 1024 * 1024, timeout=10)
    assert outcome.status == SUCCEEDED
    assert isinstance(outcome.value, bytes)
    assert len(outcome.value) == 4 * 1024 * 1024


@pytest.mark.parametrize(
    "actual_group, hint, expected",
    [
        (12345, True, True),
        (12346, True, False),
        (None, True, True),
        (None, False, False),
    ],
)
def test_group_cleanup_hint_never_overrides_live_ownership(
    monkeypatch, actual_group, hint, expected
):
    from quantide.service import process_runner

    def get_group(_pid):
        if actual_group is None:
            raise ProcessLookupError()
        return actual_group

    monkeypatch.setattr(process_runner.os, "getpgid", get_group, raising=False)
    assert process_runner._owns_process_group(12345, exited_hint=hint) is expected
