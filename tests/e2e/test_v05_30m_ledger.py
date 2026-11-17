"""Independent two-day 30m shadow ledger, restart and kill evidence."""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]

_REPO = Path(__file__).resolve().parents[2]
_WORKER = Path(__file__).with_name("shadow_30m_worker.py")
_ACTUAL_WORKER = Path(__file__).with_name("shadow_30m_actual_worker.py")
_DAYS = (datetime.date(2024, 1, 2), datetime.date(2024, 1, 3))
_TIMES = (
    datetime.time(10, 0),
    datetime.time(10, 30),
    datetime.time(11, 0),
    datetime.time(11, 30),
    datetime.time(13, 30),
    datetime.time(14, 0),
    datetime.time(14, 30),
    datetime.time(15, 0),
)
_SLOTS = [datetime.datetime.combine(day, moment) for day in _DAYS for moment in _TIMES]
_ASSET = "000001.SZ"
_MODEL_KEY = "ledger-model"
# Frozen independent oracle: cash, shares, available, cumulative fees, nav, pending.
_ORACLE = [
    (10000.00, 0, 0, 0.00, 10000.00, 1),
    (8994.99, 100, 0, 5.01, 9994.99, 1),
    (8994.99, 100, 0, 5.01, 9994.99, 0),
    (8994.99, 100, 0, 5.01, 9994.99, 0),
    (8994.99, 100, 0, 5.01, 9994.99, 0),
    (8994.99, 100, 0, 5.01, 9994.99, 0),
    (8994.99, 100, 0, 5.01, 9994.99, 1),
    (7989.98, 200, 0, 10.02, 9989.98, 0),
    (7989.98, 200, 200, 10.02, 9989.98, 1),
    (8984.47, 100, 100, 15.53, 9984.47, 1),
    (9978.96, 0, 0, 21.04, 9978.96, 0),
    (9978.96, 0, 0, 21.04, 9978.96, 0),
    (9978.96, 0, 0, 21.04, 9978.96, 0),
    (9978.96, 0, 0, 21.04, 9978.96, 0),
    (9978.96, 0, 0, 21.04, 9978.96, 0),
    (9978.96, 0, 0, 21.04, 9978.96, 0),
]


def _slot_text(slot: datetime.datetime) -> str:
    return slot.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def _all_slot_text() -> list[str]:
    return [_slot_text(slot) for slot in _SLOTS]


