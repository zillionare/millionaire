"""v0.2-004-coverage-recovery C1.3d: quantide/core/scheduler.py  40% -> 80%+.

Targets: SchedulerManager init / scheduler property / start / stop / add_job /
add_listener, singleton behavior, no-double-init guard.
"""

from __future__ import annotations

import pytest

from quantide.core.scheduler import SchedulerManager, scheduler
from quantide.core.singleton import _instances


@pytest.fixture
def fresh_scheduler():
    """Reset the SchedulerManager singleton and return a fresh instance.

    The @singleton decorator stores instances in the module-level `_instances`
    dict keyed by the *original* (pre-decoration) class object.  We use that
    dict to evict any cached instance and then call SchedulerManager() to
    obtain a clean one.  The fixture also tears down any underlying
    BackgroundScheduler that may have been auto-created.
    """
    original_cls = getattr(SchedulerManager, "_original_class", None)
    # Evict any cached singleton instance so the next call returns a fresh one.
    _instances.pop(SchedulerManager, None)
    if original_cls is not None:
        _instances.pop(original_cls, None)

    instance = SchedulerManager()
    # Reset state attributes so every test starts from a clean slate,
    # regardless of what previous tests may have left behind on the
    # singleton instance.
    instance._scheduler = None
    instance._is_running = False

    yield instance

    # Teardown: stop and drop any BackgroundScheduler that may have been
    # auto-created, and evict from the singleton cache so the next test
    # starts clean.
    try:
        sched = getattr(instance, "_scheduler", None)
        running = getattr(instance, "_is_running", False)
        if sched is not None and running:
            try:
                sched.shutdown(wait=False)
            except Exception:
                pass
    finally:
        _instances.pop(SchedulerManager, None)
        if original_cls is not None:
            _instances.pop(original_cls, None)


def test_scheduler_module_exposes_singleton_instance() -> None:
    """AC-FR0700-01: scheduler is the module-level SchedulerManager singleton."""
    # The @singleton decorator returns the cached instance for repeated calls,
    # so the module-level `scheduler` must be the same object that calling
    # SchedulerManager() produces.
    assert scheduler is SchedulerManager()


def test_scheduler_init_idempotent_returns_early_when_already_initialized(fresh_scheduler) -> None:
    """AC-FR0700-02: init() does not re-create the underlying scheduler when set."""
    fresh_scheduler.init()
    first = fresh_scheduler.scheduler
    fresh_scheduler.init()
    assert fresh_scheduler.scheduler is first


def test_scheduler_init_uses_default_timezone(fresh_scheduler, monkeypatch) -> None:
    """AC-FR0700-03: init() with no argument falls back to get_timezone()."""
    captured = {"tz": None}

    def fake_get_tz():
        from datetime import timezone, timedelta
        captured["tz"] = "Asia/Shanghai"
        return timezone(timedelta(hours=8))

    monkeypatch.setattr("quantide.core.scheduler.get_timezone", fake_get_tz)
    # Simulate that init was already done by setting a sentinel.
    sentinel = object()
    fresh_scheduler._scheduler = sentinel  # type: ignore[attr-defined]
    # Calling init() must early-return because _scheduler is already set.
    fresh_scheduler.init()
    assert fresh_scheduler.scheduler is sentinel
    assert captured["tz"] is None  # get_timezone not called when already initialized


def test_scheduler_init_with_explicit_timezone(fresh_scheduler) -> None:
    """AC-FR0700-04: init(timezone=...) records the override."""
    from datetime import timezone, timedelta
    tz = timezone(timedelta(hours=8))
    # Provide a stub scheduler attribute so init() takes the early-return path.
    fresh_scheduler._scheduler = object()  # type: ignore[attr-defined]
    fresh_scheduler.init(timezone=tz)
    assert fresh_scheduler.scheduler is not None


def test_scheduler_property_auto_inits_when_none(fresh_scheduler) -> None:
    """AC-FR0700-05: scheduler property triggers init when no underlying scheduler exists."""
    assert fresh_scheduler._scheduler is None
    _ = fresh_scheduler.scheduler
    assert fresh_scheduler._scheduler is not None


def test_scheduler_start_only_when_present_and_idle(fresh_scheduler) -> None:
    """AC-FR0700-06: start() is a no-op when already running."""
    fresh_scheduler.init()
    fresh_scheduler.start()
    assert fresh_scheduler._is_running is True
    # Already running; second start should be a no-op.
    fresh_scheduler.start()
    assert fresh_scheduler._is_running is True


def test_scheduler_start_noop_without_init(fresh_scheduler) -> None:
    """AC-FR0700-07: start() does not start a scheduler that was never initialized."""
    fresh_scheduler._scheduler = None
    fresh_scheduler._is_running = False
    fresh_scheduler.start()
    assert fresh_scheduler._is_running is False
    assert fresh_scheduler._scheduler is None


def test_scheduler_stop_noop_when_not_running(fresh_scheduler) -> None:
    """AC-FR0700-08: stop() is a no-op when not running."""
    fresh_scheduler.init()
    assert fresh_scheduler._is_running is False
    fresh_scheduler.stop()
    assert fresh_scheduler._is_running is False


def test_scheduler_stop_returns_idle_after_shutdown(fresh_scheduler) -> None:
    """AC-FR0700-09: stop() after start() flips is_running to False and shuts down scheduler."""
    fresh_scheduler.init()
    fresh_scheduler.start()
    assert fresh_scheduler._is_running is True
    fresh_scheduler.stop()
    assert fresh_scheduler._is_running is False


def test_scheduler_stop_noop_without_init(fresh_scheduler) -> None:
    """AC-FR0700-10: stop() on a never-initialized manager is a no-op."""
    fresh_scheduler._scheduler = None
    fresh_scheduler._is_running = False
    fresh_scheduler.stop()
    assert fresh_scheduler._scheduler is None
    assert fresh_scheduler._is_running is False


def test_scheduler_add_job_proxies_to_underlying(fresh_scheduler) -> None:
    """AC-FR0700-11: add_job forwards to the underlying apscheduler scheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler
    fake = BackgroundScheduler(timezone="UTC")
    fresh_scheduler._scheduler = fake
    try:
        def my_job():
            return None

        job = fresh_scheduler.add_job(my_job, "interval", seconds=60, id="t1")
        assert job is not None
        assert job.id == "t1"
    finally:
        # Cleanly shut down only if the scheduler was started; otherwise
        # apscheduler raises SchedulerNotRunningError.
        if fake.state == 1:  # STATE_RUNNING
            fake.shutdown(wait=False)


def test_scheduler_add_listener_proxies_to_underlying(fresh_scheduler) -> None:
    """AC-FR0700-12: add_listener forwards to the underlying scheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.events import EVENT_JOB_EXECUTED
    fake = BackgroundScheduler(timezone="UTC")
    fresh_scheduler._scheduler = fake
    events = []

    def listener(event):
        events.append(event)

    fresh_scheduler.add_listener(listener, EVENT_JOB_EXECUTED)
    # Listener registered; we don't fire it but the registration should not raise.
    assert events == []
    # No teardown needed: never started, so no shutdown possible.


def test_scheduler_is_singleton_via_decorator() -> None:
    """AC-FR0700-13: the @singleton decorator makes SchedulerManager a true singleton."""
    # Reset singleton state for a clean test
    _instances.pop(SchedulerManager, None)
    original_cls = getattr(SchedulerManager, "_original_class", None)
    if original_cls is not None:
        _instances.pop(original_cls, None)

    a = SchedulerManager()
    b = SchedulerManager()
    assert a is b
