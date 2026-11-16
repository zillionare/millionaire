"""User-facing data requirements, capability results and download confirmation."""

from typing import Any

from fasthtml.common import H3, A, Div, Input, Label, P, Table, Tbody, Td, Th, Thead, Tr

from quantide.config.realtime_source import realtime_source
from quantide.providers.extensions import quote_provider_enabled
from quantide.service.data_source_access import load_access_report
from quantide.service.init_wizard import init_wizard
from quantide.web.components.tencent_trial import TencentTrialControl

STATUS_LABELS = {
    "ok": "通过",
    "denied": "权限不足",
    "invalid_token": "密钥无效",
    "unavailable": "连接异常",
    "unconfirmed": "待确认",
    "incompatible": "字段不完整",
    "rate_limited": "请求受限",
}


def AccessReport(report: Any = None) -> Any:
    """Explain dataset permissions without exposing credentials or internal component names."""
    report = report or load_access_report(init_wizard.get_state())
    if not report:
        return P("点击“检测并继续”后检查数据权限；此时不会开始批量下载。", cls="text-sm mt-4")
    return Div(
        H3("数据源检测结果", cls="font-semibold mt-4"),
        Table(
            Thead(Tr(Th("所需数据"), Th("结果"), Th("说明"))),
            Tbody(
                *(
                    Tr(Td(row["label"]), Td(STATUS_LABELS[row["status"]]), Td(row["message"]))
                    for row in report["checks"]
                )
            ),
            cls="w-full text-sm mt-2",
        ),
        A(
            "查看 Tushare 权限说明",
            href="https://tushare.pro/document/1?doc_id=108",
            target="_blank",
            rel="noopener noreferrer",
            cls="text-blue-600",
        ),
        P(
            "实时快照与实时分钟是可选项，未通过不影响历史数据下载和回测。",
            cls="text-sm text-gray-500 mt-2",
        ),
        P(
            "此检查验证所选首次下载窗口的少量样本；完整历史覆盖仍以下载结果为准。",
            cls="text-sm text-gray-500 mt-2",
        ),
    )


def RealtimeSetup() -> Any:
    """Offer an optional, explicitly limited demonstration only after source configuration."""
    report = load_access_report(init_wizard.get_state()) or {}
    minute: dict[str, Any] = next(
        (row for row in report.get("checks", []) if row["endpoint"] == "rt_min"), {}
    )
    return Div(
        P(
            "如果要使用仿真和实盘交易，必须配置实时行情数据源，至少每分钟更新行情，包含最新价格、"
            "当日涨跌停及复权因子，或计算复权基准所需的数据"
            "（如交易所调整后的 pre_close 与历史数据）。",
            cls="mb-4",
        ),
        P(
            "如果已配置的数据源没有提供可用的实时行情，millionaire 出于演示和教学目的，提供了"
            "基于网络爬虫的腾讯财经实时行情实现。你可以在此启用，但只能使用一次固定 30 天，"
            "请及时替换。",
            cls="mb-4",
        ),
        P(
            "CE 当前提供回测和仿真，真实交易由 millionaire pro 或用户宿主扩展接入。",
            cls="text-sm text-gray-500",
        ),
        TencentTrialControl(),
        _extension_choice(),
        P(
            "账号已开通实时分钟接口；本版自动接入的是实时快照接口。仅有分钟接口权限时，可通过"
            "自定义行情扩展接入，无需为使用本框架另行购买快照接口。",
            cls="text-sm mt-4",
        )
        if minute.get("status") == "ok" and not report.get("realtime_ready")
        else None,
        P(
            "暂不启用实时行情，也可以下载历史数据并研究回测；开始仿真前再完成实时源配置。",
            cls="text-sm mt-4",
        ),
    )


def _extension_choice() -> Any:
    if not quote_provider_enabled():
        return None
    return Label(
        Input(
            type="checkbox",
            name="use_quote_extension",
            value="on",
            checked=realtime_source() in {"", "extension"},
        ),
        " 使用已启用的自定义实时行情扩展（与腾讯演示二选一）",
        cls="block mt-4",
    )


def HistoryConfirmation(state: Any) -> Any:
    """Keep bulk data import behind a named action after both source decisions."""
    source = {
        "tushare": "Tushare 实时快照（每分钟更新）",
        "tencent": "腾讯财经 30 天演示",
        "extension": "自定义实时行情扩展",
        "none": "暂不启用，仅研究回测",
    }
    return Div(
        P("数据源配置已保存。请确认以下内容，再点击“开始下载历史数据”。", cls="mb-4"),
        P(f"历史数据源：{state.get('data_source', 'tushare')}"),
        P(f"首次下载起点：{state.get('history_start_date') or state.get('epoch', '')}"),
        P(f"实时行情：{source.get(realtime_source(), '尚未配置')}"),
        P(
            "将下载证券列表、交易日历、日线、复权因子、ST、涨跌停、指数及 30 分钟历史数据。",
            cls="mt-4",
        ),
        AccessReport(),
    )
