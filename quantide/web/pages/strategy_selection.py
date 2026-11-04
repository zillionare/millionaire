"""Strategy selection."""

import datetime
from dataclasses import dataclass
from typing import Any

import fasthtml.common as fh
import polars as pl
from fasthtml.common import *
from fasthtml.common import (
    Div,
    Span,
    Thead,
    Tr,
)
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    Button,
    Form,
    Input,
    Table,
    Tbody,
    Td,
    Th,
)

from quantide.data.models.daily_bars import daily_bars
from quantide.service.discovery import strategy_loader
from quantide.web.pages.strategy_backtest_config import (
    _parse_params,
)
from quantide.web.pages.strategy_format import (
    _format_date,
    _format_number,
    _format_score,
    _format_signed_pct,
    _get_strategy_default_params,
    _htmx_indicator_style,
    _strategy_dialog_modal,
    _supports_stock_selection,
)
from quantide.web.pages.strategy_routes import (
    STRATEGY_MODAL_CLOSE_JS,
    rt,
)


def _selection_result_metadata(model_engine, picks, resolved_date):
    """Read selection result metadata."""
    if picks:
        first = picks[0]
        if first.get("as_of_date") or first.get("date"):
            resolved_date = _format_date(first.get("as_of_date") or first.get("date"))
        if first.get("model_engine"):
            model_engine = str(first.get("model_engine"))
    return model_engine, resolved_date


def _append_selection_table_rows(future_return_horizon, picks, table_rows):
    """Append selection table rows."""
    table_rows.extend(
        _selection_row(idx, row, future_return_horizon) for idx, row in enumerate(picks, 1)
    )


def _get_default_selection_date() -> str:
    """获取选股默认基准日期字符串 (YYYY-MM-DD)。"""
    try:
        max_dt = getattr(daily_bars, "max_date", None) or getattr(daily_bars, "end", None)
        if isinstance(max_dt, (datetime.date, datetime.datetime)):
            return max_dt.strftime("%Y-%m-%d")
        if isinstance(max_dt, str) and max_dt.strip():
            return max_dt.strip()[:10]
    except Exception:
        pass
    return "2024-12-31"


def _resolve_selection_date_notice(
    requested_date: str,
    resolved_date: str,
    latest_available: str,
    has_picks: bool,
) -> str:
    """生成选股日期回退提示；日期一致或无法解析时返回空字符串。"""
    try:
        requested_dt = datetime.date.fromisoformat(requested_date[:10])
        latest_dt = datetime.date.fromisoformat(latest_available[:10])
    except ValueError:
        return ""

    if requested_dt > latest_dt:
        if has_picks:
            return (
                f"请求日期 {requested_date} 晚于本地最新行情 {latest_available}，"
                f"已自动使用最近可用交易日 {resolved_date} 选股。"
            )
        return (
            f"请求日期 {requested_date} 晚于本地最新行情 {latest_available}，"
            "本地暂无可用行情，未选出个股。"
        )

    if has_picks and requested_date != resolved_date:
        return (
            f"请求日期 {requested_date} 不是可用交易日，"
            f"已自动使用最近可用交易日 {resolved_date} 选股。"
        )
    return ""


def _normalize_selection_output(
    raw_result: Any,
    default_date: str,
    merged_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, str]:
    """标准化策略 select_stocks 返回结果为 (picks, as_of_date, model_engine)。"""
    resolved_date = default_date
    use_lgb = bool(merged_config.get("use_lightgbm", True))
    model_engine = "LightGBM" if use_lgb else "Ridge-ICIR"
    picks_raw: Any = raw_result

    if isinstance(raw_result, dict):
        picks_raw = raw_result.get("picks", raw_result.get("items", raw_result.get("stocks", [])))
        if raw_result.get("as_of_date"):
            resolved_date = _format_date(raw_result.get("as_of_date"))
        if raw_result.get("model_engine"):
            model_engine = str(raw_result.get("model_engine"))

    picks: list[dict[str, Any]] = []
    if isinstance(picks_raw, pl.DataFrame):
        picks = [dict(row) for row in picks_raw.to_dicts()]
    elif hasattr(picks_raw, "to_dict"):
        try:
            records = picks_raw.to_dict(orient="records")
            if isinstance(records, list):
                picks = [dict(r) for r in records if isinstance(r, dict)]
        except Exception:
            picks = []
    elif isinstance(picks_raw, list):
        picks = [dict(item) for item in picks_raw if isinstance(item, dict)]

    model_engine, resolved_date = _selection_result_metadata(model_engine, picks, resolved_date)

    return picks, resolved_date, model_engine


