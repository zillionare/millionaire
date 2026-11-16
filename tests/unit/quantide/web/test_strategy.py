import datetime
from types import SimpleNamespace

import pandas as pd
import polars as pl
import pytest
from fasthtml.common import Div, to_xml

from quantide.core.enums import BrokerKind
from quantide.data.models import Portfolio
from quantide.factors import FEATURE_COLS
from quantide.web.pages import strategy as strategy_page
from quantide.web.pages import (
    strategy_backtest_views,
    strategy_deploy_views,
    strategy_log_views,
    strategy_metrics,
    strategy_report_views,
    strategy_trade_report,
)
from tests.e2e.support.system_settings_session import system_settings_e2e_session
from tests.web_assets import script_sources


class FakeRequest:
    def __init__(self, form_data):
        self._form_data = form_data

    async def form(self):
        return self._form_data


class FakePageRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


def test_strategy_live_is_unavailable_in_ce():
    with system_settings_e2e_session() as session:
        response = session.client.get("/strategy/live", follow_redirects=False)

    assert response.status_code == 503
    assert "CE edition 暂不支持实盘交易" in response.text


def test_papertrade_redirects_to_trade_paper_with_create_app_client():
    with system_settings_e2e_session() as session:
        response = session.client.get("/papertrade", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/trade/paper/"


def test_trade_simulation_redirects_to_trade_paper_with_create_app_client(monkeypatch):
    monkeypatch.setattr(
        "quantide.web.middleware_feature.get_feature_status",
        lambda: {
            "backtest": {"name": "回测功能", "available": True},
            "simulation": {"name": "仿真交易", "available": True},
            "live_trading": {"name": "实盘交易", "available": True},
        },
    )
    with system_settings_e2e_session() as session:
        response = session.client.get("/trade/simulation", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/trade/paper/"


def test_strategy_index_page_omits_runtime_and_risk_panels(monkeypatch, db):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {},
    )

    html = to_xml(strategy_page.index(None, {"auth": "admin"}))

    assert 'id="risk-event-center"' not in html
    assert 'id="runtime-monitor"' not in html
    assert "回测区间" not in html
    assert "q-input--search" in html


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
    assert "内置示例已自动加载" in html
    assert 'id="risk-event-center"' not in html
    assert 'id="runtime-monitor"' not in html


def test_strategy_index_page_renders_hash_toggle_for_backtest_list(monkeypatch, db):
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {},
    )

    html = to_xml(strategy_page.index(None, {"auth": "admin"}))
    html += script_sources(html)

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
    html += script_sources(html)

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
    monkeypatch.setattr(strategy_metrics, "metrics", lambda *args, **kwargs: stats)
    monkeypatch.setattr(strategy_metrics, "_build_benchmark_returns", lambda portfolio_id: None)

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
    monkeypatch.setattr(strategy_metrics, "metrics", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(strategy_metrics, "_build_benchmark_returns", lambda portfolio_id: None)

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

    monkeypatch.setattr(strategy_metrics, "metrics", _fake_metrics)
    monkeypatch.setattr(
        strategy_metrics,
        "_build_benchmark_returns",
        lambda portfolio_id: baseline_returns,
    )

    strategy_page._build_metrics_payload("demo")

    assert captured["portfolio_id"] == "demo"
    assert captured["baseline_returns"] is baseline_returns


def test_resolve_backtest_status_prefers_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        strategy_metrics,
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


def test_build_backtest_rows_keeps_missing_metrics_blank(
    monkeypatch, private_edition_feature_override
):
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
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_backtest_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_backtest_views, "_strategy_version", lambda cls: "--")
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
    assert "btn btn-secondary btn-sm" in html
    assert "q-btn--paper" in html
    assert "btn btn-primary btn-sm" not in html


def test_build_backtest_name_cell_places_range_under_strategy_name() -> None:
    html = to_xml(
        strategy_page._build_backtest_name_cell(
            "DualMAStrategy",
            "demo-pf",
            "2024-01-01",
            "2024-01-31",
        )
    )

    assert "DualMAStrategy" in html
    assert "2024-01-01 ~ 2024-01-31" in html
    assert "text-xs" in html


