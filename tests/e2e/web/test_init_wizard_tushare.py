"""Data-level init-wizard E2E tests backed by the local Tushare stub."""

from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl
import pytest

from quantide.service.init_wizard import init_wizard
from tests.e2e.support.init_wizard_session import init_wizard_e2e_session
from tests.e2e.support.tushare_stub import patched_tushare_fetcher


ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"


def _next_step(client, step: int, current_step: int, **form_data):
    payload = {"_current_step": str(current_step), "nav": "next"}
    payload.update(form_data)
    return client.post(f"/init-wizard/step/{step}", data=payload)


def _parse_sync_progress_payload(response_text: str) -> dict:
    lines = [line for line in response_text.splitlines() if line.startswith("data: ")]
    assert lines, response_text
    return json.loads(lines[-1][6:])


def _advance_to_data_setup(client, market_home) -> None:
    response = client.get("/init-wizard/", follow_redirects=False)
    assert response.status_code == 200

    response = _next_step(client, 2, 1)
    assert response.status_code == 200

    response = _next_step(
        client,
        3,
        2,
        app_home=str(market_home),
        app_port="9130",
        app_prefix="/quantide",
        localhost_only="true",
    )
    assert response.status_code == 200

    response = _next_step(
        client,
        4,
        3,
        admin_password="StrongPass!123",
        admin_password_confirm="StrongPass!123",
    )
    assert response.status_code == 200

    response = _next_step(client, 5, 4)
    assert response.status_code == 200
    assert "当前数据源" in response.text


def _wait_for_sync_completion(client) -> dict:
    deadline = time.monotonic() + 10
    payload = {}
    while time.monotonic() < deadline:
        response = client.get("/init-wizard/sync-progress?force=true")
        assert response.status_code == 200
        payload = _parse_sync_progress_payload(response.text)
        if payload.get("completed") or payload.get("error"):
            return payload
    raise AssertionError(f"sync did not complete in time: {payload}")


@pytest.mark.e2e
@pytest.mark.release_gate
def test_init_wizard_download_uses_fixture_backed_tushare_data() -> None:
    with init_wizard_e2e_session() as session, patched_tushare_fetcher():
        _advance_to_data_setup(session.client, session.market_home)

        response = session.client.post(
            "/init-wizard/download",
            data={
                "epoch": "2024-01-01",
                "data_source": "tushare",
                "tushare_token": "stub-token",
                "history_years": "3",
            },
        )
        assert response.status_code == 200
        assert "sync-progress-bar" in response.text

        payload = _wait_for_sync_completion(session.client)
        assert payload["completed"] is True
        assert payload["error"] is None
        assert payload["stage"] == "初始化数据下载完成"

        state = init_wizard.get_state(force_refresh=True)
        assert state.init_completed is True
        assert state.tushare_token == "stub-token"
        assert state.history_years == 3

        calendar_path = session.market_home / "data" / "calendar.parquet"
        stock_list_path = session.market_home / "data" / "stock_list.parquet"
        daily_path = session.market_home / "data" / "bars" / "daily"
        assert calendar_path.exists()
        assert stock_list_path.exists()
        assert any(daily_path.rglob("*.parquet"))

        calendar_df = pl.read_parquet(calendar_path)
        stock_df = pl.read_parquet(stock_list_path)
        actual_bars = pl.scan_parquet(str(daily_path / "**" / "*.parquet")).collect().sort(
            ["date", "asset"]
        )
        expected_bars = pl.read_parquet(ASSETS_ROOT / "2024_bars_ext_cols.parquet").sort(
            ["date", "asset"]
        )

        assert calendar_df.height > 200
        assert stock_df.height > 5000
        assert "000001.SZ" in stock_df["asset"].to_list()

        expected_slice = expected_bars.filter(
            (pl.col("asset") == "000001.SZ")
            & (pl.col("date") >= pl.datetime(2024, 1, 2))
            & (pl.col("date") <= pl.datetime(2024, 5, 31))
        ).select(actual_bars.columns)
        actual_slice = actual_bars.filter(
            (pl.col("asset") == "000001.SZ")
            & (pl.col("date") >= pl.datetime(2024, 1, 2))
            & (pl.col("date") <= pl.datetime(2024, 5, 31))
        )

        assert actual_slice.height == 98
        assert actual_slice.equals(expected_slice)