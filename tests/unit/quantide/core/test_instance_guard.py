"""Real process contention and crash recovery for the single-instance guard."""

import os
import subprocess
import sys


def test_guard_rejects_concurrent_process_but_recovers_after_kill_and_stale_pid(tmp_path):
    path = tmp_path / "instance.pid"
    path.write_text(str(os.getpid()), encoding="utf-8")  # unrelated live PID must not block recovery
    source = (
        "from pathlib import Path; from quantide.core.instance_guard import acquire_instance_guard; "
        f"acquire_instance_guard(Path({str(path)!r}), 'CE'); "
        "print('OWNED', flush=True); input()"
    )
    first = subprocess.Popen([sys.executable, "-c", source], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    try:
        assert first.stdout.readline().strip() == "OWNED"
        rejected = subprocess.run([sys.executable, "-c", source], input="\n", capture_output=True,
                                  text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=10)
        assert rejected.returncode != 0
        assert "已经在运行" in rejected.stderr
        first.kill()
        first.wait(timeout=10)
        # The dead process left its PID file; the OS released its real lock.
        assert path.exists()
        recovered = subprocess.run([sys.executable, "-c", source], input="\n", capture_output=True,
                                   text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=10)
        assert recovered.returncode == 0, recovered.stderr
        assert "OWNED" in recovered.stdout
    finally:
        if first.poll() is None:
            first.kill()
        first.wait(timeout=10)
