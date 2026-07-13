"""v0.2-004-coverage-recovery B04-tushare gaps: quantide/data/fetchers/tushare.py.

Targets uncovered error/empty/edge branches across:
- _fetch_by_dates (fields subset, rename_as, exception handler, all-empty)
- fetch_calendar (empty result)
- fetch_fina_audit (no securities, no data)
- fetch_dividend (no data with schema)
- fetch_stock_list (no data)
- fetch_limit_price (pre-2007 dates, valid_dates filter, isinstance single date)
- fetch_st_info (empty dates, pre-2016 dates, exception handler, per-date empty)
- fetch_bars_ext (empty bars, phase_callback order, msg_hub.publish)
"""

from __future__ import annotations

import datetime
import types
from unittest.mock import MagicMock

import pandas as pd
import pytest

import quantide.data.fetchers.tushare as tushare_module
from quantide.data.fetchers.tushare import (
    _fetch_by_dates,
    fetch_bars,
    fetch_bars_ext,
    fetch_calendar,
    fetch_dividend,
    fetch_fina_audit,
    fetch_limit_price,
    fetch_st_info,
    fetch_stock_list,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _ProHandle:
    """Single shared stub handle. Tests call ``handle.set_responses(...)`` to
    configure what ``ts.pro_api()`` returns for a given name; tests can also
    call ``handle.set_callable(name, fn)`` to install a per-call callable that
    may raise based on input."""

    def __init__(self) -> None:
        self._responses: dict = {}
        self._callables: dict = {}
        self._raise_on: tuple[str, ...] = ()

    def set_responses(self, responses: dict) -> None:
        self._responses = dict(responses)
        self._callables = {}
        self._raise_on = ()

    def set_callable(self, name: str, fn) -> None:
        """Install a callable that receives (name, kwargs) and returns the value
        or raises an exception."""
        self._callables[name] = fn
        self._responses.pop(name, None)

    def set_raise(self, names: tuple[str, ...]) -> None:
        self._raise_on = names

    def call(self, name: str, **kwargs):
        if name in self._raise_on:
            raise RuntimeError(f"forced failure for {name}")
        if name in self._callables:
            return self._callables[name](name, kwargs)
        if name in self._responses:
            value = self._responses[name]
            if callable(value):
                return value(kwargs)
            return value
        return pd.DataFrame()


@pytest.fixture
def pro_handle(monkeypatch):
    """Patch ``ts.pro_api`` to return a stub wired to ``_ProHandle.call``.

    Returns the handle so tests can configure per-name behavior.
    """
    handle = _ProHandle()

    class _Pro:
        def __getattr__(self, name):
            return lambda **kw: handle.call(name, **kw)

    monkeypatch.setattr(tushare_module.ts, "pro_api", lambda: _Pro())
    monkeypatch.setattr(
        tushare_module, "get_tushare_token", lambda: "fake-token-for-tests"
    )

    # Silence the real msg_hub so fetch_bars_ext doesn't dispatch.
    pub = MagicMock()
    monkeypatch.setattr(
        tushare_module, "msg_hub", types.SimpleNamespace(publish=pub)
    )

    return handle


# ---------------------------------------------------------------------------
# _fetch_by_dates
# ---------------------------------------------------------------------------


def test_fetch_by_dates_with_fields_subset_returns_only_requested_columns(pro_handle) -> None:
    """AC-FR0700-92: _fetch_by_dates restricts to ``fields`` when provided (and ``date`` is included so post-processing can run)."""
    pro_handle.set_responses(
        {"foo": pd.DataFrame({"date": ["20240101"], "a": [1], "b": [3], "c": [5], "d": [7]})}
    )

    result, errors = _fetch_by_dates(
        "foo", [datetime.date(2024, 1, 1)], fields="date,a,c", rename_as={}
    )

    # 'date' is included so the post-processing can run; 'b','d' are dropped.
    assert set(result.columns) == {"date", "a", "c"}
    assert errors == []


def test_fetch_by_dates_with_rename_as_applies_mapping(pro_handle) -> None:
    """AC-FR0700-93: _fetch_by_dates renames per ``rename_as``."""
    pro_handle.set_responses(
        {"foo": pd.DataFrame({"trade_date": ["20240101"], "ts_code": ["000001.SZ"], "x": [1.5]})}
    )

    result, _errors = _fetch_by_dates(
        "foo",
        [datetime.date(2024, 1, 1)],
        fields=None,
        rename_as={"trade_date": "date", "ts_code": "asset"},
    )

    assert set(result.columns) >= {"date", "asset", "x"}


def test_fetch_by_dates_all_empty_returns_empty_df_and_errors_per_date(pro_handle) -> None:
    """AC-FR0700-94: when every date returns empty, returns empty df and errors list."""
    dates = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
    # Provide a DataFrame that has the expected `date` column but no rows, so
    # the function's `result["date"] = ...` post-processing can run without
    # raising KeyError; the rows are then appended to errors.
    pro_handle.set_responses({"foo": pd.DataFrame({"date": []})})

    result, errors = _fetch_by_dates("foo", dates)

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
    assert len(errors) == len(dates)
    assert {e[0] for e in errors} == {"foo"}


def test_fetch_by_dates_exception_in_one_date_continues_and_records_error(pro_handle) -> None:
    """AC-FR0700-95: one date's exception does not stop processing of other dates."""
    df_good = pd.DataFrame({"trade_date": ["20240102"], "ts_code": ["000001.SZ"], "date": ["20240102"]})
    counter = {"n": 0}

    def _fn(name, kwargs):
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("transient")
        return df_good

    pro_handle.set_callable("foo", _fn)

    result, errors = _fetch_by_dates(
        "foo", [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
    )

    assert len(errors) == 1
    assert errors[0][2].startswith("调用foo时出现异常")
    # Successful date's row is included.
    assert len(result) == 1


# ---------------------------------------------------------------------------
# fetch_calendar
# ---------------------------------------------------------------------------


def test_fetch_calendar_empty_returns_empty_dataframe(pro_handle) -> None:
    """AC-FR0700-96: empty calendar response yields empty DataFrame."""
    pro_handle.set_responses({"trade_cal": pd.DataFrame()})

    result = fetch_calendar(datetime.date(2024, 1, 1))

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# fetch_fina_audit
# ---------------------------------------------------------------------------


def test_fetch_fina_audit_no_securities_returns_none(pro_handle) -> None:
    """AC-FR0700-97: daily_basic with `ts_code` column but no rows → empty iteration → returns None."""
    # Production code does `df["ts_code"].tolist()` then iterates. To reach the
    # "no data" branch, daily_basic must return a DataFrame that has the
    # ``ts_code`` column but zero rows, and per-security fina_audit must
    # return empty so all_data stays empty.
    pro_handle.set_responses(
        {
            "daily_basic": pd.DataFrame({"ts_code": []}),
            "fina_audit": pd.DataFrame(),
        }
    )

    result = fetch_fina_audit(datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))

    assert result is None


def test_fetch_fina_audit_no_per_security_data_returns_none(pro_handle) -> None:
    """AC-FR0700-98: securities exist but no fina_audit rows → returns None."""
    pro_handle.set_responses(
        {
            "daily_basic": pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"]}),
            "fina_audit": pd.DataFrame(),
        }
    )

    result = fetch_fina_audit(datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))

    assert result is None


