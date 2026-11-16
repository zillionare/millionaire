"""Strategy routes."""

from fasthtml.common import *
from monsterui.all import *

from quantide.web.application import fast_app
from quantide.web.theme import AppTheme

strategy_app, rt = fast_app(hdrs=AppTheme.headers())


BENCHMARK_ASSET = "000300.SH"


TRADE_PAIRS_PAGE_SIZE = 50


TRADE_SORT_BUY_TIME = "buy_time"


TRADE_SORT_RETURN = "return"


TRADE_SORT_DIRECTIONS = ("asc", "desc")


BACKTEST_REPORT_TABS = {
    "overview": "收益概述",
    "trades": "交易详情",
    "positions": "每日持仓",
    "logs": "日志输出",
}


STRATEGY_MODAL_CLOSE_JS = "closeStrategyModal()"


_MODAL_MAX_HEIGHTS = {
    "max-w-md": "max-h-[17.3rem]",
    "max-w-lg": "max-h-[19.8rem]",
    "max-w-xl": "max-h-[22.3rem]",
    "max-w-2xl": "max-h-[26rem]",
}


TRADE_PARAM_KEYS = (
    "horizon",
    "slippage_pct",
    "use_alpha_exit",
    "cheat_on_close",
)


TRADE_PARAM_LABELS = {
    "horizon": "持有交易日",
    "slippage_pct": "滑点比例",
    "use_alpha_exit": "启用 alpha 排名卖出",
    "cheat_on_close": "按收盘价成交",
    "commission": "佣金率(单边)",
    "stamp_duty": "印花税率(卖出)",
    "transfer_fee": "过户费率(双边)",
    "min_commission": "单笔最低佣金",
}


BROKER_FEE_PARAM_DEFAULTS = {
    "commission": 1e-4,
    "stamp_duty": 5e-4,
    "transfer_fee": 1e-5,
    "min_commission": 5.0,
}


BACKTEST_WIZARD_SCRIPT = (
    "\n(function () {\n    function showStep(step) {\n        var steps = "
    "document.querySelectorAll('[data-bt-step]');\n        for (var i = 0; i < "
    "steps.length; i++) {\n            steps[i].classList.toggle('hidden', "
    "steps[i].getAttribute('data-bt-step') !== String(step));\n        }\n        var "
    "buttons = document.querySelectorAll('[data-bt-show]');\n        for (var j = 0; j < "
    "buttons.length; j++) {\n            buttons[j].classList.toggle('hidden', "
    "buttons[j].getAttribute('data-bt-show') !== String(step));\n        }\n        var "
    "indicator = document.getElementById('backtest-step-indicator');\n        if "
    "(indicator) { var total = document.querySelectorAll('[data-bt-step]').length;\n            "
    "indicator.textContent = '第 ' + step + ' / ' + total + ' 步'; }\n    "
    "var body = document.querySelector('.backtest-dialog__body');\n    "
    "if (body) { body.scrollTop = 0; }\n    }\n    "
    "window.showBacktestStep = showStep;\n    showStep(1);\n})();\n"
)
