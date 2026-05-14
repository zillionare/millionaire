from types import SimpleNamespace

import pandas as pd
import pytest
from fasthtml.common import to_xml

from quantide.data.sqlite import Portfolio
from quantide.web.pages import strategy as strategy_page


class FakeRequest:
    def __init__(self, form_data):
        self._form_data = form_data

    async def form(self):
        return self._form_data


class FakePageRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


def test_strategy_index_page_omits_runtime_and_risk_panels(monkeypatch, db):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {},
    )

    html = to_xml(strategy_page.index(None, {"auth": "admin"}))

    assert 'id="risk-event-center"' not in html
    assert 'id="runtime-monitor"' not in html


def test_scan_config_modal_describes_builtin_examples_and_setting_only(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "get_user_scan_directory",
        lambda: "",
    )
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "get_builtin_scan_directory",
        lambda: "/opt/quantide/strategies/example",
    )

    html = to_xml(strategy_page.config_modal_route(None))

    assert "内置示例目录会始终参与扫描" in html
    assert "/opt/quantide/strategies/example" in html
    assert "复制示例请回到策略列表页点击“复制示例策略”" in html
    assert 'hx-post="/strategy/scan/copy-examples"' not in html


def test_strategy_scan_toolbar_exposes_visible_copy_button():
    html = to_xml(strategy_page._strategy_scan_toolbar())

    assert "复制示例策略" in html
    assert 'hx-post="/strategy/scan/copy-examples"' in html


def test_strategy_index_page_explains_copy_entry(monkeypatch, db):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {},
    )

    html = to_xml(strategy_page.index(None, {"auth": "admin"}))

    assert "复制示例策略" in html
    assert "内置示例已默认参与扫描" in html
    assert 'id="risk-event-center"' not in html
    assert 'id="runtime-monitor"' not in html


def test_strategy_index_page_renders_hash_toggle_for_backtest_list(monkeypatch, db):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {},
    )

    html = to_xml(strategy_page.index(None, {"auth": "admin"}))

    assert 'id="strategy-list-section"' in html
    assert 'id="backtest-list"' in html
    assert "function toggleStrategySections()" in html
    assert "window.location.hash === '#backtest-list'" in html
    assert "classList.toggle('hidden', showBacktestOnly)" in html
    assert "function setSidebarItemState(element, isActive)" in html
    assert "function findSidebarLink(expectedPath, expectedHash, expectedLabel)" in html
    assert "function handleSidebarToggleClick(event)" in html
    assert "event.preventDefault()" in html
    assert "findSidebarLink('/strategy', '#backtest-list', '回测报告')" in html
    assert "setSidebarItemState(backtestMenuLink, showBacktestOnly)" in html


def test_strategy_index_page_includes_modal_helper_script(monkeypatch, db):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {},
    )

    html = to_xml(strategy_page.index(None, {"auth": "admin"}))

    assert "window.closeStrategyModal = clearModalContainer" in html
    assert "htmx:afterSwap" in html
    assert "UIkit.modal" in html


def test_run_scan_route_scans_builtin_examples_without_user_directory(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "scan_and_cache",
        lambda: {"DualMAStrategy": object()},
    )
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "get_scan_directories",
        lambda: ["/opt/quantide/strategies/example"],
    )

    html = to_xml(strategy_page.run_scan(None))

    assert "成功发现 1 个策略" in html
    assert "内置示例目录已默认参与扫描" in html
    assert "/opt/quantide/strategies/example" in html


@pytest.mark.asyncio
async def test_copy_scan_examples_route_requires_directory_config(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "get_user_scan_directory",
        lambda: "",
    )

    response = await strategy_page.copy_scan_examples(FakeRequest({}))
    html = to_xml(response)

    assert "请先设置用户策略目录" in html
    assert 'hx-get="/strategy/scan/config-modal"' in html


