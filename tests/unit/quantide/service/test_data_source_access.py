"""Permission evidence must be specific, bounded, retryable and credential-safe."""

import datetime
import json
from types import SimpleNamespace

import pytest

from quantide.service import data_source_access as access
from tests.init_access_support import AccessClient


def test_required_history_checks_include_st_limits_and_pipeline_dependencies():
    client = AccessClient()
    report = access.check_tushare_access("secret", "2024-01-02", client=client)
    assert report["history_ready"]
    assert not report["realtime_ready"]
    assert {row["endpoint"] for row in report["checks"]} == access.REQUIRED | {"rt_k", "rt_min"}
    assert len(client.calls) == 11
    assert "secret" not in json.dumps(report)
    assert all(
        params.get("ts_code", "000001.SZ") in {"000001.SZ", "000300.SH"}
        for _, params in client.calls
    )


@pytest.mark.parametrize("endpoint", ["stock_st", "stk_limit"])
def test_missing_critical_permission_is_identified_without_silently_omitting_data(endpoint):
    client = AccessClient(failures={endpoint: PermissionError("积分不足 token=do-not-echo")})
    report = access.check_tushare_access("do-not-echo", "2024-01-02", client=client)
    row = next(row for row in report["checks"] if row["endpoint"] == endpoint)
    assert row["status"] == "denied"
    assert "权限中心" in row["message"]
    assert not report["history_ready"]
    assert "do-not-echo" not in json.dumps(report)


@pytest.mark.parametrize(
    "failure,status",
    [
        (ConnectionError("network unavailable"), "unavailable"),
        (RuntimeError("每分钟访问频次受限"), "rate_limited"),
        (RuntimeError("抱歉，您每分钟最多访问该接口200次，权限详情请访问官网"), "rate_limited"),
        (RuntimeError("token无效"), "invalid_token"),
    ],
)
def test_retryable_and_auth_failures_are_not_mislabelled_as_paid_permission(failure, status):
    report = access.check_tushare_access(
        "secret", "2024-01-02", client=AccessClient(failures={"trade_cal": failure})
    )
    assert report["checks"][0]["status"] == status
    assert "提升积分" not in report["checks"][0]["message"]
    assert not report["history_ready"]


def test_empty_data_is_unconfirmed_and_realtime_field_gaps_cannot_skip_setup():
    client = AccessClient(realtime=True, empty={"stock_st"}, missing={"rt_k": {"trade_time"}})
    report = access.check_tushare_access("secret", "2024-01-02", client=client)
    rows = {row["endpoint"]: row for row in report["checks"]}
    assert rows["stock_st"]["status"] == "unconfirmed"
    assert rows["rt_k"]["status"] == "incompatible"
    assert not report["history_ready"]
    assert not report["realtime_ready"]


def test_cache_is_bound_to_token_range_source_and_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(access, "ensure_app_config_dir", lambda: tmp_path)
    client = AccessClient(realtime=True)
    monkeypatch.setattr(access, "create_probe_client", lambda token: client)
    state = SimpleNamespace(
        tushare_token="secret", history_start_date=datetime.date(2024, 1, 2), data_source="tushare"
    )
    report = access.ensure_access_report(state)
    assert access.load_access_report(state) == report
    assert "secret" not in (tmp_path / "data-source-check.json").read_text(encoding="utf-8")
    state.tushare_token = "changed"
    assert access.load_access_report(state) is None
    state.tushare_token = "secret"
    report["checked_at"] = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    ).isoformat()
    (tmp_path / "data-source-check.json").write_text(json.dumps(report), encoding="utf-8")
    assert access.load_access_report(state) is None


def test_probe_does_not_persist_sdk_token(monkeypatch):
    created = []
    monkeypatch.setattr(access.ts, "pro_api", lambda **kw: created.append(kw) or AccessClient())
    monkeypatch.setattr(access.ts, "set_token", lambda *args: pytest.fail("SDK token write"))
    access.check_tushare_access("secret", "2024-01-02")
    assert created == [{"token": "secret", "timeout": 5}]


def test_force_recheck_observes_account_upgrade_with_same_token(tmp_path, monkeypatch):
    monkeypatch.setattr(access, "ensure_app_config_dir", lambda: tmp_path)
    client = AccessClient(failures={"stock_st": PermissionError("权限不足")})
    monkeypatch.setattr(access, "create_probe_client", lambda token: client)
    state = SimpleNamespace(
        tushare_token="secret", history_start_date=datetime.date(2024, 1, 2), data_source="tushare"
    )
    assert not access.ensure_access_report(state)["history_ready"]
    client.failures.clear()
    assert not access.ensure_access_report(state)["history_ready"]
    assert access.ensure_access_report(state, force=True)["history_ready"]