def test_build_backtest_rows_keeps_paper_deploy_available_when_gateway_missing(
    monkeypatch, private_edition_feature_override
):
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
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_backtest_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_backtest_views, "_strategy_version", lambda cls: "--")
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    rows = strategy_page._build_backtest_rows(
        {},
        paper_available=True,
        live_available=False,
        live_unavailable_reason="请先配置交易网关，才能转实盘",
    )
    html = to_xml(rows[0])

    assert 'title="请先配置交易网关，才能转实盘"' in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/paper/modal"' in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/live/modal"' not in html
    assert html.count("pointer-events-none") == 1


def test_build_backtest_rows_disables_only_paper_deploy_when_runtime_missing(
    monkeypatch, private_edition_feature_override
):
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
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_backtest_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_backtest_views, "_strategy_version", lambda cls: "--")
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "backtest_deployment_modes",
        lambda portfolio_id: {},
    )

    rows = strategy_page._build_backtest_rows(
        {},
        paper_available=False,
        paper_unavailable_reason="运行时未初始化，无法转仿真",
        live_available=True,
    )
    html = to_xml(rows[0])

    assert 'title="运行时未初始化，无法转仿真"' in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/paper/modal"' not in html
    assert 'hx-get="/strategy/backtest/demo-pf/deploy/live/modal"' in html
    assert "pointer-events-none" in html
    assert "disabled" in html