def _run_actual(db: Path, models: Path, observed: Path, *, skip: datetime.datetime | None = None):
    return subprocess.run(
        [
            sys.executable,
            str(_ACTUAL_WORKER),
            "--db",
            str(db),
            "--models",
            str(models),
            "--observed-file",
            str(observed),
            "--skip-actual-slot",
            skip.isoformat() if skip else "",
        ],
        cwd=_REPO,
        env={**os.environ, "PYTHONPATH": str(_REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _run_worker(
    db: Path,
    models: Path,
    observed: Path,
    latest: datetime.datetime,
    *,
    missing: list[datetime.datetime] | None = None,
    start: datetime.datetime | None = None,
    kill_slot: datetime.datetime | None = None,
    kill_stage: str = "after",
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(_WORKER),
        "--db",
        str(db),
        "--models",
        str(models),
        "--latest",
        latest.isoformat(),
        "--start-slot",
        start.isoformat() if start else "",
        "--missing",
        ",".join(slot.isoformat() for slot in missing or []),
        "--kill-slot",
        kill_slot.isoformat() if kill_slot else "",
        "--kill-stage",
        kill_stage,
        "--observed-file",
        str(observed),
    ]
    return subprocess.run(
        command,
        cwd=_REPO,
        env={**os.environ, "PYTHONPATH": str(_REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _observations(path: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            item = json.loads(line)
            if item.get("slot"):
                rows[str(item["slot"])] = item
    return rows


def _assert_store_rows(db: Path, source: str, observations: Path) -> None:
    from quantide.service.strategy_tracking import TrackingStore

    store = TrackingStore(db)
    bars = store.list_bars("paper:p1", "p1", source=source, bar_interval="30m")
    assert [bar["bar_slot"] for bar in bars] == _all_slot_text()
    seen_fees = 0.0
    all_trades: list[dict[str, object]] = []
    actual_observations = _observations(observations)
    for bar, expected in zip(bars, _ORACLE, strict=True):
        cash, shares, available, fees, nav, pending = expected
        positions = bar["positions"]
        held = next((item for item in positions if item["asset"] == _ASSET), None)
        assert bar["cash"] == pytest.approx(cash, rel=0.0, abs=1e-8)
        assert float(held["shares"] if held else 0) == shares
        assert float(held["avail"] if held else 0) == available
        assert bar["nav"] == pytest.approx(nav, rel=0.0, abs=1e-8)
        observed = actual_observations.get(bar["bar_slot"])
        assert observed is not None
        assert observed["pending"] == pending
        seen_fees += sum(float(trade.get("fee") or 0) for trade in bar["trades"])
        assert seen_fees == pytest.approx(fees, rel=0.0, abs=1e-8)
        all_trades.extend(bar["trades"])
    assert len(all_trades) == 4
    assert sum(float(trade["fee"]) for trade in all_trades) == pytest.approx(
        21.04, rel=0.0, abs=1e-8
    )
    assert [bar["bar_slot"] for bar in bars if bar["trades"]] == [
        _slot_text(_SLOTS[1]),
        _slot_text(_SLOTS[7]),
        _slot_text(_SLOTS[9]),
        _slot_text(_SLOTS[10]),
    ]
    run = store.get_run("paper:p1")
    assert run is not None and run["gap_slots"] == []


def _assert_intents(db: Path) -> None:
    connection = sqlite3.connect(db)
    try:
        rows = connection.execute(
            "SELECT runtime_id, signal_bar, target_bar, status "
            "FROM strategy_next_open_intents ORDER BY runtime_id, signal_bar, target_bar"
        ).fetchall()
    finally:
        connection.close()
    expected = [
        ("paper:p1:actual", _SLOTS[0].isoformat(), _SLOTS[0].isoformat(), "processed"),
        ("paper:p1:actual", _SLOTS[1].isoformat(), _SLOTS[1].isoformat(), "failed"),
        ("paper:p1:actual", _SLOTS[6].isoformat(), _SLOTS[6].isoformat(), "processed"),
        ("paper:p1:actual", _SLOTS[8].isoformat(), _SLOTS[8].isoformat(), "processed"),
        ("paper:p1:actual", _SLOTS[9].isoformat(), _SLOTS[9].isoformat(), "processed"),
        ("paper:p1:shadow", _SLOTS[0].isoformat(), _SLOTS[0].isoformat(), "processed"),
        ("paper:p1:shadow", _SLOTS[1].isoformat(), _SLOTS[1].isoformat(), "failed"),
        ("paper:p1:shadow", _SLOTS[6].isoformat(), _SLOTS[6].isoformat(), "processed"),
        ("paper:p1:shadow", _SLOTS[8].isoformat(), _SLOTS[8].isoformat(), "processed"),
        ("paper:p1:shadow", _SLOTS[9].isoformat(), _SLOTS[9].isoformat(), "processed"),
    ]
    assert rows == expected


def _assert_models(models: Path, actual_bars: list[dict[str, object]], observations: Path) -> None:
    from quantide.service.model_store import ModelStore

    store = ModelStore(models)
    refs = {str(bar["model_ref"]) for bar in actual_bars}
    assert len(refs) == 1
    model_ref = refs.pop()
    payload, _ = store.load_ref(model_ref)
    assert payload == {"generation": "A", "asset": _ASSET}
    observed = _observations(observations)
    assert {item["model_ref"] for item in observed.values()} == {model_ref}
    assert {item["loaded_generation"] for item in observed.values()} == {"A"}
    latest, _ = store.load(_MODEL_KEY)
    assert latest == {"generation": "B", "asset": _ASSET}


def test_two_day_ledger_matches_real_actual_and_frozen_oracle(tmp_path: Path) -> None:
    db = tmp_path / "ledger.db"
    models = tmp_path / "models"
    actual_observed = tmp_path / "actual.jsonl"
    shadow_observed = tmp_path / "shadow.jsonl"

    prepared = _run_actual(db, models, actual_observed)
    assert prepared.returncode == 0, prepared.stderr
    from quantide.service.strategy_tracking import TrackingStore

    store = TrackingStore(db)
    actual_before = store.list_bars("paper:p1", "p1", source="actual", bar_interval="30m")
    _assert_store_rows(db, "actual", actual_observed)

    first = _run_worker(db, models, shadow_observed, _SLOTS[1], missing=[_SLOTS[0]])
    assert first.returncode == 0, first.stderr
    assert store.list_bars("paper:p1", "p1", source="dry_run") == []
    run = store.get_run("paper:p1")
    assert run is not None and run["gap_slots"] == [_slot_text(_SLOTS[0])]

    assert _run_worker(db, models, shadow_observed, _SLOTS[7]).returncode == 0
    from quantide.service.model_store import ModelArtifact, ModelStore

    ModelStore(models).save(
        key=_MODEL_KEY,
        model={"generation": "B", "asset": _ASSET},
        metadata=ModelArtifact(
            model_key=_MODEL_KEY,
            strategy_name="ShadowLedgerWorker",
            config_hash="actual-B",
            train_end="2024-01-03",
            effective_from="2024-01-03",
            pipeline_version="pipeline-B",
        ),
    )
    latest, _ = ModelStore(models).load(_MODEL_KEY)
    assert latest == {"generation": "B", "asset": _ASSET}

    assert (
        _run_worker(db, models, shadow_observed, _SLOTS[11], missing=[_SLOTS[10]]).returncode == 0
    )
    run = store.get_run("paper:p1")
    assert run is not None and run["gap_slots"] == [_slot_text(_SLOTS[10])]
    assert _run_worker(db, models, shadow_observed, _SLOTS[15]).returncode == 0

    _assert_store_rows(db, "dry_run", shadow_observed)
    _assert_intents(db)
    _assert_models(models, actual_before, shadow_observed)
    actual_after = store.list_bars("paper:p1", "p1", source="actual", bar_interval="30m")
    assert actual_after == actual_before


def test_missing_actual_fact_is_explicit_in_tracking_output(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "missing-actual.db"
    models = tmp_path / "models"
    actual_observed = tmp_path / "actual.jsonl"
    shadow_observed = tmp_path / "shadow.jsonl"
    assert _run_actual(db, models, actual_observed).returncode == 0
    assert _run_worker(db, models, shadow_observed, _SLOTS[15]).returncode == 0
    connection = sqlite3.connect(db)
    try:
        connection.execute(
            "DELETE FROM strategy_tracking_bars WHERE runtime_id='paper:p1' "
            "AND bar_slot=? AND source='actual'",
            (_slot_text(_SLOTS[15]),),
        )
        connection.commit()
    finally:
        connection.close()

    from fasthtml.common import to_xml

    import quantide.web.pages.tracking as tracking
    from quantide.service.strategy_tracking import TrackingStore

    store = TrackingStore(db)
    assert store.get_bar("paper:p1", _slot_text(_SLOTS[15]), source="actual") is None
    assert store.get_bar("paper:p1", _slot_text(_SLOTS[15]), source="dry_run") is not None
    monkeypatch.setattr(tracking, "tracking_store", store)
    html = to_xml(tracking._intraday_section("p1", store.get_run("paper:p1")))
    assert "实际缺失 1 个" in html
    assert "实际缺失" in html.split("实际净值", 1)[-1]


def test_forming_bucket_is_provided_but_not_consumed() -> None:
    from quantide.service.shadow_intraday import load_closed_bar_frame

    closed = _SLOTS[3]
    rows = [
        {
            "date": [closed, closed + datetime.timedelta(minutes=30)],
            "asset": [_ASSET, _ASSET],
            "open": [10.0, 99.0],
            "high": [10.0, 99.0],
            "low": [10.0, 99.0],
            "close": [10.0, 99.0],
            "volume": [1_000_000.0, 1_000_000.0],
            "amount": [10_000_000.0, 99_000_000.0],
        }
    ]
    frame = pl.concat([pl.DataFrame(row) for row in rows])

    class _Minute:
        @staticmethod
        def get_bars_in_range(*_args, **_kwargs):
            return frame

    loaded = load_closed_bar_frame(closed, [_ASSET], minute_model=_Minute())
    assert loaded is not None
    assert loaded["date"].to_list() == [closed]
    assert loaded["close"].to_list() == [10.0]


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL evidence is POSIX-only")
@pytest.mark.parametrize("kill_stage", ["before", "after"])
def test_sigkill_before_or_after_commit_resumes_without_duplicate_fill(
    tmp_path: Path, kill_stage: str
) -> None:
    db = tmp_path / f"ledger-{kill_stage}.db"
    models = tmp_path / "models"
    actual_observed = tmp_path / "actual.jsonl"
    shadow_observed = tmp_path / f"observed-{kill_stage}.jsonl"
    assert _run_actual(db, models, actual_observed).returncode == 0
    assert _run_worker(db, models, shadow_observed, _SLOTS[0]).returncode == 0

    killed = _run_worker(
        db,
        models,
        shadow_observed,
        _SLOTS[1],
        kill_slot=_SLOTS[1],
        kill_stage=kill_stage,
    )
    assert killed.returncode == -9, killed.stderr
    # The strategy and its queued sell ran before the injected boundary. The
    # before case therefore exercises replay effects awaiting the SQL commit.
    assert _slot_text(_SLOTS[1]) in _observations(shadow_observed)
    connection = sqlite3.connect(db)
    try:
        queued = connection.execute(
            "SELECT COUNT(*) FROM strategy_next_open_intents WHERE runtime_id=? AND signal_bar=?",
            ("paper:p1:shadow", _SLOTS[1].isoformat()),
        ).fetchone()[0]
    finally:
        connection.close()
    assert queued == 1
    from quantide.service.strategy_tracking import TrackingStore

    killed_row = TrackingStore(db).get_bar("paper:p1", _slot_text(_SLOTS[1]), source="dry_run")
    if kill_stage == "before":
        assert killed_row is None
    else:
        assert killed_row is not None

    assert _run_worker(db, models, shadow_observed, _SLOTS[7]).returncode == 0
    assert _run_worker(db, models, shadow_observed, _SLOTS[15]).returncode == 0

    _assert_store_rows(db, "dry_run", shadow_observed)
    from quantide.service.strategy_tracking import TrackingStore

    store = TrackingStore(db)
    actual_bar = store.get_bar("paper:p1", _slot_text(_SLOTS[1]), source="actual")
    assert actual_bar is not None and actual_bar["model_ref"]
    # The committed shadow row is write-once: a replay of the same slot after the
    # crash cannot insert a duplicate fill or overwrite created_at/observed facts.
    committed = store.get_bar("paper:p1", _slot_text(_SLOTS[1]), source="dry_run")
    assert committed is not None
    replayed = _run_worker(db, models, shadow_observed, _SLOTS[1], missing=[_SLOTS[0]])
    assert replayed.returncode == 0, replayed.stderr
    replay_bar = store.get_bar("paper:p1", _slot_text(_SLOTS[1]), source="dry_run")
    assert replay_bar is not None and replay_bar["created_at"] == committed["created_at"]
    _assert_store_rows(db, "dry_run", shadow_observed)


def test_missing_actual_model_ref_does_not_fall_back_to_latest_b(tmp_path: Path) -> None:
    db = tmp_path / "missing-model.db"
    models = tmp_path / "models"
    actual_observed = tmp_path / "actual.jsonl"
    shadow_observed = tmp_path / "shadow.jsonl"
    assert _run_actual(db, models, actual_observed).returncode == 0
    from quantide.service.model_store import ModelArtifact, ModelStore
    from quantide.service.strategy_tracking import TrackingStore

    actual = TrackingStore(db).get_bar("paper:p1", _slot_text(_SLOTS[0]), source="actual")
    assert actual is not None
    model_ref = str(actual["model_ref"])
    ModelStore(models).save(
        key=_MODEL_KEY,
        model={"generation": "B", "asset": _ASSET},
        metadata=ModelArtifact(
            model_key=_MODEL_KEY,
            strategy_name="ShadowLedgerWorker",
            config_hash="actual-B",
            train_end="2024-01-03",
            effective_from="2024-01-03",
            pipeline_version="pipeline-B",
        ),
    )
    key, digest = model_ref.rsplit("/", 1)
    (models / key / "versions" / f"{digest}.pkl").unlink()

    result = _run_worker(db, models, shadow_observed, _SLOTS[0])
    assert result.returncode == 0, result.stderr
    assert TrackingStore(db).list_bars("paper:p1", "p1", source="dry_run") == []
    errors = [
        json.loads(line)
        for line in shadow_observed.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert any("not loadable" in str(item.get("error", "")) for item in errors)
