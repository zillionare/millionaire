"""Small page-object helpers for TestClient-driven UI journeys."""

from __future__ import annotations

from dataclasses import dataclass

from starlette.testclient import TestClient


@dataclass
class HtmlPage:
    """Minimal wrapper around a fetched HTML page."""

    client: TestClient
    path: str
    status_code: int
    text: str

    def contains(self, text: str) -> bool:
        return text in self.text

    def require(self, *fragments: str) -> "HtmlPage":
        for fragment in fragments:
            assert fragment in self.text, f"missing {fragment!r} in {self.path}"
        return self


class AuthPage:
    """Login page actions."""

    def __init__(self, client: TestClient):
        self._client = client

    def open_login(self) -> HtmlPage:
        response = self._client.get("/auth/login", follow_redirects=False)
        return HtmlPage(self._client, "/auth/login", response.status_code, response.text)

    def login(self, username: str, password: str, redirect_to: str = "/strategy/"):
        return self._client.post(
            "/auth/login",
            data={
                "username": username,
                "password": password,
                "redirect_to": redirect_to,
            },
            follow_redirects=False,
        )


class StrategyPage:
    """Strategy page navigation helpers."""

    def __init__(self, client: TestClient):
        self._client = client

    def open(self) -> HtmlPage:
        response = self._client.get("/strategy/", follow_redirects=True)
        return HtmlPage(self._client, "/strategy/", response.status_code, response.text)

    def open_report(self, portfolio_id: str) -> HtmlPage:
        response = self._client.get(f"/strategy/backtest/{portfolio_id}", follow_redirects=True)
        return HtmlPage(self._client, f"/strategy/backtest/{portfolio_id}", response.status_code, response.text)


class TradePage:
    """Trade page navigation helpers."""

    def __init__(self, client: TestClient):
        self._client = client

    def open_main(self) -> HtmlPage:
        response = self._client.get("/trade", follow_redirects=True)
        return HtmlPage(self._client, "/trade", response.status_code, response.text)

    def open_live(self) -> HtmlPage:
        response = self._client.get("/trade/live/", follow_redirects=False)
        return HtmlPage(self._client, "/trade/live/", response.status_code, response.text)

    def open_history_orders(self) -> HtmlPage:
        response = self._client.get("/trade/orders/history", follow_redirects=True)
        return HtmlPage(self._client, "/trade/orders/history", response.status_code, response.text)

    def open_history_trades(self) -> HtmlPage:
        response = self._client.get("/trade/records/history", follow_redirects=True)
        return HtmlPage(self._client, "/trade/records/history", response.status_code, response.text)


class SystemPage:
    """System page helpers."""

    def __init__(self, client: TestClient):
        self._client = client

    def open_accounts(self) -> HtmlPage:
        response = self._client.get("/system/accounts/", follow_redirects=True)
        return HtmlPage(self._client, "/system/accounts/", response.status_code, response.text)

    def open_jobs(self) -> HtmlPage:
        response = self._client.get("/system/jobs/", follow_redirects=True)
        return HtmlPage(self._client, "/system/jobs/", response.status_code, response.text)

    def open_market(self) -> HtmlPage:
        response = self._client.get("/system/market/", follow_redirects=True)
        return HtmlPage(self._client, "/system/market/", response.status_code, response.text)

    def open_stocks(self) -> HtmlPage:
        response = self._client.get("/system/stocks/", follow_redirects=True)
        return HtmlPage(self._client, "/system/stocks/", response.status_code, response.text)

    def open_gateway(self) -> HtmlPage:
        response = self._client.get("/system/gateway/", follow_redirects=True)
        return HtmlPage(self._client, "/system/gateway/", response.status_code, response.text)