def test_build_backtest_rows_renders_active_deployment_statuses(
    monkeypatch, private_edition_feature_override
):
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
    monkeypatch.setattr(strategy_page.db, "portfolios_all", lambda: pl.from_pandas(portfolios))
    monkeypatch.setattr(strategy_backtest_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_backtest_views, "_strategy_version", lambda cls: "--")
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
    monkeypatch.setattr(
        strategy_report_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )
    monkeypatch.setattr(strategy_report_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(
        strategy_report_views, "_build_date_axis", lambda portfolio_id: ["2024-01-02", "2024-01-03"]
    )
    monkeypatch.setattr(
        strategy_report_views,
        "_build_series_payload",
        lambda portfolio_id, date_axis: {
            "date_axis": date_axis,
            "total": [1.0, 1.1],
            "benchmark": [1.0, 1.0],
            "daily_pnl": [0.0, 0.1],
            "trade_count": [0, 1],
        },
    )
    monkeypatch.setattr(strategy_metrics, "_build_trade_rows", lambda portfolio_id, limit=200: [])
    monkeypatch.setattr(strategy_report_views, "_build_daily_positions", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_report_views, "_build_log_rows", lambda portfolio_id, limit=200: []
    )
    monkeypatch.setattr(
        strategy_log_views,
        "_build_log_meta",
        lambda portfolio_id: {
            "save_requested": False,
            "saved": False,
            "saved_path": "/tmp/demo.jsonl",
        },
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
    monkeypatch.setattr(
        strategy_report_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )
    monkeypatch.setattr(strategy_report_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_report_views, "_build_date_axis", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_report_views,
        "_build_series_payload",
        lambda portfolio_id, date_axis: {
            "date_axis": [],
            "total": [],
            "benchmark": [],
            "daily_pnl": [],
            "trade_count": [],
        },
    )
    monkeypatch.setattr(strategy_metrics, "_build_trade_rows", lambda portfolio_id, limit=200: [])
    monkeypatch.setattr(strategy_report_views, "_build_daily_positions", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_report_views,
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
        strategy_log_views,
        "_build_log_meta",
        lambda portfolio_id: {
            "save_requested": True,
            "saved": True,
            "saved_path": "/tmp/demo.jsonl",
        },
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
    monkeypatch.setattr(
        strategy_log_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )
    monkeypatch.setattr(
        strategy_log_views,
        "load_saved_backtest_logs",
        lambda portfolio_id, limit=200: (_ for _ in ()).throw(FileNotFoundError("未找到日志文件")),
    )
    monkeypatch.setattr(
        strategy_log_views,
        "_build_log_meta",
        lambda portfolio_id: {
            "save_requested": True,
            "saved": False,
            "saved_path": "/tmp/demo.jsonl",
        },
    )

    html = to_xml(strategy_page.load_saved_backtest_log_panel("demo-pf"))

    assert "未找到日志文件" in html


def test_deploy_backtest_to_paper_modal_requests_principal_confirmation():
    html = to_xml(strategy_page.deploy_backtest_to_paper_modal("demo-pf"))

    assert "确认转入仿真" in html
    assert 'id="deploy-paper-form"' in html
    assert 'name="paper_principal"' in html
    assert 'hx-post="/strategy/backtest/demo-pf/deploy/paper"' in html


def test_paper_modal_renders_readonly_params_and_fee_inputs():
    """转入弹窗：策略参数只读，仅交易费用可改."""
    html = to_xml(
        strategy_page._paper_deploy_modal(
            "demo-pf",
            principal="500000",
            config={"symbol": "000001.SZ", "fast": 5, "commission": 0.0002},
            default_config={"symbol": "000001.SZ", "fast": 3, "slow": 10},
        )
    )
    assert 'id="deploy-paper-form"' in html
    assert "策略参数（以回测为准，只读）" in html
    assert "fast" in html
    assert 'name="custom_fast"' not in html
    assert 'name="custom_commission"' in html
    assert "0.0002" in html


def test_load_backtest_run_config_resolves_default_from_strategy_class(monkeypatch):
    """#47 followup: loader 返回 dict[str, type], 按 key 匹配策略类名 + cls.default_config()."""
    from quantide.core.strategy import BaseStrategy
    from quantide.service import strategy_runtime

    class _DemoStrategy(BaseStrategy):
        @staticmethod
        def default_config() -> dict:
            return {"symbol": "000001.SZ", "fast": 3}

    fake_run = strategy_runtime.BacktestRun(
        runtime_id="backtest:demo-pf",
        portfolio_id="demo-pf",
        strategy_name="_DemoStrategy",
        config={"symbol": "000001.SZ"},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1000000,
        status="finished",
    )

    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "get_backtest_run",
        lambda portfolio_id: fake_run if portfolio_id == "demo-pf" else None,
    )
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {"_DemoStrategy": _DemoStrategy},
    )

    config, default_config = strategy_page._load_backtest_run_config("demo-pf")
    assert config == {"symbol": "000001.SZ"}
    assert default_config == {"symbol": "000001.SZ", "fast": 3}


def test_load_backtest_run_config_falls_back_to_resolve_after_restart(monkeypatch):
    """#47 followup2: 进程重启后 in-memory history 丢失, 必须回退到 _resolve_backtest_run.

    回归 Aaron 8054a94 review: _load_backtest_run_config 只看 get_backtest_run (内存),
    重启后回 ({}, None), deploy modal 失去 config 表 + POST 传空 config 覆盖
    恢复出来的 run.config.
    """
    from quantide.service import strategy_runtime

    recovered_run = strategy_runtime.BacktestRun(
        runtime_id="backtest:demo-pf",
        portfolio_id="demo-pf",
        strategy_name="DemoStrategy",
        config={"symbol": "000001.SZ", "fast": 7},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1000000,
        status="finished",
    )

    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "get_backtest_run",
        lambda portfolio_id: None,
    )
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "_resolve_backtest_run",
        lambda portfolio_id: recovered_run if portfolio_id == "demo-pf" else None,
    )

    config, default_config = strategy_page._load_backtest_run_config("demo-pf")
    assert config == {"symbol": "000001.SZ", "fast": 7}, (
        f"重启后应从 _resolve_backtest_run 恢复 config, got {config}"
    )
    assert default_config is None


def test_build_cheat_on_close_badge_uses_resolve_after_restart(monkeypatch):
    """#49 followup2: 进程重启后 in-memory history 丢失, 必须回退到 _resolve_backtest_run.

    回归 Aaron 8054a94 review: _build_cheat_on_close_badge 只看 get_backtest_run (内存),
    重启后即使持久化 specs 有 cheat metadata, 也走 hidden 分支.
    """
    from quantide.service import strategy_runtime

    recovered_run = strategy_runtime.BacktestRun(
        runtime_id="backtest:demo-pf",
        portfolio_id="demo-pf",
        strategy_name="DemoStrategy",
        config={"cheat_on_close": True},
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_cash=1000000,
        status="finished",
        cheat_on_close=True,
        cheat_on_close_time="14:30",
    )

    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "get_backtest_run",
        lambda portfolio_id: None,
    )
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "_resolve_backtest_run",
        lambda portfolio_id: recovered_run if portfolio_id == "demo-pf" else None,
    )

    badge = strategy_page._build_cheat_on_close_badge("demo-pf")
    html = to_xml(badge)
    assert "14:30" in html, f"重启后 badge 应展示持久化的 cheat_on_close_time, got {html}"
    assert 'id="cheat_badge"' in html
    assert "hidden" not in (badge.attrs.get("cls") or "")


