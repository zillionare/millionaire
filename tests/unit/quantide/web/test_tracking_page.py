"""dry-run 对照页基础渲染测试。"""

from __future__ import annotations

from tests.e2e.support.system_settings_session import system_settings_e2e_session


def test_tracking_page_renders_empty_state():
    with system_settings_e2e_session() as session:
        response = session.client.get("/tracking/unknown-account")
    assert response.status_code == 200
    assert "dry-run 对照" in response.text
    assert "暂无跟踪数据" in response.text


def test_tracking_page_renders_30m_bars_and_gaps(tmp_path, monkeypatch):
    import datetime
    from types import SimpleNamespace

    import quantide.web.pages.tracking as module
    from quantide.service.strategy_tracking import TrackingStore

    store = TrackingStore(tmp_path / "page-track.db")
    store.ensure_run(
        "paper:p1",
        "p1",
        start_date=datetime.date(2026, 10, 27),
        fill_timing="next_open",
        bar_interval="30m",
    )
    store.update_run("paper:p1", gap_slots=["2026-10-27T10:30:00+08:00"])
    store.save_bar(
        runtime_id="paper:p1",
        portfolio_id="p1",
        bar_slot="2026-10-27T10:00:00+08:00",
        bar_interval="30m",
        source="dry_run",
        nav=100100.0,
        cash=90000.0,
        market_value=10100.0,
        positions=[{"asset": "000001.SZ", "shares": 1000, "avail": 1000}],
    )
    store.save_bar(
        runtime_id="paper:p1",
        portfolio_id="p1",
        bar_slot="2026-10-27T10:00:00+08:00",
        bar_interval="30m",
        source="actual",
        nav=99950.0,
        cash=90000.0,
        market_value=9950.0,
        positions=[{"asset": "000001.SZ", "shares": 900, "avail": 900}],
    )
    store.save_bar(
        runtime_id="paper:p1",
        portfolio_id="p1",
        bar_slot="2026-10-27T10:30:00+08:00",
        bar_interval="30m",
        source="dry_run",
        nav=100200.0,
        cash=90000.0,
        market_value=10200.0,
        positions=[{"asset": "000001.SZ", "shares": 1000, "avail": 1000}],
    )
    monkeypatch.setattr(module, "tracking_store", store)
    response = module.tracking_page(SimpleNamespace(path_params={"portfolio_id": "p1"}, scope={}))
    html = response.body.decode()
    assert "逐 30m bar" in html
    assert "2026-10-27 10:00" in html
    assert "2026-10-27 10:30" in html
    assert "100,100.00" in html
    assert "99,950.00" in html
    assert "150.00" in html
    assert "000001.SZ 1000" in html
    assert "000001.SZ 900" in html
    assert "待回补缺口 1 个" in html
    assert "2026-10-27T10:30:00+08:00" in html
    assert "实际缺失 1 个" in html
    assert "实际缺失" in html.split("实际净值", 1)[-1]
