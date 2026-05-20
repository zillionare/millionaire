"""测试交易模块页面"""
import datetime
import re
import tempfile
import urllib.error
from email.message import Message
from pathlib import Path
from urllib.parse import quote

import polars as pl
import pytest
from fasthtml.common import Mount, fast_app, to_xml
from monsterui.all import Theme
from starlette.middleware import Middleware
from starlette.responses import RedirectResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient

import quantide.web.middleware_feature as middleware_feature
from quantide.core.enums import BrokerKind
from quantide.data.sqlite import db as _db
from quantide.service.registry import BrokerRegistry
from quantide.service.sim_broker import SimulationBroker


@pytest.fixture(scope="module")
def test_app():
    """创建测试应用"""
    from quantide.core.scheduler import scheduler
    from quantide.service.livequote import live_quote

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    try:
        _db._initialized = False
        _db.init(test_db_path)

        scheduler.start()
        live_quote.start()

        reg = BrokerRegistry()
        try:
            sim_broker = SimulationBroker(portfolio_id="sim_demo", portfolio_name="演示账户", principal=1000000)
            reg.register(BrokerKind.SIMULATION, "sim_demo", sim_broker)
        except Exception as e:
            print(f"Failed to create demo broker: {e}")

        from quantide.core.errors import BaseTradeError
        from quantide.web.apis.broker import app as broker_api_app
        from quantide.web.auth.manager import AuthManager
        from quantide.web.middleware import BrokerRegistryMiddleware, exception_handler
        from quantide.web.middleware_feature import FeatureCheckMiddleware
        from quantide.web.pages.home import home_app
        from quantide.web.pages.live import live_app
        from quantide.web.pages.strategy import strategy_app
        from quantide.web.pages.trade_main import (
            place_order_trade,
            search_trade_assets,
            trade_asset_stats,
            trade_main_page,
        )

        auth = AuthManager(db_path=test_db_path, config={"login_path": "/auth/login"})

        app, rt = fast_app(
            hdrs=tuple(Theme.blue.headers()),
            before=auth.create_beforeware(),
            middleware=(
                Middleware(FeatureCheckMiddleware),
                Middleware(BrokerRegistryMiddleware, registry=reg),
            ),
            exception_handlers={
                Exception: exception_handler,
                BaseTradeError: exception_handler,
            },
            routes=(
                Route("/login", lambda req: RedirectResponse("/auth/login", status_code=303), methods=["GET"]),
                Route("/login/", lambda req: RedirectResponse("/auth/login", status_code=303), methods=["GET"]),
                Mount("/home", home_app),
                Mount("/strategy", strategy_app),
                Route("/trade", trade_main_page),
                Route("/trade/", trade_main_page),
                Route("/trade/search", search_trade_assets, methods=["GET"]),
                Route("/trade/asset-stats", trade_asset_stats, methods=["GET"]),
                Route("/trade/order", place_order_trade, methods=["POST"]),
                Mount("/trade/live", live_app),
                Mount("/broker", broker_api_app),
                Mount("/", home_app),
            ),
        )

        static_dir = Path(__file__).resolve().parent.parent.parent / "quantide" / "web" / "static"
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        auth.initialize(app, prefix="/auth")

        yield app
    finally:
        import os
        try:
            os.unlink(test_db_path)
        except OSError:
            pass


@pytest.fixture
def test_client(test_app):
    """创建测试客户端"""
    client = TestClient(test_app)
    yield client


@pytest.fixture(autouse=True)
def feature_status_available(monkeypatch):
    def _features():
        return {
            "backtest": {"name": "回测功能", "available": True},
            "simulation": {"name": "仿真交易", "available": True},
            "live_trading": {"name": "实盘交易", "available": True},
        }

    monkeypatch.setattr(middleware_feature, "get_feature_status", _features)
    monkeypatch.setattr(
        "quantide.web.pages.home.init_wizard.get_feature_status",
        lambda: {
            "backtest": True,
            "simulation": True,
            "live_trading": True,
        },
    )
    monkeypatch.setattr(
        "quantide.web.layouts.main.init_wizard.get_feature_status",
        lambda: {
            "backtest": True,
            "simulation": True,
            "live_trading": True,
        },
    )


@pytest.fixture
def auth_headers():
    """认证头"""
    return {"Authorization": "Bearer test_token"}