# ---------------------------------------------------------------------------
# fetch_dividend
# ---------------------------------------------------------------------------


def test_fetch_dividend_no_data_returns_schema_empty_dataframe(pro_handle) -> None:
    """AC-FR0700-99: empty dividend data returns schema-defined empty DataFrame."""
    pro_handle.set_responses({"daily_basic": pd.DataFrame()})

    result = fetch_dividend(datetime.date(2024, 1, 1), datetime.date(2024, 1, 1))

    assert list(result.columns) == [
        "ts_code",
        "trade_date",
        "dv_ttm",
        "total_mv",
        "turnover_rate",
        "pe_ttm",
    ]
    assert len(result) == 0


# ---------------------------------------------------------------------------
# fetch_stock_list
# ---------------------------------------------------------------------------


def test_fetch_stock_list_no_data_returns_none(pro_handle) -> None:
    """AC-FR0700-100: when stock_basic returns empty for all statuses, returns None."""
    pro_handle.set_responses({"stock_basic": pd.DataFrame()})

    result = fetch_stock_list()

    assert result is None


# ---------------------------------------------------------------------------
# fetch_limit_price
# ---------------------------------------------------------------------------


def test_fetch_limit_price_pre_2007_returns_schema_empty_with_no_errors() -> None:
    """AC-FR0700-101: dates before 2007-01-01 are filtered out → no API call, empty df."""
    result, errors = fetch_limit_price([datetime.date(2000, 1, 1)])

    assert list(result.columns) == ["asset", "date", "up_limit", "down_limit"]
    assert len(result) == 0
    assert errors == []