def test_deploy_backtest_to_live_modal_requires_gateway(monkeypatch):
    monkeypatch.setattr(strategy_page, "_get_live_accounts", lambda req: [])

    html = to_xml(strategy_page.deploy_backtest_to_live_modal(FakePageRequest(), "demo-pf"))

    assert "无法转入实盘" in html
    assert "未检测到可用的实盘网关" in html


def test_deploy_backtest_to_live_modal_confirms_when_gateway_exists(
    monkeypatch, private_edition_feature_override
):
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
            kind=BrokerKind.BACKTEST,
            start="2024-01-01",
            name="DemoStrategy",
        ),
    )
    monkeypatch.setattr(
        strategy_deploy_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )
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
    monkeypatch.setattr(
        strategy_deploy_views, "_resolve_backtest_status", lambda portfolio_id: ("running", "")
    )
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
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
    monkeypatch.setattr(
        strategy_deploy_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
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
    monkeypatch.setattr(strategy_deploy_views, "delete_saved_backtest_log", lambda pid: None)
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager, "remove_backtest_run", lambda pid: None
    )
    monkeypatch.setattr(
        strategy_deploy_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )

    response = strategy_page.delete_backtest_execute("demo-pf")

    assert response.headers["hx-redirect"] == "/strategy"


def test_delete_backtest_route_rejects_running_backtest(monkeypatch):
    monkeypatch.setattr(
        strategy_deploy_views, "_resolve_backtest_status", lambda portfolio_id: ("running", "")
    )

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


def _trades_tab_page(monkeypatch, trade_rows, query=None):
    query = query or {"tab": "trades"}
    monkeypatch.setattr(
        strategy_report_views, "_resolve_backtest_status", lambda portfolio_id: ("finished", "")
    )
    monkeypatch.setattr(strategy_report_views, "_build_metrics_payload", lambda portfolio_id: {})
    monkeypatch.setattr(strategy_report_views, "_build_date_axis", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_report_views,
        "_build_series_payload",
        lambda portfolio_id, date_axis: {
            "date_axis": [],
            "total": [],
            "benchmark": [],
            "daily_pnl": [],
            "trade_count": [],
        },
    )
    monkeypatch.setattr(
        strategy_report_views, "_build_trade_pair_rows", lambda portfolio_id: trade_rows
    )
    monkeypatch.setattr(strategy_report_views, "_build_daily_positions", lambda portfolio_id: [])
    monkeypatch.setattr(
        strategy_report_views, "_build_log_rows", lambda portfolio_id, limit=200: []
    )
    monkeypatch.setattr(
        strategy_log_views,
        "_build_log_meta",
        lambda portfolio_id: {"save_requested": False, "saved": False, "saved_path": ""},
    )

    return to_xml(
        strategy_page.backtest_result(
            FakePageRequest(query),
            {"auth": "admin"},
            "demo-pf",
        )
    )


def test_backtest_result_trades_tab_shows_pairs_with_pagination(monkeypatch):
    rows = [
        {
            "asset": "002078.SZ",
            "buy_tm": "2024-01-02 09:30:00",
            "sell_tm": "2024-01-10 14:55:00",
            "buy_amount": 1250.0,
            "sell_amount": 1300.0,
            "pnl": 40.0,
            "unrealized_pnl": None,
            "return_rate": 0.032,
            "fee": 10.0,
            "status": "closed",
            "buy_tid": "tid-1",
            "sell_tid": "tid-2",
        }
    ]
    html = _trades_tab_page(monkeypatch, rows)

    assert (
        'hx-get="/strategy/backtest/demo-pf/trade/kline/modal?buy_tid=tid-1&amp;sell_tid=tid-2"'
        in html
    )
    assert 'hx-target="#modal-container"' in html
    assert "cursor-pointer" in html
    assert "金额(买入)" in html
    assert "PnL" in html
    assert "第 1/1 页" in html


