"""Shutdown waits for a running maintenance job before storage can be closed."""

import threading

from apscheduler.schedulers.background import BackgroundScheduler

from quantide.core.scheduler import scheduler


def test_waiting_stop_drains_running_scheduled_work(monkeypatch):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    monkeypatch.setattr(scheduler, "_scheduler", BackgroundScheduler())
    monkeypatch.setattr(scheduler, "_is_running", False)

    def work():
        entered.set()
        assert release.wait(5)

    def stop():
        scheduler.pause()
        scheduler.stop(wait=True)
        stopped.set()

    scheduler.add_job(work, "date")
    scheduler.start()
    stopper = threading.Thread(target=stop)
    try:
        assert entered.wait(3)
        stopper.start()
        assert not stopped.wait(0.05)
        release.set()
        assert stopped.wait(3)
        assert scheduler._scheduler is None
    finally:
        release.set()
        if stopper.ident is not None:
            stopper.join(timeout=5)
        scheduler.stop(wait=True)
