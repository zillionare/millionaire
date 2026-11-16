"""Factor research navigation and detail page tests."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import polars as pl
import pytest
from starlette.testclient import TestClient

from quantide.factors.metadata import FACTOR_METADATA
from quantide.service import factor_study, factor_tracking


@pytest.fixture()
def isolated_tracking(monkeypatch, tmp_path):
    monkeypatch.setattr(factor_tracking, "_root", lambda: tmp_path / "factor-tracking")


@pytest.fixture()
def synthetic_panel(monkeypatch):
    dates = [dt.date(2024, 1, 2) + dt.timedelta(days=index) for index in range(12)]
    rows = []
    for asset in range(120):
        for index, day in enumerate(dates):
            rows.append(
                {
                    "date": day,
                    "asset": f"{asset:06d}",
                    "bias_5": float(asset + index),
                    "open": 10.0 + asset * 0.1 + index * 0.05,
                    "close": 10.0 + asset * 0.1 + index * 0.06,
                }
            )
    panel = pl.DataFrame(rows)
    monkeypatch.setattr(factor_study, "load_factor_panel", lambda start, end: panel)
    monkeypatch.setattr(
        factor_study,
        "trading_days",
        lambda start, end: tuple(day for day in dates if start <= day <= end),
    )


@pytest.fixture(scope="module")
def client():
    from quantide.app_factory import create_app
    from tests.e2e.support.auth_fixture import sign_in_test_admin

    app = create_app(enforce_single_instance=False)
    with TestClient(app) as test_client:
        sign_in_test_admin(test_client)
        yield test_client


def test_factor_index_opens_from_header(client, isolated_tracking) -> None:
    redirect = client.get("/factors", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/factors/"

    response = client.get("/factors/")
    assert response.status_code == 200
    assert "因子总览" in response.text
    assert "bias_5" in response.text
    assert "因子" in response.text
    assert "筛选左侧因子目录" in response.text
    assert "名称或 ID" in response.text
    assert "因子总数" in response.text
    assert "多空年化中位数" in response.text
    assert "纯多年化" in response.text
    assert "当前 28 / 共 28 个因子" in response.text
    assert "还没有因子跟踪结果" in response.text
    assert "每日 18:45 自动更新" in response.text
    assert "应用筛选" in response.text
    assert "刷新全部跟踪" not in response.text
    assert "点击数值列标题可切换排序" in response.text
    assert "字段说明" in response.text
    assert 'aria-label="因子总览列表"' in response.text
    assert "sticky top-0" in response.text
    assert "sort=rank_ic" in response.text
    assert "data-sidebar-entry" in response.text


def _tracking_view(status: str, rank_ic: float | None = None):
    profile = factor_tracking.default_profile("bias_5")
    current = None
    if rank_ic is not None:
        current = {
            "data_cutoff": "2024-01-10",
            "computed_at": dt.datetime(2024, 1, 5, 15, 30),
            "primary_metrics": {
                "holding_days": 5,
                "rank_ic": {"mean": rank_ic, "t_naive": 1.2, "n_days": 3},
                "diagnostics": {"as_of_date": "2024-01-05"},
                "deciles": {
                    "d1_mean_common": 0.01,
                    "d10_mean_common": 0.02,
                    "d1_minus_d10": -0.02,
                },
            },
        }
    return factor_tracking.TrackingView(
        profile=profile,
        current=current,
        last_attempt=None,
        status=status,
    )


def test_overview_uses_raw_data_cutoff_and_keeps_evaluation_date_in_tooltip() -> None:
    from quantide.web.pages import factors_overview

    html = str(
        factors_overview.overview_row(FACTOR_METADATA["bias_5"], _tracking_view("normal", 0.1))
    )

    assert "2024-01-10" in html
    assert "评价截至 2024-01-05" in html
    assert "待重新检验" not in html


def test_factor_overview_summary_counts_computed_factors() -> None:
    from quantide.web.pages import factors

    entries = [
        (FACTOR_METADATA["bias_5"], _tracking_view("normal", 0.1)),
        (FACTOR_METADATA["rs_board_5d"], _tracking_view("stale_data")),
        (FACTOR_METADATA["bias_20"], _tracking_view("uninitialized")),
    ]
    html = str(factors._overview_summary(entries))

    assert "因子总数" in html
    assert "已有结果" in html
    assert "多空年化中位数" in html
    assert "纯多年化中位数" in html
    assert "最近更新" in html
    assert ">3<" in html
    assert ">1<" in html
    assert "+50.40%" in html
    assert "+100.80%" in html
    assert "待处理" not in html
    assert "未建立" not in html


def test_factor_overview_sorting_and_direction() -> None:
    from quantide.web.pages import factors, factors_overview

    entries = [
        (FACTOR_METADATA["bias_5"], _tracking_view("normal", 0.1)),
        (FACTOR_METADATA["rs_board_5d"], _tracking_view("normal", -0.2)),
        (FACTOR_METADATA["bias_20"], _tracking_view("uninitialized")),
    ]

    descending = factors._sort_entries(entries, "rank_ic", "desc")
    ascending = factors._sort_entries(entries, "rank_ic", "asc")

    assert [meta.factor_id for meta, _ in descending] == ["bias_5", "rs_board_5d", "bias_20"]
    assert [meta.factor_id for meta, _ in ascending] == ["rs_board_5d", "bias_5", "bias_20"]

    link = str(
        factors_overview._sort_header(
            "RankIC",
            "rank_ic",
            query="bias",
            group_filter="",
            sort_key="rank_ic",
            sort_dir="desc",
        )
    )
    assert "sort=rank_ic" in link
    assert "dir=asc" in link
    assert "q=bias" in link
    assert "按RankIC排序" in link


def test_factor_overview_row_links_factor_and_shows_annualized_return() -> None:
    from quantide.web.pages import factors, factors_overview

    meta = FACTOR_METADATA["bias_5"]
    view = _tracking_view("normal", 0.1)
    html = str(factors._overview_row(meta, view))

    assert 'href="/factors/bias_5"' in html
    assert "刷新" not in html
    assert "操作" not in html
    assert "+50.40%" in html
    assert "+100.80%" in html
    assert factors_overview.annualized_long_short(view) == pytest.approx(0.504)
    assert factors_overview.annualized_long_only(view) == pytest.approx(1.008)


def test_factor_detail_renders_card_and_report_tabs(client, isolated_tracking) -> None:
    response = client.get("/factors/bias_5")
    assert response.status_code == 200
    assert FACTOR_METADATA["bias_5"].display_name in response.text
    assert "因子卡片" in response.text
    assert "检验报告" in response.text
    assert "尚未建立跟踪" in response.text or "数据截至" in response.text


def test_unknown_factor_returns_404(client, isolated_tracking) -> None:
    response = client.get("/factors/not_a_factor")
    assert response.status_code == 404


def test_profile_update_persists_and_reloads(client, isolated_tracking, monkeypatch) -> None:
    monkeypatch.setattr("quantide.web.pages.factors.trigger_refresh", lambda factor_id: True)
    response = client.post(
        "/factors/bias_5/profile",
        data={
            "lookback": "5y",
            "primary_holding_days": "10",
            "comparison_holding_days": ["1", "10"],
            "price_field": "close",
            "enabled": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    profile = factor_tracking.load_profile("bias_5")
    assert profile.lookback == "5y"
    assert profile.primary_holding_days == 10
    assert profile.comparison_holding_days == (1, 10)
    assert profile.price_field == "close"


def test_custom_study_does_not_change_profile(client, isolated_tracking, monkeypatch) -> None:
    from quantide.web.pages import factors

    before = factor_tracking.load_profile("bias_5")
    monkeypatch.setattr(factors, "submit_study", lambda *args: "run-queued")
    monkeypatch.setattr(
        factors,
        "study_run",
        lambda run_id: SimpleNamespace(
            run_id="run-queued",
            factor_ids=("bias_5",),
            status="pending",
            phase="",
            error="",
            result=None,
        ),
    )
    response = client.post(
        "/factors/bias_5/study",
        data={
            "start": "2024-01-02",
            "end": "2024-01-08",
            "holding_days": ["1", "3"],
            "price_field": "open",
        },
    )
    assert response.status_code == 200
    assert "自定义检验任务" in response.text
    assert "已排队" in response.text
    assert factor_tracking.load_profile("bias_5") == before


def test_custom_study_can_be_explicitly_promoted(client, isolated_tracking, monkeypatch) -> None:
    monkeypatch.setattr("quantide.web.pages.factors.trigger_refresh", lambda factor_id: True)
    response = client.post(
        "/factors/bias_5/profile/from-study",
        data={
            "study_id": "study-123",
            "lookback": "3y",
            "primary_holding_days": "3",
            "holding_days": ["1", "3"],
            "price_field": "close",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    profile = factor_tracking.load_profile("bias_5")
    assert profile.source_study_id == "study-123"
    assert profile.source == "custom_study"
    assert profile.source_selected_at
    assert profile.primary_holding_days == 3
    assert profile.comparison_holding_days == (1, 3)
    assert profile.price_field == "close"


def test_profile_reset_restores_defaults(client, isolated_tracking, monkeypatch) -> None:
    monkeypatch.setattr("quantide.web.pages.factors.trigger_refresh", lambda factor_id: True)
    factor_tracking.save_profile(
        "bias_5",
        lookback="5y",
        primary_holding_days=10,
        comparison_holding_days=[1, 10],
        price_field="close",
    )
    response = client.post("/factors/bias_5/profile/reset", follow_redirects=False)
    assert response.status_code == 303
    profile = factor_tracking.load_profile("bias_5")
    defaults = factor_tracking.default_profile("bias_5")
    assert profile.lookback == defaults.lookback
    assert profile.primary_holding_days == defaults.primary_holding_days
    assert profile.comparison_holding_days == defaults.comparison_holding_days
    assert profile.price_field == defaults.price_field
    assert profile.revision == 2


def test_invalid_profile_is_rejected(client, isolated_tracking) -> None:
    response = client.post(
        "/factors/bias_5/profile",
        data={
            "lookback": "3y",
            "primary_holding_days": "4",
            "comparison_holding_days": ["4"],
            "price_field": "open",
        },
    )
    assert response.status_code == 200
    assert "invalid holding days" in response.text


def test_old_alpha_ledger_route_is_removed(client) -> None:
    response = client.get("/system/alpha-ledger")
    assert response.status_code == 404
