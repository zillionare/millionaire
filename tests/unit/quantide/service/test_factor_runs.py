"""Durable factor-run ledger and worker tests."""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from quantide.service.factor_runs import (
    CANCELLED,
    INTERRUPTED,
    PENDING,
    RUNNING,
    SUCCEEDED,
    FactorRun,
    FactorRunStore,
    FactorRunWorker,
    RunBudget,
    _heartbeat_loop,
)
from quantide.service.process_runner import SUCCEEDED as PROCESS_SUCCEEDED
from quantide.service.process_runner import ProcessOutcome


@pytest.fixture(autouse=True)
def _stop_workers(monkeypatch):
    workers: list[FactorRunWorker] = []
    original_start = FactorRunWorker.start

    def tracked_start(worker: FactorRunWorker) -> None:
        workers.append(worker)
        original_start(worker)

    monkeypatch.setattr(FactorRunWorker, "start", tracked_start)
    yield
    for worker in workers:
        worker.stop()


def _store(tmp_path) -> FactorRunStore:
    return FactorRunStore(tmp_path / "runs.sqlite")


def _enqueue(store: FactorRunStore, factors=("bias_5",), revision: int = 0):
    return store.enqueue(
        factors,
        lookback="3y",
        profile_revisions={factor: 0 for factor in factors},
        source_revision=revision,
        source_versions={"source_market_version": f"m{revision}"},
        budget=RunBudget(),
    )


