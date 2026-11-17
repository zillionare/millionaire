"""Offline loopback closed-loop journeys for the Web AI factor studio."""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Callable
from typing import Any

import pytest

from quantide.service import ai_agent
from quantide.service.ai_studio_store import get_session
from quantide.web.pages import factors_studio
from tests.e2e.support.openai_stub import OpenAIStub, _assistant
from tests.e2e.support.system_settings_session import system_settings_e2e_session

pytestmark = [pytest.mark.e2e, pytest.mark.release_gate]

WIND_FAIL = {
    "ok": False,
    "status": "FAIL",
    "first_difference": {
        "date": "2024-01-03",
        "asset": "000001.SZ",
        "expected": 0.0,
        "actual": 1.5,
    },
    "diagnostics": [
        {
            "code": "cross_section_isolation",
            "message": "missing .over('asset')",
            "first_difference": {"asset": "000001.SZ"},
        }
    ],
    "orthogonality": {"max_abs_rank_corr": 0.31},
}

WIND_PASS = {
    "ok": True,
    "status": "PASS",
    "first_difference": None,
    "diagnostics": [],
    "orthogonality": {
        "max_abs_rank_corr": 0.24,
        "nearest_peer_id": "bias_5",
        "high_collinearity": False,
    },
}

IC_RESULT = {
    "ok": True,
    "data_cutoff": "2024-12-31",
    "results": [
        {
            "holding_days": 5,
            "rank_ic": {"mean": 0.031, "icir": 0.42, "n_days": 100},
            "deciles": {"d1_minus_d10": -0.12},
            "as_of_date": "2024-12-31",
        }
    ],
}


