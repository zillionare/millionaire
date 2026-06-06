"""End-to-end checks for the development stub startup switch."""

from __future__ import annotations

import pytest

from quantide.config.dev_stubs import (
    DEV_STUBS_ENV_VAR,
    ensure_dev_stubs_started,
    reset_dev_stub_runtime_for_tests,
)
from quantide.core.runtime.gateway_broker import GatewayBrokerAdapter
from quantide.core.runtime.gateway_client import GatewayClient
from quantide.data.fetchers.registry import get_data_fetcher
from quantide.service.strategy_runtime import strategy_runtime_manager
from quantide.web.middleware_feature import get_feature_status
from tests.e2e.support.system_settings_session import system_settings_e2e_session


@pytest.mark.e2e
def test_dev_stub_switch_starts_gateway_and_tushare(monkeypatch) -> None:
    monkeypatch.setenv(DEV_STUBS_ENV_VAR, "1")
    reset_dev_stub_runtime_for_tests()

    portfolio_id = "dev-stub-demo-pf"
    try:
        with system_settings_e2e_session() as session:
            response = session.client.get("/strategy/live", follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/trade/live/"

            response = session.client.get("/papertrade", follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/trade/paper/"

            response = session.client.get("/trade/live/", follow_redirects=False)
            assert response.status_code != 403

            strategy_runtime_manager.create_backtest_runtime(
                portfolio_id=portfolio_id,
                strategy_name="DualMAStrategy",
                config={"fast": 5, "slow": 10, "invest": 100000},
                interval="1d",
                start_date="2024-01-01",
                end_date="2024-01-31",
                initial_cash=200000,
            )

            try:
                strategy_page_response = session.client.get("/strategy/", follow_redirects=True)
                assert strategy_page_response.status_code == 200
                assert "策略列表" in strategy_page_response.text
                assert "回测报告列表" in strategy_page_response.text

                paper_modal = session.client.get(f"/strategy/backtest/{portfolio_id}/deploy/paper/modal")
                assert paper_modal.status_code == 200
                assert "确认转入仿真" in paper_modal.text
                assert f'hx-post="/strategy/backtest/{portfolio_id}/deploy/paper"' in paper_modal.text

                paper_response = session.client.post(
                    f"/strategy/backtest/{portfolio_id}/deploy/paper",
                    data={"paper_principal": "1000000"},
                    follow_redirects=True,
                )
                assert paper_response.status_code == 200
                assert "已转入仿真" in paper_response.text

                live_modal = session.client.get(f"/strategy/backtest/{portfolio_id}/deploy/live/modal")
                assert live_modal.status_code == 200
                assert "确认转入实盘" in live_modal.text
                assert "gateway:default" in live_modal.text

                live_response = session.client.post(
                    f"/strategy/backtest/{portfolio_id}/deploy/live",
                    data={"live_account_id": "gateway:default"},
                    follow_redirects=True,
                )
                assert live_response.status_code == 200
                assert "已转入实盘" in live_response.text
            finally:
                with strategy_runtime_manager._lock:
                    paper_portfolio_ids = [
                        runtime.portfolio_id
                        for runtime in strategy_runtime_manager._strategy_runtimes.values()
                        if runtime.source_backtest_portfolio_id == portfolio_id and runtime.mode == "paper"
                    ]
                    for runtime in list(strategy_runtime_manager._strategy_runtimes.values()):
                        if runtime.source_backtest_portfolio_id == portfolio_id:
                            strategy_runtime_manager._strategy_runtimes.pop(runtime.runtime_id, None)
                    strategy_runtime_manager._backtest_history.pop(portfolio_id, None)
                    strategy_runtime_manager._backtest_runtimes.pop(portfolio_id, None)
                for paper_portfolio_id in paper_portfolio_ids:
                    try:
                        from quantide.data.sqlite import db

                        db.delete_portfolio_cascade(paper_portfolio_id)
                    except Exception:
                        pass

            runtime = ensure_dev_stubs_started()
            assert runtime is not None

            features = get_feature_status()
            assert features["backtest"]["available"] is True
            assert features["simulation"]["available"] is True
            assert features["live_trading"]["available"] is True

            adapter = GatewayBrokerAdapter(
                GatewayClient(
                    runtime.gateway_base_url,
                    username=runtime.gateway_username,
                    password=runtime.gateway_password,
                    timeout=2,
                )
            )
            asset = adapter.query_assets()
            assert asset is not None
            assert asset.total == pytest.approx(100000.0)

            stock_list = get_data_fetcher("tushare").fetch_stock_list()
            assert stock_list is not None
            assert len(stock_list) > 5000
    finally:
        with strategy_runtime_manager._lock:
            strategy_runtime_manager._strategy_runtimes.clear()
            strategy_runtime_manager._account_runtimes.clear()
            strategy_runtime_manager._backtest_runtimes.clear()
            strategy_runtime_manager._backtest_history.clear()
            strategy_runtime_manager._runtime_specs.clear()
            strategy_runtime_manager._blocked_accounts.clear()
            strategy_runtime_manager._blocked_strategies.clear()
            strategy_runtime_manager._risk_events.clear()
            strategy_runtime_manager._runtime = None
            strategy_runtime_manager._registry = None
            strategy_runtime_manager._adapters = None
            strategy_runtime_manager._market_data = None
            strategy_runtime_manager._gateway_broker = None
        reset_dev_stub_runtime_for_tests()
