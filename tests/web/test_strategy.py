from types import SimpleNamespace

import pandas as pd
import pytest
from fasthtml.common import to_xml

from quantide.web.pages import strategy as strategy_page


class FakeRequest:
    def __init__(self, form_data):
        self._form_data = form_data

    async def form(self):
        return self._form_data


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
                "29.15%",
                "29.26",
                "1086.49%",
                "-0.05",
                "0.12",
                "555.86",
                "1.23",
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
            "Win Rate (Daily)",
            "Profit Factor",
            "Alpha (ann.)",
            "Beta",
            "Skewness",
            "Kurtosis",
            "Information Ratio",
        ],
    )
    monkeypatch.setattr(strategy_page, "metrics", lambda portfolio_id: stats)

    payload = strategy_page._build_metrics_payload("demo")

    assert payload["total_returns"] == pytest.approx(13.9479)
    assert payload["annual_return"] == pytest.approx(2.3339)
    assert payload["max_drawdown"] == pytest.approx(-0.0526)
    assert payload["volatility"] == pytest.approx(4.7644)
    assert payload["sharpe"] == pytest.approx(0.74)
    assert payload["sortino"] == pytest.approx(29.66)
    assert payload["calmar"] == pytest.approx(44.34)
    assert payload["win_rate"] == pytest.approx(0.2915)
    assert payload["profit_factor"] == pytest.approx(29.26)
    assert payload["alpha"] == pytest.approx(10.8649)
    assert payload["beta"] == pytest.approx(-0.05)
    assert payload["skew"] == pytest.approx(0.12)
    assert payload["kurtosis"] == pytest.approx(555.86)
    assert payload["information_ratio"] == pytest.approx(1.23)
    assert payload["avg_return"] is None
    assert strategy_page._format_percent(payload["annual_return"]) == "233.4%"
    assert strategy_page._format_percent(payload["max_drawdown"]) == "-5.3%"


def test_build_metrics_payload_keeps_missing_metrics_empty(monkeypatch):
    monkeypatch.setattr(strategy_page, "metrics", lambda portfolio_id: pd.DataFrame())

    payload = strategy_page._build_metrics_payload("demo")

    assert payload["annual_return"] is None
    assert payload["sharpe"] is None
    assert payload["win_rate"] is None
    assert strategy_page._format_percent(payload["annual_return"]) == "--"
    assert strategy_page._format_number(payload["sharpe"]) == "--"
