"""Broker API routes."""

# The application object must be created before these route dependencies load.
# ruff: noqa: E402

import datetime
import json
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from quantide.config.branding import get_runtime_version
from quantide.config.settings import get_settings
from quantide.core.enums import FrameType
from quantide.core.errors import TradeError, TradeErrors
from quantide.core.strategy import BaseStrategy
from quantide.service.discovery import strategy_loader
from quantide.service.param_optimizer import (
    OptimizationSpec,
    ParamOptimizer,
    rank_results,
)
from quantide.service.runner import BacktestRunner
from quantide.web.application import fast_app
from quantide.web.components.account_summary import build_asset_overview as build_asset_overview

app, rt = fast_app()

import pickle

import arrow
import numpy as np

ver = get_runtime_version()


async def _request_json(request: Request) -> dict[str, Any]:
    """Read a JSON payload through both FastHTML's and Starlette's request shapes."""
    payload = getattr(request, "json", None)
    if callable(payload):
        payload = await payload()
    return payload if isinstance(payload, dict) else {}


def _request_args(request: Request) -> Any:
    """Keep compatibility with the legacy broker API's request.args fallback."""
    args = getattr(request, "args", None)
    return args if args is not None else request.query_params


def _request_token(request: Request) -> Any:
    return getattr(request, "token", None) or request.headers.get("token")


def _legacy_accounts(request: Request) -> Any:
    context = getattr(request.app, "ctx", None)
    accounts = getattr(context, "accounts", None)
    if accounts is None:
        raise RuntimeError("legacy broker accounts are unavailable")
    return accounts


def _get_broker(req: Request) -> Any:
    reg = req.scope.get("registry")
    if reg is None:
        return None
    kind = req.query_params.get("kind")
    broker_id = req.query_params.get("id")
    if kind and broker_id:
        return reg.get(kind, broker_id)
    session = req.scope.get("session", {})
    active_kind = session.get("active_account_kind")
    active_id = session.get("active_account_id")
    if active_kind and active_id:
        return reg.get(active_kind, active_id)
    default = reg.get_default()
    if default is None:
        return None
    return reg.get(default[0], default[1])


def _require_broker(req: Request) -> Any:
    broker = _get_broker(req)
    if broker is None:
        raise RuntimeError("broker not found")
    return broker


def _backtest_requires_bid_time(bid_time: datetime.datetime | None) -> bool:
    return bid_time is None and get_settings().runtime_mode == "backtest"


@rt("/status")
async def status(request: Request) -> Any:
    """获取当前服务状态"""
    return {"status": "ok", "listen": request.url, "version": ver}


@rt("/start_backtest", methods=["POST"])
async def start_backtest(req: Request) -> Any:
    """启动回测

    启动回测时，将为接下来的回测创建一个新的账户。

    Args:
        request Request: 包含以下字段的请求对象

            - name, 账户名称
            - token,账户token
            - principal,账户初始资金
            - commission,账户手续费率
            - start,回测开始日期，格式为YYYY-MM-DD
            - end,回测结束日期，格式为YYYY-MM-DD

    Returns:
        json: 包含以下字段的json对象

        - account_name, str
        - token, str
        - account_start_date, str
        - principal, float

    """
    broker = _require_broker(req)
    params = await _request_json(req)
    return broker.start_backtest(params)


@rt("/stop_backtest", methods=["POST"])
async def stop_backtest(req: Request) -> Any:
    """结束回测

    结束回测后，账户将被冻结，此后将不允许进行任何操作

    # todo: 增加持久化操作

    """
    broker = _require_broker(req)
    return await broker.stop_backtest()


@rt("/accounts", methods=["GET"])
async def list_accounts(req: Request) -> Any:
    """只在回测模式下有效？"""
    broker = _require_broker(req)
    return broker.list_accounts()


@rt("/buy", methods=["POST"])
async def buy(
    req: Request,
    asset: str,
    price: int | float,
    shares: int | float,
    bid_time: datetime.datetime | None = None,
    timeout: float = 0.5,
) -> Any:
    broker = _require_broker(req)

    if _backtest_requires_bid_time(bid_time):
        return Response("bid_time must be provided", status_code=400)

    return await broker.buy(
        asset=asset,
        shares=shares,
        price=float(price),
        bid_time=bid_time,
        timeout=timeout,
    )


