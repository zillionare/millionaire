"""系统维护 - 因子台账模块。

用单因子检验（:mod:`quantide.factors.alphatest`）查看各因子与前瞻收益的
截面相关性，作为因子取舍与模型体检的依据。
"""

import datetime
import math

from fasthtml.common import *
from fasthtml.common import (
    Any,
    Div,
    P,
    Span,
    Thead,
    Tr,
)

# Use FastHTML's plain Label for form elements to avoid MonsterUI's uk-label styling
from fasthtml.common import Label as _Label
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    Button,
    Form,
    Input,
    Table,
    Tbody,
    Th,
)

from quantide.factors import FEATURE_COLS, FEATURE_GROUPS
from quantide.factors.alphatest import (
    SingleFactorResult,
    load_factor_panel,
    study_factors,
)
from quantide.web.application import fast_app
from quantide.web.layouts.main import MainLayout
from quantide.web.theme import PRIMARY_COLOR, AppTheme

# 定义子路由应用
system_alpha_ledger_app, rt = fast_app(hdrs=AppTheme.headers())

DEFAULT_START = "2022-06-01"
DEFAULT_END = "2026-10-19"
DEFAULT_HOLDINGS = (1, 3, 5)
HOLDING_CHOICES = (1, 2, 3, 5, 10, 20)

#: 台账结果缓存（键：区间 + 持有期 + 因子集）
_LEDGER_CACHE: dict[tuple, list[SingleFactorResult]] = {}


def _append_annual_result_cells(base, cells):
    """Append annual result cells."""
    for year in (2023, 2024, 2025, 2026):
        summary = base.by_year.get(year)
        cells.append(
            Td(
                _format_cell(summary.mean if summary else None),
                cls="tabular-nums text-gray-600",
            )
        )


def _parse_holdings(raw: str) -> list[int]:
    """解析持有期参数。"""
    values: list[int] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value >= 1 and value not in values:
            values.append(value)
    return sorted(values) or list(DEFAULT_HOLDINGS)


def _run_ledger(
    start: str,
    end: str,
    holdings: list[int],
    factors: list[str],
) -> list[SingleFactorResult]:
    """执行台账计算（带内存缓存）。"""
    key = (start, end, tuple(holdings), tuple(factors))
    cached = _LEDGER_CACHE.get(key)
    if cached is not None:
        return cached
    panel = load_factor_panel(datetime.date.fromisoformat(start), datetime.date.fromisoformat(end))
    results: list[SingleFactorResult] = []
    for holding in holdings:
        results.extend(study_factors(panel, factors, holding_days=holding, price="open"))
    if len(_LEDGER_CACHE) >= 8:
        _LEDGER_CACHE.clear()
    _LEDGER_CACHE[key] = results
    return results


def _format_cell(value: float | None, digits: int = 4, percent: bool = False) -> str:
    """格式化表格数值。"""
    if value is None or value != value:
        return "—"
    if percent:
        return f"{value * 100:+.2f}%"
    return f"{value:+.{digits}f}"


def _build_result_table(
    results: list[SingleFactorResult],
    holdings: list[int],
) -> Any:
    """构建台账结果表格。"""
    if not results:
        return P("没有可展示的结果。", cls="text-sm text-gray-500 p-4")

    by_factor: dict[str, dict[int, SingleFactorResult]] = {}
    for result in results:
        by_factor.setdefault(result.factor, {})[result.holding_days] = result

    header_cells = ["因子"]
    for holding in holdings:
        header_cells.append(f"IC{holding} / t")
    header_cells.append("D1-D10 价差(3日)")
    header_cells.extend(["2023", "2024", "2025", "2026"])

    rows: list[Any] = []
    for factor in FEATURE_COLS:
        row = _factor_result_row(factor, by_factor, holdings)
        if row is not None:
            rows.append(row)

    head = Tr(
        *[
            Th(text, cls="text-left text-xs font-semibold text-gray-600 py-2")
            for text in header_cells
        ]
    )
    return Table(
        Thead(head),
        Tbody(*rows),
        cls="w-full text-xs",
    )