def _wait(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_enqueue_dedupes_same_input_and_supersedes_older(tmp_path) -> None:
    store = _store(tmp_path)
    first = _enqueue(store)
    assert len(first) == 1
    assert _enqueue(store) == []

    newer = _enqueue(store, revision=1)
    assert len(newer) == 1
    statuses = {run.run_id: run.status for run in store.list_runs()}
    assert statuses[first[0]] == "superseded"
    assert statuses[newer[0]] == PENDING


def test_owns_fences_released_or_foreign_owners(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    claimed = store.claim("owner-a", budget=RunBudget())
    assert claimed is not None
    assert store.owns(run_id, "owner-a")
    assert not store.owns(run_id, "owner-b")
    store.release_owner("owner-a")
    assert not store.owns(run_id, "owner-a")


def test_claim_checkpoint_and_finish_require_owner(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    claimed = store.claim("owner-a", budget=RunBudget())
    assert claimed is not None and claimed.run_id == run_id
    assert claimed.status == RUNNING
    assert store.checkpoint(
        run_id, "owner-a", phase="panel", checkpoint={"rows": 10}, lease_seconds=30
    )
    assert not store.checkpoint(run_id, "owner-b", phase="panel", checkpoint={}, lease_seconds=30)
    run = store.list_runs()[0]
    assert run.checkpoint == {"rows": 10}
    assert run.phase == "panel"
    assert not store.finish(run_id, "owner-b", SUCCEEDED)
    assert store.finish(run_id, "owner-a", SUCCEEDED)
    assert store.list_runs()[0].status == SUCCEEDED


def test_expired_lease_becomes_claimable(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    store.claim("owner-a", budget=RunBudget())
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE factor_runs SET lease_until = ? WHERE run_id = ?", (0.0, run_id))
    assert store.recover() == 1
    assert store.list_runs()[0].status == PENDING


def test_cancel_pending_and_running(tmp_path) -> None:
    store = _store(tmp_path)
    _enqueue(store)
    assert store.cancel_factors(["bias_5"])
    assert store.list_runs()[0].status == CANCELLED

    running = _enqueue(store, revision=1)[0]
    store.claim("owner-a", budget=RunBudget())
    assert store.request_cancel(running)
    assert store.cancelled(running)


def test_worker_executes_and_stops(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    phases: list[str] = []

    def executor(run, cancel, checkpoint):
        checkpoint("panel", {"rows": 5})
        phases.append("done")
        return SUCCEEDED

    worker = FactorRunWorker(store, executor, poll_seconds=0.01)
    worker.start()
    assert _wait(lambda: store.list_runs()[0].status == SUCCEEDED)
    worker.stop()
    assert phases == ["done"]
    assert store.list_runs()[0].phase == "panel"
    assert run_id


def test_worker_cancellation_and_timeout(tmp_path) -> None:
    store = _store(tmp_path)
    _enqueue(store)

    def executor(run, cancel, checkpoint):
        while not cancel.is_set():
            time.sleep(0.005)
        raise InterruptedError

    budget = RunBudget(max_seconds=0.05, lease_seconds=0.05)
    worker = FactorRunWorker(store, executor, budget=budget, poll_seconds=0.01)
    worker.start()
    assert _wait(lambda: store.list_runs()[0].status == RUNNING)
    run = store.list_runs()[0]
    store.request_cancel(run.run_id)
    assert _wait(lambda: store.list_runs()[0].status == CANCELLED)
    worker.stop()


def test_late_owner_cannot_publish_after_release(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    claimed = store.claim("owner-a", budget=RunBudget())
    assert claimed is not None
    assert store.release_owner("owner-a") == 1
    assert not store.set_result(
        run_id, {"kind": "custom_study", "study_id": "late"}, owner="owner-a"
    )
    assert store.get(run_id).status == PENDING
    assert store.get(run_id).result is None


def test_worker_stop_cancels_never_returns_and_prevents_publish(tmp_path) -> None:
    store = _store(tmp_path)
    _enqueue(store)
    observed = {"cancel": False, "executed": False}

    def executor(run, cancel, checkpoint):
        while not cancel.is_set():
            time.sleep(0.01)
        observed["cancel"] = True
        observed["executed"] = True
        return SUCCEEDED

    worker = FactorRunWorker(store, executor, poll_seconds=0.01)
    worker.start()
    assert _wait(lambda: store.list_runs()[0].status == RUNNING)
    worker.stop(timeout=0.1)
    assert _wait(lambda: observed["cancel"], timeout=2)
    run = store.list_runs()[0]
    assert run.status in {CANCELLED, INTERRUPTED, PENDING}
    assert run.result is None


def test_heartbeat_lost_lease_sets_cancel(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    budget = RunBudget(lease_seconds=0.06)
    assert store.claim("old", budget=budget) is not None
    cancel = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(
        target=_heartbeat_loop,
        args=(store, run_id, "old", budget, cancel, stop),
    )
    thread.start()
    store.release_owner("old")
    assert _wait(cancel.is_set, timeout=2)
    stop.set()
    thread.join(1)
    assert not thread.is_alive()


def test_worker_restart_resumes_a_released_task(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    release = threading.Event()

    def stuck(*_):
        release.wait()
        return SUCCEEDED

    first = FactorRunWorker(store, stuck, poll_seconds=0.01, concurrency=1)
    second = FactorRunWorker(store, lambda *_: SUCCEEDED, poll_seconds=0.01, concurrency=1)
    try:
        first.start()
        assert _wait(lambda: store.get(run_id).status == RUNNING)
        first.stop(timeout=0.01)
        assert _wait(lambda: store.get(run_id).status == PENDING)

        second.start()
        assert _wait(lambda: store.get(run_id).status == SUCCEEDED, timeout=15)
    finally:
        release.set()
        first.stop()
        second.stop()


def test_study_and_tracking_supersede_only_within_their_scope(tmp_path) -> None:
    store = _store(tmp_path)
    study = store.enqueue_task(
        scope="study",
        factor_ids=["bias_5"],
        lookback="custom",
        payload={"start": "2024-01-02"},
        budget=RunBudget(),
    )
    tracking = _enqueue(store)[0]
    assert store.get(study).status == PENDING
    assert store.get(tracking).status == PENDING

    second_study = store.enqueue_task(
        scope="study",
        factor_ids=["bias_5"],
        lookback="custom",
        payload={"start": "2024-02-02"},
        budget=RunBudget(),
    )
    assert store.get(study).status == PENDING
    assert store.get(second_study).status == PENDING
    assert store.get(tracking).status == PENDING


def test_expired_lease_requeues_with_remaining_attempts(tmp_path) -> None:
    store = _store(tmp_path)
    run_id = _enqueue(store)[0]
    budget = RunBudget(max_attempts=2)
    first = store.claim("owner-a", budget=budget)
    assert first is not None and first.run_id == run_id and first.attempt == 1
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE factor_runs SET lease_until = 0 WHERE run_id = ?", (run_id,))
    second = store.claim("owner-b", budget=budget)
    assert second is not None and second.run_id == run_id
    assert second.attempt == 2
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE factor_runs SET lease_until = 0 WHERE run_id = ?", (run_id,))
    assert store.claim("owner-c", budget=budget) is None
    assert store.get(run_id).status == INTERRUPTED


def test_store_closes_each_connection(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    opened: list[sqlite3.Connection] = []
    original_connect = store._connect

    def tracking_connect() -> sqlite3.Connection:
        connection = original_connect()
        opened.append(connection)
        return connection

    monkeypatch.setattr(store, "_connect", tracking_connect)
    store.list_runs()
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


def test_tracking_executor_runs_in_isolation(monkeypatch) -> None:
    from quantide.service import factor_tracking_worker

    run = FactorRun(
        run_id="run-1",
        idempotency_key="key-1",
        scope="factor",
        factor_ids=("bias_5",),
        lookback="3y",
        status=PENDING,
        owner="worker-1",
        phase="pending",
    )
    calls = []

    def fake_run_isolated(target, *args, **kwargs):
        calls.append((target, args, kwargs))
        return ProcessOutcome(PROCESS_SUCCEEDED, {"status": "succeeded", "pending": []})

    monkeypatch.setattr(factor_tracking_worker, "run_isolated", fake_run_isolated)
    assert factor_tracking_worker._execute_run(run, threading.Event(), None) == "succeeded"
    assert calls
    assert calls[0][0] is factor_tracking_worker._tracking_target
    assert calls[0][1] == (run,)
