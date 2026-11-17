"""User-visible propagation of compact PIT research diagnostics."""

from quantide.factors.universe import UniverseFilterConfig
from quantide.service.ai_agent import _study_card
from quantide.service.ai_factor_tools import _study_summary
from quantide.web.pages.factors_studio import _card


def test_study_diagnostics_reach_visible_user_card() -> None:
    config = UniverseFilterConfig(max_universe_size=20).as_dict()
    report = {
        "factor_id": "bias_5",
        "universe_filter": config,
        "universe_diagnostics": {
            "applied": True,
            "config": config,
            "by_date": {
                "2024-01-02": {
                    "warnings": ["st_history_unavailable", "market_cap_unavailable_amount_20d_cap"],
                    "size_basis": "amount_20d",
                    "assets": ["PRIVATE_ASSET_A", "PRIVATE_ASSET_B"],
                    "exclusion_counts": {"st": 1},
                    "capped": True,
                },
                "2024-01-03": {
                    "warnings": ["st_history_unavailable"],
                    "size_basis": "none",
                    "assets": ["PRIVATE_ASSET_A"],
                    "exclusion_counts": {"st": 2},
                    "capped": False,
                },
            },
        },
    }
    summary = _study_summary(report)
    assert summary["universe"]["size_bases"] == ["amount_20d", "none"]
    assert summary["universe"]["exclusion_counts"] == {"st": 3}
    card = _study_card({"ok": True, **summary}, {})
    assert card["universe_filter"] == config
    assert card["universe"] == summary["universe"]
    html = str(_card(card, "session", "bias_5"))
    for text in (
        "证券池与数据质量",
        "缺少历史 ST 状态",
        "已改按 20 日成交额",
        "生效过滤条件",
        "排除 ST：启用",
        "上市至少 60 个交易日",
        "证券池上限：20 只",
        "2 个信号日",
        "3 个合格股票日期样本",
        "20 日成交额、未截取",
    ):
        assert text in html
    assert "PRIVATE_ASSET" not in html
    assert len(str(summary)) < 3000
