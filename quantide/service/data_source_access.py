"""Bounded, credential-specific checks before initialization downloads."""

import datetime
import hashlib
import json
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, cast

import pandas as pd
import tushare as ts

from quantide.config.paths import ensure_app_config_dir
from quantide.core.atomic_files import write_json
from quantide.data.fetchers.tushare_realtime import compatible_snapshot
from quantide.data.models.app_state import AppState


class ProbeClient(Protocol):
    """The subset of the Tushare client used by the access probe."""

    def query(self, endpoint: str, *, fields: str, **params: object) -> pd.DataFrame:
        """Read a small sample from one endpoint."""
        ...


CACHE_SECONDS = 900
SAMPLE_ASSET = "000001.SZ"
REQUIRED = {
    "trade_cal",
    "stock_basic",
    "daily",
    "adj_factor",
    "stk_limit",
    "stock_st",
    "daily_basic",
    "index_daily",
    "index_weight",
}


@dataclass(frozen=True)
class AccessQuery:
    """One small read with the fields required by the corresponding adapter."""

    endpoint: str
    label: str
    columns: tuple[str, ...]
    params: dict[str, Any]


def _historical_queries(day: str) -> tuple[AccessQuery, ...]:
    sample = {"ts_code": SAMPLE_ASSET, "trade_date": day}
    month_end = day[:6] + str(monthrange(int(day[:4]), int(day[4:6]))[1])
    return (
        AccessQuery(
            "stock_basic",
            "证券列表",
            ("ts_code", "name"),
            {"ts_code": SAMPLE_ASSET, "list_status": "L"},
        ),
        AccessQuery("daily", "历史日线", ("ts_code", "close"), sample),
        AccessQuery("adj_factor", "复权因子", ("ts_code", "adj_factor"), sample),
        AccessQuery("stk_limit", "历史涨跌停价格", ("ts_code", "up_limit", "down_limit"), sample),
        AccessQuery("stock_st", "历史 ST 标记", ("ts_code", "trade_date"), {"trade_date": day}),
        AccessQuery("daily_basic", "市值与换手数据", ("ts_code", "trade_date", "total_mv"), sample),
        AccessQuery(
            "index_daily",
            "指数日线",
            ("ts_code", "close"),
            {"ts_code": "000300.SH", "trade_date": day},
        ),
        AccessQuery(
            "index_weight",
            "指数成分与权重",
            ("index_code", "con_code", "weight"),
            {"index_code": "000300.SH", "start_date": day[:6] + "01", "end_date": month_end},
        ),
    )


def _realtime_queries() -> tuple[AccessQuery, ...]:
    return (
        AccessQuery(
            "rt_k",
            "实时行情快照（可选，每分钟更新）",
            ("ts_code", "open", "high", "low", "close", "vol", "amount", "pre_close", "trade_time"),
            {"ts_code": SAMPLE_ASSET},
        ),
        AccessQuery(
            "rt_min",
            "实时分钟接口权限（可选，需扩展接入）",
            ("ts_code", "time", "close"),
            {"ts_code": SAMPLE_ASSET, "freq": "1MIN"},
        ),
    )


def _failure_status(error: BaseException) -> tuple[str, str]:
    text = str(error).casefold()
    if any(word in text for word in ("频率", "频次", "限流", "最多访问", "rate limit", "too many")):
        return "rate_limited", "请求受限，请稍后重试。"
    if any(word in text for word in ("token不对", "token无效", "invalid token", "token过期")):
        return "invalid_token", "访问密钥无效，请重新填写 Token。"
    if isinstance(error, PermissionError) or any(
        word in text for word in ("权限", "积分", "permission", "not authorized", "无权")
    ):
        return "denied", "账号缺少此接口权限，请在 Tushare 权限中心提升积分或开通对应权限后重试。"
    return "unavailable", "连接或服务异常，暂时无法确认；请检查网络并重试。"


