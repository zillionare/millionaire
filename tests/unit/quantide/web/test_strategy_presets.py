"""Web preset page and async ablation bridge for WP-3."""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from fasthtml.common import to_xml
from starlette.datastructures import FormData

from quantide.service import factor_presets
from quantide.service.factor_presets import save_preset
from quantide.web.pages import strategy_presets


class _FakeRequest:
    def __init__(self, form: FormData) -> None:
        self._form = form

    async def form(self) -> FormData:
        return self._form


@pytest.fixture
def preset_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(factor_presets, "ensure_app_config_dir", lambda: tmp_path)
    return tmp_path


def test_preset_page_lists_persisted_preset(preset_home: Path) -> None:
    save_preset("web_preset", "Web Preset", ["ma20_slope"])

    html = to_xml(strategy_presets.preset_index(None, {"auth": "admin"}))

    assert "web_preset" in html
    assert "一键消融对比" in html


def test_ablation_route_runs_calculation_in_worker_thread(
    preset_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_preset("base", "Base", ["ma20_slope"])
    save_preset("variant", "Variant", ["ma20_slope", "bias_5"])
    report = {
        "spec": {
            "baseline_preset_id": "base",
            "variant_preset_ids": ["variant"],
            "start": "2024-01-02",
            "end": "2024-01-31",
            "principal": 1_000_000.0,
            "commission": 0.0001,
            "stamp_tax": 0.0005,
            "seed": 42,
        },
        "baseline": {},
        "variants": [
            {
                "preset_id": "variant",
                "annual_return": 0.12,
                "annual_excess": 0.02,
                "max_drawdown": -0.1,
                "sharpe": 1.2,
                "calmar": 0.8,
                "turnover": 2.0,
                "total_fees": 100.0,
            }
        ],
        "diagnostics": [],
    }
    called: list[Any] = []

    def fake_ablation(spec: Any) -> dict[str, Any]:
        called.append(spec)
        return report

    monkeypatch.setattr(strategy_presets, "run_ablation", fake_ablation)
    form = FormData(
        [
            ("baseline", "base"),
            ("variant", "variant"),
            ("start", "2024-01-02"),
            ("end", "2024-01-31"),
            ("principal", "1000000"),
        ]
    )

    html = to_xml(asyncio.run(strategy_presets.preset_ablation_run(_FakeRequest(form))))

    assert called[0].baseline_preset_id == "base"
    assert called[0].start == dt.date(2024, 1, 2)
    assert "variant" in html
    assert "2.00%" in html


def test_preset_selector_script_is_rendered_as_javascript(preset_home: Path) -> None:
    from quantide.web.pages.strategy_backtest_views import _preset_selector

    save_preset("web_preset", "Web Preset", ["ma20_slope"], label_kind="cs_rank")
    html = to_xml(_preset_selector())

    assert "option.dataset.features" in html
    assert 'data-features=\'["ma20_slope"]\'' in html
    assert "&&" in html
    assert "&amp;&amp;" not in html
