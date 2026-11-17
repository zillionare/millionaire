"""Real child-process research CLI closure used by the official Agent Skill."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from quantide.config.paths import get_app_db_path, set_app_config_dir_override
from quantide.data.sqlite import db
from quantide.service.demo_bundle import activate_demo_bundle
from quantide.service.init_wizard import init_wizard

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]


def _paper_state(path: Path) -> dict[str, list[tuple[object, ...]]]:
    if not path.is_file():
        return {}
    connection = sqlite3.connect(path)
    try:
        names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            if any(part in str(row[0]).lower() for part in ("paper", "account", "order"))
        ]
        return {
            name: connection.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()
            for name in names
        }
    finally:
        connection.close()


def _run(env: dict[str, str], *args: str) -> tuple[int, dict[str, object]]:
    completed = subprocess.run(
        [sys.executable, env["CLI_RUNNER"], *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    stdout = completed.stdout.strip()
    assert "NaN" not in stdout and "Infinity" not in stdout, completed.stderr[-1000:]
    assert stdout, completed.stderr[-2000:]
    return completed.returncode, json.loads(stdout)


def test_skill_cli_creates_repairs_checks_studies_and_saves_presets(tmp_path: Path) -> None:
    config_home = tmp_path / "config"
    previous = set_app_config_dir_override(config_home)
    db.init(get_app_db_path())
    state = init_wizard.get_state()
    state.app_home = str(tmp_path / "formal")
    state.factor_dir = str(config_home / "factors")
    state.strategy_dir = str(config_home / "strategies")
    state.init_completed = True
    state.init_step = 6
    state.tushare_token = ""
    init_wizard.save_state(state)
    demo = activate_demo_bundle()
    runner = tmp_path / "cli_runner.py"
    runner.write_text(
        "from quantide.cli import main\nif __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "QUANTIDE_CONFIG_HOME": str(config_home),
        "QUANTIDE_DATA_HOME": str(demo["demo_home"]),
        "QUANTIDE_LOG_HOME": str(tmp_path / "logs"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CLI_RUNNER": str(runner),
    }
    db_path = get_app_db_path()
    paper_before = _paper_state(db_path)
    try:
        rc, created = _run(env, "factor", "init", "ai_skill_factor", "--json")
        assert rc == 0 and created["ok"] is True
        path = Path(str((created["data"] or {})["path"]))
        good = path.read_text(encoding="utf-8")
        path.write_text(
            good.replace(
                'pl.col("close").shift(1).over("asset")',
                'pl.col("close").shift(-1).over("asset")',
            ),
            encoding="utf-8",
        )
        rc, bad = _run(env, "factor", "check", "ai_skill_factor", "--json")
        assert rc == 3 and bad["status"] == "FAIL"
        assert bad["diagnostics"]

        path.write_text(good, encoding="utf-8")
        rc, passed = _run(env, "factor", "check", "ai_skill_factor", "--json")
        assert rc == 0 and passed["status"] == "PASS"
        assert (passed["data"] or {})["orthogonality"]["max_abs_rank_corr"] is not None

        rc, study = _run(
            env,
            "factor",
            "study",
            "ai_skill_factor",
            "--start",
            "2024-01-02",
            "--end",
            "2024-06-28",
            "--holdings",
            "5",
            "--json",
        )
        assert rc == 0 and study["status"] == "OK"
        assert (study["data"] or {})["results"]

        rc, base = _run(
            env,
            "preset",
            "save",
            "--id",
            "skill_base",
            "--name",
            "Skill Base",
            "--features",
            "ma20_slope,bias_5",
            "--json",
        )
        assert rc == 0 and base["ok"] is True
        rc, preset = _run(
            env,
            "preset",
            "save",
            "--id",
            "skill_ai",
            "--name",
            "Skill AI",
            "--features",
            "ma20_slope,bias_5,ai_skill_factor",
            "--json",
        )
        assert rc == 0 and preset["ok"] is True
        assert (preset["data"] or {})["features"][-1] == "ai_skill_factor"
    finally:
        assert _paper_state(db_path) == paper_before
        set_app_config_dir_override(previous)
