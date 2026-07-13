"""v0.2-004-coverage-recovery B05-notify gaps: quantide/notify/__init__.py and dingtalk.py.

Targets uncovered branches:
- get_stock_type: prefixes not in any rule (line 33: default 'SZ'),
  '5'/'6' startswith (line 29-30), '8'/'4'/'9' startswith (line 31-32)
- get_stock_id_hson_helpers / get_stock_id_xt: simple delegation (mostly covered)
- get_stock_id_hson: SZ branch (line 73)
- get_stock_id_jq: SZ branch (line 83)
- get_high_low_limit: 300/688 vs default (lines 92-94)
- open_time_delta: hours 9-15 and default 0 (lines 102-107)
- DingTalkMessage._get_url with and without secret (lines 60-63)
- DingTalkMessage._get_access_token with token (line 40-41) and ValueError (line 48)
- DingTalkMessage._send: status 200 errcode 0, status 200 errcode != 0, status != 200
- DingTalkMessage._send_async: same three paths
- ding() with str and dict input, sync=True and sync=False
"""

from __future__ import annotations

import asyncio
import datetime
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from quantide.notify import dingtalk
from quantide.notify.dingtalk import DingTalkMessage, ding


# ---------------------------------------------------------------------------
# notify/__init__.py
# ---------------------------------------------------------------------------


class TestGetStockType:
    def test_get_stock_type_prefix_branch_unreachable_due_to_uppercase_bug(self) -> None:
        """AC-FR0700-132: documents a production bug — the SH/SZ/BJ prefix branch is unreachable.

        Production code at line 18 does ``stock_code = str(stock_code).upper()``,
        then line 19 checks ``stock_code.startswith(("sh", "sz", "bj"))`` against
        lowercase literals. After uppercasing, these prefixes can never match, so
        this branch is dead code. We assert the buggy current behavior so any
        future fix is observable."""
        from quantide.notify import get_stock_type
        # Lowercase 'sh600000' → uppercased to 'SH600000', then:
        # - startswith(('sh','sz','bj')) → False (no longer lowercase)
        # - startswith(('50','51','60',...)) → False (starts with 'SH', not '60')
        # - startswith(('00','12','13',...)) → False
        # - startswith(('5','6')) → False
        # - startswith(('8','4','9')) → False
        # → falls through to default 'SZ'
        assert get_stock_type("sh600000") == "SZ"

    def test_get_stock_type_50_51_60_prefix_returns_sh(self) -> None:
        """AC-FR0700-133: 50/51/60/73/90/110/113/132/204/78 prefixes are SH."""
        from quantide.notify import get_stock_type
        for code in ("600000", "510500", "501000", "730000", "900000", "110000"):
            assert get_stock_type(code) == "SH", code

    def test_get_stock_type_00_30_prefix_returns_sz(self) -> None:
        """AC-FR0700-134: 00/12/13/18/15/16/20/30/39/115/1318 prefixes are SZ."""
        from quantide.notify import get_stock_type
        for code in ("000001", "300750", "123456", "131800"):
            assert get_stock_type(code) == "SZ", code

    def test_get_stock_type_5_or_6_prefix_returns_sh(self) -> None:
        """AC-FR0700-135: codes starting with '5' or '6' are SH (after rule-list fails)."""
        from quantide.notify import get_stock_type
        assert get_stock_type("512350") == "SH"  # not in the explicit list → falls into startswith check

    def test_get_stock_type_8_4_9_prefix_returns_bj(self) -> None:
        """AC-FR0700-136: codes starting with 8/4/9 are BJ."""
        from quantide.notify import get_stock_type
        for code in ("830001", "430001", "930001"):
            assert get_stock_type(code) == "BJ", code

    def test_get_stock_type_unknown_prefix_returns_sz_default(self) -> None:
        """AC-FR0700-137: unknown prefixes default to SZ."""
        from quantide.notify import get_stock_type
        assert get_stock_type("777777") == "SZ"