def _render_stock_selection_modal(
    name: str,
    strategy_cls: Any,
    *,
    as_of_date: str | None = None,
    config: dict[str, Any] | None = None,
    auto_run: bool = True,
) -> Any:
    """渲染策略个股筛选弹窗及选股结果表。"""
    merged_config = _get_strategy_default_params(strategy_cls)
    if config:
        merged_config.update(config)

    latest_available = _get_default_selection_date()
    requested_date = (as_of_date or "").strip() or latest_available
    sizing = _SelectionSizing.from_config(merged_config)
    outcome = _selection_outcome(
        name, strategy_cls, merged_config, requested_date, latest_available, auto_run, sizing.engine
    )

    table_rows: list[Any] = []
    _append_selection_table_rows(sizing.horizon, outcome.picks, table_rows)

    if not table_rows:
        table_rows.append(
            Tr(
                Td(
                    "暂无符合条件的候选个股",
                    colspan="12",
                    cls="px-4 py-8 text-center text-gray-400 text-sm",
                )
            )
        )

    selection_table = Table(
        Thead(
            Tr(
                Th("排名", cls="px-3 py-2 font-medium"),
                Th("代码", cls="px-3 py-2 font-medium"),
                Th("名称", cls="px-3 py-2 font-medium"),
                Th("板块", cls="px-3 py-2 font-medium"),
                Th("最新价", cls="px-3 py-2 font-medium"),
                Th("当日涨跌", cls="px-3 py-2 font-medium"),
                Th("5日/20日涨幅", cls="px-3 py-2 font-medium"),
                Th("板块相对强弱(20D)", cls="px-3 py-2 font-medium"),
                Th("训练目标(未来收盘收益)", cls="px-3 py-2 font-medium"),
                Th("短线与均线形态", cls="px-3 py-2 font-medium"),
                Th("ML得分", cls="px-3 py-2 font-medium"),
                Th("核心选股逻辑", cls="px-3 py-2 font-medium"),
                cls="text-left text-xs text-gray-600 bg-gray-50 border-b border-gray-200",
            )
        ),
        Tbody(*table_rows, cls="text-xs"),
        id="stock-selection-table",
        cls="w-full",
    )

    error_banner = (
        Div(
            f"选股执行异常: {outcome.error}",
            cls="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600",
        )
        if outcome.error
        else None
    )

    body = Div(
        Form(
            Div(
                Div(
                    Span("基准日期", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        type="date",
                        name="as_of_date",
                        value=outcome.date,
                        cls="input input-sm w-36",
                    ),
                ),
                Div(
                    Span("选股数量 (Top K)", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        type="number",
                        name="param_top_k",
                        value=str(sizing.top_k),
                        min="1",
                        max="50",
                        cls="input input-sm w-24",
                    ),
                ),
                Div(
                    Span("股票池规模", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        type="number",
                        name="param_universe_size",
                        value=str(sizing.universe_size),
                        min="20",
                        max="2000",
                        cls="input input-sm w-28",
                    ),
                ),
                Div(
                    Span("训练窗口(日)", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        type="number",
                        name="param_train_window",
                        value=str(sizing.train_window),
                        min="20",
                        max="250",
                        cls="input input-sm w-24",
                    ),
                ),
                Div(
                    Span("未来收益标签前瞻(日)", cls="block text-xs text-gray-500 mb-1"),
                    Input(
                        type="number",
                        name="param_future_return_horizon",
                        value=str(sizing.horizon),
                        min="1",
                        max="30",
                        cls="input input-sm w-24",
                    ),
                ),
                Div(
                    Span("模型引擎", cls="block text-xs text-gray-500 mb-1"),
                    fh.Select(
                        fh.Option(
                            "LightGBM (GBDT 截面排序)",
                            value="true",
                            selected="selected" if sizing.use_lightgbm else None,
                        ),
                        fh.Option(
                            "Ridge-ICIR 线性集成",
                            value="false",
                            selected=None if sizing.use_lightgbm else "selected",
                        ),
                        name="param_use_lightgbm",
                        cls="uk-select uk-form-small text-gray-700 w-52",
                    ),
                ),
                Div(
                    Button(
                        "立即选股",
                        type="button",
                        cls=(
                            "px-4 py-1.5 bg-green-600 text-white rounded-lg "
                            "hover:bg-green-700 text-xs font-medium mt-5 "
                            "disabled:opacity-50 disabled:cursor-wait"
                        ),
                        hx_post=f"/strategy/{name}/select/run",
                        hx_target="#modal-container",
                        hx_include="closest form",
                        hx_indicator="#select-loading",
                        hx_disabled_elt="this",
                    ),
                ),
                cls=(
                    "flex flex-wrap items-center gap-3 p-3 rounded-lg "
                    "bg-gray-50 border border-gray-200 mb-4"
                ),
            )
        ),
        Div(
            Span(
                cls=(
                    "inline-block h-3.5 w-3.5 animate-spin rounded-full "
                    "border-2 border-green-600 border-t-transparent"
                )
            ),
            Span("正在拉取行情、计算 24 个因子并运行模型，请稍候…"),
            id="select-loading",
            cls="htmx-indicator items-center gap-2 text-xs text-green-700 mb-3",
        ),
        Div(
            Span(
                f"选股基准日: {outcome.date}",
                cls="px-2.5 py-1 rounded-full bg-[#fff3f2] text-[#e41815] text-xs font-medium",
            ),
            Span(
                f"模型引擎: {outcome.engine}",
                cls="px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 text-xs font-medium",
            ),
            Span(
                f"入选个股数: {len(outcome.picks)} 只",
                cls="px-2.5 py-1 rounded-full bg-green-50 text-green-700 text-xs font-medium",
            ),
            Span(
                f"训练目标: 未来{sizing.horizon}日收盘收益（仅训练）",
                cls="px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 text-xs font-medium",
            ),
            cls="flex flex-wrap items-center gap-2 mb-3",
        ),
        (
            Div(
                outcome.notice,
                cls=(
                    "mb-3 rounded-lg border border-gray-200 bg-gray-50 "
                    "px-3 py-2 text-xs text-gray-700"
                ),
            )
            if outcome.notice
            else None
        ),
        error_banner,
        Div(
            selection_table,
            cls="max-h-[460px] overflow-auto rounded-lg border border-gray-200",
        ),
        _htmx_indicator_style(),
    )

    footer = Div(
        Button(
            "关闭",
            type="button",
            cls=(
                "px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm"
            ),
            onclick=STRATEGY_MODAL_CLOSE_JS,
        ),
        cls="flex justify-end gap-2",
    )

    return _strategy_dialog_modal(
        f"一键选股 - {name}",
        body,
        footer,
        modal_id="stock-selection-modal",
        width_cls="max-w-6xl",
    )