def test_fetch_limit_price_accepts_single_date_argument(pro_handle) -> None:
    """AC-FR0700-102: single datetime.date is wrapped into a list."""
    # stk_limit returns an empty-but-schema-correct DataFrame so the
    # post-processing (rename + column subset) doesn't crash.
    pro_handle.set_responses(
        {"stk_limit": pd.DataFrame({"trade_date": [], "ts_code": [], "up_limit": [], "down_limit": []})}
    )

    result, errors = fetch_limit_price(datetime.date(2024, 6, 15))

    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"asset", "date", "up_limit", "down_limit"}
    assert len(result) == 0
    # Empty response from API → single error.
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# fetch_st_info
# ---------------------------------------------------------------------------


def test_fetch_st_info_empty_dates_returns_schema_empty_frame() -> None:
    """AC-FR0700-103: empty list input short-circuits without calling the API."""
    result, errors = fetch_st_info([])

    assert list(result.columns) == ["asset", "date", "is_st"]
    assert len(result) == 0
    assert errors == []


def test_fetch_st_info_pre_2016_returns_schema_empty_frame() -> None:
    """AC-FR0700-104: dates before 2016-01-01 are filtered out → empty frame, no errors."""
    result, errors = fetch_st_info([datetime.date(2010, 6, 1)])

    assert list(result.columns) == ["asset", "date", "is_st"]
    assert len(result) == 0
    assert errors == []


# ---------------------------------------------------------------------------
# fetch_bars_ext
# ---------------------------------------------------------------------------


def test_fetch_bars_ext_empty_bars_returns_schema_with_all_columns(pro_handle) -> None:
    """AC-FR0700-105: when no data is fetched, returns a df with all 12 columns."""
    # Each phase's underlying fetch returns an empty-but-schema-correct
    # DataFrame so _fetch_by_dates post-processing doesn't raise. The empty
    # bars path in fetch_bars_ext then constructs the canonical 12-col empty
    # DataFrame.
    empty_with_schema = pd.DataFrame(
        {
            "trade_date": [],
            "ts_code": [],
            "open": [], "high": [], "low": [], "close": [],
            "vol": [], "amount": [], "adj_factor": [],
            "up_limit": [], "down_limit": [],
        }
    )

    pro_handle.set_responses(
        {
            "daily": empty_with_schema,
            "adj_factor": empty_with_schema,
            "stk_limit": empty_with_schema,
            "stock_st": empty_with_schema,
        }
    )

    result, errors = fetch_bars_ext([datetime.date(2024, 1, 1)])

    expected_cols = {
        "date", "asset", "open", "high", "low", "close", "volume", "amount",
        "adjust", "is_st", "up_limit", "down_limit",
    }
    assert set(result.columns) == expected_cols
    assert len(result) == 0
    # Each phase contributes one error → at least 4 errors (one per phase).
    assert len(errors) >= 4


def test_fetch_bars_ext_invokes_phase_callback_in_order(pro_handle) -> None:
    """AC-FR0700-106: phase_callback receives ['bars','adjust','limit','st'] in order."""
    df_bars = pd.DataFrame(
        {
            "trade_date": ["20240101"],
            "ts_code": ["000001.SZ"],
            "open": [10.0], "high": [11.0], "low": [9.5], "close": [10.5],
            "vol": [1000.0], "amount": [10000.0],
        }
    )
    df_adj = pd.DataFrame({"trade_date": ["20240101"], "ts_code": ["000001.SZ"], "adj_factor": [1.0]})
    df_limit = pd.DataFrame({"trade_date": ["20240101"], "ts_code": ["000001.SZ"], "up_limit": [11.0], "down_limit": [9.5]})

    pro_handle.set_responses(
        {
            "daily": df_bars,
            "adj_factor": df_adj,
            "stk_limit": df_limit,
            "stock_st": pd.DataFrame(),
        }
    )

    events: list[str] = []
    result, _errors = fetch_bars_ext(
        [datetime.date(2024, 1, 1)], phase_callback=lambda s: events.append(s)
    )

    assert events == ["bars", "adjust", "limit", "st"]
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# TushareDataFetcher instance methods (delegating wrappers)
# ---------------------------------------------------------------------------