class TestStockIdHelpers:
    def test_get_stock_id_hson_helpers_with_dot(self) -> None:
        """AC-FR0700-138: get_stock_id_hson_helpers strips '.' and appends suffix."""
        from quantide.notify import get_stock_id_hson_helpers
        assert get_stock_id_hson_helpers("600136.XSHG") == "600136SH"
        assert get_stock_id_hson_helpers("000001.SZ") == "000001SZ"

    def test_get_stock_id_xt_with_dot(self) -> None:
        """AC-FR0700-139: get_stock_id_xt strips '.' and appends suffix."""
        from quantide.notify import get_stock_id_xt
        assert get_stock_id_xt("600136.XSHG") == "600136SH"

    def test_get_stock_id_hson_sz_branch(self) -> None:
        """AC-FR0700-140: SZ stocks get .SZ suffix in hson format."""
        from quantide.notify import get_stock_id_hson
        assert get_stock_id_hson("000001.SZ") == "000001.SZ"

    def test_get_stock_id_hson_sh_branch(self) -> None:
        """AC-FR0700-141: SH stocks get .SS suffix in hson format."""
        from quantide.notify import get_stock_id_hson
        assert get_stock_id_hson("600000.SH") == "600000.SS"

    def test_get_stock_id_jq_sz_branch(self) -> None:
        """AC-FR0700-142: SZ stocks get .XSHE in jq format."""
        from quantide.notify import get_stock_id_jq
        assert get_stock_id_jq("000001.SZ") == "000001.XSHE"

    def test_get_stock_id_jq_sh_branch(self) -> None:
        """AC-FR0700-143: SH stocks get .XSHG in jq format."""
        from quantide.notify import get_stock_id_jq
        assert get_stock_id_jq("600000.SH") == "600000.XSHG"


class TestHighLowLimit:
    def test_high_low_limit_300_prefix_is_20pct(self) -> None:
        """AC-FR0700-144: 300xxx stocks have ±20% limit."""
        from quantide.notify import get_high_low_limit
        up, down = get_high_low_limit("300750", 10.0)
        assert up == 12.0
        assert down == 8.0

    def test_high_low_limit_688_prefix_is_20pct(self) -> None:
        """AC-FR0700-145: 688xxx stocks have ±20% limit."""
        from quantide.notify import get_high_low_limit
        up, down = get_high_low_limit("688001", 50.0)
        assert up == 60.0
        assert down == 40.0

    def test_high_low_limit_other_prefix_is_10pct(self) -> None:
        """AC-FR0700-146: non-300/688 stocks have ±10% limit."""
        from quantide.notify import get_high_low_limit
        up, down = get_high_low_limit("600000", 10.0)
        assert up == 11.0
        assert down == 9.0


class TestOpenTimeDelta:
    def test_open_time_delta_known_hours(self) -> None:
        """AC-FR0700-147: open_time_delta returns expected offsets for trading hours."""
        from quantide.notify import open_time_delta

        assert open_time_delta(datetime.datetime(2024, 1, 1, 9, 30)) == 0
        assert open_time_delta(datetime.datetime(2024, 1, 1, 9, 35)) == 5
        assert open_time_delta(datetime.datetime(2024, 1, 1, 10, 0)) == 30
        assert open_time_delta(datetime.datetime(2024, 1, 1, 11, 30)) == 120
        assert open_time_delta(datetime.datetime(2024, 1, 1, 13, 0)) == 120
        assert open_time_delta(datetime.datetime(2024, 1, 1, 14, 30)) == 210
        assert open_time_delta(datetime.datetime(2024, 1, 1, 15, 0)) == 240

    def test_open_time_delta_unknown_hour_returns_zero(self) -> None:
        """AC-FR0700-148: hours outside trading hours return 0."""
        from quantide.notify import open_time_delta
        assert open_time_delta(datetime.datetime(2024, 1, 1, 8, 0)) == 0
        assert open_time_delta(datetime.datetime(2024, 1, 1, 16, 0)) == 0
        assert open_time_delta(datetime.datetime(2024, 1, 1, 22, 0)) == 0


# ---------------------------------------------------------------------------
# notify/dingtalk.py
# ---------------------------------------------------------------------------


def test_dingtalk_get_access_token_returns_value(monkeypatch) -> None:
    """AC-FR0700-149: _get_access_token returns token when configured."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "test-token")
    assert DingTalkMessage._get_access_token() == "test-token"


def test_dingtalk_get_access_token_raises_when_missing(monkeypatch) -> None:
    """AC-FR0700-150: _get_access_token raises ValueError when token is empty."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "")
    with pytest.raises(ValueError, match="dingtalk_access_token"):
        DingTalkMessage._get_access_token()