@rt("/{name}/select/modal")
def strategy_select_modal(name: str):
    """打开策略个股筛选弹窗并默认执行一次选股。"""
    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    if not _supports_stock_selection(cls):
        return "Strategy does not support stock selection"
    default_date_str = _get_default_selection_date()
    default_params = _get_strategy_default_params(cls)
    return _render_stock_selection_modal(
        name,
        cls,
        as_of_date=default_date_str,
        config=default_params,
        auto_run=True,
    )


@rt("/{name}/select/run", methods=["POST"])
async def run_strategy_select(req, name: str):
    """根据用户提交的参数重新运行个股筛选。"""
    strategies = strategy_loader.load_from_cache()
    cls = strategies.get(name)
    if not _supports_stock_selection(cls):
        return "Strategy does not support stock selection"
    form = await req.form()
    as_of_date = str(form.get("as_of_date") or "").strip() or None
    config = _parse_params(form)
    return _render_stock_selection_modal(
        name,
        cls,
        as_of_date=as_of_date,
        config=config,
        auto_run=True,
    )


def _selection_row(idx, row, future_return_horizon):
    """Render one ranked selection and its signed-return cells."""
    rank_val = row.get("rank", idx)
    asset_code = str(row.get("asset") or row.get("symbol") or "--")
    asset_name = str(row.get("name") or row.get("asset_name") or asset_code)
    board_name = str(row.get("board") or row.get("sector") or "主板")
    close_text = _format_number(row.get("close"))
    pattern_text = str(row.get("kline_pattern") or row.get("pattern") or "均线多头")
    ml_score_val = row.get("ml_score") if row.get("ml_score") is not None else row.get("score")
    score_text = _format_score(ml_score_val)
    reason_text = str(row.get("signal_reason") or row.get("reason") or "--")
    return Tr(
        Td(f"#{rank_val}", cls="px-3 py-2 font-semibold text-gray-700"),
        Td(Code(asset_code), cls="px-3 py-2 font-mono text-xs text-[#e41815]"),
        Td(asset_name, cls="px-3 py-2 font-medium text-gray-900"),
        Td(
            Span(board_name, cls="px-2 py-0.5 rounded bg-gray-100 text-gray-700 text-xs"),
            cls="px-3 py-2",
        ),
        Td(close_text, cls="px-3 py-2 font-mono text-gray-900"),
        _selection_percent_cell(row.get("ret_1d")),
        _selection_relative_cell(row.get("ret_5d"), row.get("ret_20d")),
        _selection_percent_cell(row.get("rs_board_20d")),
        Td(
            f"未来{future_return_horizon}日收盘收益（仅训练）",
            cls="px-3 py-2 font-mono text-xs whitespace-nowrap",
        ),
        Td(
            Span(
                pattern_text,
                cls=(
                    "px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 "
                    "border border-gray-200 text-xs"
                ),
            ),
            cls="px-3 py-2",
        ),
        Td(score_text, cls="px-3 py-2 font-mono font-semibold text-gray-900"),
        Td(reason_text, cls="px-3 py-2 text-xs text-gray-600 max-w-xs"),
        cls="border-b border-gray-100 hover:bg-gray-50",
    )


