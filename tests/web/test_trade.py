"""测试交易模块页面"""
import datetime
import re
import tempfile
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
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
from quantide.core.enums import BidType, BrokerKind, OrderSide, OrderStatus
from quantide.data.sqlite import Order
from quantide.data.sqlite import db as _db
from quantide.service.registry import BrokerRegistry
from quantide.service.sim_broker import SimulationBroker
from tests.e2e.support.system_settings_session import system_settings_e2e_session


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
        from quantide.web.pages.trade_lightning import (
            trade_lightning_clear,
            trade_lightning_clear_modal,
            trade_lightning_create,
            trade_lightning_create_modal,
            trade_lightning_delete,
            trade_lightning_delete_modal,
            trade_lightning_edit_modal,
            trade_lightning_search,
            trade_lightning_update,
        )
        from quantide.web.pages.trade_main import (
            place_order_trade,
            search_trade_assets,
            trade_asset_stats,
            trade_live_quote,
            trade_main_page,
            trade_orders_refresh,
            trade_positions_refresh,
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
                Route("/trade/positions", trade_positions_refresh, methods=["GET"]),
                Route("/trade/orders", trade_orders_refresh, methods=["GET"]),
                Route("/trade/search", search_trade_assets, methods=["GET"]),
                Route("/trade/lightning/search", trade_lightning_search, methods=["GET"]),
                Route("/trade/asset-stats", trade_asset_stats, methods=["GET"]),
                Route("/trade/live-quote", trade_live_quote, methods=["GET"]),
                Route("/trade/order", place_order_trade, methods=["POST"]),
                Route(
                    "/trade/lightning/{portfolio_id:str}/create-modal",
                    trade_lightning_create_modal,
                    methods=["GET"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/create",
                    trade_lightning_create,
                    methods=["POST"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/clear-modal",
                    trade_lightning_clear_modal,
                    methods=["GET"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/clear",
                    trade_lightning_clear,
                    methods=["POST"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/{asset:str}/edit-modal",
                    trade_lightning_edit_modal,
                    methods=["GET"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/{asset:str}/update",
                    trade_lightning_update,
                    methods=["POST"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/{asset:str}/delete-modal",
                    trade_lightning_delete_modal,
                    methods=["GET"],
                ),
                Route(
                    "/trade/lightning/{portfolio_id:str}/{asset:str}/delete",
                    trade_lightning_delete,
                    methods=["POST"],
                ),
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
        # Issue #31 复盘：原断言 ``in [200, 302, 303]`` 太宽松，把 500 也「放行」了；
        # 收紧到具体状态码，500/503/404 等任何错误状态必须被显式断言失败。
        response = test_client.get("/trade", follow_redirects=False)
        assert response.status_code in (200, 303), (
            f"expected 200 or 303, got {response.status_code}; "
            f"body[:500]={response.text[:500]!r}"
        )

    def test_positions_refresh_route_returns_200(self, test_client):
        """Issue #29 复盘：原 ``hx_get="/trade/positions"`` 按钮没有对应路由。

        现在补齐 ``trade_positions_refresh``，点击按钮应直接 200。
        """
        response = test_client.get("/trade/positions", follow_redirects=False)
        assert response.status_code in (200, 303)

    def test_orders_refresh_route_returns_200(self, test_client):
        """``hx_get="/trade/orders"`` 按钮对应路由 (Issue #29)."""
        response = test_client.get("/trade/orders", follow_redirects=False)
        assert response.status_code in (200, 303)


class TestTodayOrdersTableWithOrders:
    """``TodayOrdersTable`` 在订单非空时也不能 500（Issue #31 复盘）.

    原 #29 修复只改了 ``status_map`` 的 enum 查表，忘了第 1461 行的
    ``o.status in [OrderStatus.PENDING, OrderStatus.PARTIAL]`` 撤单按钮判定。
    走 ``if o.status in [...]`` 路径前需要先拿到 ``o.status``，所以当
    orders 列表非空时，loop 第一次进入就会触发 ``AttributeError``。

    dev-stub 默认场景 ``orders=[]``，循环根本不进入，所以这条 bug 一直被
    隐藏；这条用例直接喂非空 orders 进去，绕开 dev-stub 的默认空列表。
    """

    def _build_order(self, status: OrderStatus) -> Order:
        return Order(
            portfolio_id="test",
            asset="000001.SZ",
            side=OrderSide.BUY,
            shares=100,
            bid_type=BidType.FIXED,
            tm=datetime.datetime(2026, 6, 4, 9, 31, 0),
            price=10.0,
            filled=0.0,
            foid=None,
            status=status,
        )

    def _render(self, orders):
        from fasthtml.common import to_xml

        from quantide.web.pages.trade_main import TodayOrdersTable

        # 注意：``str(FT_object)`` 只返回 id（fastcore 行为），
        # 要拿渲染后的 HTML 必须走 ``to_xml``。
        return to_xml(TodayOrdersTable(orders))

    def test_empty_orders_still_renders(self) -> None:
        # baseline: 空委托路径（默认 dev-stub 场景）应该能渲染
        html = self._render([])
        assert "暂无当日委托" in html

    def test_cancellable_statuses_render_cancel_button(self) -> None:
        # 这些状态对应网关的 _is_order_cancellable() 集合
        for status in (
            OrderStatus.UNREPORTED,
            OrderStatus.WAIT_REPORTING,
            OrderStatus.REPORTED,
            OrderStatus.PART_SUCC,
        ):
            html = self._render([self._build_order(status)])
            assert "撤单" in html, f"cancel button missing for {status!r}"

    def test_non_cancellable_statuses_omit_cancel_button(self) -> None:
        # 已成交 / 已撤 / 已拒绝 / 未知 不应再渲染撤单按钮
        for status in (
            OrderStatus.SUCCEEDED,
            OrderStatus.CANCELED,
            OrderStatus.JUNK,
            OrderStatus.UNKNOWN,
        ):
            html = self._render([self._build_order(status)])
            assert "撤单" not in html, f"cancel button wrongly shown for {status!r}"

    def test_regression_issue_31_does_not_500(self) -> None:
        """直接复现 #31：原代码 ``o.status in [OrderStatus.PENDING, ...]`` 在非空 orders 列表下会 ``AttributeError``。

        这条用例就是为了在 CI 上立刻抓出「PENDING/PARTIAL 这两个属性不存在」这种回归。
        """
        try:
            self._render([self._build_order(OrderStatus.REPORTED)])
        except AttributeError as e:
            pytest.fail(
                f"TodayOrdersTable 500 回归 (Issue #31): AttributeError {e!r}. "
                "检查是不是又把 OrderStatus.PENDING / OrderStatus.PARTIAL "
                "（在 OrderStatus 枚举里不存在）当 attribute 引用了。"
            )

    def test_mixed_status_orders_all_render(self) -> None:
        """混合状态下整个表能正常渲染."""
        orders = [
            self._build_order(OrderStatus.REPORTED),
            self._build_order(OrderStatus.PART_SUCC),
            self._build_order(OrderStatus.SUCCEEDED),
            self._build_order(OrderStatus.CANCELED),
        ]
        html = self._render(orders)
        # 4 行委托；每行在「代码」和「名称」两列里都出现资产代码（line 1434：
        # ``Td(o.asset), Td(o.asset),  # TODO: 获取证券名称``），所以总数是 4*2=8。
        assert html.count("000001.SZ") == 8
        # 4 行里 2 行可撤单（REPORTED + PART_SUCC）；用 ``hx-post="/trade/cancel/"``
        # 这个具体属性来精确匹配撤单按钮，避免被页面其它位置（侧栏、toast 等）的
        # 「撤单」字样误伤。
        assert html.count('hx-post="/trade/cancel/') == 2
        # 各状态文本都出现
        assert "已报" in html
        assert "部分成交" in html
        assert "已成交" in html
        assert "已撤" in html


class TestFetchPositionsOrdersViaGateway:
    """``_fetch_positions_orders_via_gateway`` 的回归测试 (Issue #31 + 用户架构要求).

    /trade 页面已切到直接调 gateway JSON API（``X-API-Key`` 鉴权），
    不再走 broker 包装层。helper 必须：
    1. 正确返回网关 JSON（成功路径）
    2. 网关 500 / 鉴权失败 / 超时一律返回 ``([], [])``，永不抛异常
       —— qmt-gateway#45 修了 500 后这条契约更不能破
    3. 空 base_url / 空 api_key 立即短路返回空，不发请求
    """

    def _helper(self):
        from quantide.web.pages.trade_main import (
            _fetch_positions_orders_via_gateway,
        )

        return _fetch_positions_orders_via_gateway

    def test_returns_empty_when_base_url_blank(self) -> None:
        positions, orders = self._helper()(
            base_url="", api_key="some-key", timeout=2
        )
        assert positions == []
        assert orders == []

    def test_returns_empty_when_api_key_blank(self) -> None:
        positions, orders = self._helper()(
            base_url="http://127.0.0.1:1", api_key="", timeout=2
        )
        assert positions == []
        assert orders == []

    def test_returns_parsed_json_from_real_dev_stub(self) -> None:
        from urllib.parse import urlparse

        from tests.e2e.support.gateway_stub import running_gateway_stub

        with running_gateway_stub(prefix="/qmt", api_key="good-key") as stub:
            host = urlparse(stub.base_url).hostname
            port = urlparse(stub.base_url).port
            base_url = f"http://{host}:{port}/qmt"
            positions, orders = self._helper()(
                base_url=base_url, api_key="good-key", timeout=2
            )
        assert isinstance(positions, list)
        assert isinstance(orders, list)
        # dev-stub 默认场景是空列表；只要返回了 list 类型就是成功的
        assert positions == []
        assert orders == []

    def test_wrong_api_key_returns_empty(self) -> None:
        from urllib.parse import urlparse

        from tests.e2e.support.gateway_stub import running_gateway_stub

        with running_gateway_stub(prefix="/qmt", api_key="good-key") as stub:
            host = urlparse(stub.base_url).hostname
            port = urlparse(stub.base_url).port
            base_url = f"http://{host}:{port}/qmt"
            # 错 key → 网关 401 → helper 必须返回空，不抛
            positions, orders = self._helper()(
                base_url=base_url, api_key="bad-key", timeout=2
            )
        assert positions == []
        assert orders == []

    def test_unreachable_server_returns_empty(self) -> None:
        # 端口 1 在大多数系统上没有被占用，连接会被立即拒绝
        positions, orders = self._helper()(
            base_url="http://127.0.0.1:1", api_key="x", timeout=1
        )
        assert positions == []
        assert orders == []


class TestCoerceGatewayOrder:
    """``_coerce_gateway_order`` 把 gateway 委托 dict 转 ``Order`` 数据类."""

    def _helper(self):
        from quantide.web.pages.trade_main import _coerce_gateway_order

        return _coerce_gateway_order

    def test_coerces_normalized_status_strings(self) -> None:
        for raw, expected in [
            ("filled", OrderStatus.SUCCEEDED),
            ("partial", OrderStatus.PART_SUCC),
            ("cancelled", OrderStatus.CANCELED),
            ("reported", OrderStatus.REPORTED),
            ("pending", OrderStatus.WAIT_REPORTING),
        ]:
            order = self._helper()(
                {
                    "qtoid": "qt-1",
                    "symbol": "000001.SZ",
                    "side": "buy",
                    "shares": 100,
                    "price": 10.0,
                    "filled": 0.0,
                    "status": raw,
                    "time": "2026-06-04 09:31:00",
                }
            )
            assert order.status is expected, f"status {raw!r} → {order.status!r}"

    def test_falls_back_to_unknown_for_garbage_status(self) -> None:
        order = self._helper()(
            {
                "qtoid": "qt-1",
                "symbol": "000001.SZ",
                "side": "buy",
                "shares": 100,
                "price": 10.0,
                "filled": 0.0,
                "status": "submitted",  # 不在映射里 → OrderStatus.UNKNOWN
                "time": "2026-06-04 09:31:00",
            }
        )
        assert order.status is OrderStatus.UNKNOWN

    def test_resolves_qtoid_from_order_id_field(self) -> None:
        order = self._helper()(
            {
                "order_id": "ext-abc",
                "symbol": "000001.SZ",
                "side": "buy",
                "shares": 100,
                "price": 10.0,
                "filled": 0.0,
                "status": "filled",
                "time": "2026-06-04 09:31:00",
            }
        )
        # 没有 qtoid 字段时 fallback 到 order_id——helper 把 order_id 当作
        # ``foid``（gateway 外部 id，透传），不再额外包前缀。
        assert order.foid == "ext-abc"

    def test_falls_back_to_uuid_when_no_id_field(self) -> None:
        order = self._helper()(
            {
                "symbol": "000001.SZ",
                "side": "buy",
                "shares": 100,
                "price": 10.0,
                "filled": 0.0,
                "status": "filled",
                "time": "2026-06-04 09:31:00",
            }
        )
        # 没有 qtoid / order_id / foid → 生成 uuid-like 字符串
        assert order.foid.startswith("gw-")
        assert len(order.foid) > 10

    def test_parses_iso_time_string(self) -> None:
        order = self._helper()(
            {
                "qtoid": "qt-1",
                "symbol": "000001.SZ",
                "side": "buy",
                "shares": 100,
                "price": 10.0,
                "filled": 0.0,
                "status": "filled",
                "time": "2026-06-04T09:31:00",
            }
        )
        assert order.tm == datetime.datetime(2026, 6, 4, 9, 31, 0)

    def test_garbage_time_falls_back_to_now(self) -> None:
        """坏 time 字符串不应让 helper 抛异常."""
        order = self._helper()(
            {
                "qtoid": "qt-1",
                "symbol": "000001.SZ",
                "side": "buy",
                "shares": 100,
                "price": 10.0,
                "filled": 0.0,
                "status": "filled",
                "time": "this is not a date",
            }
        )
        # tm 应该是 datetime.datetime 实例（不验证具体值，但应该是合理的）
        assert isinstance(order.tm, datetime.datetime)


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
        assert "Millionaire" in response.text
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
        from quantide.web.pages import home as home_page

        def _boom():
            raise RuntimeError("broker lookup unavailable")

        monkeypatch.setattr(home_page.init_wizard, "get_feature_status", _boom)

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

    def test_authenticated_header_shows_avatar_menu_actions(self, test_client):
        with test_client as client:
            login = client.post(
                "/auth/login",
                data={"username": "admin", "password": "admin123"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            response = client.get("/strategy/", follow_redirects=False)

        assert response.status_code == 200
        assert "Millionaire" in response.text
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
        assert 'id="trade-toast-slot"' in response.text
        assert "pointer-events-none absolute inset-x-6 top-0 z-50" in response.text
        assert 'class="relative p-6"' in response.text

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
        assert 'hx-target="#trade-toast-slot"' in text
        assert 'id="trade-result"' not in text

    def test_trade_panel_order_mode_changes_label(self, test_client):
        """验证下单方式切换时动态标签存在所需 DOM 元素."""
        response = test_client.get("/trade")
        text = response.text
        assert response.status_code == 200
        # 需要存在 JS 可以操作的元素
        assert 'id="value-label"' in text
        assert 'id="order-mode-amount"' in text
        assert 'id="order-mode-quantity"' in text

    def test_trade_panel_uses_limit_price_placeholder_and_change_hint(self, test_client):
        """验证限价输入框使用 placeholder，并提供涨跌幅提示区域。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert 'id="price-input"' in text
        assert 'placeholder="价格"' in text
        assert 'value="0.00"' not in text
        assert 'id="price-change-hint"' in text
        assert 'class="relative flex-1"' in text
        assert "pointer-events-none absolute right-1 top-full pt-1 text-right" in text
        assert 'class="flex items-start mb-6"' in text
        assert "function updatePriceChangeHint()" in text
        assert "function setLimitPlaceholderPrice(value)" in text
        assert "let lastQuickPricePct = null;" in text
        assert "function clearQuickPriceSelection()" in text
        assert "function getReferenceClosePrice()" in text
        assert "priceInput.placeholder = limitPlaceholderPrice || '价格';" in text
        assert "priceChangeHint.textContent = sign + deltaPct.toFixed(2) + '%';" in text
        assert "if (lastQuickPricePct !== null && priceInput.value === lastQuickPriceValue)" in text
        assert "lastQuickPriceValue = nextPrice;" in text

    def test_trade_order_errors_render_as_top_toast(self, test_client):
        """验证下单错误通过顶部 toast 返回，而不是底部行内提示。"""
        response = test_client.post(
            "/trade/order",
            data={
                "side": "BUY",
                "asset": "",
                "price_mode": "LIMIT",
                "order_mode": "AMOUNT",
                "price": "10.0",
                "value": "1",
            },
        )
        text = response.text

        assert response.status_code == 200
        assert "请输入股票代码" in text
        assert "pointer-events-auto flex min-h-8 items-start rounded-xl border px-4 py-3" in text
        assert 'role="alert"' in text
        assert "bg-red-50 text-red-700" in text
        assert 'aria-label="关闭提示"' in text
        assert "window.setTimeout(function()" in text
        assert "7000" in text
        assert "bg-red-100 rounded" not in text

    def test_trade_panel_uses_independent_lightning_routes(self, test_client):
        """验证闪电单由独立路由与容器驱动。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert 'id="trade-lightning-panel"' in text
        assert 'id="trade-lightning-modal-container"' in text
        assert "/trade/lightning/" in text
        assert "lightning-create-button" in text
        assert "lightning-clear-button" in text
        assert "/create-modal" in text
        assert "/clear-modal" in text
        assert "尚未添加闪电单股票" in text

    def test_trade_lightning_create_update_delete_and_clear_flow(self, test_client, monkeypatch):
        """验证闪电买入单支持新建、编辑、删除和清空。"""
        from quantide.web.pages import trade_lightning as lightning_page

        portfolio_id = "sim_lightning_flow"
        names = {
            "000001.SZ": "平安银行",
            "000002.SZ": "万科A",
        }
        monkeypatch.setattr(lightning_page.stock_list, "get_name", lambda asset: names[asset])
        monkeypatch.setattr(lightning_page.stock_list, "get_pinyin", lambda asset: "PINYIN")

        create_response = test_client.post(
            f"/trade/lightning/{portfolio_id}/create",
            data={
                "asset_query": "000001.SZ",
                "amount_wan": "12",
                "price_ref": "ma5",
            },
        )
        create_text = create_response.text
        assert create_response.status_code == 200
        assert "已创建闪电买入单" in create_text
        assert 'data-lightning-asset="000001.SZ"' in create_text
        assert "平安银行" in create_text
        assert "12万" in create_text
        assert "5日均线" in create_text

        update_response = test_client.post(
            f"/trade/lightning/{portfolio_id}/000001.SZ/update",
            data={"amount_wan": "8.5", "price_ref": "current"},
        )
        update_text = update_response.text
        assert update_response.status_code == 200
        assert "闪电买入单已更新" in update_text
        assert "8.5万" in update_text
        assert "最新价" in update_text
        assert 'hx-swap-oob="outerHTML"' in update_text

        delete_response = test_client.post(
            f"/trade/lightning/{portfolio_id}/000001.SZ/delete"
        )
        delete_text = delete_response.text
        assert delete_response.status_code == 200
        assert "已删除闪电买入单" in delete_text
        assert "尚未添加闪电单股票" in delete_text

        test_client.post(
            f"/trade/lightning/{portfolio_id}/create",
            data={
                "asset_query": "000001.SZ",
                "amount_wan": "10",
                "price_ref": "current",
            },
        )
        test_client.post(
            f"/trade/lightning/{portfolio_id}/create",
            data={
                "asset_query": "000002.SZ",
                "amount_wan": "15",
                "price_ref": "ma10",
            },
        )
        clear_response = test_client.post(f"/trade/lightning/{portfolio_id}/clear")
        clear_text = clear_response.text
        assert clear_response.status_code == 200
        assert "已清空 2 条闪电买入单" in clear_text
        assert "尚未添加闪电单股票" in clear_text

    def test_trade_lightning_edit_modal_renders_buy_order_form(self, test_client, monkeypatch):
        """验证闪电买入单编辑按钮会返回买入单表单弹窗。"""
        from quantide.web.pages import trade_lightning as lightning_page

        portfolio_id = "sim_lightning_edit_modal"
        monkeypatch.setattr(lightning_page.stock_list, "get_name", lambda asset: "平安银行")
        monkeypatch.setattr(lightning_page.stock_list, "get_pinyin", lambda asset: "PAYH")
        test_client.post(
            f"/trade/lightning/{portfolio_id}/create",
            data={
                "asset_query": "000001.SZ",
                "amount_wan": "6",
                "price_ref": "ma20",
            },
        )

        response = test_client.get(
            f"/trade/lightning/{portfolio_id}/000001.SZ/edit-modal"
        )
        text = response.text

        assert response.status_code == 200
        assert "修改闪电买入单" in text
        assert 'name="amount_wan"' in text
        assert 'name="price_ref"' in text
        assert "平安银行（000001）" in text
        assert "readonly" in text
        assert "20日均线" in text
        assert 'value="ma20" selected="selected"' in text
        assert "000001" in text
        assert "平安银行" in text

    def test_trade_lightning_create_and_clear_modals_render(self, test_client):
        """验证表头新建与清空操作会返回对应弹窗。"""
        create_modal = test_client.get("/trade/lightning/sim_demo/create-modal")
        create_text = create_modal.text
        assert create_modal.status_code == 200
        assert "创建闪电买入单" in create_text
        assert 'name="asset_query"' in create_text
        assert 'name="amount_wan"' in create_text
        assert 'name="price_ref"' in create_text
        assert "请输入股票代码、拼音或者名称" in create_text
        assert "买入金额" in create_text
        assert "买入价格" in create_text
        assert "/trade/lightning/search" in create_text
        assert 'id="lightning-asset-search-dropdown"' in create_text

        clear_modal = test_client.get("/trade/lightning/sim_demo/clear-modal")
        clear_text = clear_modal.text
        assert clear_modal.status_code == 200
        assert "清空闪电买入单" in clear_text
        assert "确定清空当前账户下的全部闪电买入单吗？" in clear_text

    def test_trade_lightning_search_supports_name_code_and_pinyin(self, test_client, monkeypatch):
        """验证闪电买入单搜索接口支持代码、名称和拼音。"""
        from quantide.web.pages import trade_lightning as lightning_page

        result_df = pl.DataFrame(
            {
                "asset": ["000001.SZ"],
                "name": ["平安银行"],
                "pinyin": ["PAYH"],
            }
        ).to_pandas()
        monkeypatch.setattr(
            lightning_page.stock_list,
            "fuzzy_search",
            lambda *args, **kwargs: result_df,
        )

        response = test_client.get("/trade/lightning/search?asset_query=payh")
        text = response.text

        assert response.status_code == 200
        assert "平安银行" in text
        assert "000001.SZ · PAYH" in text
        assert 'data-display="平安银行（000001.SZ）"' in text
        assert "lightning-asset-search-item" in text

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
        assert "reference-price-btn" in text
        assert 'data-ref-key="close"' in text
        assert "flex flex-col items-center justify-center gap-1" in text
        assert "disabled:opacity-40 disabled:cursor-not-allowed" in text
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

    def test_trade_panel_polls_live_quote_and_gates_speed_dial(self, test_client):
        """验证现价轮询与 speed dial 可点击状态由选股控制。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert "function refreshLiveQuote(asset)" in text
        assert "/trade/live-quote?asset=" in text
        assert "function startLiveQuotePolling(asset)" in text
        assert "function stopLiveQuotePolling()" in text
        assert "currentQuotePollId = setInterval(function()" in text
        assert "}, 3000);" in text
        assert "function setQuickPriceButtonsEnabled(enabled)" in text
        assert "function setReferencePriceButtonsEnabled(enabled)" in text
        assert "btn.disabled = !enabled;" in text
        assert "function updateQuickPriceAvailability()" in text
        assert "return getCurrentQuotePrice();" in text
        assert "referenceValues.current.textContent = selectedAssetStats.current || '';" in text
        assert "if (items.length === 1) {" in text
        assert "selectAsset(items[0]);" in text

    def test_trade_panel_allows_reference_price_buttons_to_fill_limit_price(self, test_client):
        """验证昨收/MA/现价按钮可回填限价输入框。"""
        response = test_client.get("/trade")
        text = response.text

        assert response.status_code == 200
        assert "document.querySelectorAll('.reference-price-btn').forEach(function(btn)" in text
        assert "const refKey = this.dataset.refKey;" in text
        assert "const nextPrice = selectedAssetStats[refKey] || '';" in text
        assert "priceMode.value = 'LIMIT';" in text
        assert "priceInput.value = parsed.toFixed(2);" in text

    def test_trade_live_quote_returns_cached_live_price(self, test_client, monkeypatch):
        """验证 trade live quote 接口优先返回 live quote 当前价。"""
        from quantide.web.pages import trade_main as trade_page

        monkeypatch.setattr(trade_page, "_maybe_start_live_quote", lambda: None)
        monkeypatch.setattr(
            trade_page.live_quote,
            "get_quote",
            lambda asset: {"price": 12.41} if asset == "000001.SZ" else None,
        )

        response = test_client.get("/trade/live-quote?asset=000001.SZ")
        payload = response.json()

        assert response.status_code == 200
        assert payload["asset"] == "000001.SZ"
        assert payload["current"] == "12.41"
        assert payload["visible"] is True

    def test_trade_live_quote_falls_back_to_reference_close(self, test_client, monkeypatch):
        """验证 live quote 缺失时仍返回稳定的参考现价。"""
        from quantide.web.pages import trade_main as trade_page

        monkeypatch.setattr(trade_page, "_maybe_start_live_quote", lambda: None)
        monkeypatch.setattr(trade_page.live_quote, "get_quote", lambda asset: None)
        monkeypatch.setattr(trade_page, "_resolve_trade_reference_close", lambda asset: 11.23)

        response = test_client.get("/trade/live-quote?asset=000001.SZ")
        payload = response.json()

        assert response.status_code == 200
        assert payload["current"] == "11.23"
        assert payload["visible"] is True

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


class TestDynamicHomeRedirect:

    def test_redirects_to_strategy_when_gateway_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "quantide.web.pages.home.init_wizard.get_feature_status",
            lambda: {"backtest": True, "simulation": False, "live_trading": False},
        )

        with system_settings_e2e_session() as session:
            response = session.client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/strategy/"

    def test_redirects_to_trade_live_when_gateway_enabled(self, monkeypatch):
        monkeypatch.setattr(
            "quantide.web.pages.home.init_wizard.get_feature_status",
            lambda: {"backtest": True, "simulation": True, "live_trading": True},
        )

        with system_settings_e2e_session() as session:
            response = session.client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/trade/live/"

    def test_redirects_to_strategy_when_feature_status_lookup_fails(self, monkeypatch):
        def _boom():
            raise RuntimeError("feature status unavailable")

        monkeypatch.setattr(
            "quantide.web.pages.home.init_wizard.get_feature_status",
            _boom,
        )

        with system_settings_e2e_session() as session:
            response = session.client.get("/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/strategy/"


class TestSidebarLinks:

    def test_live_link_points_to_trade_live(self):
        from quantide.web.layouts.main import HEADER_MENU

        urls = {item["title"]: item["url"] for item in HEADER_MENU}

        assert urls["实盘"] == "/trade/live/"

    def test_papertrade_legacy_redirect_targets_trade_paper(self):
        with system_settings_e2e_session() as session:
            response = session.client.get("/papertrade", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/trade/paper/"

    def test_trade_simulation_legacy_redirect_targets_trade_paper(self):
        with system_settings_e2e_session() as session:
            response = session.client.get("/trade/simulation", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/trade/paper/"


class TestPaperEntry:

    def _sim_registry(self, sims):
        reg = SimpleNamespace()
        reg.list_by_kind = lambda kind: sims if (str(kind) == "BrokerKind.SIMULATION" or getattr(kind, "value", kind) == "simulation") else []
        return reg

    def test_simulation_disabled_when_no_paper_accounts(self):
        from quantide.web.layouts.main import build_header_menu

        req = SimpleNamespace(scope={"registry": self._sim_registry([])})
        menu = build_header_menu(trade_enabled=True, req=req)
        paper = next(item for item in menu if item.get("title") == "仿真")

        assert paper.get("disabled") is True
        assert paper.get("label_override") == "未配置仿真账户"
        assert paper.get("title_attr") == "请先在 init wizard 中添加仿真账户"
        assert paper.get("children") in (None, [])

    def test_simulation_jumps_directly_with_single_paper_account(self):
        from quantide.web.layouts.main import build_header_menu

        reg = self._sim_registry([{"id": "sim_a", "name": "仿真A", "status": True}])
        req = SimpleNamespace(scope={"registry": reg})
        menu = build_header_menu(trade_enabled=True, req=req)
        paper = next(item for item in menu if item.get("title") == "仿真")

        assert paper.get("url") == "/trade/paper?account_id=sim_a"
        assert paper.get("disabled") in (None, False)
        assert not paper.get("children")

    def test_simulation_has_dropdown_with_multiple_paper_accounts(self):
        from quantide.web.layouts.main import build_header_menu

        reg = self._sim_registry([
            {"id": "sim_a", "name": "仿真A", "status": True},
            {"id": "sim_b", "name": "仿真B", "status": True},
            {"id": "sim_c", "name": "仿真C", "status": True},
        ])
        req = SimpleNamespace(scope={"registry": reg})
        menu = build_header_menu(trade_enabled=True, req=req)
        paper = next(item for item in menu if item.get("title") == "仿真")

        children = paper.get("children") or []
        assert len(children) == 3
        assert {c["url"] for c in children} == {
            "/trade/paper?account_id=sim_a",
            "/trade/paper?account_id=sim_b",
            "/trade/paper?account_id=sim_c",
        }
        names = {c["title"] for c in children}
        assert names == {"仿真A", "仿真B", "仿真C"}

    def test_simulation_falls_back_to_disabled_when_registry_unavailable(self):
        from quantide.web.layouts.main import build_header_menu

        req = SimpleNamespace(scope={})
        menu = build_header_menu(trade_enabled=True, req=req)
        paper = next(item for item in menu if item.get("title") == "仿真")

        assert paper.get("disabled") is True


class TestPaperAccountPage:

    def test_paper_route_returns_200(self):
        with system_settings_e2e_session() as session:
            response = session.client.get(
                "/trade/paper/",
                follow_redirects=False,
            )

        assert response.status_code == 200
        assert "仿真交易" in response.text

    def test_paper_with_unknown_account_id_renders_not_found(self):
        with system_settings_e2e_session() as session:
            response = session.client.get(
                "/trade/paper/?account_id=missing_account_xyz_for_test",
                follow_redirects=False,
            )

        assert response.status_code == 200
        assert "未找到该仿真账户" in response.text

    def test_paper_entry_handler_dispatches_by_account_count(self, monkeypatch):
        from quantide.web.pages import paper as paper_page

        def _build_req(sim_list, get_map=None, query_params=None):
            reg = SimpleNamespace()
            reg.list_by_kind = lambda kind: sim_list
            reg.get = lambda kind, pid: (get_map or {}).get(pid)
            return SimpleNamespace(
                scope={"registry": reg},
                query_params=query_params or {},
            )

        class _StubBroker:
            def __init__(self, account_id, name):
                self.portfolio_id = account_id
                self.portfolio_name = name
                self.positions = []
                self.total_assets = 100000
                self.cash = 100000
                self.principal = 100000

        monkeypatch.setattr(
            paper_page, "_render_paper_account",
            lambda layout, broker: f"<rendered {broker.portfolio_id}>",
        )
        monkeypatch.setattr(paper_page, "_render_empty_paper", lambda layout: "<empty>")
        monkeypatch.setattr(
            paper_page, "_render_paper_picker",
            lambda layout, sims: f"<picker {len(sims)}>",
        )

        result0 = paper_page.paper_list(_build_req([]), {})
        assert result0 == "<empty>"

        result1 = paper_page.paper_list(
            _build_req(
                [{"id": "sim_a", "name": "A", "status": True}],
                get_map={"sim_a": _StubBroker("sim_a", "A")},
            ),
            {},
        )
        assert result1 == "<rendered sim_a>"

        result2 = paper_page.paper_list(
            _build_req(
                [
                    {"id": "sim_a", "name": "A", "status": True},
                    {"id": "sim_b", "name": "B", "status": True},
                ],
            ),
            {},
        )
        assert result2 == "<picker 2>"

        result3 = paper_page.paper_list(
            _build_req(
                [],
                get_map={"sim_explicit": _StubBroker("sim_explicit", "E")},
                query_params={"account_id": "sim_explicit"},
            ),
            {},
        )
        assert result3 == "<rendered sim_explicit>"

        result4 = paper_page.paper_list(
            _build_req(
                [],
                query_params={"account_id": "ghost"},
            ),
            {},
        )
        result4_str = str(result4)
        assert "ghost" in result4_str
        assert "p-6" in result4_str


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