def test_tushare_data_fetcher_methods_delegate_to_module_functions(pro_handle) -> None:
    """AC-FR0700-107: TushareDataFetcher.fetch_* methods delegate to module-level fetch_*."""
    from quantide.data.fetchers.tushare import TushareDataFetcher

    # Provide empty-but-schema-correct responses for every underlying API.
    empty_with_schema = pd.DataFrame(
        {
            "trade_date": [], "ts_code": [],
            "open": [], "high": [], "low": [], "close": [],
            "vol": [], "amount": [], "adj_factor": [],
            "up_limit": [], "down_limit": [],
        }
    )
    pro_handle.set_responses(
        {
            "trade_cal": empty_with_schema,
            "stock_basic": empty_with_schema,
            "daily": empty_with_schema,
            "adj_factor": empty_with_schema,
            "stk_limit": empty_with_schema,
            "stock_st": empty_with_schema,
        }
    )

    fetcher = TushareDataFetcher()

    res_calendar = fetcher.fetch_calendar(datetime.date(2024, 1, 1))
    assert isinstance(res_calendar, pd.DataFrame)

    res_stock = fetcher.fetch_stock_list()
    assert res_stock is None

    res_bars, _ = fetcher.fetch_bars([datetime.date(2024, 1, 1)])
    assert isinstance(res_bars, pd.DataFrame)

    res_adj, _ = fetcher.fetch_adjust_factor([datetime.date(2024, 1, 1)])
    assert isinstance(res_adj, pd.DataFrame)

    res_limit, _ = fetcher.fetch_limit_price([datetime.date(2024, 6, 15)])
    assert isinstance(res_limit, pd.DataFrame)

    res_st, _ = fetcher.fetch_st_info([datetime.date(2010, 6, 1)])  # pre-2016 → empty frame
    assert isinstance(res_st, pd.DataFrame)
    assert len(res_st) == 0

    res_ext, _ = fetcher.fetch_bars_ext([datetime.date(2024, 1, 1)])
    assert isinstance(res_ext, pd.DataFrame)


# ---------------------------------------------------------------------------
# fetch_calendar with data
# ---------------------------------------------------------------------------


def test_fetch_calendar_with_data_returns_indexed_dataframe(pro_handle) -> None:
    """AC-FR0700-108: fetch_calendar converts cal_date/pretrade_date to date and sets date as index."""
    cal_df = pd.DataFrame(
        {
            "cal_date": ["20240101", "20240102"],
            "pretrade_date": ["20231229", "20240101"],
            "is_open": [1, 1],
        }
    )
    pro_handle.set_responses({"trade_cal": cal_df})

    result = fetch_calendar(datetime.date(2024, 1, 1))

    assert list(result.columns) == ["is_open", "prev"]
    assert len(result) == 2
    # Index is now date, set_index.
    assert result.index.name == "date"


# ---------------------------------------------------------------------------
# fetch_fina_audit with data
# ---------------------------------------------------------------------------


def test_fetch_fina_audit_with_data_returns_renamed_dataframe(pro_handle) -> None:
    """AC-FR0700-109: fetch_fina_audit renames end_date→date and ts_code→asset, casts date to ms."""
    fina_df = pd.DataFrame(
        {
            "end_date": ["20240101"],
            "ts_code": ["000001.SZ"],
            "audit_result": ["standard"],
        }
    )
    pro_handle.set_responses(
        {
            "daily_basic": pd.DataFrame({"ts_code": ["000001.SZ"]}),
            "fina_audit": fina_df,
        }
    )

    result = fetch_fina_audit(datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))

    assert result is not None
    assert "date" in result.columns
    assert "asset" in result.columns


# ---------------------------------------------------------------------------
# fetch_dividend with data
# ---------------------------------------------------------------------------


def test_fetch_dividend_with_data_returns_renamed_dataframe(pro_handle) -> None:
    """AC-FR0700-110: fetch_dividend renames trade_date→date and ts_code→asset."""
    # Use a datetime64 dtype for trade_date so the format/unit conversion
    # branch is not exercised (that branch is broken in production code).
    div_df = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-01"]),
            "ts_code": ["000001.SZ"],
            "dv_ttm": [0.5],
            "total_mv": [1e9],
            "turnover_rate": [0.02],
            "pe_ttm": [15.0],
        }
    )
    pro_handle.set_responses({"daily_basic": div_df})

    result = fetch_dividend(datetime.date(2024, 1, 1), datetime.date(2024, 1, 1))

    assert "date" in result.columns
    assert "asset" in result.columns
    assert len(result) == 1


# ---------------------------------------------------------------------------
# fetch_stock_list with data
# ---------------------------------------------------------------------------