@pytest.mark.asyncio
async def test_copy_scan_examples_route_uses_saved_directory_and_reports_result(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "get_user_scan_directory",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "copy_examples_to_directory",
        lambda directory: SimpleNamespace(copied_count=1, skipped_count=0),
    )

    response = await strategy_page.copy_scan_examples(FakeRequest({}))
    html = to_xml(response)

    assert "示例已复制" in html
    assert str(tmp_path.resolve()) in html
    assert 'hx-post="/strategy/scan/run"' in html


def test_build_metrics_payload_normalizes_percent_metrics_and_current_keys(monkeypatch):
    stats = pd.DataFrame(
        {
            "Value": [
                "1394.79%",
                "233.39%",
                "-5.26%",
                "476.44%",
                "0.74",
                "29.66",
                "44.34",
                "0.55",
                "1.23",
                "29.15%",
                "8.53",
                "29.26",
                "0.82%",
                "2.42%",
                "-0.09%",
                "5.10%",
                "-3.20%",
                "1.25",
                "0.12",
                "555.86",
                "-2.14%",
                "0.88",
            ]
        },
        index=[
            "Total Return",
            "CAGR",
            "Max Drawdown",
            "Volatility (ann.)",
            "Sharpe Ratio",
            "Sortino Ratio",
            "Calmar Ratio",
            "Alpha (ann.)",
            "Beta",
            "Win Rate (Daily)",
            "Profit Factor",
            "Payoff Ratio",
            "Average Return",
            "Average Win",
            "Average Loss",
            "Best Day",
            "Worst Day",
            "Tail Ratio",
            "Skewness",
            "Kurtosis",
            "Daily Value at Risk",
            "Information Ratio",
        ],
    )
    monkeypatch.setattr(strategy_page, "metrics", lambda *args, **kwargs: stats)
    monkeypatch.setattr(strategy_page, "_build_benchmark_returns", lambda portfolio_id: None)

    payload = strategy_page._build_metrics_payload("demo")

    assert payload["total_returns"] == pytest.approx(13.9479)
    assert payload["annual_return"] == pytest.approx(2.3339)
    assert payload["max_drawdown"] == pytest.approx(-0.0526)
    assert payload["volatility"] == pytest.approx(4.7644)
    assert payload["sharpe"] == pytest.approx(0.74)
    assert payload["sortino"] == pytest.approx(29.66)
    assert payload["calmar"] == pytest.approx(44.34)
    assert payload["alpha"] == pytest.approx(0.55)
    assert payload["beta"] == pytest.approx(1.23)
    assert payload["win_rate"] == pytest.approx(0.2915)
    assert payload["profit_factor"] == pytest.approx(8.53)
    assert payload["payoff_ratio"] == pytest.approx(29.26)
    assert payload["avg_return"] == pytest.approx(0.0082)
    assert payload["avg_win"] == pytest.approx(0.0242)
    assert payload["avg_loss"] == pytest.approx(-0.0009)
    assert payload["best_day"] == pytest.approx(0.051)
    assert payload["worst_day"] == pytest.approx(-0.032)
    assert payload["tail_ratio"] == pytest.approx(1.25)
    assert payload["skew"] == pytest.approx(0.12)
    assert payload["kurtosis"] == pytest.approx(555.86)
    assert payload["value_at_risk"] == pytest.approx(-0.0214)
    assert payload["information_ratio"] == pytest.approx(0.88)
    assert strategy_page._format_percent(payload["annual_return"]) == "233.4%"
    assert strategy_page._format_percent(payload["max_drawdown"]) == "-5.3%"