def _read_check(
    client: ProbeClient, query: AccessQuery
) -> tuple[dict[str, Any], pd.DataFrame | None]:
    row = {"endpoint": query.endpoint, "label": query.label}
    try:
        frame = client.query(query.endpoint, fields=",".join(query.columns), **query.params)
    except Exception as error:
        status, message = _failure_status(error)
        return {**row, "status": status, "message": message}, None
    if frame is None or frame.empty:
        return {
            **row,
            "status": "unconfirmed",
            "message": "未返回样本，无法确认权限；空响应不等于权限不足。",
        }, frame
    if not set(query.columns).issubset(frame.columns):
        return {**row, "status": "incompatible", "message": "返回字段不完整，暂不能接入。"}, frame
    if query.endpoint == "rt_k" and not any(
        compatible_snapshot(record)
        for record in cast(list[dict[str, Any]], frame.to_dict("records"))
    ):
        return {
            **row,
            "status": "unconfirmed",
            "message": "接口有响应，但尚无有效价格和完整时间戳；请在交易时段重试。",
        }, frame
    return {**row, "status": "ok", "message": "样本检查通过。"}, frame


def access_fingerprint(
    token: str, start: datetime.date | str | None, source: str = "tushare"
) -> str:
    """Bind saved results to credentials and the first download window without saving the token."""
    return hashlib.sha256(f"{source}\0{token}\0{start}".encode()).hexdigest()


def create_probe_client(token: str) -> ProbeClient:
    """Use explicit credentials and bounded calls without changing SDK-global state."""
    return cast(ProbeClient, ts.pro_api(token=token, timeout=5))


def check_tushare_access(
    token: str, start: str | datetime.date, *, client: ProbeClient | None = None
) -> dict[str, Any]:
    """Read at most eleven small samples; never bulk download or write SDK tokens."""
    client = client or create_probe_client(token)
    start = datetime.date.fromisoformat(str(start))
    end = min(start + datetime.timedelta(days=40), datetime.date.today())
    calendar_query = AccessQuery(
        "trade_cal",
        "交易日历",
        ("cal_date", "is_open"),
        {
            "exchange": "SSE",
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        },
    )
    calendar_check, frame = _read_check(client, calendar_query)
    checks = [calendar_check]
    if calendar_check["status"] == "ok" and frame is not None:
        opened = frame[frame["is_open"].astype(str) == "1"].sort_values("cal_date")
        if not opened.empty:
            sample_day = str(opened["cal_date"].iloc[0]).replace("-", "")[:8]
            queries = (*_historical_queries(sample_day), *_realtime_queries())
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="data-access") as pool:
                checks.extend(pool.map(lambda query: _read_check(client, query)[0], queries))
        else:
            checks[0].update(status="unconfirmed", message="样本窗口没有交易日，请核对日期后重试。")
    return {
        "source": "tushare",
        "checked_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "fingerprint": access_fingerprint(token, start),
        "checks": checks,
        "history_ready": REQUIRED.issubset(
            item["endpoint"] for item in checks if item["status"] == "ok"
        ),
        "realtime_ready": any(
            item["endpoint"] == "rt_k" and item["status"] == "ok" for item in checks
        ),
    }


def load_access_report(state: AppState) -> dict[str, Any] | None:
    """Return a recent result only for the currently saved credentials and download range."""
    path = ensure_app_config_dir() / "data-source-check.json"
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        checked = datetime.datetime.fromisoformat(report["checked_at"])
        age = (datetime.datetime.now(datetime.UTC) - checked).total_seconds()
        expected = access_fingerprint(
            state.tushare_token, state.history_start_date, state.data_source
        )
        if 0 <= age < CACHE_SECONDS and report["fingerprint"] == expected:
            return cast(dict[str, Any], report)
    except (ValueError, KeyError, TypeError):
        return None
    return None


def ensure_access_report(state: AppState, *, force: bool = False) -> dict[str, Any]:
    """Keep forward navigation and direct download requests on the same validation path."""
    cached = load_access_report(state)
    if cached is not None and not force:
        return cached
    if state.data_source != "tushare":
        raise ValueError("当前向导仅支持检测 Tushare；其它历史源请按扩展文档接入。")
    if state.history_start_date is None:
        raise ValueError("历史起始日期未配置，无法检测数据源权限。")
    report = check_tushare_access(state.tushare_token, state.history_start_date)
    write_json(ensure_app_config_dir() / "data-source-check.json", report)
    return report