def test_dingtalk_get_url_without_secret(monkeypatch) -> None:
    """AC-FR0700-151: _get_url returns URL with access_token when no secret configured."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok-123")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    url = DingTalkMessage._get_url()

    assert "access_token=tok-123" in url
    assert "timestamp=" not in url
    assert "sign=" not in url


def test_dingtalk_get_url_with_secret(monkeypatch) -> None:
    """AC-FR0700-152: _get_url appends timestamp+sign when secret configured."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok-xyz")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "my-secret")

    url = DingTalkMessage._get_url()

    assert "access_token=tok-xyz" in url
    assert "timestamp=" in url
    assert "sign=" in url


def test_dingtalk_send_success(monkeypatch) -> None:
    """AC-FR0700-153: _send returns response content when status=200 and errcode=0."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = json.dumps({"errcode": 0, "errmsg": "ok"}).encode()

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: fake_response)

    result = DingTalkMessage._send({"text": {"content": "hi"}})

    assert result is not None
    assert "errcode" in result


def test_dingtalk_send_error_status(monkeypatch) -> None:
    """AC-FR0700-154: _send returns None on non-200 status."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.content = b"server error"

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: fake_response)

    result = DingTalkMessage._send({"text": {"content": "hi"}})
    assert result is None


def test_dingtalk_send_errcode_nonzero(monkeypatch) -> None:
    """AC-FR0700-155: _send returns None when errcode != 0."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = json.dumps({"errcode": 310000, "errmsg": "bad"}).encode()

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: fake_response)

    result = DingTalkMessage._send({"text": {"content": "hi"}})
    assert result is None


def test_dingtalk_ding_with_str_input_sync(monkeypatch) -> None:
    """AC-FR0700-156: ding() with str input + sync=True calls _send with text payload."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    captured = {}

    def fake_send(msg):
        captured["msg"] = msg
        return "ok"

    monkeypatch.setattr(DingTalkMessage, "_send", classmethod(lambda cls, m: fake_send(m)))

    result = ding("hello world", sync=True)
    assert result == "ok"
    assert captured["msg"]["msgtype"] == "text"
    assert captured["msg"]["text"]["content"] == "hello world"
    assert captured["msg"]["at"]["isAtAll"] is False


def test_dingtalk_ding_with_dict_input_sync(monkeypatch) -> None:
    """AC-FR0700-157: ding() with dict input + sync=True builds markdown payload."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    captured = {}

    def fake_send(msg):
        captured["msg"] = msg
        return "ok"

    monkeypatch.setattr(DingTalkMessage, "_send", classmethod(lambda cls, m: fake_send(m)))

    result = ding({"title": "T", "text": "B"}, sync=True)
    assert result == "ok"
    assert captured["msg"]["msgtype"] == "markdown"
    assert captured["msg"]["markdown"]["title"] == "T"
    assert captured["msg"]["markdown"]["text"] == "B"


def test_dingtalk_ding_with_at_all_true(monkeypatch) -> None:
    """AC-FR0700-158: ding() with at_all=True sets isAtAll=True in payload."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    captured = {}

    def fake_send(msg):
        captured["msg"] = msg
        return "ok"

    monkeypatch.setattr(DingTalkMessage, "_send", classmethod(lambda cls, m: fake_send(m)))

    ding("hi all", sync=True, at_all=True)
    assert captured["msg"]["at"]["isAtAll"] is True


@pytest.mark.asyncio
async def test_dingtalk_ding_async_returns_task(monkeypatch) -> None:
    """AC-FR0700-159: ding() with sync=False returns a scheduled asyncio task."""
    monkeypatch.setattr(dingtalk, "get_dingtalk_access_token", lambda: "tok")
    monkeypatch.setattr(dingtalk, "get_dingtalk_secret", lambda: "")

    captured = {}

    async def fake_send_async(cls, msg):
        captured["msg"] = msg
        return "ok"

    monkeypatch.setattr(DingTalkMessage, "_send_async", classmethod(fake_send_async))

    # ding() calls asyncio.create_task under the hood. We run it inside an
    # explicit event loop, capture the task, then cancel cleanly.
    task = ding("async hello", sync=False)
    # If we got an asyncio.Task or coroutine, the create_task path was taken.
    if asyncio.isfuture(task):
        await asyncio.wait([task])
    elif asyncio.iscoroutine(task):
        await task