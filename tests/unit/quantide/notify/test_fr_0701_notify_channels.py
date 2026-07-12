"""v0.2-003 FR-0701 AC-FR-0701-1..5 notification channel contracts."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage

import pytest

from quantide.notify import (
    get_high_low_limit,
    get_stock_id_hson,
    get_stock_id_jq,
    get_stock_id_xt,
)
from quantide.notify.dingtalk import DingTalkMessage
from quantide.notify.mail import compose, send_mail


def test_compose_builds_plain_html_and_attachment_messages(tmp_path):
    """AC-FR-0701-1: MIME bodies and attachment bytes are preserved."""
    attachment = tmp_path / "report.txt"
    attachment.write_bytes(b"report bytes")

    plain = compose("plain", plain_txt="body")
    html = compose("html", html="<b>body</b>")
    attached = compose("attached", plain_txt="body", attachment=str(attachment))

    assert plain.get_content_type() == "text/plain"
    assert html.get_content_subtype() == "html"
    assert attached.get_payload()[-1].get_payload(decode=True) == b"report bytes"


def test_compose_requires_a_body():
    """AC-FR-0701-1: body-less messages fail at the composition boundary."""
    with pytest.raises(AssertionError, match="Either plain_txt or html"):
        compose("empty")


async def test_send_mail_forwards_envelope_to_smtp_boundary(monkeypatch):
    """AC-FR-0701-2: SMTP is a fake boundary and receives all envelope fields."""
    sent: dict[str, object] = {}

    async def fake_send(message: EmailMessage, **kwargs: object) -> None:
        sent["message"] = message
        sent["kwargs"] = kwargs

    monkeypatch.setattr("quantide.notify.mail.aiosmtplib.send", fake_send)
    task = send_mail(
        "from@example.test",
        ["to@example.test"],
        "password",
        subject="subject",
        body="body",
        host="smtp.example.test",
        port=2525,
        cc=["cc@example.test"],
        bcc=["bcc@example.test"],
    )
    await task

    message = sent["message"]
    assert isinstance(message, EmailMessage)
    assert message["From"] == "from@example.test"
    assert message["To"] == "to@example.test"
    assert message["Cc"] == "cc@example.test"
    assert message["Bcc"] == "bcc@example.test"
    assert sent["kwargs"] == {
        "hostname": "smtp.example.test",
        "port": 2525,
        "username": "from@example.test",
        "password": "password",
    }


def test_dingtalk_business_error_is_not_reported_as_success(monkeypatch):
    """AC-FR-0701-4: a non-zero DingTalk errcode has an observable failure."""
    class Response:
        status_code = 200
        content = b'{"errcode": 310000, "errmsg": "bad request"}'

    monkeypatch.setattr(DingTalkMessage, "_get_url", lambda: "https://example.test")
    monkeypatch.setattr("quantide.notify.dingtalk.httpx.post", lambda *args, **kwargs: Response())

    assert DingTalkMessage._send({"msgtype": "text"}) is None


def test_market_helpers_use_independent_market_rules():
    """AC-FR-0701-5: Shanghai, Shenzhen and price-limit conversions are stable."""
    assert get_stock_id_hson("600000.XSHG") == "600000.SS"
    assert get_stock_id_xt("000001.XSHE") == "000001SZ"
    assert get_stock_id_jq("600000.SS") == "600000.XSHG"
    assert get_high_low_limit("300001", 10.0) == (12.0, 8.0)
    assert get_high_low_limit("600000", 10.0) == (11.0, 9.0)