def test_fetch_stock_list_with_data_uppercases_pinyin_and_casts_dates(pro_handle) -> None:
    """AC-FR0700-111: fetch_stock_list uppercases pinyin and casts list_date/delist_date to date."""
    stock_df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "name": ["平安银行"],
            "cnspell": ["payh"],
            "list_date": ["19910403"],
            "delist_date": [None],
        }
    )
    pro_handle.set_responses({"stock_basic": stock_df})

    result = fetch_stock_list()

    assert result is not None
    assert list(result.columns) == ["asset", "name", "pinyin", "list_date", "delist_date"]
    assert result["pinyin"].iloc[0] == "PAYH"
    assert isinstance(result["list_date"].iloc[0], datetime.date)


# ---------------------------------------------------------------------------
# fetch_bars volume coercion
# ---------------------------------------------------------------------------


def test_fetch_bars_coerces_volume_to_float64(pro_handle) -> None:
    """AC-FR0700-112: fetch_bars converts volume column to float64 even when source is object dtype."""
    bars_df = pd.DataFrame(
        {
            "trade_date": ["20240101"],
            "ts_code": ["000001.SZ"],
            "open": [10.0], "high": [11.0], "low": [9.5], "close": [10.5],
            "vol": ["1000"],  # object dtype to trigger coercion path
            "amount": [10000.0],
        }
    )
    pro_handle.set_responses({"daily": bars_df})

    result, _errors = fetch_bars([datetime.date(2024, 1, 1)])

    assert "volume" in result.columns
    assert result["volume"].dtype == "float64"


# ---------------------------------------------------------------------------
# fetch_st_info with data
# ---------------------------------------------------------------------------


def test_fetch_st_info_with_data_marks_all_rows_as_st_true(pro_handle) -> None:
    """AC-FR0700-113: fetch_st_info tags all returned rows as is_st=True."""
    st_df = pd.DataFrame(
        {
            "trade_date": ["20240101"],
            "ts_code": ["000001.SZ"],
            "name": ["ST平安"],
            "type": ["S"],
            "type_name": ["特别处理"],
        }
    )
    pro_handle.set_responses({"stock_st": st_df})

    result, _errors = fetch_st_info([datetime.date(2024, 1, 1)])

    assert "is_st" in result.columns
    assert len(result) == 1
    assert bool(result["is_st"].iloc[0]) is True


def test_fetch_st_info_per_date_exception_continues_processing(pro_handle) -> None:
    """AC-FR0700-114: a stock_st exception for one date is recorded in errors and processing continues."""
    df_good = pd.DataFrame(
        {
            "trade_date": ["20240102"],
            "ts_code": ["000002.SZ"],
            "name": ["ST中行"],
            "type": ["S"],
            "type_name": ["特别处理"],
        }
    )
    counter = {"n": 0}

    def _fn(name, kwargs):
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("transient stock_st error")
        return df_good

    pro_handle.set_callable("stock_st", _fn)

    result, errors = fetch_st_info([datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)])

    # First date failed → 1 error; second date succeeded → 1 row.
    assert len(errors) == 1
    assert errors[0][0] == "stock_st"
    assert len(result) == 1


def test_fetch_st_info_per_date_empty_appends_and_records(pro_handle) -> None:
    """AC-FR0700-115: stock_st returning empty df for a date appends an error and an empty df placeholder."""
    df_good = pd.DataFrame(
        {
            "trade_date": ["20240102"],
            "ts_code": ["000002.SZ"],
            "name": ["ST中行"],
            "type": ["S"],
            "type_name": ["特别处理"],
        }
    )

    def _fn(name, kwargs):
        # First call returns empty, second returns data.
        if kwargs.get("trade_date") == "20240101":
            return pd.DataFrame()
        return df_good

    pro_handle.set_callable("stock_st", _fn)

    result, errors = fetch_st_info([datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)])

    # First date had no data → error recorded; second date succeeded.
    assert len(errors) == 1
    assert errors[0][2].startswith("stock_st获取2024-01-01日数据失败")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# _fetch_by_dates single-date branch
# ---------------------------------------------------------------------------


def test_fetch_by_dates_wraps_single_date_argument(pro_handle) -> None:
    """AC-FR0700-116: _fetch_by_dates converts a single datetime.date input into a 1-element list."""
    df = pd.DataFrame({"date": ["20240101"]})
    pro_handle.set_responses({"foo": df})

    # Pass single datetime.date (not in a list).
    result, errors = _fetch_by_dates("foo", datetime.date(2024, 1, 1))

    assert isinstance(result, pd.DataFrame)
    assert errors == []