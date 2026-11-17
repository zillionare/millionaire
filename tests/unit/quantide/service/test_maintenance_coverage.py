"""Maintenance must recover earlier dataset gaps instead of trusting the latest daily bar."""

import datetime

from quantide.service.maintenance import maintenance_start


def test_minute_gap_is_not_hidden_by_newer_daily_bars():
    history = datetime.date(2024, 1, 1)
    assert maintenance_start(history, [datetime.date(2024, 6, 5),
                                       datetime.date(2024, 6, 4),
                                       datetime.date(2024, 2, 1)]) == datetime.date(2024, 2, 1)


def test_absent_dataset_restarts_from_user_history_floor():
    history = datetime.date(2024, 1, 1)
    assert maintenance_start(history, [datetime.date(2024, 6, 5), None]) == history
    assert maintenance_start(history, [datetime.date(2020, 1, 1)]) == history


def test_maintain_data_uses_epoch_and_stops_on_pause(monkeypatch) -> None:
    import datetime as dt
    from types import SimpleNamespace

    from quantide.service import maintenance
    from quantide.service.data_backfill import BackfillWindow

    windows = (
        BackfillWindow(dt.date(2025, 10, 1), dt.date(2025, 10, 31), "historical", ("daily_bars",)),
        BackfillWindow(dt.date(2025, 9, 1), dt.date(2025, 9, 30), "historical", ("daily_bars",)),
    )
    seen = []
    refreshed = []
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(epoch=dt.date(2005, 1, 1)))
    monkeypatch.setattr(maintenance, "market_today", lambda: dt.datetime(2026, 11, 13, 18, 30))
    monkeypatch.setattr(
        "quantide.service.minute_backfill._minute_history_end",
        lambda _today: dt.date(2026, 11, 13),
    )
    monkeypatch.setattr(maintenance, "_backfill_windows", lambda epoch, end: windows)
    monkeypatch.setattr(
        maintenance,
        "_run_backfill_window",
        lambda window: seen.append(window.start) or "quota_exhausted",
    )
    monkeypatch.setattr(maintenance, "_trigger_factor_refresh", lambda: refreshed.append(True))

    message = maintenance.maintain_data()

    assert seen == [dt.date(2025, 10, 1)]
    assert "已暂停" in message
    assert refreshed == []


def test_maintain_data_continues_after_unfillable_window(monkeypatch) -> None:
    import datetime as dt
    from types import SimpleNamespace

    from quantide.service import maintenance
    from quantide.service.data_backfill import BackfillWindow

    windows = (
        BackfillWindow(dt.date(2025, 10, 1), dt.date(2025, 10, 31), "historical", ("daily_bars",)),
        BackfillWindow(dt.date(2025, 9, 1), dt.date(2025, 9, 30), "historical", ("daily_bars",)),
    )
    outcomes = iter(["skip", "ok"])
    refreshed = []
    monkeypatch.setattr(maintenance, "get_settings", lambda: SimpleNamespace(epoch=dt.date(2005, 1, 1)))
    monkeypatch.setattr(maintenance, "market_today", lambda: dt.datetime(2026, 11, 13, 18, 30))
    monkeypatch.setattr(
        "quantide.service.minute_backfill._minute_history_end",
        lambda _today: dt.date(2026, 11, 13),
    )
    monkeypatch.setattr(maintenance, "_backfill_windows", lambda epoch, end: windows)
    monkeypatch.setattr(maintenance, "_run_backfill_window", lambda window: next(outcomes))
    monkeypatch.setattr(maintenance, "_trigger_factor_refresh", lambda: refreshed.append(True))

    message = maintenance.maintain_data()

    assert "完成 1 个窗口" in message
    assert refreshed == [True]


def test_run_backfill_window_pauses_before_request_when_budget_exhausted(monkeypatch) -> None:
    import datetime as dt

    from quantide.data.fetchers.budget import BudgetDecision
    from quantide.service import maintenance
    from quantide.service.data_backfill import BackfillWindow

    class _Budget:
        def acquire(self):
            return BudgetDecision.EXHAUSTED

    class _Sync:
        created = []

        def create_task(self, params):
            self.created.append(params)

    sync = _Sync()
    monkeypatch.setattr(maintenance, "_source_budget", lambda: _Budget())
    monkeypatch.setattr(maintenance, "data_sync_service", sync)

    outcome = maintenance._run_backfill_window(
        BackfillWindow(dt.date(2025, 1, 2), dt.date(2025, 1, 31), "historical", ("daily_bars",))
    )

    assert outcome == "quota_exhausted"
    assert sync.created == []


def test_run_backfill_window_delays_before_request_when_rate_limited(monkeypatch) -> None:
    import datetime as dt

    from quantide.data.fetchers.budget import BudgetDecision
    from quantide.service import maintenance
    from quantide.service.data_backfill import BackfillWindow

    class _Budget:
        def acquire(self):
            return BudgetDecision.DELAY

    class _Sync:
        created = []

        def create_task(self, params):
            self.created.append(params)

    sync = _Sync()
    monkeypatch.setattr(maintenance, "_source_budget", lambda: _Budget())
    monkeypatch.setattr(maintenance, "data_sync_service", sync)

    outcome = maintenance._run_backfill_window(
        BackfillWindow(dt.date(2025, 1, 2), dt.date(2025, 1, 31), "historical", ("daily_bars",))
    )

    assert outcome == "rate_limited"
    assert sync.created == []
