"""系统维护 - 行情数据页面测试"""

import datetime
import html

import polars as pl
import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """创建测试客户端"""
    from quantide.app_factory import create_app
    from tests.e2e.support.auth_fixture import sign_in_test_admin

    app = create_app(enforce_single_instance=False)
    with TestClient(app) as c:
        sign_in_test_admin(c)
        yield c


class TestMarketPage:
    """行情数据页面测试"""

    def test_market_page_ok(self, client):
        """页面返回 200"""
        resp = client.get("/system/market/", follow_redirects=True)
        assert resp.status_code == 200

    def test_market_redirect(self, client):
        """不带尾部斜杠时 303 重定向"""
        resp = client.get("/system/market", follow_redirects=False)
        assert resp.status_code == 303
        assert "/system/market/" in resp.headers["location"]

    def test_market_has_layout(self, client):
        """页面包含布局元素"""
        resp = client.get("/system/market/", follow_redirects=True)
        assert "<nav" in resp.text.lower()
        assert "<aside" in resp.text.lower()

    def test_market_has_filter(self, client):
        """页面包含筛选条件"""
        resp = client.get("/system/market/", follow_redirects=True)
        assert "证券代码" in resp.text

    def test_market_has_adjust_toggle(self, client):
        """默认显示不复权，点击后应切换到前复权。"""
        resp = client.get("/system/market/", follow_redirects=True)
        text = html.unescape(resp.text)
        assert ">不复权</a>" in text
        assert ">前复权</a>" not in text
        assert ">复权</a>" not in text
        assert "复权方式" not in text
        assert "adjust=qfq" in text

    def test_market_controls_are_compact_single_row(self, client):
        """查询控件保持单行，输入框与按钮高度一致。"""
        resp = client.get("/system/market/", follow_redirects=True)
        text = resp.text
        assert text.count("height:36px;width:144px") == 3
        assert "height:36px;width:72px" in text
        assert "q-btn h-9 min-w-[72px] whitespace-nowrap" in text
        assert "uk-input" not in text
        assert "uk-btn" not in text
        assert "card p-4 mb-3" not in text
        assert "未提供筛选条件" not in text

    def test_market_adjust_toggle_disables_qfq_on_click(self, client):
        """前复权状态显示红色边框，点击后回到不复权。"""
        resp = client.get("/system/market/?adjust=qfq", follow_redirects=True)
        text = html.unescape(resp.text)
        assert ">前复权</a>" in text
        assert ">不复权</a>" not in text
        assert "立即刷新" not in text
        assert "bg-gray-900" not in text
        assert "text-[#e41815] border-[#e41815] font-semibold" in text
        assert (
            'href="/system/market/?code=&start_date=&end_date=&adjust=none&page=1&per_page=20"'
            in text
        )

    def test_market_optional_columns_default_hidden(self, client):
        """成交、涨跌停、ST 默认隐藏并显示对应开启按钮。"""
        resp = client.get("/system/market/", follow_redirects=True)
        text = resp.text
        assert "显示成交" in text
        assert "显示涨跌停" in text
        assert "显示ST" in text
        assert ">成交量</th>" not in text
        assert ">成交额</th>" not in text
        assert ">涨停价</th>" not in text
        assert ">跌停价</th>" not in text
        assert ">ST</th>" not in text

    def test_market_optional_columns_toggle_and_preserve_query(self, client):
        """开启可选项后显示隐藏按钮、列和保留状态的查询链接。"""
        resp = client.get(
            "/system/market/?adjust=qfq&show_turnover=1&show_limits=1&show_st=1",
            follow_redirects=True,
        )
        text = html.unescape(resp.text)
        assert "隐藏成交" in text
        assert "隐藏涨跌停" in text
        assert "隐藏ST" in text
        assert ">成交量</th>" in text
        assert ">成交额</th>" in text
        assert ">涨停价</th>" in text
        assert ">跌停价</th>" in text
        assert ">ST</th>" in text
        assert 'name="show_turnover" value="1"' in text
        assert 'name="show_limits" value="1"' in text
        assert 'name="show_st" value="1"' in text
        assert "show_turnover=1" in text
        assert "show_limits=1" in text
        assert "show_st=1" in text


def test_market_defaults_to_latest_page_data(monkeypatch):
    """无筛选条件时默认返回最近一个交易日首页数据"""
    from quantide.web.pages.system import market as market_page

    sample = pl.DataFrame(
        [
            {
                "date": datetime.date(2024, 6, 3),
                "asset": "000001.SZ",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 1000.0,
                "amount": 10000.0,
                "up_limit": 11.0,
                "down_limit": 9.0,
                "adjust": 1.0,
                "is_st": False,
            },
            {
                "date": datetime.date(2024, 6, 3),
                "asset": "000002.SZ",
                "open": 20.0,
                "high": 20.5,
                "low": 19.8,
                "close": 20.2,
                "volume": 2000.0,
                "amount": 20000.0,
                "up_limit": 22.0,
                "down_limit": 18.0,
                "adjust": 1.0,
                "is_st": False,
            },
        ]
    )

    monkeypatch.setattr(market_page.daily_bars, "get_bars", lambda *args, **kwargs: sample)

    data, total = market_page._get_market_data(page=1, per_page=20)

    assert total == 2
    assert data[0]["asset"] == "000001.SZ"
    assert data[1]["asset"] == "000002.SZ"