def test_build_metrics_payload_keeps_missing_metrics_empty(monkeypatch):
    monkeypatch.setattr(strategy_page, "metrics", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(strategy_page, "_build_benchmark_returns", lambda portfolio_id: None)

    payload = strategy_page._build_metrics_payload("demo")

    assert payload["annual_return"] is None
    assert payload["sharpe"] is None
    assert payload["win_rate"] is None
    assert strategy_page._format_percent(payload["annual_return"]) == "--"
    assert strategy_page._format_number(payload["sharpe"]) == "--"


def test_build_metrics_payload_passes_benchmark_returns(monkeypatch):
    captured = {}
    baseline_returns = pd.DataFrame({"dt": ["2024-01-02"], "returns": [0.01]})

    def _fake_metrics(portfolio_id, baseline_returns=None):
        captured["portfolio_id"] = portfolio_id
        captured["baseline_returns"] = baseline_returns
        return pd.DataFrame({"Value": ["1.00"]}, index=["Sharpe Ratio"])

    monkeypatch.setattr(strategy_page, "metrics", _fake_metrics)
    monkeypatch.setattr(
        strategy_page,
        "_build_benchmark_returns",
        lambda portfolio_id: baseline_returns,
    )

    strategy_page._build_metrics_payload("demo")

    assert captured["portfolio_id"] == "demo"
    assert captured["baseline_returns"] is baseline_returns


def test_resolve_backtest_status_prefers_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        strategy_page,
        "strategy_runtime_manager",
        SimpleNamespace(
            get_backtest_run=lambda portfolio_id: SimpleNamespace(
                status="failed",
                error="boom",
            )
        ),
    )
    monkeypatch.setattr(strategy_page.db, "get_portfolio", lambda portfolio_id: None)

    status, error = strategy_page._resolve_backtest_status("demo")

    assert status == "failed"
    assert error == "boom"


def test_build_backtest_rows_keeps_missing_metrics_blank(monkeypatch):
    portfolios = pd.DataFrame(
        [
            {
                "portfolio_id": "demo-pf",
                "kind": "bt",
                "name": "DualMAStrategy",
                "start": "2024-01-01",
                "end": "2024-01-31",
                "info": "",
            }
        ]
    )
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: strategy_page.pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_page, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_page, "_strategy_version", lambda cls: "--")
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    rows = strategy_page._build_backtest_rows({})
    html = to_xml(rows[0])

    assert "--" in html
    assert "0.0%" not in html
    assert 'href="/strategy/backtest/demo-pf"' in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/paper/modal"' in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/live/modal"' in html
    assert 'btn btn-secondary btn-sm' in html
    assert 'btn btn-primary btn-sm' not in html


def test_build_backtest_rows_disabled_deploy_buttons_explain_gateway_requirement(monkeypatch):
    portfolios = pd.DataFrame(
        [
            {
                "portfolio_id": "demo-pf",
                "kind": "bt",
                "name": "DualMAStrategy",
                "start": "2024-01-01",
                "end": "2024-01-31",
                "info": "",
            }
        ]
    )
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: strategy_page.pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_page, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_page, "_strategy_version", lambda cls: "--")
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    rows = strategy_page._build_backtest_rows({}, gateway_available=False)
    html = to_xml(rows[0])

    assert 'title="请先配置交易网关，才能转仿真"' in html
    assert 'title="请先配置交易网关，才能转实盘"' in html
    assert "pointer-events-none" in html
    assert "disabled" in html


def test_build_backtest_rows_renders_active_deployment_statuses(monkeypatch):
    portfolios = pd.DataFrame(
        [
            {
                "portfolio_id": "demo-pf",
                "kind": "bt",
                "name": "DualMAStrategy",
                "start": "2024-01-01",
                "end": "2024-01-31",
                "info": "",
            }
        ]
    )
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: strategy_page.pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_page, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_page, "_strategy_version", lambda cls: "--")
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {"paper": {"status": "running"}, "live": {"status": "running"}},
    )

    rows = strategy_page._build_backtest_rows({})
    html = to_xml(rows[0])

    assert "仿真中" in html
    assert "实盘中" in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/paper/modal"' not in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/live/modal"' not in html


def test_normalize_backtest_tab_falls_back_to_overview():
    assert strategy_page._normalize_backtest_tab("logs") == "logs"
    assert strategy_page._normalize_backtest_tab("unknown") == "overview"