def _selection_percent_cell(value):
    text, color = _format_signed_pct(value)
    return Td(text, cls=f"px-3 py-2 font-mono {color}")


def _selection_relative_cell(short, medium):
    short_text, short_color = _format_signed_pct(short)
    medium_text, medium_color = _format_signed_pct(medium)
    return Td(
        Span(short_text, cls=short_color),
        Span(" / ", cls="text-gray-400"),
        Span(medium_text, cls=medium_color),
        cls="px-3 py-2 font-mono text-xs",
    )


@dataclass(frozen=True)
class _SelectionSizing:
    top_k: int
    universe_size: int
    train_window: int
    horizon: int
    use_lightgbm: bool

    @classmethod
    def from_config(cls, config):
        return cls(
            int(config.get("top_k", 10)),
            int(config.get("universe_size", 300)),
            int(config.get("train_window", 60)),
            int(config.get("future_return_horizon", config.get("horizon", 5))),
            bool(config.get("use_lightgbm", True)),
        )

    @property
    def engine(self):
        return "LightGBM" if self.use_lightgbm else "Ridge-ICIR"


@dataclass
class _SelectionOutcome:
    picks: list
    date: str
    engine: str
    error: str
    notice: str


def _selection_outcome(name, strategy_cls, config, requested, latest, auto_run, engine):
    picks, date, error = [], requested, ""
    if auto_run:
        try:
            raw = strategy_cls.select_stocks(as_of_date=date, config=config)
            picks, date, engine = _normalize_selection_output(raw, date, config)
        except Exception as exc:
            logger.error(f"Failed to run stock selection for {name}: {exc}")
            error = str(exc)
    notice = _resolve_selection_date_notice(requested, date, latest, bool(picks))
    return _SelectionOutcome(picks, latest if not picks and notice else date, engine, error, notice)
