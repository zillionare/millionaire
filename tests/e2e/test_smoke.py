"""UI smoke journeys for the locked v0.2-002-ui spec."""

from __future__ import annotations

import pytest

from quantide.service.strategy_runtime import strategy_runtime_manager
from tests.e2e.pages import AuthPage, StrategyPage


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_login_redirects_into_strategy_workspace(anonymous_initialized_client):
    """AC-FR0110-01 AC-FR0120-01: 已初始化未登录访问根路由会跳登录, 登录后进入主工作区."""
    client = anonymous_initialized_client
    auth = AuthPage(client)

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/strategy/"

    login_page = auth.open_login()
    login_page.require("登录", "username", "password")

    login = auth.login("admin", "admin123")
    assert login.status_code == 303
    assert login.headers["location"] == "/strategy/"

    strategy_page = StrategyPage(client).open()
    assert strategy_page.status_code == 200
    strategy_page.require("策略列表", "回测报告列表")


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_strategy_workspace_can_open_backtest_report_tabs(paper_session):
    """AC-FR0080-01 AC-FR0091-01 AC-FR0091-02: 策略页可进入回测报告, 报告页保留核心页签."""
    portfolio_id = "shield-smoke-report"
    strategy_runtime_manager.create_backtest_runtime(
        portfolio_id=portfolio_id,
        strategy_name="DualMAStrategy",
        config={"fast": 5, "slow": 10, "invest": 100000},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=200000,
    )

    strategy_page = StrategyPage(paper_session.client).open()
    strategy_page.require("策略列表", "回测报告列表")

    report_page = StrategyPage(paper_session.client).open_report(portfolio_id)
    assert report_page.status_code == 200
    report_page.require("回测报告", "概览", "收益", "风险", "日志")
