"""Factor tracking profile and snapshot tests."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import threading

import polars as pl
import pytest

from quantide.service import factor_tracking
from quantide.service.factor_runs import FactorRunStore, RunBudget, RunFence
from quantide.service.factor_tracking_summary import summary_path, tracking_summary

_DAYS = [dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(12)]

_SOURCE = {
    "source_token": [1.0, "2024-01-13"],
    "source_market_version": "market-1",
    "source_calendar_version": "calendar-1",
    "source_universe_version": "universe-1",
    "source_dependency_version": "dependency-1",
}


def _source(**overrides):
    values = dict(_SOURCE)
    values.update(overrides)
    return values


def _days(start, end):
    return tuple(day for day in _DAYS if start <= day <= end)


@pytest.fixture(autouse=True)
def isolated_tracking(monkeypatch, tmp_path):
    monkeypatch.setattr(factor_tracking, "_root", lambda: tmp_path / "factor-tracking")
    monkeypatch.setattr(factor_tracking, "_REFRESHING", set())
    monkeypatch.setattr(factor_tracking, "_PENDING_REFRESH", set())
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: _source())
    monkeypatch.setattr(factor_tracking, "trading_days", _days)
    monkeypatch.setattr(factor_tracking, "_latest_market_day", lambda: None)
    yield


def _panel() -> pl.DataFrame:
    days = _DAYS
    rows = []
    for asset_index in range(120):
        asset = f"{asset_index:06d}"
        for day_index, day in enumerate(days):
            factor = asset_index + day_index * 0.01
            price = 10 + asset_index * 0.1 + day_index * 0.05
            rows.append(
                {
                    "asset": asset,
                    "date": day,
                    "bias_5": factor,
                    "rs_board_5d": factor * 2,
                    "open": price,
                    "close": price * 1.001,
                }
            )
    return pl.DataFrame(rows)


def test_default_profile_and_normalization() -> None:
    profile = factor_tracking.load_profile("bias_5")
    assert profile.revision == 0
    assert profile.lookback == "3y"
    assert profile.primary_holding_days == 5
    assert profile.comparison_holding_days == (1, 3, 5)
    assert factor_tracking.normalize_holdings(3, [5, 5, 1]) == (1, 3, 5)
    with pytest.raises(ValueError):
        factor_tracking.normalize_holdings(1, [2, 3, 5, 10, 20])


def test_save_profile_increments_revision_and_reloads() -> None:
    saved = factor_tracking.save_profile(
        "bias_5",
        lookback="5y",
        primary_holding_days=10,
        comparison_holding_days=[1, 10],
        price_field="close",
        enabled=False,
    )
    assert saved.revision == 1
    loaded = factor_tracking.load_profile("bias_5")
    assert loaded == saved
    assert loaded.enabled is False
    assert factor_tracking.tracking_view("bias_5").status == "disabled"


def test_refresh_writes_snapshot_with_horizons(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    state = factor_tracking.refresh_factor("bias_5")

    assert state["current"] is not None
    snapshot = state["current"]
    assert snapshot["factor_id"] == "bias_5"
    assert snapshot["status"] == "ok"
    assert snapshot["primary_holding_days"] == 5
    assert snapshot["primary_metrics"]["rank_ic"]["n_days"] > 0
    assert set(snapshot["horizon_metrics"]) == {"1", "3", "5"}
    assert snapshot["common_cohort"]["n_days"] > 0
    assert snapshot["coverage"]["latest_symbols"] == 120
    assert snapshot["coverage"]["sufficient"] is True
    assert snapshot["data_cutoff"] == "2024-01-13"
    assert state["last_attempt"]["status"] == "succeeded"
    assert factor_tracking.tracking_view("bias_5").status == "normal"


def test_group_refresh_shares_one_panel(monkeypatch) -> None:
    calls = []

    def _load(start, end):
        calls.append((start, end))
        return _panel()

    monkeypatch.setattr(factor_tracking, "load_factor_panel", _load)
    factor_tracking._refresh_group(["bias_5", "rs_board_5d"], "3y")

    assert len(calls) == 1
    assert factor_tracking.tracking_view("bias_5").status == "normal"
    assert factor_tracking.tracking_view("rs_board_5d").status == "normal"


def test_failed_refresh_keeps_previous_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    before = factor_tracking.load_state("bias_5")["current"]

    def _fail(start, end):
        raise RuntimeError("market data unavailable")

    monkeypatch.setattr(factor_tracking, "load_factor_panel", _fail)
    state = factor_tracking.refresh_factor("bias_5")

    assert state["current"] == before
    assert state["last_attempt"]["status"] == "failed"
    assert factor_tracking.tracking_view("bias_5").status == "failed"


def test_profile_change_during_refresh_does_not_publish(monkeypatch) -> None:
    changed = False

    def _panel_then_save(start, end):
        nonlocal changed
        if not changed:
            changed = True
            factor_tracking.save_profile(
                "bias_5",
                lookback="1y",
                primary_holding_days=5,
                comparison_holding_days=[1, 3, 5],
                price_field="open",
            )
        return _panel()

    monkeypatch.setattr(factor_tracking, "load_factor_panel", _panel_then_save)
    state = factor_tracking.refresh_factor("bias_5")

    assert state["current"] is None
    assert state["last_attempt"]["status"] == "superseded"
    assert factor_tracking.load_profile("bias_5").revision == 1


def test_profile_change_keeps_latest_result_visible_for_automatic_refresh(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    factor_tracking.save_profile(
        "bias_5",
        lookback="1y",
        primary_holding_days=5,
        comparison_holding_days=[1, 3, 5],
        price_field="open",
    )

    view = factor_tracking.tracking_view("bias_5")
    assert view.status == "normal"
    assert isinstance(view.current, dict)
    assert factor_tracking._config_changed(view.profile, view.current)


def test_snapshot_records_data_and_calendar_fingerprints(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    state = factor_tracking.refresh_factor("bias_5")

    snapshot = state["current"]
    assert snapshot["data_hash"]
    assert snapshot["universe_hash"]
    assert snapshot["calendar_version"].startswith("2024-01-02:2024-01-13:12:")
    assert snapshot["input_revision"] == 1
    assert snapshot["dependency_hash"] == "dependency-1"
    assert snapshot["source_market_version"] == "market-1"
    assert snapshot["source_calendar_version"] == "calendar-1"
    assert snapshot["source_universe_version"] == "universe-1"
    assert snapshot["panel_start"]
    assert snapshot["evaluation_start"]
    assert snapshot["source_kind"] == "tracking"
    assert snapshot["coverage"]["coverage_date"] == "2024-01-13"

    revised = _panel().with_columns(
        pl.when(pl.col("asset") == "000001")
        .then(pl.col("open") + 0.01)
        .otherwise(pl.col("open"))
        .alias("open")
    )
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: revised)
    updated = factor_tracking.refresh_factor("bias_5")["current"]
    assert updated["data_hash"] != snapshot["data_hash"]
    assert updated["idempotency_key"] != snapshot["idempotency_key"]


def test_reset_keeps_monotonic_revision_and_supersedes_old_runs(monkeypatch) -> None:
    profile = factor_tracking.default_profile("bias_5")
    assert profile.revision == 0
    factor_tracking.save_profile(
        "bias_5",
        lookback="5y",
        primary_holding_days=5,
        comparison_holding_days=[1, 3, 5],
        price_field="open",
    )
    reset = factor_tracking.reset_profile("bias_5")
    assert reset.revision == 2
    assert reset.lookback == profile.lookback
    assert reset.comparison_holding_days == profile.comparison_holding_days

    stale = factor_tracking.TrackingProfile(
        factor_id="bias_5",
        revision=1,
        enabled=True,
        lookback="5y",
        primary_holding_days=5,
        comparison_holding_days=(1, 3, 5),
        price_field="open",
        source="user",
    )
    snapshot = {
        "status": "ok",
        "profile_revision": 1,
        "profile_hash": factor_tracking._profile_hash(stale),
    }
    state = factor_tracking._publish_snapshot(
        "bias_5", stale, snapshot, dt.datetime.now(dt.UTC), "run", "start"
    )
    assert state["current"] is None
    assert state["last_attempt"]["status"] == "superseded"


def test_lost_run_ownership_blocks_snapshot_publication() -> None:
    profile = factor_tracking.default_profile("bias_5")
    snapshot = {
        "status": "ok",
        "profile_revision": profile.revision,
        "profile_hash": factor_tracking._profile_hash(profile),
        "data_cutoff": "2024-01-13",
        "idempotency_key": "fenced",
    }
    state = factor_tracking._publish_snapshot(
        "bias_5",
        profile,
        snapshot,
        dt.datetime.now(dt.UTC),
        "run",
        "start",
        fence=lambda: False,
    )
    assert state["current"] is None
    assert state["last_attempt"] is None


def test_revoked_owner_cannot_publish_after_fence_pause(tmp_path) -> None:
    root = tmp_path / "factor-tracking"
    store = FactorRunStore(root / "runs.sqlite")
    profile = factor_tracking.default_profile("bias_5")
    run_id = store.enqueue(
        ["bias_5"],
        lookback=profile.lookback,
        profile_revisions={"bias_5": profile.revision},
        source_revision=0,
        source_versions={},
        budget=RunBudget(),
    )[0]
    assert store.claim("old", budget=RunBudget()) is not None
    ready = threading.Event()
    resume = threading.Event()

    class PausingFence(RunFence):
        def __call__(self) -> bool:
            valid = super().__call__()
            if not ready.is_set():
                ready.set()
                resume.wait(2)
            return valid

    fence = PausingFence(store, run_id, "old")
    snapshot = {
        "status": "ok",
        "profile_revision": profile.revision,
        "profile_hash": factor_tracking._profile_hash(profile),
        "data_cutoff": "2024-01-13",
        "idempotency_key": "racing",
    }
    published: dict[str, object] = {}

    def publish() -> None:
        state = factor_tracking._publish_snapshot(
            "bias_5",
            profile,
            snapshot,
            dt.datetime.now(dt.UTC),
            run_id,
            "start",
            fence=fence,
        )
        published["current"] = state.get("current")

    thread = threading.Thread(target=publish)
    thread.start()
    assert ready.wait(2)
    store.release_owner("old")
    assert store.claim("new", budget=RunBudget()) is not None
    resume.set()
    thread.join(3)
    assert not store.owns(run_id, "old")
    assert published["current"] is None


def test_insufficient_snapshot_does_not_replace_success(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    before = factor_tracking.load_state("bias_5")["current"]

    profile = factor_tracking.load_profile("bias_5")
    insufficient = {
        "status": "insufficient",
        "profile_revision": profile.revision,
        "profile_hash": factor_tracking._profile_hash(profile),
        "data_cutoff": "2024-01-13",
        "idempotency_key": "insufficient-run",
    }
    state = factor_tracking._publish_snapshot(
        "bias_5", profile, insufficient, dt.datetime.now(dt.UTC), "run", "start"
    )
    assert state["current"] == before
    assert state["last_attempt"]["status"] == "insufficient"
    view = factor_tracking.tracking_view("bias_5")
    assert view.status == "insufficient"
    assert view.current == before


def test_older_data_snapshot_cannot_replace_newer_current() -> None:
    profile = factor_tracking.default_profile("bias_5")
    newer = {
        "status": "ok",
        "profile_revision": profile.revision,
        "profile_hash": factor_tracking._profile_hash(profile),
        "data_cutoff": "2024-01-13",
        "idempotency_key": "newer",
    }
    older = {
        "status": "ok",
        "profile_revision": profile.revision,
        "profile_hash": factor_tracking._profile_hash(profile),
        "data_cutoff": "2024-01-10",
        "idempotency_key": "older",
    }
    now = dt.datetime.now(dt.UTC)
    factor_tracking._publish_snapshot("bias_5", profile, newer, now, "run-new", "start")
    state = factor_tracking._publish_snapshot("bias_5", profile, older, now, "run-old", "start")
    assert state["current"] == newer
    assert state["last_attempt"]["status"] == "superseded"


def test_revised_market_same_cutoff_marks_snapshot_stale(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")

    monkeypatch.setattr(
        factor_tracking,
        "_source_versions",
        lambda **_: _source(source_token=[2.0, "2024-01-13"], source_market_version="market-2"),
    )
    assert factor_tracking.tracking_view("bias_5").status == "stale_data"


def test_manifest_revision_tracks_raw_sources_not_windows(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    first = factor_tracking.load_state("bias_5")["current"]
    assert first["input_revision"] == 1

    factor_tracking.refresh_factor("bias_5")
    repeated = factor_tracking.load_state("bias_5")["current"]
    assert repeated["input_revision"] == 1
    assert factor_tracking._read_manifest()["revision"] == 1

    monkeypatch.setattr(
        factor_tracking,
        "_source_versions",
        lambda **_: _source(source_token=[2.0, "2024-01-13"], source_market_version="market-2"),
    )
    factor_tracking.refresh_factor("bias_5")
    second = factor_tracking.load_state("bias_5")["current"]
    assert second["input_revision"] == 2
    assert factor_tracking._read_manifest()["revision"] == 2


def test_older_input_token_cannot_replace_newer_snapshot() -> None:
    profile = factor_tracking.default_profile("bias_5")
    now = dt.datetime.now(dt.UTC)
    newer = {
        "status": "ok",
        "profile_revision": profile.revision,
        "profile_hash": factor_tracking._profile_hash(profile),
        "data_cutoff": "2024-01-13",
        "source_token": [2.0, "2024-01-13"],
        "data_hash": "new",
        "universe_hash": "u",
        "calendar_version": "c",
        "idempotency_key": "newer",
    }
    older = {
        **newer,
        "source_token": [1.0, "2024-01-13"],
        "data_hash": "old",
        "idempotency_key": "older",
    }
    factor_tracking._publish_snapshot("bias_5", profile, newer, now, "run-new", "start")
    state = factor_tracking._publish_snapshot("bias_5", profile, older, now, "run-old", "start")
    assert state["current"] == newer
    assert state["last_attempt"]["status"] == "superseded"


def test_old_source_fields_cannot_replace_newer_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")

    newer_source = _source(source_token=[2.0, "2024-01-14"], source_market_version="market-2")
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: newer_source)
    factor_tracking.refresh_factor("bias_5")
    newer = factor_tracking.load_state("bias_5")["current"]

    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: _source())
    state = factor_tracking.refresh_factor("bias_5")
    assert state["current"] == newer
    assert state["last_attempt"]["status"] == "superseded"


def test_input_advance_during_refresh_queues_new_run(monkeypatch) -> None:
    sources = iter(
        [
            _source(),
            _source(source_token=[2.0, "2024-01-13"], source_market_version="market-2"),
        ]
    )
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: next(sources))
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    assert "bias_5" in factor_tracking._PENDING_REFRESH


def test_two_lookbacks_share_one_raw_source_revision(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    monkeypatch.setattr(
        factor_tracking,
        "market_now",
        lambda: dt.datetime(2024, 1, 13, 18, tzinfo=dt.UTC),
    )
    factor_tracking.save_profile(
        "rs_board_5d",
        lookback="1y",
        primary_holding_days=5,
        comparison_holding_days=[1, 3, 5],
        price_field="open",
    )
    factor_tracking._refresh_group(["bias_5"], "3y")
    factor_tracking._refresh_group(["rs_board_5d"], "1y")
    assert factor_tracking.tracking_view("bias_5").status == "normal"
    assert factor_tracking.tracking_view("rs_board_5d").status == "normal"
    assert factor_tracking._read_manifest()["revision"] == 1

    factor_tracking._refresh_group(["bias_5"], "3y")
    factor_tracking._refresh_group(["rs_board_5d"], "1y")
    assert factor_tracking.tracking_view("bias_5").status == "normal"
    assert factor_tracking.tracking_view("rs_board_5d").status == "normal"
    assert factor_tracking._read_manifest()["revision"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_calendar_version", "calendar-2"),
        ("source_universe_version", "universe-2"),
        ("source_dependency_version", "dependency-2"),
    ],
)
def test_each_standalone_source_change_marks_stale(monkeypatch, field, value) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: _source(**{field: value}))
    assert factor_tracking.tracking_view("bias_5").status == "stale_data"


def test_unavailable_sources_are_never_reported_normal(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    unavailable = {
        "source_token": None,
        "source_market_version": None,
        "source_calendar_version": None,
        "source_universe_version": None,
        "source_dependency_version": None,
    }
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: unavailable)
    view = factor_tracking.tracking_view("bias_5")
    assert view.status == "source_unavailable"
    assert view.current is not None

    state = factor_tracking.refresh_factor("bias_5")
    assert state["last_attempt"]["status"] == "source_unavailable"
    assert state["current"] == view.current


def test_group_source_advance_queues_every_active_factor(monkeypatch) -> None:
    sources = iter(
        [
            _source(),
            _source(source_token=[2.0, "2024-01-13"], source_market_version="market-2"),
        ]
    )
    monkeypatch.setattr(factor_tracking, "_source_versions", lambda **_: next(sources))
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking._refresh_group(["bias_5", "rs_board_5d"], "3y")
    assert {"bias_5", "rs_board_5d"} <= factor_tracking._PENDING_REFRESH


def test_interrupted_attempt_with_latest_snapshot_requires_backfill(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    state = factor_tracking.load_state("bias_5")
    state["last_attempt"] = {"status": "interrupted"}
    factor_tracking._write_state("bias_5", state)
    assert factor_tracking._needs_backfill()


def test_stale_market_data_is_reported_without_hiding_success(monkeypatch) -> None:
    monkeypatch.setattr(factor_tracking, "load_factor_panel", lambda start, end: _panel())
    factor_tracking.refresh_factor("bias_5")
    monkeypatch.setattr(factor_tracking, "_latest_market_day", lambda: dt.date(2024, 1, 15))
    view = factor_tracking.tracking_view("bias_5")
    assert view.status == "stale_data"
    assert view.current is not None


def test_recover_marks_running_attempt_as_interrupted() -> None:
    factor_tracking._write_state(
        "bias_5",
        {"current": None, "last_attempt": {"status": "running", "run_id": "old"}},
    )
    factor_tracking._recover_interrupted()
    attempt = factor_tracking.load_state("bias_5")["last_attempt"]
    assert attempt["status"] == "interrupted"
    assert attempt["run_id"] == "old"


def test_tracking_service_registers_single_daily_job(monkeypatch) -> None:
    class _Scheduler:
        def __init__(self):
            self.jobs = {}
            self.removed = []

        def add_job(self, func, trigger, **kwargs):
            self.jobs[kwargs["id"]] = (func, trigger, kwargs)

        def remove_job(self, job_id):
            self.removed.append(job_id)
            self.jobs.pop(job_id, None)

    scheduler = _Scheduler()
    monkeypatch.setattr(factor_tracking, "scheduler", scheduler)
    monkeypatch.setattr(factor_tracking, "_startup_catch_up", lambda: None)
    service = factor_tracking.FactorTrackingService()
    service.start()
    service.start()
    assert list(scheduler.jobs) == ["factor_tracking_daily"]
    assert scheduler.jobs["factor_tracking_daily"][1] == "cron"
    service.stop()
    assert scheduler.removed == ["factor_tracking_daily"]


def test_concurrent_saves_produce_monotonic_revisions() -> None:
    barrier = threading.Barrier(2)
    revisions: list[int] = []

    def worker() -> None:
        barrier.wait()
        saved = factor_tracking.save_profile(
            "bias_5",
            lookback="1y",
            primary_holding_days=5,
            comparison_holding_days=[1, 3, 5],
            price_field="open",
        )
        revisions.append(saved.revision)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(revisions) == [1, 2]
    assert factor_tracking.load_profile("bias_5").revision == 2


def test_cross_process_saves_serialize_revisions(tmp_path) -> None:
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from quantide.service.factor_profiles import save_profile\n"
        "profile = save_profile(\n"
        "    Path(sys.argv[1]), 'bias_5', lookback='1y', primary_holding_days=5,\n"
        "    comparison_holding_days=[1, 3, 5], price_field='open')\n"
        "print(profile.revision)\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [process.communicate(timeout=30) for process in processes]
    assert all(process.returncode == 0 for process in processes), outputs
    revisions = sorted(int(stdout.strip()) for stdout, _ in outputs)
    assert revisions == [1, 2]
    from quantide.service.factor_profiles import load_profile

    assert load_profile(tmp_path, "bias_5").revision == 2


def test_invalid_profile_file_falls_back_to_defaults() -> None:
    path = factor_tracking._profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bias_5": {"revision": 1}}), encoding="utf-8")
    profile = factor_tracking.load_profile("bias_5")
    assert profile == factor_tracking.default_profile("bias_5")


def test_tracking_summary_keeps_overview_fields_only() -> None:
    current = {
        "status": "ok",
        "data_cutoff": "2024-01-13",
        "computed_at": "2024-01-14T09:00:00",
        "profile_revision": 0,
        "profile_hash": "hash-1",
        "factor_version": "factor-1",
        "statistics_version": "stats-1",
        "input_revision": 3,
        **_source(),
        "primary_metrics": {
            "holding_days": 5,
            "rank_ic": {
                "mean": 0.12,
                "t_naive": 2.4,
                "n_days": 120,
                "daily_ic": [1, 2, 3],
            },
            "deciles": {
                "d1_mean_common": 0.01,
                "d10_mean_common": 0.03,
                "d1_minus_d10": -0.02,
                "buckets": [{"bucket": 1, "mean_forward": 0.01}],
            },
            "diagnostics": {"as_of_date": "2024-01-12", "n_rows": 999},
        },
        "common_cohort": {"daily": [1, 2, 3]},
    }
    factor_tracking._write_state(
        "bias_5", {"current": current, "last_attempt": {"status": "succeeded"}}
    )

    view = tracking_summary(
        "bias_5",
        source=_source(),
        latest_day=dt.date(2024, 1, 13),
        revision=3,
    )

    assert view.current is not None
    assert view.current["primary_metrics"]["rank_ic"] == {
        "mean": 0.12,
        "t_naive": 2.4,
        "n_days": 120,
    }
    assert view.current["primary_metrics"]["diagnostics"] == {"as_of_date": "2024-01-12"}
    assert "common_cohort" not in view.current
    assert set(view.current["primary_metrics"]) == {
        "holding_days",
        "rank_ic",
        "deciles",
        "diagnostics",
    }
    assert view.status == "normal"
    summary_file = summary_path(factor_tracking._root(), "bias_5")
    assert summary_file.exists()
    assert len(summary_file.read_text(encoding="utf-8")) < len(
        factor_tracking._state_path("bias_5").read_text(encoding="utf-8")
    )
