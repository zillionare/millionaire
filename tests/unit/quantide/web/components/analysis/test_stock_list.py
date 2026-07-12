"""FR-0501 analysis StockList contract tests.

AC-FR-0501-3 and AC-FR-0501-4: rendering presents stock data and does not
invent in-component search, filter, or sort behavior.
"""

from quantide.web.components.analysis.stock_list import StockList


def _html(node: object) -> str:
    return node.__html__()  # type: ignore[attr-defined]


def test_render_shows_stock_fields_and_one_selected_row() -> None:
    """FR-0501 AC-3: rows include code/name and only the selected code is active."""
    html = _html(
        StockList(
            stocks=[
                {"symbol": "000001", "name": "平安银行"},
                {"symbol": "600000", "name": "浦发银行"},
            ],
            selected_symbol="600000",
        ).render()
    )

    assert "000001" in html
    assert "平安银行" in html
    assert "600000" in html
    assert "浦发银行" in html
    assert html.count("bg-blue-50") == 1


def test_empty_list_and_toolbar_have_explicit_output() -> None:
    """FR-0501 AC-3: empty lists and sector tools render predictable content."""
    empty_html = _html(StockList().render())
    toolbar_html = _html(StockList.toolbar("银行"))

    assert "暂无股票数据" in empty_html
    assert "成分股 (银行)" in toolbar_html
    assert "添加" in toolbar_html
    assert "导入" in toolbar_html