def _wait_until(predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for AI studio background round")


def _session_id(location: str) -> str:
    values = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    return str(values["session_id"][0])


def _save_ai_config(session, base_url: str, api_key: str) -> None:
    response = session.client.post(
        "/system/ai/save",
        data={
            "provider_preset": "custom",
            "base_url": base_url,
            "model": "mock-model",
            "api_key": api_key,
            "timeout_seconds": "5",
            "max_repair_rounds": "3",
            "max_tool_steps": "12",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _start_conversation(session) -> str:
    created = session.client.post("/factors/studio/sessions", follow_redirects=False)
    assert created.status_code == 303
    session_id = _session_id(created.headers["location"])
    posted = session.client.post(
        f"/factors/studio/sessions/{session_id}/messages",
        data={"message": "写一个 20 日缩量反转因子，并按证券分组计算"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    return session_id


def test_web_studio_repairs_factor_and_runs_preset(monkeypatch) -> None:
    responses = [
        _assistant(calls=[("write_factor_plugin", {"factor_id": "ai_reversal", "code": "bad"})]),
        _assistant(calls=[("run_factor_wind_tunnel", {"factor_id": "ai_reversal"})]),
        _assistant(
            calls=[
                (
                    "write_factor_plugin",
                    {"factor_id": "ai_reversal", "code": "fixed .over('asset')"},
                )
            ]
        ),
        _assistant(calls=[("run_factor_wind_tunnel", {"factor_id": "ai_reversal"})]),
        _assistant(content="因子已通过风洞并完成 IC 检验。"),
    ]
    wind_calls: list[str] = []
    ic_calls: list[str] = []

    def execute(name: str, arguments: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        if name == "write_factor_plugin":
            return {"ok": True, "factor_id": arguments["factor_id"], "source_hash": "hash"}
        if name == "run_factor_wind_tunnel":
            wind_calls.append(str(arguments["factor_id"]))
            result = WIND_FAIL if len(wind_calls) == 1 else WIND_PASS
            return {**result, "factor_id": arguments["factor_id"]}
        if name == "run_factor_ic_study":
            ic_calls.append(str(arguments["factor_id"]))
            return {**IC_RESULT, "factor_id": arguments["factor_id"]}
        return {"ok": True}

    def preset_tool(name: str, arguments: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        assert name == "save_preset_and_run_ablation"
        return {
            "ok": True,
            "preset": {"preset_id": arguments["preset_id"], "features": [arguments["add_factor_id"]]},
            "ablation": {"status": "completed"},
        }

    with OpenAIStub(responses) as server, system_settings_e2e_session() as session:
        _save_ai_config(session, server.base_url, server.api_key)
        monkeypatch.setattr(ai_agent, "execute_tool", execute)
        monkeypatch.setattr(factors_studio, "execute_tool", preset_tool)

        session_id = _start_conversation(session)
        _wait_until(lambda: (get_session(session_id) or {}).get("status") == "completed")

        panel = session.client.get(f"/factors/studio/sessions/{session_id}/panel")
        assert panel.status_code == 200
        for text in (
            "风洞体检",
            "自动修复第 1 轮",
            "RankIC",
            "D1-D10",
            "最高相关现有因子",
            "加入策略预设做消融回测",
        ):
            assert text in panel.text
        assert wind_calls == ["ai_reversal", "ai_reversal"]
        assert ic_calls == ["ai_reversal"]
        assert server.request_count == 5

        preset = session.client.post(
            f"/factors/studio/sessions/{session_id}/actions/preset",
            follow_redirects=False,
        )
        assert preset.status_code == 303
        refreshed = session.client.get(f"/factors/studio/sessions/{session_id}/panel")
        assert "已保存因子预设。" in refreshed.text
        assert "预设：ai_ai_reversal" in refreshed.text


def test_web_studio_cancel_stops_background_round(monkeypatch) -> None:
    responses = [
        _assistant(calls=[("write_factor_plugin", {"factor_id": "ai_slow", "code": "draft"})]),
        _assistant(content="不应执行到这里。"),
    ]
    tool_calls: list[str] = []

    def execute(name: str, _arguments: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        tool_calls.append(name)
        return {"ok": True}

    with OpenAIStub(responses, delay_seconds=0.6) as server, system_settings_e2e_session() as session:
        _save_ai_config(session, server.base_url, server.api_key)
        monkeypatch.setattr(ai_agent, "execute_tool", execute)
        session_id = _start_conversation(session)
        _wait_until(lambda: server.request_count >= 1)

        stopped = session.client.post(
            f"/factors/studio/sessions/{session_id}/cancel",
            follow_redirects=False,
        )
        assert stopped.status_code == 303
        _wait_until(lambda: (get_session(session_id) or {}).get("status") == "cancelled")

    assert tool_calls == []


def test_web_studio_stops_after_max_repair_rounds(monkeypatch) -> None:
    responses: list[dict[str, Any]] = []
    for _ in range(3):
        responses.append(
            _assistant(calls=[("write_factor_plugin", {"factor_id": "ai_bad", "code": "bad"})])
        )
        responses.append(
            _assistant(calls=[("run_factor_wind_tunnel", {"factor_id": "ai_bad"})])
        )
    wind_calls: list[str] = []

    def execute(name: str, arguments: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        if name == "write_factor_plugin":
            return {"ok": True, "factor_id": arguments["factor_id"], "source_hash": "hash"}
        if name == "run_factor_wind_tunnel":
            wind_calls.append(str(arguments["factor_id"]))
            return {**WIND_FAIL, "factor_id": arguments["factor_id"]}
        raise AssertionError(f"unexpected tool after max repair: {name}")

    with OpenAIStub(responses) as server, system_settings_e2e_session() as session:
        _save_ai_config(session, server.base_url, server.api_key)
        monkeypatch.setattr(ai_agent, "execute_tool", execute)

        session_id = _start_conversation(session)
        _wait_until(lambda: (get_session(session_id) or {}).get("status") == "failed")

        panel = session.client.get(f"/factors/studio/sessions/{session_id}/panel")
        assert panel.status_code == 200
        assert "连续 3 轮未通过" in panel.text
        assert wind_calls == ["ai_bad", "ai_bad", "ai_bad"]
        assert server.request_count == 6


def test_web_studio_real_tools_repair_against_demo_market() -> None:
    from quantide.service.demo_bundle import activate_demo_bundle
    from quantide.service.factor_audit import factor_wind_tunnel_badge
    from quantide.service.research_cli import _template

    good = _template("ai_web_real", "自定义因子")
    bad = good.replace(
        'previous = pl.col("close").shift(1).over("asset")',
        'previous = pl.col("close").shift(1)',
    )
    responses = [
        _assistant(
            calls=[
                (
                    "write_factor_plugin",
                    {"factor_id": "ai_web_real", "code": bad},
                )
            ]
        ),
        _assistant(calls=[("run_factor_wind_tunnel", {"factor_id": "ai_web_real"})]),
        _assistant(
            calls=[
                (
                    "write_factor_plugin",
                    {"factor_id": "ai_web_real", "code": good},
                )
            ]
        ),
        _assistant(calls=[("run_factor_wind_tunnel", {"factor_id": "ai_web_real"})]),
        _assistant(content="真实风洞与 IC 检验已完成。"),
    ]
    with OpenAIStub(responses) as server, system_settings_e2e_session() as session:
        activate_demo_bundle()
        _save_ai_config(session, server.base_url, server.api_key)
        session_id = _start_conversation(session)
        _wait_until(
            lambda: (get_session(session_id) or {}).get("status") == "completed",
            timeout=60,
        )

        panel = session.client.get(f"/factors/studio/sessions/{session_id}/panel")
        assert panel.status_code == 200
        for text in ("风洞体检", "自动修复第 1 轮", "RankIC", "D1-D10"):
            assert text in panel.text
        assert factor_wind_tunnel_badge("ai_web_real").badge_status == "PASS"

        preset = session.client.post(
            f"/factors/studio/sessions/{session_id}/actions/preset",
            follow_redirects=False,
        )
        assert preset.status_code == 303
        refreshed = session.client.get(f"/factors/studio/sessions/{session_id}/panel")
        assert "已保存因子预设。" in refreshed.text