def test_backtest_result_defaults_to_overview_only(monkeypatch):
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("finished", ""))
    monkeypatch.setattr(strategy_page, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_page, "_build_date_axis", lambda portfolio_id: ["2024-01-02", "2024-01-03"])
    monkeypatch.setattr(
        strategy_page,
        "_build_series_payload",
        lambda portfolio_id, date_axis: {
            "date_axis": date_axis,
            "total": [1.0, 1.1],
            "benchmark": [1.0, 1.0],
            "daily_pnl": [0.0, 0.1],
            "trade_count": [0, 1],
        },
    )
    monkeypatch.setattr(strategy_page, "_build_trade_rows", lambda portfolio_id, limit=200: [])
    monkeypatch.setattr(strategy_page, "_build_daily_positions", lambda portfolio_id: [])
    monkeypatch.setattr(strategy_page, "_build_log_rows", lambda portfolio_id, limit=200: [])
    monkeypatch.setattr(
        strategy_page,
        "_build_log_meta",
        lambda portfolio_id: {"save_requested": False, "saved": False, "saved_path": "/tmp/demo.jsonl"},
    )

    html = to_xml(strategy_page.backtest_result(FakePageRequest(), {"auth": "admin"}, "demo-pf"))

    assert 'id="overview"' in html
    assert 'id="trades"' not in html
    assert 'id="positions"' not in html
    assert 'id="backtest-log-panel"' not in html
    assert 'id="backtest-deploy-panel"' not in html
    assert 'id="backtest_status"' not in html
    assert 'id="modal-container"' in html


def test_backtest_result_logs_tab_renders_only_log_panel(monkeypatch):
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("finished", ""))
    monkeypatch.setattr(strategy_page, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_page, "_build_date_axis", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_page,
        "_build_series_payload",
        lambda portfolio_id, date_axis: {
            "date_axis": [],
            "total": [],
            "benchmark": [],
            "daily_pnl": [],
            "trade_count": [],
        },
    )
    monkeypatch.setattr(strategy_page, "_build_trade_rows", lambda portfolio_id, limit=200: [])
    monkeypatch.setattr(strategy_page, "_build_daily_positions", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_page,
        "_build_log_rows",
        lambda portfolio_id, limit=200: [
            {
                "dt": "2024-01-02 09:30:00",
                "level": "INFO",
                "source": "runner",
                "message": "开始回测",
                "extra": "",
            }
        ],
    )
    monkeypatch.setattr(
        strategy_page,
        "_build_log_meta",
        lambda portfolio_id: {"save_requested": True, "saved": True, "saved_path": "/tmp/demo.jsonl"},
    )

    html = to_xml(
        strategy_page.backtest_result(
            FakePageRequest({"tab": "logs"}),
            {"auth": "admin"},
            "demo-pf",
        )
    )

    assert 'id="overview"' not in html
    assert 'id="trades"' not in html
    assert 'id="positions"' not in html
    assert 'id="backtest-log-panel"' in html
    assert 'id="backtest-deploy-panel"' not in html
    assert 'id="backtest_status"' not in html
    assert "开始回测" in html
    assert 'hx-get="/strategy/backtest/demo-pf/logs/saved"' in html


def test_load_saved_backtest_log_panel_surfaces_read_error(monkeypatch):
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("finished", ""))
    monkeypatch.setattr(
        strategy_page,
        "load_saved_backtest_logs",
        lambda portfolio_id, limit=200: (_ for _ in ()).throw(FileNotFoundError("未找到日志文件")),
    )
    monkeypatch.setattr(
        strategy_page,
        "_build_log_meta",
        lambda portfolio_id: {"save_requested": True, "saved": False, "saved_path": "/tmp/demo.jsonl"},
    )

    html = to_xml(strategy_page.load_saved_backtest_log_panel("demo-pf"))

    assert "未找到日志文件" in html


