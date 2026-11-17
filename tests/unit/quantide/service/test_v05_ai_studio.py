"""Session persistence and the six-tool AI sandbox contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quantide.service import ai_factor_tools, factor_audit
from quantide.service.ai_factor_tools import (
    TOOL_HANDLERS,
    TOOL_SCHEMAS,
    AIToolError,
    run_factor_ic_study,
    write_factor_plugin,
)
from quantide.service.ai_studio_store import (
    append_message,
    create_session,
    ensure_ai_studio_tables,
    get_session,
    latest_assistant_cards,
    list_messages,
    list_sessions,
    update_session,
)


def test_studio_session_and_messages_persist(db) -> None:
    ensure_ai_studio_tables()
    db.execute("DELETE FROM ai_studio_messages")
    db.execute("DELETE FROM ai_studio_sessions")
    session = create_session("测试会话")
    append_message(session["session_id"], "user", "写一个因子")
    append_message(
        session["session_id"],
        "assistant",
        "已生成",
        step_cards=[{"stage": "generate", "status": "done"}],
    )

    listed = list_sessions()
    loaded = get_session(session["session_id"])
    messages = list_messages(session["session_id"])

    assert listed[0]["session_id"] == session["session_id"]
    assert loaded is not None and loaded["status"] == "idle"
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert latest_assistant_cards(session["session_id"]) == [
        {"stage": "generate", "status": "done"}
    ]
    updated = update_session(session["session_id"], status="completed")
    assert updated is not None and updated["status"] == "completed"


def test_studio_rejects_unknown_status(db) -> None:
    session = create_session("测试会话")
    with pytest.raises(ValueError, match="状态"):
        update_session(session["session_id"], status="bogus")


def test_tool_set_is_exactly_six_and_has_no_shell() -> None:
    names = {item["function"]["name"] for item in TOOL_SCHEMAS}
    assert names == {
        "inspect_market_schema",
        "search_registered_factors",
        "write_factor_plugin",
        "run_factor_wind_tunnel",
        "run_factor_ic_study",
        "save_preset_and_run_ablation",
    }
    assert set(TOOL_HANDLERS) == names
    assert not any("shell" in name or "exec" in name or "file" == name for name in names)


@pytest.fixture
def factor_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "factors"
    target.mkdir()
    monkeypatch.setattr(ai_factor_tools, "get_factor_dir", lambda: str(target))
    return target


CODE = """
import polars as pl
from quantide.factors.plugins import FactorPlugin
FACTOR_PLUGIN = FactorPlugin(
    factor_id="ai_momentum",
    display_name="AI momentum",
    compute=lambda panel: panel.select(
        pl.col("close").pct_change().over("asset").alias("ai_momentum")
    ).to_series(),
    required_columns=("close",),
    warmup_bars=1,
)
"""


def test_write_factor_plugin_writes_one_direct_child(factor_dir: Path) -> None:
    result = write_factor_plugin({"factor_id": "ai_momentum", "code": CODE})

    assert result["ok"] is True
    assert (factor_dir / "ai_momentum.py").read_text(encoding="utf-8") == CODE
    assert len(result["source_hash"]) == 16


@pytest.mark.parametrize("factor_id", ["../escape", "/absolute/path", "ma20_slope", "A_Bad"])
def test_write_factor_plugin_rejects_traversal_absolute_and_builtin(
    factor_dir: Path, factor_id: str
) -> None:
    with pytest.raises(AIToolError) as exc:
        write_factor_plugin({"factor_id": factor_id, "code": CODE})
    assert exc.value.code in {"invalid_factor_id", "builtin_conflict", "path_escape"}


def test_write_factor_plugin_rejects_symlink_escape(factor_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text(CODE, encoding="utf-8")
    (factor_dir / "ai_momentum.py").symlink_to(outside)

    with pytest.raises(AIToolError) as exc:
        write_factor_plugin({"factor_id": "ai_momentum", "code": CODE})
    assert exc.value.code == "path_escape"
    assert outside.read_text(encoding="utf-8") == CODE


def test_write_factor_plugin_rejects_empty_code(factor_dir: Path) -> None:
    with pytest.raises(AIToolError, match="不能为空"):
        write_factor_plugin({"factor_id": "ai_momentum", "code": " "})


def test_ic_study_requires_current_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        factor_audit,
        "factor_wind_tunnel_badge",
        lambda _factor_id: SimpleNamespace(
            badge_status="FAIL", message="future perturbation mismatch"
        ),
    )

    with pytest.raises(AIToolError) as exc:
        run_factor_ic_study({"factor_id": "ai_momentum"})

    assert exc.value.code == "wind_tunnel_not_passed"
    assert "FAIL" in exc.value.message


def test_ic_study_requires_pass_for_stale_badge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        factor_audit,
        "factor_wind_tunnel_badge",
        lambda _factor_id: SimpleNamespace(badge_status="STALE", message="fingerprint changed"),
    )
    with pytest.raises(AIToolError) as exc:
        run_factor_ic_study({"factor_id": "ai_momentum"})
    assert exc.value.code == "wind_tunnel_not_passed"


def test_preset_action_requires_current_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        factor_audit,
        "factor_wind_tunnel_badge",
        lambda _factor_id: SimpleNamespace(badge_status="FAIL", message="mismatch"),
    )
    monkeypatch.setattr(
        ai_factor_tools,
        "save_preset",
        lambda *_args, **_kwargs: pytest.fail("preset must not be saved"),
        raising=False,
    )
    with pytest.raises(AIToolError) as exc:
        ai_factor_tools.save_preset_and_run_ablation(
            {
                "preset_id": "ai_momentum",
                "name": "AI momentum",
                "add_factor_id": "ai_momentum",
                "label_kind": "raw_return",
            }
        )
    assert exc.value.code == "wind_tunnel_not_passed"
