"""系统维护 - 交易日历页面测试"""

import datetime

import pyarrow as pa
import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """创建测试客户端"""
    from quantide.app_factory import create_app

    app = create_app(enforce_single_instance=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def trade_calendar_data():
    from quantide.data.models.calendar import calendar as trade_calendar
    from quantide.web.pages.system import calendar as cal_page

    original = cal_page.trade_calendar._data
    yield trade_calendar
    cal_page.trade_calendar._data = original


def _make_calendar_table(start: datetime.date, end: datetime.date) -> pa.Table:
    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        cur += datetime.timedelta(days=1)
    return pa.table({"date": dates, "is_open": [1] * len(dates)})


class TestCalendarPage:
    """交易日历页面测试"""

    def test_calendar_page_ok(self, client):
        """页面返回 200"""
        resp = client.get("/system/calendar/", follow_redirects=True)
        assert resp.status_code == 200

    def test_calendar_redirect(self, client):
        """不带尾部斜杠时 303 重定向"""
        resp = client.get("/system/calendar", follow_redirects=False)
        assert resp.status_code == 303
        assert "/system/calendar/" in resp.headers["location"]

    def test_calendar_has_layout(self, client):
        """页面包含布局元素（header, sidebar）"""
        resp = client.get("/system/calendar/", follow_redirects=True)
        assert "<title>" in resp.text.lower()
        assert "<nav" in resp.text.lower()
        assert "<aside" in resp.text.lower()

    def test_calendar_sidebar_enables_fragment_navigation(self, client):
        """系统维护 sidebar 默认启用 fragment 导航属性。"""
        resp = client.get("/system/calendar/", follow_redirects=True)

        assert 'id="layout-sidebar"' in resp.text
        assert 'id="layout-main-content"' in resp.text
        assert 'hx-boost="true"' in resp.text
        assert 'hx-target="#layout-main-content"' in resp.text
        assert 'hx-swap="outerHTML show:none"' in resp.text
        assert 'hx-push-url="true"' in resp.text

    def test_calendar_has_content(self, client):
        """页面包含日历内容"""
        resp = client.get("/system/calendar/", follow_redirects=True)
        assert "交易日历" in resp.text

    def test_calendar_navigation_links(self, client):
        """页面包含导航链接"""
        resp = client.get("/system/calendar/?year=2024&month=6", follow_redirects=True)
        assert "year=2023" in resp.text  # 上一年
        assert "year=2025" in resp.text  # 下一年

    def test_calendar_selectors_auto_submit(self, client):
        """年月选择器变更后自动提交"""
        resp = client.get("/system/calendar/?year=2024&month=6", follow_redirects=True)
        assert 'id="year-select"' in resp.text
        assert 'id="month-select"' in resp.text
        assert 'onchange="this.form.submit()"' in resp.text


class TestGetCalendarData:
    def test_dates_in_data_use_table_value(self, trade_calendar_data):
        """数据表里有明确 is_open 的日期，必须按表值返回。"""
        from quantide.web.pages.system.calendar import _get_calendar_data

        trade_calendar_data._data = _make_calendar_table(
            datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
        )
        rows = _get_calendar_data(2024, 1)

        by_date = {r["date"]: r for r in rows}
        assert by_date[datetime.date(2024, 1, 2)]["is_trading"] is True
        assert by_date[datetime.date(2024, 1, 6)]["is_trading"] is True

    def test_dates_not_in_data_fall_back_to_weekday(self, trade_calendar_data):
        """数据表里没有的日期，按周一到周五默认交易、周末默认休市兜底。"""
        from quantide.web.pages.system.calendar import _get_calendar_data

        trade_calendar_data._data = _make_calendar_table(
            datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
        )
        rows = _get_calendar_data(2024, 6)

        by_date = {r["date"]: r for r in rows}
        assert by_date[datetime.date(2024, 6, 3)]["is_trading"] is True
        assert by_date[datetime.date(2024, 6, 7)]["is_trading"] is True
        assert by_date[datetime.date(2024, 6, 8)]["is_trading"] is False
        assert by_date[datetime.date(2024, 6, 9)]["is_trading"] is False

    def test_empty_data_does_not_mark_everyday_closed(self, trade_calendar_data):
        """issue #25 复现：_data 为 None 时，不应该整月都被标为休市。"""
        from quantide.web.pages.system.calendar import _get_calendar_data

        trade_calendar_data._data = None
        rows = _get_calendar_data(2026, 6)

        by_date = {r["date"]: r for r in rows}
        assert by_date[datetime.date(2026, 6, 1)]["is_trading"] is True
        assert by_date[datetime.date(2026, 6, 5)]["is_trading"] is True
        assert by_date[datetime.date(2026, 6, 6)]["is_trading"] is False
        assert by_date[datetime.date(2026, 6, 7)]["is_trading"] is False


class TestIsCalendarDataStale:
    def test_none_data_is_stale(self, trade_calendar_data):
        """_data 为 None 时返回 True。"""
        from quantide.web.pages.system.calendar import _is_calendar_data_stale

        trade_calendar_data._data = None
        assert _is_calendar_data_stale(2024, 1) is True

    def test_month_within_range_is_not_stale(self, trade_calendar_data):
        """所请求月份完全落在数据范围内时返回 False。"""
        from quantide.web.pages.system.calendar import _is_calendar_data_stale

        trade_calendar_data._data = _make_calendar_table(
            datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)
        )
        assert _is_calendar_data_stale(2024, 6) is False

    def test_month_after_data_is_stale(self, trade_calendar_data):
        """所请求月份的最后一天超出数据表末尾时返回 True。"""
        from quantide.web.pages.system.calendar import _is_calendar_data_stale

        trade_calendar_data._data = _make_calendar_table(
            datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)
        )
        assert _is_calendar_data_stale(2025, 6) is True

    def test_partial_overlap_is_stale(self, trade_calendar_data):
        """所请求月份有部分日期超出数据表时也算陈旧。"""
        from quantide.web.pages.system.calendar import _is_calendar_data_stale

        trade_calendar_data._data = _make_calendar_table(
            datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)
        )
        assert _is_calendar_data_stale(2024, 6) is True


class TestCalendarStaleBanner:
    def test_banner_appears_when_data_is_stale(self, trade_calendar_data):
        """数据陈旧时页面显示 warning 横幅。"""
        from quantide.app_factory import create_app

        app = create_app(enforce_single_instance=False)
        with TestClient(app) as c:
            trade_calendar_data._data = _make_calendar_table(
                datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)
            )
            resp = c.get(
                "/system/calendar/?year=2025&month=6", follow_redirects=True
            )
        assert resp.status_code == 200
        assert "2024-01-01 ~ 2024-12-31" in resp.text
        assert "「立即更新」" in resp.text

    def test_banner_absent_when_data_covers_month(self, trade_calendar_data):
        """数据覆盖所选月份时，warning 横幅不出现。"""
        from quantide.app_factory import create_app

        app = create_app(enforce_single_instance=False)
        with TestClient(app) as c:
            trade_calendar_data._data = _make_calendar_table(
                datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)
            )
            resp = c.get(
                "/system/calendar/?year=2024&month=6", follow_redirects=True
            )
        assert resp.status_code == 200
        assert "2024-01-01 ~ 2024-12-31" not in resp.text