@rt("/buy_percent", methods=["POST"])
async def buy_percent(
    req: Request,
    asset: str,
    percent: float,
    bid_time: datetime.datetime | None = None,
    timeout: float = 0.5,
) -> Any:
    broker = _require_broker(req)
    if _backtest_requires_bid_time(bid_time):
        return Response("bid_time must be provided", status_code=400)

    if not 0 < percent <= 1.0:
        return Response("percent must be between 0 and 1.0", status_code=400)

    return await broker.buy_percent(asset, percent, bid_time, timeout)


@rt("/buy_amount", methods=["POST"])
async def buy_amount(
    req: Request,
    asset: str,
    amount: int | float,
    price: int | float | None = None,
    bid_time: datetime.datetime | None = None,
    timeout: float = 0.5,
) -> Any:
    broker = _require_broker(req)
    if _backtest_requires_bid_time(bid_time):
        return Response("bid_time must be provided", status_code=400)

    return await broker.buy_amount(asset, amount, price, bid_time, timeout)


@rt("/sell", methods=["POST"])
async def sell(
    req: Request,
    asset: str,
    price: int | float,
    shares: int | float,
    bid_time: datetime.datetime | None = None,
    timeout: float = 0.5,
) -> Any:
    broker = _require_broker(req)
    if _backtest_requires_bid_time(bid_time):
        return Response("bid_time must be provided", status_code=400)

    return await broker.sell(
        asset=asset,
        shares=shares,
        price=float(price),
        bid_time=bid_time,
        timeout=timeout,
    )


@rt("/sell_percent", methods=["POST"])
async def sell_percent(
    req: Request,
    asset: str,
    percent: float,
    bid_time: datetime.datetime | None = None,
    timeout: float = 0.5,
) -> Any:
    broker = _require_broker(req)
    if _backtest_requires_bid_time(bid_time):
        return Response("bid_time must be provided", status_code=400)

    if not 0 < percent <= 1.0:
        return Response("percent must be between 0 and 1.0", status_code=400)

    return await broker.sell_percent(asset, percent, bid_time, timeout)


@rt("/sell_amount", methods=["POST"])
async def sell_amount(
    req: Request,
    asset: str,
    amount: int | float,
    price: int | float | None = None,
    bid_time: datetime.datetime | None = None,
    timeout: float = 0.5,
) -> Any:
    broker = _require_broker(req)
    if _backtest_requires_bid_time(bid_time):
        return Response("bid_time must be provided", status_code=400)

    return await broker.sell_amount(asset, amount, price, bid_time, timeout)


@rt("/positions", methods=["GET"])
async def positions(req: Request, asset: str, date: datetime.date | None = None) -> Any:
    broker = _require_broker(req)
    return broker.get_position(asset, date)


@rt("/account_info", methods=["GET"])
async def account_info(req: Request, asset: str, date: datetime.date | None = None) -> Any:
    """获取账户信息

    Args:
        request Request: 以args方式传入，包含以下字段

            - date: 日期，格式为YYYY-MM-DD,待获取账户信息的日期，如果为空，
            则意味着取当前日期的账户信息

    Returns:
        Response: 结果以binary方式返回。结果为一个dict，其中包含以下字段：

        - name: str, 账户名
        - principal: float, 初始资金
        - assets: float, 当前资产
        - start: datetime.date, 账户创建时间
        - last_trade: datetime.date, 最后一笔交易日期
        - end: 账户结束时间，仅对回测模式有效
        - available: float, 可用资金
        - market_value: 股票市值
        - pnl: 盈亏(绝对值)
        - ppnl: 盈亏(百分比)，即pnl/principal
        - positions: 当前持仓，dtype为[backtest.trade.datatypes.position_dtype][]的numpy
        structured array
    """
    broker = _require_broker(req)
    return broker.get_account_info(asset, date)