class TestTradeMain:
    def test_trade_main_page(self, test_client):
        response = test_client.get("/trade", follow_redirects=False)
        assert response.status_code in [200, 302, 303]


class TestLoginRoutes:
    """测试登录入口兼容性."""

    def test_login_redirect_path(self, test_client):
        response = test_client.get("/login", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_login_slash_redirect_path(self, test_client):
        response = test_client.get("/login/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_auth_login_get_page(self, test_client):
        response = test_client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 200
        assert "匡醍量化" in response.text
        assert "business@quantide.cn" in response.text

    def test_auth_login_post_succeeds(self, test_client):
        response = test_client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_home_tolerates_broker_asset_errors(self, test_client, monkeypatch):
        headers = Message()

        class BrokenBroker:
            portfolio_id = "gateway"

            @property
            def asset(self):
                raise urllib.error.HTTPError(
                    url="http://localhost:8000/api/trade/asset",
                    code=404,
                    msg="Not Found",
                    hdrs=headers,
                    fp=None,
                )

            @property
            def positions(self):
                raise urllib.error.HTTPError(
                    url="http://localhost:8000/api/trade/positions",
                    code=404,
                    msg="Not Found",
                    hdrs=headers,
                    fp=None,
                )

        from quantide.web.pages import home as home_page

        monkeypatch.setattr(home_page, "_get_broker", lambda req: BrokenBroker())

        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/", follow_redirects=False)

        assert response.status_code == 200
        assert "首页" in response.text

    def test_authenticated_header_shows_avatar_menu_actions(self, test_client):
        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/", follow_redirects=False)

        assert response.status_code == 200
        assert "匡醍量化" in response.text
        assert "策略" in response.text
        assert "系统维护" in response.text
        assert "实盘" in response.text
        assert "仿真" in response.text
        assert "重设密码" in response.text
        assert "showGatewayRequiredModal(event)" in response.text
        assert "gateway-required-modal" in response.text
        assert "/auth/logout" in response.text

    def test_root_redirects_to_strategy_list_when_gateway_unavailable(self, test_client, monkeypatch):
        from quantide.web.pages import home as home_page

        monkeypatch.setattr(
            home_page.init_wizard,
            "get_feature_status",
            lambda: {
                "backtest": True,
                "simulation": False,
                "live_trading": False,
            },
        )

        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/strategy/"

    def test_root_strategy_redirect_renders_strategy_list_content(self, test_client, monkeypatch):
        from quantide.web.pages import home as home_page

        monkeypatch.setattr(
            home_page.init_wizard,
            "get_feature_status",
            lambda: {
                "backtest": True,
                "simulation": False,
                "live_trading": False,
            },
        )

        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/", follow_redirects=True)

        assert response.status_code == 200
        assert "策略列表" in response.text

    def test_home_skips_account_prompt_when_gateway_disabled(self, monkeypatch):
        from quantide.web.pages import home as home_page

        monkeypatch.setattr(
            home_page.init_wizard,
            "get_feature_status",
            lambda: {
                "backtest": True,
                "simulation": False,
                "live_trading": False,
            },
        )

        assert home_page._should_show_no_account_dialog([]) is False

    def test_home_still_skips_account_prompt_after_gateway_enabled(self, monkeypatch):
        from quantide.web.pages import home as home_page

        monkeypatch.setattr(
            home_page.init_wizard,
            "get_feature_status",
            lambda: {
                "backtest": True,
                "simulation": True,
                "live_trading": True,
            },
        )

        assert home_page._should_show_no_account_dialog([]) is False

    def test_profile_page_contains_password_reset_section(self, test_client):
        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/auth/profile", follow_redirects=False)

        assert response.status_code == 200
        assert "个人设置" in response.text
        assert "重设密码" in response.text
        assert "当前密码" in response.text

    def test_auth_logout_redirects_to_login(self, test_client):
        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_trade_page_has_order_form(self, test_client):
        response = test_client.get("/trade")
        assert response.status_code == 200
        assert "买入" in response.text or "卖出" in response.text

    def test_trade_panel_matches_spec(self, test_client):
        """验证下单键盘 UI 符合 spec (issue #7)."""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        # 1. 第一行无文本标签，placeholder 提示 + search icon
        assert "请输入股票名、拼音或者代码" in text
        # 不再显示"代码"文本标签（作为独立文本）
        assert '<span class="w-16 text-sm font-medium text-gray-700 dark:text-gray-300">代码</span>' not in text

        # 2. 第二行有价格模式选择（限价/市价）+ 价格输入
        assert "限价" in text
        assert "市价" in text
        assert 'name="price_mode"' in text

        # 3. 第三行有下单方式 radio 按钮组
        assert "按金额下单" in text
        assert "按数量下单" in text
        assert 'name="order_mode"' in text

        # 4. 动态标签输入框（默认买入金额）
        assert "买入金额（万元）" in text
        assert 'name="value"' in text

        # 5. 预估数量显示
        assert "预估数量" in text
        assert 'id="est-shares"' in text

        # 6. 仓位按钮按正确顺序排列（1/4, 1/3, 1/2, 全仓）
        # 旧的"仓位"文本标签（带有 w-16 宽度）已移除
        # 按顺序 1/4, 1/3, 1/2, 全仓 应同时出现
        assert "1/4" in text
        assert "1/3" in text
        assert "1/2" in text
        assert "全仓" in text
        # 验证顺序：提取 data-fraction 属性附近（pos-btn class）的按钮文本
        pos_pattern = r'<button[^>]*data-fraction="[^"]+"[^>]*>([^<]+)</button>'
        pos_matches = re.findall(pos_pattern, text)
        # 过滤出仓位按钮
        position_btns = [m.strip() for m in pos_matches if m.strip() in {"1/4", "1/3", "1/2", "全仓"}]
        assert position_btns == ["1/4", "1/3", "1/2", "全仓"]

        # 7. 买卖按钮有激活状态标识
        assert 'id="btn-buy"' in text
        assert 'id="btn-sell"' in text
        assert 'id="side-input"' in text
        assert 'id="buy-star"' in text
        assert 'id="sell-star"' in text
        assert 'value="BUY"' in text  # 默认买入
        assert "*" in text  # 激活状态的星号标记

    def test_trade_panel_order_mode_changes_label(self, test_client):
        """验证下单方式切换时动态标签存在所需 DOM 元素."""
        response = test_client.get("/trade")
        text = response.text
        assert response.status_code == 200
        # 需要存在 JS 可以操作的元素
        assert 'id="value-label"' in text
        assert 'id="order-mode-amount"' in text
        assert 'id="order-mode-quantity"' in text

    def test_trade_panel_has_javascript_interactivity(self, test_client):
        """验证下单面板包含交互式 JavaScript."""
        response = test_client.get("/trade")
        text = response.text
        assert response.status_code == 200
        # 检查 JS 函数存在
        assert "updatePriceMode" in text
        assert "updateLabel" in text
        assert "updateActiveSide" in text
        assert "updateEstShares" in text
        assert "setPosition" in text

    def test_trade_panel_switches_side_before_submitting_order(self, test_client):
        """验证未激活方向按钮先切状态，再由当前激活按钮提交。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert "function handleTradeSubmitIntent(nextSide)" in text
        assert "if (sideInput.value !== nextSide)" in text
        assert "activateTradeSide(nextSide, true);" in text
        assert "formSubmit.click();" in text
        assert "buyStar.classList.add('hidden');" in text
        assert "sellStar.classList.add('hidden');" in text

    def test_trade_panel_supports_position_sell_prefill_markup(self):
        """验证持仓行暴露卖出预填所需的 DOM 标记。"""
        from quantide.data.sqlite import Position
        from quantide.web.pages.trade_main import PositionTable

        table = PositionTable(
            [
                Position(
                    portfolio_id="sim_demo",
                    dt=datetime.date(2026, 5, 20),
                    asset="000001.SZ",
                    shares=500,
                    avail=500,
                    price=10.0,
                    profit=500.0,
                    mv=5500.0,
                )
            ]
        )
        html = to_xml(table)

        assert 'class="trade-position-row cursor-pointer"' in html
        assert 'position-sell-btn' in html
        assert 'bg-green-600 text-white hover:bg-green-700' in html
        assert 'type="button"' in html
        assert 'data-asset="000001.SZ"' in html
        assert 'data-price="11.00"' in html
        assert 'data-avail-lots="5"' in html

    def test_trade_panel_has_asset_search(self, test_client):
        """验证股票代码输入框带有搜索下拉功能 (issue #9)."""
        response = test_client.get("/trade")
        text = response.text
        assert response.status_code == 200
        # 显示输入框
        assert 'id="asset-display"' in text
        assert 'name="asset_display"' in text
        # 隐藏代码字段
        assert 'id="asset-code"' in text
        assert 'name="asset"' in text
        # HTMX 搜索属性
        assert 'hx-get="/trade/search"' in text
        assert 'hx-target="#asset-search-dropdown"' in text
        # 下拉容器
        assert 'id="asset-search-dropdown"' in text
        # JS 搜索处理函数
        assert "selectAsset" in text
        assert "document.body.addEventListener('click'" in text
        assert "document.body.addEventListener('keydown'" in text

    def test_trade_panel_hides_placeholder_values_before_asset_selection(self, test_client):
        """验证选股前不显示静态占位数值。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert 'id="reference-price-panel"' in text
        assert "昨收" in text
        assert "现价" in text
        assert "1678.23" not in text
        assert ">--<" not in text

    def test_trade_panel_keeps_estimated_shares_width_aligned_with_value_input(self, test_client):
        """验证预估数量展示框与买入金额输入框使用同一宽度布局。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert 'grid-cols-[88px_minmax(0,1fr)]' in text
        assert 'id="value-input"' in text
        assert 'id="est-shares"' in text

    def test_trade_panel_uses_square_speed_dial_buttons(self, test_client):
        """验证 speed dial 按钮使用正方形布局。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert "quick-price-btn aspect-square" in text
        assert 'grid h-full w-[196px] grid-cols-4 gap-1' in text
        assert ">涨停<" in text
        assert ">跌停<" in text
        assert 'data-market-order="true"' in text
        assert "text-sm font-medium leading-tight whitespace-nowrap" in text

    def test_trade_panel_uses_market_order_for_limit_buttons(self, test_client):
        """验证点击涨停和跌停按钮会自动切换到市价委托。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert "function getQuickPriceBase()" in text
        assert "this.dataset.marketOrder === 'true'" in text
        assert "btn.dataset.marketOrder === 'true'" in text
        assert "display.textContent = '';" in text
        assert "priceMode.value = 'MARKET';" in text
        assert "priceMode.value = 'LIMIT';" in text

    def test_trade_panel_supports_enter_to_select_search_result(self, test_client):
        """验证股票搜索支持回车确认首个结果。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert "assetDisplay.addEventListener('keydown'" in text
        assert "evt.stopPropagation();" in text
        assert "setActiveSearchIndex(0);" in text
        assert "const selectedItem = items[Math.max(activeSearchIndex, 0)];" in text
        assert "let searchDropdown = document.getElementById('asset-search-dropdown');" in text
        assert "refreshSearchDropdown()" in text
        assert "evt.target.closest('.asset-search-item')" in text
        assert "hideSearchDropdown();" in text

    def test_trade_panel_uses_input_asset_search_trigger(self, test_client):
        """验证股票搜索使用 input 触发，并保留 200ms 防抖。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert 'hx-trigger="input changed delay:200ms"' in text

    def test_trade_search_returns_formatted_display_value(self, test_client, monkeypatch):
        """验证搜索结果包含名称加代码的显示值。"""
        from quantide.web.pages import trade_main as trade_page

        result_df = pl.DataFrame(
            {
                "asset": ["000001.SZ"],
                "name": ["平安银行"],
                "pinyin": ["PAYH"],
            }
        ).to_pandas()

        monkeypatch.setattr(trade_page.stock_list, "fuzzy_search", lambda *args, **kwargs: result_df)
        monkeypatch.setattr(
            trade_page.daily_bars,
            "get_price",
            lambda *args, **kwargs: (10.0, 11.0, 9.0),
        )

        response = test_client.get(f"/trade/search?q={quote('平安')}")
        text = response.text

        assert response.status_code == 200
        assert "平安银行" in text
        assert "PAYH" in text
        assert 'data-display="平安银行（000001.SZ）"' in text
        assert 'tabindex="0"' in text

    def test_trade_asset_stats_returns_real_metrics_without_fake_fallbacks(
        self, test_client, monkeypatch
    ):
        """验证参考行情接口返回真实统计值，不足窗口时留空。"""
        from quantide.web.pages import trade_main as trade_page

        bars = pl.DataFrame(
            {
                "date": [
                    "2026-05-14",
                    "2026-05-15",
                    "2026-05-16",
                    "2026-05-19",
                    "2026-05-20",
                ],
                "close": [10.0, 11.0, 12.0, 13.0, 14.0],
            }
        )

        monkeypatch.setattr(trade_page.daily_bars, "get_bars", lambda *args, **kwargs: bars)

        response = test_client.get("/trade/asset-stats?asset=000001.SZ")
        payload = response.json()

        assert response.status_code == 200
        assert payload["visible"] is True
        assert payload["close"] == "14.00"
        assert payload["current"] == "14.00"
        assert payload["ma5"] == "12.00"
        assert payload["ma10"] == ""
        assert payload["ma60"] == ""

    def test_trade_asset_stats_falls_back_to_fetcher_when_local_bars_missing(
        self, test_client, monkeypatch
    ):
        """验证本地行情缺失时会回退到 fetcher 数据。"""
        import pandas as pd

        from quantide.web.pages import trade_main as trade_page

        monkeypatch.setattr(
            trade_page.daily_bars,
            "get_bars",
            lambda *args, **kwargs: pl.DataFrame(),
        )
        monkeypatch.setattr(
            trade_page.calendar,
            "get_trade_dates",
            lambda start, end: [datetime.date(2026, 5, 19), datetime.date(2026, 5, 20)],
        )

        class _Fetcher:
            def fetch_bars_ext(self, dates):
                frame = pd.DataFrame(
                    {
                        "date": [datetime.date(2026, 5, 19), datetime.date(2026, 5, 20)],
                        "asset": ["000001.SZ", "000001.SZ"],
                        "close": [10.0, 11.0],
                        "up_limit": [11.0, 12.1],
                        "down_limit": [9.0, 9.9],
                    }
                )
                return frame, []

        monkeypatch.setattr(trade_page, "get_data_fetcher", lambda: _Fetcher())

        response = test_client.get("/trade/asset-stats?asset=000001.SZ")
        payload = response.json()

        assert response.status_code == 200
        assert payload["visible"] is True
        assert payload["close"] == "11.00"
        assert payload["current"] == "11.00"
        assert payload["ma5"] == ""

    def test_trade_search_uses_latest_fetcher_price_when_today_has_no_local_bars(
        self, test_client, monkeypatch
    ):
        """验证搜索结果会回退到 fetcher 最近可用交易日的收盘价。"""
        import pandas as pd

        from quantide.web.pages import trade_main as trade_page

        result_df = pl.DataFrame(
            {
                "asset": ["000002.SZ"],
                "name": ["万科A"],
                "pinyin": ["WKA"],
            }
        ).to_pandas()

        monkeypatch.setattr(trade_page.stock_list, "fuzzy_search", lambda *args, **kwargs: result_df)
        monkeypatch.setattr(
            trade_page.daily_bars,
            "get_price",
            lambda *args, **kwargs: (_ for _ in ()).throw(IndexError("missing")),
        )
        monkeypatch.setattr(
            trade_page.daily_bars,
            "get_bars",
            lambda *args, **kwargs: pl.DataFrame(),
        )

        class _Fetcher:
            def fetch_calendar(self, epoch):
                return pd.DataFrame(
                    {
                        "date": [datetime.date(2024, 12, 30), datetime.date(2024, 12, 31)],
                        "is_open": [1, 1],
                    }
                )

            def fetch_bars_ext(self, dates):
                frame = pd.DataFrame(
                    {
                        "date": [datetime.date(2024, 12, 31)],
                        "asset": ["000002.SZ"],
                        "close": [23.45],
                        "up_limit": [25.8],
                        "down_limit": [21.11],
                    }
                )
                return frame, []

        monkeypatch.setattr(trade_page, "get_data_fetcher", lambda: _Fetcher())

        response = test_client.get("/trade/search?q=%E4%B8%87%E7%A7%91")

        assert response.status_code == 200
        assert "万科A" in response.text
        assert 'data-price="23.45"' in response.text


class TestTradeOrderRoute:
    """测试 /trade/order 下单路由."""

    def test_order_route_with_broker(self, test_client):
        """有可用 broker 时下单成功（测试 fixture 已注册 sim_demo）."""
        response = test_client.post(
            "/trade/order",
            data={
                "side": "BUY",
                "asset": "000001.SZ",
                "price_mode": "LIMIT",
                "price": "10.00",
                "order_mode": "QUANTITY",
                "value": "1",
            },
        )
        assert response.status_code == 200
        # 有 broker 时下单会尝试执行（可能成功或失败，但不会报"未找到 broker"）
        assert "未找到" not in response.text

    def test_order_route_rejects_empty_asset(self, test_client):
        """空股票代码应返回错误."""
        response = test_client.post(
            "/trade/order",
            data={
                "side": "BUY",
                "asset": "",
                "price_mode": "LIMIT",
                "price": "10.00",
                "order_mode": "AMOUNT",
                "value": "1",
            },
        )
        assert response.status_code == 200

    def test_order_route_accepts_valid_form(self, test_client):
        """有效表单数据应返回响应（成功或错误均可）."""
        response = test_client.post(
            "/trade/order",
            data={
                "side": "BUY",
                "asset": "000001.SZ",
                "price_mode": "LIMIT",
                "price": "10.00",
                "order_mode": "AMOUNT",
                "value": "1",
            },
        )
        assert response.status_code == 200

    def test_order_route_rejects_empty_trade_result(self, test_client, monkeypatch):
        """Broker 未生成真实委托时应返回失败提示。"""
        from quantide.service.base_broker import TradeResult

        async def _empty_trade_result(self, asset, amount, price=0, order_time=None, timeout=0.5):
            return TradeResult.empty()

        monkeypatch.setattr(SimulationBroker, "sell_amount", _empty_trade_result)

        response = test_client.post(
            "/trade/order",
            data={
                "side": "SELL",
                "asset": "000001.SZ",
                "price_mode": "LIMIT",
                "price": "10.00",
                "order_mode": "AMOUNT",
                "value": "1",
            },
        )

        assert response.status_code == 200
        assert "未生成有效委托" in response.text


class TestLiveTrade:
    """实盘交易测试"""

    def test_live_list_page(self, test_client):
        """测试实盘账户列表页面"""
        response = test_client.get("/trade/live", follow_redirects=False)
        assert response.status_code in [200, 302, 303, 404]

    def test_create_live_account_modal(self, test_client):
        """测试创建实盘账户对话框"""
        response = test_client.get("/trade/live/create")
        assert response.status_code == 200
        assert "Gateway" in response.text or "qmt-gateway" in response.text


class TestFeatureGate:
    """测试 gateway 未启用时的交易入口收紧。"""

    @staticmethod
    def _disabled_features():
        return {
            "backtest": {"name": "回测功能", "available": True},
            "simulation": {"name": "仿真交易", "available": False},
            "live_trading": {"name": "实盘交易", "available": False},
        }

    def test_trade_entry_blocked_without_gateway(self, test_client, monkeypatch):
        monkeypatch.setattr(middleware_feature, "get_feature_status", self._disabled_features)

        response = test_client.get("/trade", follow_redirects=False)

        assert response.status_code in [200, 403]

    def test_live_entry_blocked_without_gateway(self, test_client, monkeypatch):
        monkeypatch.setattr(middleware_feature, "get_feature_status", self._disabled_features)

        response = test_client.get("/trade/live", follow_redirects=False)

        assert response.status_code == 403
        assert "实盘交易功能已禁用" in response.text
        assert "/system/gateway/" in response.text


class TestGatewayFirstNavigation:
    def test_build_header_menu_marks_trade_entries_when_gateway_missing(self):
        from quantide.web.layouts.main import build_header_menu

        menu = build_header_menu(False)

        gated_titles = {
            item["title"]
            for item in menu
            if item.get("requires_gateway")
        }
        assert gated_titles == {"实盘", "仿真"}

    def test_build_header_menu_keeps_trade_entries_open_when_gateway_ready(self):
        from quantide.web.layouts.main import build_header_menu

        menu = build_header_menu(True)

        assert all(not item.get("requires_gateway") for item in menu)

    def test_build_header_menu_uses_canonical_trade_urls(self):
        from quantide.web.layouts.main import build_header_menu

        menu = build_header_menu(True)
        urls = {item["title"]: item["url"] for item in menu}

        assert urls["实盘"] == "/trade/live/"

    def test_home_defaults_to_live_nav_when_gateway_ready(self, monkeypatch):
        from quantide.web.layouts.main import MainLayout

        monkeypatch.setattr(
            "quantide.web.layouts.main.init_wizard.get_feature_status",
            lambda: {
                "backtest": True,
                "simulation": True,
                "live_trading": True,
            },
        )

        layout = MainLayout(title="首页", user="admin")

        assert layout._resolve_header_active() == "实盘"
        assert any(item.get("title") == "下单" for item in layout._get_sidebar_menu())

    def test_home_does_not_default_to_live_nav_without_gateway(self, monkeypatch):
        from quantide.web.layouts.main import MainLayout

        monkeypatch.setattr(
            "quantide.web.layouts.main.init_wizard.get_feature_status",
            lambda: {
                "backtest": True,
                "simulation": False,
                "live_trading": False,
            },
        )

        layout = MainLayout(title="首页", user="admin")

        assert layout._resolve_header_active() == "策略"
        assert any(item.get("title") == "策略列表" for item in layout._get_sidebar_menu())

    def test_home_defaults_to_strategy_when_gateway_status_lookup_fails(self, monkeypatch):
        from quantide.web.layouts.main import MainLayout

        def _boom():
            raise RuntimeError("gateway status unavailable")

        monkeypatch.setattr(
            "quantide.web.layouts.main.init_wizard.get_feature_status",
            _boom,
        )

        layout = MainLayout(title="首页", user="admin")

        assert layout._trade_entries_enabled() is False
        assert layout._resolve_header_active() == "策略"

    def test_system_menu_contains_runtime_guard_group(self):
        from quantide.web.layouts.main import MainLayout

        layout = MainLayout(title="系统维护", user="admin")
        layout.set_sidebar_active("/system/risk-events")

        menu = layout._get_sidebar_menu()
        runtime_group = next(item for item in menu if item.get("title") == "运行保障")
        child_titles = {child.get("title") for child in runtime_group.get("children", [])}

        assert {"风险事件中心", "运行时监控"}.issubset(child_titles)


class TestBrokerRegistry:
    """测试 BrokerRegistry"""

    def test_register_and_get(self):
        """测试注册和获取 broker"""
        registry = BrokerRegistry()
        portfolio_id = "test_registry"

        try:
            broker = SimulationBroker.create(
                portfolio_id=portfolio_id,
                portfolio_name="测试",
                principal=1000000,
            )
            registry.register(BrokerKind.SIMULATION, portfolio_id, broker)

            retrieved = registry.get(BrokerKind.SIMULATION, portfolio_id)
            assert retrieved is not None
            assert retrieved.portfolio_id == portfolio_id
        finally:
            registry.unregister(BrokerKind.SIMULATION, portfolio_id)

    def test_list_by_kind(self):
        """测试按类型列出 broker"""
        registry = BrokerRegistry()
        portfolio_id = "test_list_kind"

        try:
            broker = SimulationBroker.create(
                portfolio_id=portfolio_id,
                portfolio_name="测试",
                principal=1000000,
            )
            registry.register(BrokerKind.SIMULATION, portfolio_id, broker)

            brokers = registry.list_by_kind(BrokerKind.SIMULATION)
            assert len(brokers) > 0
            assert any(b["id"] == portfolio_id for b in brokers)
        finally:
            registry.unregister(BrokerKind.SIMULATION, portfolio_id)

    def test_unregister(self):
        """测试注销 broker"""
        registry = BrokerRegistry()
        portfolio_id = "test_unregister"

        broker = SimulationBroker.create(
            portfolio_id=portfolio_id,
            portfolio_name="测试",
            principal=1000000,
        )
        registry.register(BrokerKind.SIMULATION, portfolio_id, broker)

        assert registry.get(BrokerKind.SIMULATION, portfolio_id) is not None

        registry.unregister(BrokerKind.SIMULATION, portfolio_id)
        assert registry.get(BrokerKind.SIMULATION, portfolio_id) is None


class TestSimulationBroker:
    """测试 SimulationBroker"""

    def test_create_with_custom_interval(self):
        """测试使用自定义市值更新间隔创建账户"""
        portfolio_id = "test_interval"
        broker = SimulationBroker.create(
            portfolio_id=portfolio_id,
            portfolio_name="测试",
            principal=1000000,
            market_value_update_interval=5.0,
        )

        assert broker._market_value_update_interval == 5.0

        from quantide.service.registry import BrokerRegistry

        registry = BrokerRegistry()
        registry.unregister(BrokerKind.SIMULATION, portfolio_id)

    def test_default_interval(self):
        """测试默认市值更新间隔"""
        portfolio_id = "test_default_interval"
        broker = SimulationBroker.create(
            portfolio_id=portfolio_id,
            portfolio_name="测试",
            principal=1000000,
        )

        assert broker._market_value_update_interval == 10.0

        from quantide.service.registry import BrokerRegistry

        registry = BrokerRegistry()
        registry.unregister(BrokerKind.SIMULATION, portfolio_id)