def test_backtest_result_trades_tab_paginates_pairs(monkeypatch):
    rows = [
        {
            "asset": f"00000{index}.SZ",
            "buy_tm": "2024-01-02 09:30:00",
            "sell_tm": "2024-01-10 14:55:00",
            "buy_amount": 100.0,
            "sell_amount": 110.0,
            "pnl": 10.0,
            "unrealized_pnl": None,
            "return_rate": 0.1,
            "fee": 1.0,
            "status": "closed",
            "buy_tid": f"tid-{index}",
            "sell_tid": f"sell-{index}",
        }
        for index in range(150)
    ]
    html = _trades_tab_page(monkeypatch, rows, query={"tab": "trades", "page": "2"})

    assert "第 2/3 页 · 共 150 笔成交对" in html
    assert html.count("trade/kline/modal") == 50
    # 每页 50 行
    assert strategy_page.TRADE_PAIRS_PAGE_SIZE == 50


def test_trade_kline_modal_route_renders_chart(monkeypatch):
    monkeypatch.setattr(
        strategy_trade_report,
        "build_trade_kline_payload",
        lambda portfolio_id, buy_tid, sell_tid=None, panel="": {
            "asset": "002078.SZ",
            "name": "测试股",
            "pair": {
                "buy_tid": buy_tid,
                "sell_tid": sell_tid,
                "buy_tm": "2024-01-02 09:30:00",
                "sell_tm": "2024-01-10 14:55:00",
                "buy_dt": "2024-01-02",
                "sell_dt": "2024-01-10",
                "shares": 100,
                "buy_price": 12.5,
                "sell_price": 13.0,
                "buy_amount": 1250,
                "sell_amount": 1300,
                "fee": 10,
                "pnl": 40,
                "return_rate": 0.03,
                "holding_days": 8,
                "status": "closed",
                "unrealized_pnl": None,
            },
            "bars": [
                {
                    "dt": "2024-01-02",
                    "open": 12.0,
                    "high": 13.0,
                    "low": 11.5,
                    "close": 12.5,
                    "volume": 1000.0,
                    "ma": {"5": 12.0, "10": 12.0, "20": 12.0, "30": 12.0, "120": 12.0, "250": 12.0},
                }
            ],
            "markers": [],
            "ma_periods": [5, 10, 20, 30, 120, 250],
            "lookback_bars": 120,
            "initial_bars": 1,
            "post_trend_bars": 0,
            "post_sell_trend": False,
            "buy_attribution": {
                "asset": "002078.SZ",
                "date": "2024-01-02",
                "engine": "LightGBM",
                "score": 1.5,
                "baseline": -0.1,
                "rank": 3,
                "cross_section": 100,
                "features": [{"name": "bias_5", "value": -0.0229, "z": -1.16, "total": 0.05}],
            },
            "sell_attribution": {
                "asset": "002078.SZ",
                "date": "2024-01-10",
                "engine": "LightGBM",
                "score": -0.8,
                "baseline": -0.1,
                "rank": 88,
                "cross_section": 100,
                "features": [{"name": "bias_5", "value": 0.0311, "z": -1.2, "total": -0.06}],
            },
            "available_panels": ["summary", "buy", "sell"],
            "active_panel": "summary",
        },
    )

    html = to_xml(
        strategy_page.trade_kline_modal(
            FakePageRequest({"buy_tid": "tid-1", "sell_tid": "tid-2"}), "demo-pf"
        )
    )

    assert 'id="trade-kline-chart"' in html
    assert "echarts.init" in html
    assert "MA250" in html
    assert "买入金额" in html
    assert "收益率" in html
    assert "买入日期" in html
    assert "卖出日期" in html
    assert "摘要" in html
    assert "买入归因" in html
    assert "卖出归因" in html
    # 摘要页不展示归因明细
    assert "bias_5" not in html
    assert "PnL" not in html
    assert 'onclick="closeStrategyModal()"' in html