@rt("/metrics", methods=["GET"])
async def metrics(request: Request) -> Any:
    """获取回测的评估指标信息

    Args:
        request : 以args方式传入，包含以下字段

            - start: 开始时间，格式为YYYY-MM-DD
            - end: 结束时间，格式为YYYY-MM-DD
            - baseline: str, 用来做对比的证券代码，默认为空，即不做对比

    Returns:
        Response: 结果以binary方式返回,参考[backtest.trade.broker.Broker.metrics][]

    """
    args = _request_args(request)
    start = args.get("start")
    end = args.get("end")
    args.get("baseline")

    if start:
        start = arrow.get(start).date()

    if end:
        end = arrow.get(end).date()


@rt("/bills", methods=["GET"])
async def bills(request: Request) -> Any:
    """获取交易记录

    Returns:
        Response: 以binary方式返回。结果为一个字典，包括以下字段：

        - tx: 配对的交易记录
        - trades: 成交记录
        - positions: 持仓记录
        - assets: 每日市值

    """


@rt("/accounts", methods=["DELETE"])
async def delete_accounts(request: Request) -> Any:
    """删除账户

    当提供了账户名`name`和token（通过headers传递)时，如果name与token能够匹配，则删除`name`账户。
    Args:
        request Request: 通过params传递以下字段

            - name, 待删除的账户名。如果为空，且提供了admin token，则删除全部账户。

    """
    account_to_delete = _request_args(request).get("name", None)
    accounts = _legacy_accounts(request)

    if account_to_delete is None:
        broker = _require_broker(request)
        if broker.account_name == "admin":
            accounts.delete_accounts()
        else:
            return PlainTextResponse("admin account required", status_code=403)

    broker = _require_broker(request)
    if account_to_delete == broker.account_name:
        accounts.delete_accounts(account_to_delete)


@rt("/assets", methods=["GET"])
async def get_assets(request: Request) -> Any:
    """获取账户资产信息

    本方法主要为绘制资产收益曲线提供数据。

    Args:
        request Request: 以args方式传入，包含以下字段

            - start: 日期，格式为YYYY-MM-DD,待获取账户信息的日期，如果为空，则取账户起始日
            - end: 日期，格式为YYYY-MM-DD,待获取账户信息的日期，如果为空，则取最后交易日

    Returns:
        Response: 从`start`到`end`期间的账户资产信息，
        结果以binary方式返回,参考[backtest.trade.datatypes.rich_assets_dtype][]
    """
    broker = _require_broker(request)

    args = _request_args(request)
    start = args.get("start")
    if start:
        start = arrow.get(start).date()
    else:
        start = broker.bt_start

    end = args.get("end")
    if end:
        end = arrow.get(end).date()
    else:
        end = broker._assets[-1]["date"]

    filter = np.argwhere(
        (broker._assets["date"] >= start) & (broker._assets["date"] <= end)
    ).flatten()
    return Response(pickle.dumps(broker._assets[filter]), media_type="application/octet-stream")


@rt("/asset_overview", methods=["GET"])
async def asset_overview(request: Request) -> Any:
    broker = _require_broker(request)
    return build_asset_overview(broker.asset)


@rt("/save_backtest", methods=["POST"])
async def save_backtest(request: Request) -> Any:
    """在回测结束后，保存回测相关参数及数据。

    通过本接口，可以保存以下数据供之后查阅：

    1. 执行回测时的策略参数
    2. 策略或者回测描述
    3. 回测时产生的 tx, positions, assets, metrics等对象

    Args:
        request Request: json

            - name_prefix: 服务器保存状态后，将返回以此前缀开头的惟一名称。
            - strategy_params: 策略参数
            - desc: 策略或者回测描述
            - baseline: 计算参照用。如不传入，将使用沪深300

    Returns:
        Response: 成功时，通过response.text返回名字。此后可以此名字来存取状态。
    """
    params = await _request_json(request)
    if "name_prefix" not in params:
        raise TradeError(TradeErrors.ERROR_BAD_PARAMS, "name_prefix must be specified")

    name_prefix = params["name_prefix"]
    strategy_params = params.get("params")
    baseline = params.get("baseline")
    desc = params.get("desc")

    token = _request_token(request)
    accounts = _legacy_accounts(request)

    name = await accounts.save_backtest(name_prefix, strategy_params, token, baseline, desc)
    return PlainTextResponse(name)