def test_deploy_backtest_to_paper_modal_requests_principal_confirmation():
    html = to_xml(strategy_page.deploy_backtest_to_paper_modal("demo-pf"))

    assert "确认转入仿真" in html
    assert 'id="deploy-paper-form"' in html
    assert 'name="paper_principal"' in html
    assert 'hx-post="/strategy/backtest/demo-pf/deploy/paper"' in html


def test_deploy_backtest_to_live_modal_requires_gateway(monkeypatch):
    monkeypatch.setattr(strategy_page, "_get_live_accounts", lambda req: [])

    html = to_xml(strategy_page.deploy_backtest_to_live_modal(FakePageRequest(), "demo-pf"))

    assert "无法转入实盘" in html
    assert "未检测到可用的实盘网关" in html


def test_deploy_backtest_to_live_modal_confirms_when_gateway_exists(monkeypatch):
    monkeypatch.setattr(
        strategy_page,
        "_get_live_accounts",
        lambda req: [{"id": "gateway:default", "name": "gateway:default"}],
    )

    html = to_xml(strategy_page.deploy_backtest_to_live_modal(FakePageRequest(), "demo-pf"))

    assert "确认转入实盘" in html
    assert "gateway:default" in html
    assert 'id="deploy-live-form"' in html
    assert 'hx-post="/strategy/backtest/demo-pf/deploy/live"' in html


def test_delete_backtest_modal_renders_confirmation(monkeypatch):
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=strategy_page.BrokerKind.BACKTEST,
            start="2024-01-01",
            name="DemoStrategy",
        ),
    )
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("finished", ""))
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    html = to_xml(strategy_page.delete_backtest_modal("demo-pf"))

    assert "DemoStrategy" in html
    assert "demo-pf"[:8] in html
    assert "确认删除回测" in html
    assert 'hx-post="/strategy/backtest/demo-pf/delete"' in html
    assert "取消" in html
    assert 'onclick="closeStrategyModal()"' in html
    assert "max-w-md" in html
    assert "uk-modal-container" not in html


def test_delete_backtest_modal_disables_button_for_running_backtest(monkeypatch):
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("running", ""))
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=strategy_page.BrokerKind.BACKTEST,
            start="2024-01-01",
            name="DemoStrategy",
        ),
    )
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    html = to_xml(strategy_page.delete_backtest_modal("demo-pf"))

    assert "回测正在运行，无法删除" in html
    assert "disabled" in html


def test_delete_backtest_modal_warns_for_deployed_backtest(monkeypatch):
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("finished", ""))
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=strategy_page.BrokerKind.BACKTEST,
            start="2024-01-01",
            name="DemoStrategy",
        ),
    )
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {"paper": {"status": "running"}},
    )

    html = to_xml(strategy_page.delete_backtest_modal("demo-pf"))

    assert "此回测已投放，删除报告不影响投放运行" in html
    assert 'hx-post="/strategy/backtest/demo-pf/delete"' in html
    assert 'disabled="' not in html


def test_delete_backtest_route_redirects_on_success(monkeypatch):
    monkeypatch.setattr(strategy_page.db, "delete_portfolio_cascade", lambda pid: None)
    monkeypatch.setattr(strategy_page, "delete_saved_backtest_log", lambda pid: None)
    monkeypatch.setattr(strategy_page.strategy_runtime_manager, "remove_backtest_run", lambda pid: None)
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("finished", ""))

    response = strategy_page.delete_backtest_execute("demo-pf")

    assert response.headers["hx-redirect"] == "/strategy"


def test_delete_backtest_route_rejects_running_backtest(monkeypatch):
    monkeypatch.setattr(strategy_page, "_resolve_backtest_status", lambda portfolio_id: ("running", ""))

    html = to_xml(strategy_page.delete_backtest_execute("demo-pf"))

    assert "回测正在运行，无法删除" in html


def test_build_backtest_action_cell_includes_delete_button(monkeypatch):
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    html = to_xml(strategy_page._build_backtest_action_cell("demo-pf"))

    assert 'hx-get="/strategy/backtest/demo-pf/delete/modal"' in html
    assert "trash-2" in html
