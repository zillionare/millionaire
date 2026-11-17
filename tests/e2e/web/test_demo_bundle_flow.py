"""Offline, token-free Demo Bundle wizard and research closed loop."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from quantide.data.sqlite import db
from quantide.service.demo_bundle import demo_status
from quantide.service.init_wizard import init_wizard
from quantide.service.research_backtest import run_single_backtest
from quantide.service.research_cli import data_status
from tests.e2e.support.init_wizard_session import init_wizard_e2e_session
from tests.e2e.support.sqlite_state import capture_sqlite_state, restore_sqlite_state


def _next_step(client, step: int, current_step: int, **form_data):
    payload = {"_current_step": str(current_step), "nav": "next"}
    payload.update(form_data)
    return client.post(f"/init-wizard/step/{step}", data=payload)


def _reach_data_setup(client, market_home: Path) -> None:
    assert client.get("/init-wizard/", follow_redirects=False).status_code == 200
    assert _next_step(client, 2, 1).status_code == 200
    assert _next_step(
        client,
        3,
        2,
        app_home=str(market_home),
        app_port="9130",
        app_prefix="/quantide",
        localhost_only="true",
    ).status_code == 200
    response = _next_step(
        client,
        4,
        3,
        admin_password="StrongPass!123",
        admin_password_confirm="StrongPass!123",
    )
    assert "内置离线体验数据包" in response.text
    assert "Tushare 访问密钥" in response.text


@pytest.mark.e2e
@pytest.mark.release_gate
def test_offline_demo_bundle_wizard_flow_runs_study_wind_tunnel_ml_and_shap() -> None:
    from quantide.factors.alphatest import load_factor_panel, study_single_factor
    from quantide.service.attribution import explain_prediction
    from quantide.service.factor_wind_tunnel import run_factor_wind_tunnel

    with init_wizard_e2e_session() as session:
        _reach_data_setup(session.client, session.market_home)
        before = {path.relative_to(session.market_home) for path in session.market_home.rglob("*")}
        response = session.client.post("/init-wizard/demo/activate", follow_redirects=False)
        assert response.status_code == 303
        after = {path.relative_to(session.market_home) for path in session.market_home.rglob("*")}
        assert after == before

        state = init_wizard.get_state(force_refresh=True)
        assert state.init_completed
        assert state.data_source_mode == "demo_bundle"
        assert state.app_home == str(session.market_home)
        assert not state.tushare_token
        assert demo_status()["active"]
        assert data_status()["mode"] == "demo_bundle"

        panel = load_factor_panel(dt.date(2023, 1, 3), dt.date(2024, 6, 28))
        study = study_single_factor(panel, "ma20_slope", holding_days=5)
        assert study.rank_ic.n_days > 100
        assert study.n_rows > 0

        tunnel = run_factor_wind_tunnel(
            "ma20_slope",
            start=dt.date(2023, 1, 3),
            end=dt.date(2024, 6, 28),
            save=False,
        )
        assert tunnel.status == "PASS"
        assert tunnel.report.status.value == "PASS"

        backtest = run_single_backtest(
            "MLMomentumReversalStrategy",
            start=dt.date(2024, 1, 2),
            end=dt.date(2024, 1, 31),
            initial_cash=1_000_000,
            params={
                "train_window": 20,
                "universe_rebalance_days": 20,
                "retrain_days": 20,
                "top_k": 3,
                "universe_size": 150,
            },
        )
        assert backtest["trade_count"] > 0
        assert backtest["shap_top_features"]
        trades = db.get_trades(portfolio_id=backtest["portfolio_id"])
        assert trades is not None and not trades.is_empty()
        buys = trades.filter(trades["side"] == 1)
        assert not buys.is_empty()
        row = buys.head(1).row(0, named=True)
        trade_date = row["tm"].date()
        attribution = explain_prediction(backtest["portfolio_id"], str(row["asset"]), trade_date)
        assert attribution is not None
        assert str(attribution["engine"]).lower() == "lightgbm"
        assert attribution["features"]


@pytest.mark.e2e
@pytest.mark.release_gate
def test_init_wizard_session_restores_outer_database(tmp_path: Path) -> None:
    before = capture_sqlite_state()
    outer = tmp_path / "outer.db"
    db.init(outer)
    try:
        with init_wizard_e2e_session():
            assert Path(db.db_path).name == "quantide.db"
        assert Path(db.db_path) == outer
        assert db["app_state"].count >= 0
    finally:
        restore_sqlite_state(before)
