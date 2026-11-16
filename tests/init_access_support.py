"""Deterministic raw API responses for initialization permission and routing tests."""

import datetime

import pandas as pd


class AccessClient:
    def __init__(self, *, realtime=False, failures=None, empty=(), missing=None):
        self.realtime = realtime
        self.failures = failures or {}
        self.empty = set(empty)
        self.missing = missing or {}
        self.calls = []

    def query(self, endpoint, fields="", **params):
        self.calls.append((endpoint, params))
        if endpoint in self.failures:
            raise self.failures[endpoint]
        if endpoint in {"rt_k", "rt_min"} and not self.realtime:
            raise PermissionError("此实时接口需单独开通权限")
        columns = fields.split(",") if fields else []
        if endpoint in self.empty:
            return pd.DataFrame(columns=columns)
        row = {
            "ts_code": "000001.SZ", "cal_date": params.get("start_date", "20240102"),
            "is_open": 1, "name": "平安银行", "trade_date": params.get("trade_date", "20240102"),
            "open": 10.0, "high": 10.5, "low": 9.9, "close": 10.2, "pre_close": 10.0,
            "up_limit": 11.0, "down_limit": 9.0, "adj_factor": 2.0, "vol": 10000.0,
            "amount": 100000.0, "total_mv": 10000000.0,
            "index_code": "000300.SH", "con_code": "000001.SZ", "weight": 1.0,
            "time": "2024-01-02 10:00:00", "trade_time": "2024-01-02 10:00:00",
        }
        frame = pd.DataFrame([{key: row[key] for key in columns}])
        return frame.drop(columns=list(self.missing.get(endpoint, ())), errors="ignore")