def test_trade_kline_modal_route_reports_missing_trade(monkeypatch):
    monkeypatch.setattr(
        strategy_trade_report,
        "build_trade_kline_payload",
        lambda portfolio_id, buy_tid, sell_tid=None, panel="": None,
    )

    html = to_xml(
        strategy_page.trade_kline_modal(FakePageRequest({"buy_tid": "missing"}), "demo-pf")
    )

    assert "未找到该笔成交记录" in html
    assert "trade-kline-chart" not in html


def test_parse_params_skips_blank_values():
    form = {
        "param_top_k": "3",
        "param_take_profit_pct": "",
        "param_use_broker_barriers": "false",
        "param_slippage_pct": "0.002",
        "start_date": "2024-01-01",
    }

    config = strategy_page._parse_params(form)

    assert config == {
        "top_k": 3,
        "use_broker_barriers": False,
        "slippage_pct": 0.002,
    }


def test_trade_kline_modal_title_exposes_prev_next_arrows(monkeypatch):
    from quantide.service.trade_pairs import TradePair

    def _pair(buy_tid: str, sell_tid: str | None) -> TradePair:
        return TradePair(
            asset="002078.SZ",
            buy_tid=buy_tid,
            sell_tid=sell_tid,
            buy_tm=datetime.datetime(2024, 1, 2, 9, 30),
            sell_tm=datetime.datetime(2024, 1, 10, 14, 55) if sell_tid else None,
            shares=100.0,
            buy_price=12.5,
            sell_price=13.0 if sell_tid else None,
            buy_amount=1250.0,
            sell_amount=1300.0 if sell_tid else 0.0,
            fee=10.0,
            pnl=40.0 if sell_tid else None,
            return_rate=0.03 if sell_tid else None,
            holding_days=8 if sell_tid else None,
            status="closed" if sell_tid else "open",
        )

    pairs = [_pair("buy-1", "sell-1"), _pair("buy-2", "sell-2"), _pair("buy-3", "sell-3")]
    monkeypatch.setattr(
        strategy_trade_report,
        "_ordered_trade_pairs",
        lambda portfolio_id: pairs,
    )

    title = strategy_page._trade_kline_modal_title(
        "demo-pf", {"name": "测试", "asset": "002078.SZ"}, "buy-2", "sell-2"
    )
    html = to_xml(title)

    assert "上一笔成交对" in html
    assert "下一笔成交对" in html
    assert "buy_tid=buy-1" in html
    assert "buy_tid=buy-3" in html


class _ModalDemoStrategy:
    """演示用策略：同时包含策略参数与交易参数。"""

    SUPPORTS_FEATURE_SELECTION = True

    @staticmethod
    def default_config():
        return {
            "top_k": 5,
            "universe_size": 300,
            "take_profit_pct": 0.15,
            "stop_loss_pct": 0.06,
            "horizon": 3,
            "slippage_pct": 0.001,
            "use_broker_barriers": True,
        }


def test_backtest_modal_shows_feature_step_for_feature_strategy(monkeypatch):
    """支持特征选择的策略显示参数、因子、风控三步。"""
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {"DemoStrategy": _ModalDemoStrategy},
    )

    html = to_xml(strategy_page.backtest_modal("DemoStrategy"))

    assert 'data-bt-step="1"' in html
    assert 'data-bt-step="2"' in html
    assert 'data-bt-step="3"' in html
    assert "选择因子" in html
    # 因子勾选项：全部因子默认勾选
    assert html.count('name="param_features"') == len(FEATURE_COLS)
    assert 'value="bias_5"' in html
    # 步骤切换脚本
    assert "showBacktestStep" in html
    assert "第 1 / 3 步" in html
    assert "下一步：选择因子" in html
    assert "q-btn--outline-brand" in html
    assert "开始运行" in html


