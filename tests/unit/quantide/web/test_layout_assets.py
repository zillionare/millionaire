"""Shared theme assets must be local and emitted once per full page load."""

from __future__ import annotations

import pytest

from tests.e2e.support.system_settings_session import system_settings_e2e_session


@pytest.mark.parametrize("path", ["/factors/", "/strategy"])
def test_primary_pages_include_shared_assets_once(path: str) -> None:
    with system_settings_e2e_session() as session:
        response = session.client.get(path)

    assert response.status_code == 200
    html = response.text
    assert html.count("/static/vendor/tailwindcss-3.4.17.js") == 1
    assert html.count("/static/vendor/htmx-1.9.12.min.js") == 1
    assert html.count("/static/vendor/franken-ui-2.0.0-core.min.css") == 1
    assert html.count("--brand: #e41815") == 1
    assert "cdn.tailwindcss.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "unpkg.com" not in html


@pytest.mark.parametrize(
    "asset",
    [
        "/static/vendor/htmx-1.9.12.min.js",
        "/static/vendor/echarts-5.4.3.min.js",
        "/static/vendor/lightweight-charts-4.1.0.standalone.production.js",
    ],
)
def test_vendored_assets_are_served(asset: str) -> None:
    with system_settings_e2e_session() as session:
        response = session.client.get(asset)

    assert response.status_code == 200
    assert response.content
