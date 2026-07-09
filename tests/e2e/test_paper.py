"""L1 paper UI journeys backed by dev stubs."""

from __future__ import annotations

import pytest

from quantide.service.strategy_runtime import strategy_runtime_manager
from tests.e2e.pages import StrategyPage, SystemPage, TradePage


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_paper_journey_covers_accounts_trade_history_and_data_pages(paper_session):
    """AC-FR0390-01 AC-FR0400-01 AC-FR0310-01 AC-FR0320-01 AC-FR0330-01: paper 主路径可打开账户、委托成交与系统数据页."""
    trade_page = TradePage(paper_session.client).open_main()
    assert trade_page.status_code == 200
    trade_page.require("当前账号", "委托", "持仓")

    accounts_page = SystemPage(paper_session.client).open_accounts()
    assert accounts_page.status_code == 200
    accounts_page.require("账户")

    order_history_page = TradePage(paper_session.client).open_history_orders()
    assert order_history_page.status_code == 200
    order_history_page.require("历史委托")

    trade_history_page = TradePage(paper_session.client).open_history_trades()
    assert trade_history_page.status_code == 200
    trade_history_page.require("历史成交")

    jobs_page = SystemPage(paper_session.client).open_jobs()
    assert jobs_page.status_code == 200
    jobs_page.require("同步")

    market_page = SystemPage(paper_session.client).open_market()
    assert market_page.status_code == 200
    market_page.require("行情数据")

    stocks_page = SystemPage(paper_session.client).open_stocks()
    assert stocks_page.status_code == 200
    stocks_page.require("股票")


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_paper_journey_promotes_backtest_into_paper_and_live_modes(paper_session):
    """AC-FR0040-01 AC-FR0420-01 AC-FR0430-01: 回测报告可转入仿真和实盘, 入口页保持可访问."""
    portfolio_id = "shield-paper-promote"
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
    strategy_page.require("回测报告列表")

    paper_modal = paper_session.client.get(
        f"/strategy/backtest/{portfolio_id}/deploy/paper/modal",
        follow_redirects=True,
    )
    assert paper_modal.status_code == 200
    assert "确认转入仿真" in paper_modal.text

    paper_response = paper_session.client.post(
        f"/strategy/backtest/{portfolio_id}/deploy/paper",
        data={"paper_principal": "1000000"},
        follow_redirects=True,
    )
    assert paper_response.status_code == 200
    assert "已转入仿真" in paper_response.text

    live_modal = paper_session.client.get(
        f"/strategy/backtest/{portfolio_id}/deploy/live/modal",
        follow_redirects=True,
    )
    assert live_modal.status_code == 200
    assert "确认转入实盘" in live_modal.text

    live_response = paper_session.client.post(
        f"/strategy/backtest/{portfolio_id}/deploy/live",
        data={"live_account_id": "gateway:default"},
        follow_redirects=True,
    )
    assert live_response.status_code == 200
    assert "已转入实盘" in live_response.text

    assert TradePage(paper_session.client).open_live().status_code == 200