def test_backtest_modal_skips_feature_step_for_non_feature_strategy(monkeypatch):
    """均线等不使用因子的策略只显示参数、风控两步。"""
    from quantide.strategies.example.monthly_ma import MonthlyMAStrategy

    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {"MonthlyMAStrategy": MonthlyMAStrategy},
    )

    html = to_xml(strategy_page.backtest_modal("MonthlyMAStrategy"))

    assert 'data-bt-step="1"' in html
    assert 'data-bt-step="2"' in html
    assert 'data-bt-step="3"' not in html
    assert "选择因子" not in html
    assert 'name="param_features"' not in html
    assert "第 1 / 2 步" in html
    assert "下一步：选择风控" in html
    assert "下一步：选择因子" not in html
    assert "q-btn--outline-brand" in html
    assert "开始运行" in html


def test_parse_params_collects_repeated_feature_values():
    """同名多值字段（因子勾选）解析成列表。"""
    form = {
        "param_features": ["bias_5", "ma20_slope"],
        "param_top_k": "3",
    }

    class _Form(dict):
        def getlist(self, key):
            value = self[key]
            return value if isinstance(value, list) else [value]

    config = strategy_page._parse_params(_Form(form))

    assert config["features"] == ["bias_5", "ma20_slope"]
    assert config["top_k"] == 3


def test_parse_params_keeps_single_value_as_scalar():
    """单值字段仍然是标量。"""

    class _Form(dict):
        def getlist(self, key):
            return [self[key]]

    config = strategy_page._parse_params(_Form({"param_top_k": "5"}))

    assert config == {"top_k": 5}


def test_params_to_text_compacts_list_values() -> None:
    """列表型参数（如因子选择）只显示项数，避免刷屏。"""
    text = strategy_page._params_to_text(
        {"top_k": 5, "features": ["a", "b", "c"], "commission": 0.0001}
    )

    assert "top_k=5" in text
    assert "features=3项" in text
    assert "commission=0.0001" in text


def test_foldable_cell_wraps_long_text() -> None:
    """过长的参数文本折叠，点击展开。"""
    short = strategy_page._foldable_cell("top_k=5")
    long_text = "x" * 200
    long_cell = strategy_page._foldable_cell(long_text)

    assert "<details" not in str(short)
    assert "<details" in str(long_cell)
    assert "<summary" in str(long_cell)
    assert long_text in str(long_cell)


def test_resolve_backtest_status_repairs_stale_running_state(monkeypatch):
    """进程内没有运行记录、且运行没到结束日 → 视为异常中断并修复状态。"""
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "get_backtest_run",
        lambda portfolio_id: None,
    )
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
            start="2024-01-02",
            end="2024-06-30",
            name="DemoStrategy",
            status=True,
        ),
    )
    monkeypatch.setattr(
        strategy_page.db,
        "query_assets",
        lambda portfolio_id=None: pl.DataFrame(
            {"dt": [datetime.date(2024, 5, 6)], "total": [100.0]}
        ),
    )
    repaired: list[str] = []
    monkeypatch.setattr(
        strategy_page.db,
        "update_portfolio",
        lambda portfolio_id, **updates: repaired.append(portfolio_id),
    )

    status, error = strategy_page._resolve_backtest_status("demo-pf")

    assert status == "failed"
    assert "异常中断" in error
    assert repaired == ["demo-pf"]


def test_resolve_backtest_status_keeps_running_when_not_provable(monkeypatch):
    """无法证明已失效时保持"运行中"语义（AC-NFR1101-01）。"""
    monkeypatch.setattr(
        strategy_page.strategy_runtime_manager,
        "get_backtest_run",
        lambda portfolio_id: None,
    )
    fake_portfolio = SimpleNamespace(status=True)
    monkeypatch.setattr(
        strategy_page.db,
        "get_portfolio",
        lambda portfolio_id: fake_portfolio,
    )

    status, error = strategy_page._resolve_backtest_status("demo-pf")

    assert status == "running"
    assert error == ""


def test_trade_pairs_page_size_is_50() -> None:
    """交易详情每页 50 行。"""
    assert strategy_page.TRADE_PAIRS_PAGE_SIZE == 50