@rt("/load_backtest", methods=["GET"])
async def load_backtest(request: Request) -> Any:
    """通过名字获取回测状态

    Args:
    request Request: 以args方式传入，包含以下字段

        - name: save_backtest时返回的名字
    """
    name = _request_args(request).get("name", None)
    if name is None:
        raise TradeError(TradeErrors.ERROR_BAD_PARAMS, "name of the backtest is required")

    token = _request_token(request)
    accounts = _legacy_accounts(request)

    return JSONResponse(accounts.load_backtest(name, token))


@rt("/strategies", methods=["GET"])
async def list_strategies(req: Request) -> Any:
    """GET /broker/strategies -> interfaces.md §3.1 schema."""
    import json

    info_list = strategy_loader.list_strategies()
    builtin_dir = strategy_loader.get_builtin_scan_directory()

    strategies: list[dict[str, Any]] = []
    for info in info_list:
        try:
            default_config = json.loads(info.params) if info.params else {}
        except Exception:
            default_config = {}

        is_builtin = bool(info.file_path and info.file_path.startswith(builtin_dir))

        strategies.append(
            {
                "strategy_id": f"{info.module_path}.{info.name}",
                "name": info.name,
                "description": info.description or "",
                "strategy_type": info.strategy_type or "independent",
                "module": info.module_path or "",
                "is_builtin": is_builtin,
                "default_config": default_config,
                "skipped_reasons": [],
            }
        )

    # Diagnostics currently follows the empty-list protocol contract.
    return {"strategies": strategies, "diagnostics": []}


@rt("/grid_search/run", methods=["POST"])
async def run_grid_search_job(req: Request) -> Any:
    """启动网格搜索"""
    try:
        params = await req.json()
    except Exception:
        params = {}

    strategy_name = params.get("strategy_name")
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    strategies = strategy_loader.load_from_cache()

    if strategy_name not in strategies:
        return Response(f"Strategy {strategy_name} not found", status_code=404)

    try:
        if not start_date or not end_date:
            return Response("start_date and end_date are required", status_code=400)
        start = arrow.get(start_date).date()
        end = arrow.get(end_date).date()
    except Exception as e:
        return Response(f"Invalid date format: {e}", status_code=400)

    spec = OptimizationSpec(
        strategy_name=strategy_name,
        base_config=params.get("base_config", {}),
        param_grid=params.get("param_grid", {}),
        start_date=start,
        end_date=end,
        objective=params.get("objective", "sharpe"),
        in_sample_ratio=params.get("in_sample_ratio", 0.7),
        mode=params.get("mode", "grid"),
        n_random=params.get("n_random", 20),
        max_workers=params.get("max_workers", None) or 4,
        interval=params.get("interval", "1d"),
        initial_cash=params.get("initial_cash", 1000000),
    )

    try:
        optimizer = ParamOptimizer(spec)
        results = optimizer.run()
        ranked = rank_results(results, spec.objective)
        return Response(
            json.dumps(ranked, ensure_ascii=False, default=str),
            media_type="application/json",
        )
    except Exception as e:
        return Response(f"Grid search failed: {str(e)}", status_code=500)


@rt("/backtest/run", methods=["POST"])
async def run_backtest_job(req: Request) -> Any:
    """启动新的回测任务"""
    try:
        params = await req.json()
    except Exception:
        params = {}

    strategy_name = params.get("strategy_name")
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    strategies = strategy_loader.load_from_cache()

    if strategy_name not in strategies:
        return Response(f"Strategy {strategy_name} not found", status_code=404)

    strategy_cls = strategies[strategy_name]

    try:
        if not start_date or not end_date:
            return Response("start_date and end_date are required", status_code=400)
        start = arrow.get(start_date).date()
        end = arrow.get(end_date).date()
    except Exception as e:
        return Response(f"Invalid date format: {e}", status_code=400)

    runner = BacktestRunner()
    try:
        result = await runner.run(
            strategy_cls=cast(type[BaseStrategy], strategy_cls),
            config=params.get("config", {}),
            start_date=start,
            end_date=end,
            frame_type=FrameType(params.get("interval", "1d")),
            initial_cash=params.get("initial_cash", 1000000),
            portfolio_id=params.get("portfolio_id"),
        )
        return result
    except Exception as e:
        return Response(f"Backtest failed: {str(e)}", status_code=500)