def _build_form(
    start: str,
    end: str,
    holdings: list[int],
    factors: list[str],
) -> Any:
    """构建筛选表单。"""
    holding_boxes = [
        Div(
            _Label(
                Input(
                    type="checkbox",
                    name="holdings",
                    value=str(holding),
                    checked=holding in holdings,
                    cls="checkbox checkbox-sm",
                ),
                Span(f"{holding} 日", cls="text-sm text-gray-700 ml-1"),
                cls="flex items-center gap-1 mr-4",
            ),
            cls="flex items-center",
        )
        for holding in HOLDING_CHOICES
    ]
    factor_boxes: list[Any] = []
    for group, names in FEATURE_GROUPS.items():
        items = [
            Div(
                _Label(
                    Input(
                        type="checkbox",
                        name="factors",
                        value=name,
                        checked=name in factors,
                        cls="checkbox checkbox-xs",
                    ),
                    Span(name, cls="text-xs text-gray-600 ml-1"),
                    cls="flex items-center gap-1",
                ),
                cls="flex items-center",
            )
            for name in names
        ]
        factor_boxes.append(
            Div(
                Div(group, cls="text-xs font-semibold text-gray-700 mb-1"),
                Div(*items, cls="grid grid-cols-3 gap-x-2 gap-y-1"),
                cls="mb-3",
            )
        )
    return Form(
        Div(
            Div(
                _Label("起始日期", cls="block text-sm font-medium text-gray-700 mb-1"),
                Input(type="date", name="start", value=start, cls="input input-bordered w-full"),
                cls="mb-2",
            ),
            Div(
                _Label("结束日期", cls="block text-sm font-medium text-gray-700 mb-1"),
                Input(type="date", name="end", value=end, cls="input input-bordered w-full"),
                cls="mb-2",
            ),
            Div(
                _Label("持有期", cls="block text-sm font-medium text-gray-700 mb-1"),
                Div(*holding_boxes, cls="flex flex-wrap items-center"),
                cls="mb-2",
            ),
            cls="grid grid-cols-1 md:grid-cols-3 gap-4",
        ),
        Div(
            Div("因子", cls="text-sm font-medium text-gray-700 mb-1"),
            Div(*factor_boxes),
            cls="mb-3",
        ),
        Div(
            Input(type="hidden", name="run", value="1"),
            Button("开始检验", type="submit", cls="btn btn-primary"),
            Span(
                "RankIC 的负值表示样本内反向关联；t 值未调整序列相关，不能单独证明显著性。",
                cls="text-xs text-gray-500 ml-3",
            ),
            cls="flex items-center",
        ),
        cls="bg-white p-4 rounded-lg shadow mb-3",
    )


@rt("/")
async def index(req):
    """因子台账页面。"""
    query = req.query_params
    start = query.get("start") or DEFAULT_START
    end = query.get("end") or DEFAULT_END
    holdings = _parse_holdings(",".join(query.getlist("holdings")))
    raw_factors = query.getlist("factors")
    if not raw_factors:
        factors = list(FEATURE_COLS)
    else:
        picked = set(raw_factors)
        factors = [f for f in FEATURE_COLS if f in picked] or list(FEATURE_COLS)

    layout = MainLayout(title="因子台账")
    layout.set_sidebar_active("/system/alpha-ledger")

    results: list[SingleFactorResult] = []
    error_text = ""
    if query.get("run"):
        try:
            results = _run_ledger(start, end, holdings, factors)
        except Exception as exc:  # pragma: no cover - 依赖真实数据
            logger.exception(f"因子台账计算失败: {exc}")
            error_text = f"计算失败: {exc}"

    result_block: Any = Div(
        Div(
            Div(
                UkIcon("bar-chart-2", size=32, cls="mr-3", style=f"color: {PRIMARY_COLOR};"),
                H2("因子台账", cls="text-2xl font-bold"),
                cls="flex items-center",
            ),
            cls="mb-6",
        ),
        _build_form(start, end, holdings, factors),
        Div(
            Div(
                P(
                    f"样本区间 {start} ~ {end}｜持有期 {', '.join(str(h) for h in holdings)} 日｜"
                    f"共 {len(factors)} 个因子",
                    cls="text-sm text-gray-600 mb-3",
                ),
                (
                    P(error_text, cls="text-sm text-red-600 mb-3")
                    if error_text
                    else _build_result_table(results, holdings)
                ),
            ),
            cls="bg-white p-4 rounded-lg shadow",
        ),
        cls="p-8",
    )

    layout.main_block = result_block
    return layout.render(req)


def _factor_result_row(factor, by_factor, holdings):
    """Render the IC and spread summaries for a single factor."""
    per_holding = by_factor.get(factor) or {}
    if not per_holding:
        return None
    cells: list[Any] = [Td(factor, cls="font-medium text-gray-800")]
    for holding in holdings:
        result = per_holding.get(holding)
        if result is None:
            cells.append(Td("—", cls="text-gray-400"))
            continue
        ic = result.rank_ic
        color = "text-red-600" if ic.mean < 0 else "text-green-600"
        cells.append(
            Td(
                Span(f"{ic.mean:+.4f}", cls=f"{color} font-medium"),
                Span(f" t={ic.t_stat:+.1f}", cls="text-xs text-gray-400 ml-1"),
                cls="tabular-nums",
            )
        )
    base = per_holding.get(3) or next(iter(per_holding.values()))
    spread = ""
    buckets = {item.bucket: item.mean_forward for item in base.deciles}
    if all(index in buckets and math.isfinite(buckets[index]) for index in (1, 10)):
        spread = (buckets[1] - buckets[10]) * 100
    cells.append(Td(f"{spread:+.2f}%" if spread != "" else "—", cls="tabular-nums"))
    _append_annual_result_cells(base, cells)
    return Tr(*cells, cls="border-b border-gray-100")