def test_trade_pairs_sort_by_return_rate() -> None:
    """按收益率排序：升序最差在前，未平仓（无收益率）排最后。"""
    rows = [
        {"asset": "A", "return_rate": 0.05, "buy_tm": "2024-01-03"},
        {"asset": "B", "return_rate": -0.02, "buy_tm": "2024-01-02"},
        {"asset": "C", "return_rate": None, "buy_tm": "2024-01-01"},
        {"asset": "D", "return_rate": 0.01, "buy_tm": "2024-01-04"},
    ]

    asc = strategy_page._sort_trade_pair_rows(rows, "return", "asc")
    desc = strategy_page._sort_trade_pair_rows(rows, "return", "desc")

    assert [r["asset"] for r in asc] == ["B", "D", "A", "C"]
    assert [r["asset"] for r in desc] == ["A", "D", "B", "C"]
    # 非收益率排序时保持原顺序
    assert [r["asset"] for r in strategy_page._sort_trade_pair_rows(rows, "", "asc")] == [
        "A",
        "B",
        "C",
        "D",
    ]


def test_trades_tab_renders_sort_link_and_jump_box(monkeypatch):
    """交易详情页提供按收益率排序的表头与跳页输入框。"""
    rows = [
        {
            "asset": "002078.SZ",
            "buy_tm": "2024-01-02 09:30:00",
            "sell_tm": "2024-01-10 14:55:00",
            "buy_amount": 1250.0,
            "pnl": 40.0,
            "unrealized_pnl": None,
            "return_rate": 0.032,
            "fee": 10.0,
            "status": "closed",
            "buy_tid": "tid-1",
            "sell_tid": "tid-2",
        }
    ]
    html = _trades_tab_page(
        monkeypatch, rows, query={"tab": "trades", "sort": "return", "dir": "desc"}
    )

    assert "sort=return" in html
    assert "跳页" not in html  # 占位，确保不是误加
    assert "跳转" in html
    assert 'name="page"' in html
    assert 'value="1"' in html


def test_backtest_list_shows_only_changed_params(monkeypatch):
    """回测报告列表的参数列只显示与默认不同的参数。"""
    from quantide.service import backtest_params

    backtest_params.default_backtest_params(_ModalDemoStrategy)
    config = {
        "top_k": 5,
        "keep_top_n": 15,
        "universe_size": 2000,
        "universe_mode": "market_cap_trim",
        "market_cap_trim_pct": 0.05,
        "universe_rebalance_days": 20,
        "train_window": 45,
        "horizon": 3,
        "retrain_days": 5,
        "stop_loss_pct": 0.06,
        "take_profit_pct": 0.15,
        "slippage_pct": 0.001,
        "use_lightgbm": True,
        "use_broker_barriers": True,
        "use_alpha_exit": False,
        "commission": 0.0001,
        "stamp_duty": 0.0005,
        "transfer_fee": 1e-05,
        "min_commission": 5.0,
        "features": list(FEATURE_COLS),
    }
    monkeypatch.setattr(
        strategy_page.db,
        "portfolios_all",
        lambda: __import__("polars").DataFrame(
            {
                "portfolio_id": ["pf-1"],
                "kind": ["bt"],
                "name": ["DemoStrategy"],
                "start": ["2024-01-02"],
                "end": ["2024-06-30"],
                "info": [__import__("json").dumps({"config": config})],
            }
        ),
    )
    monkeypatch.setattr(
        strategy_page.strategy_loader,
        "load_from_cache",
        lambda: {"DemoStrategy": _ModalDemoStrategy},
    )
    monkeypatch.setattr(strategy_backtest_views, "_build_metrics_payload", lambda portfolio_id: {})

    rows = strategy_page._build_backtest_rows({"DemoStrategy": _ModalDemoStrategy})
    html = str(rows[0])

    assert "use_alpha_exit=False" in html
    assert "top_k=5" not in html
    assert "features" not in html
    assert "commission" not in html


def test_strategy_dialog_uses_golden_ratio_max_height():
    """对话框宽度/最大高度比约为 1.618，正文可滚动。"""
    html = to_xml(
        strategy_page._strategy_dialog_modal(
            "标题",
            Div("内容"),
            Div("底部"),
            modal_id="golden-modal",
            width_cls="max-w-2xl",
        )
    )
    assert "max-w-2xl" in html
    assert "max-h-[26rem]" in html
    assert "overflow-y-auto" in html
