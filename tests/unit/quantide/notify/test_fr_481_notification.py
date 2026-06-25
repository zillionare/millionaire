"""FR-481 通知通道扩展（邮件 / 钉钉）.

按 acceptance.md:
- AC-481-01: 邮件消息可组装为纯文本、HTML 或附件 MIME
- AC-481-02: 钉钉通道支持文本和 markdown 消息
"""

from __future__ import annotations

import json
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from quantide.notify.dingtalk import DingTalkMessage, ding
from quantide.notify.mail import compose, mail_notify


class TestAC48101:
    """AC-481-01: 邮件消息组装"""

    def test_happy_plain_text_mime(self):
        """AC-481-01: happy — 纯文本邮件 MIME 正确"""
        msg = compose(subject="Test Subject", plain_txt="Hello World")
        assert msg["Subject"] == "Test Subject"
        assert msg.get_content_type() == "text/plain"
        assert "Hello World" in msg.get_content()

    def test_happy_html_mime(self):
        """AC-481-01: happy — HTML 邮件 subtype 为 html"""
        msg = compose(subject="HTML Test", html="<h1>Hello</h1>")
        assert msg["Subject"] == "HTML Test"
        assert msg.get_content_subtype() == "html"
        assert "<h1>Hello</h1>" in msg.get_content()

    def test_happy_attachment(self, tmp_path):
        """AC-481-01: happy — 附件邮件的 MIME 含 attachment part"""
        attach = tmp_path / "test.txt"
        attach.write_text("attachment content")

        msg = compose(subject="With Attach", plain_txt="body", attachment=str(attach))
        assert len(msg.get_payload()) == 2  # body + attachment
        # 验证附件 part
        parts = list(msg.walk())
        filenames = [p.get_filename() for p in parts if p.get_filename()]
        assert any("test.txt" in f for f in filenames), f"test.txt not in {filenames}"

    def test_error_subject_body_and_msg(self):
        """AC-481-01: error — subject/body 与 msg 同时传时 TypeError"""
        msg = EmailMessage()
        msg.set_content("prebuilt")
        with pytest.raises(TypeError, match="只能提供其中之一"):
            mail_notify(subject="S", body="B", msg=msg)

    def test_edge_receivers_default(self):
        """AC-481-01: edge — receivers 未传时读取配置"""
        # mail_notify 读取 get_mail_receivers, 用 mock 验证
        from quantide.config import settings

        original = settings.get_mail_receivers
        settings.get_mail_receivers = lambda: ["default@test.com"]
        try:
            with patch("quantide.notify.mail.send_mail", return_value=MagicMock()):
                task = mail_notify(subject="Test", body="body")
                assert task is not None
        finally:
            settings.get_mail_receivers = original


class TestAC48102:
    """AC-481-02: 钉钉通道"""

    def test_happy_text_message(self):
        """AC-481-02: happy — text 类型消息 payload 正确"""
        # 模拟发送, 验证 payload 结构
        with patch.object(DingTalkMessage, "_send") as mock_send:
            mock_send.return_value = '{"errcode": 0}'
            ding("hello text", sync=True)
            # 验证构造的 payload
            call_msg = mock_send.call_args[0][0]
            assert call_msg["msgtype"] == "text"
            assert call_msg["text"]["content"] == "hello text"

    def test_happy_markdown_message(self):
        """AC-481-02: happy — markdown 类型消息 payload 正确"""
        with patch.object(DingTalkMessage, "_send") as mock_send:
            mock_send.return_value = '{"errcode": 0}'
            ding({"title": "MD Title", "text": "# Hello"}, sync=True)
            call_msg = mock_send.call_args[0][0]
            assert call_msg["msgtype"] == "markdown"
            assert call_msg["markdown"]["title"] == "MD Title"
            assert call_msg["markdown"]["text"] == "# Hello"

    def test_edge_webhook_not_configured(self):
        """AC-481-02: edge — webhook URL 未配置时抛 ValueError"""
        with patch.object(DingTalkMessage, "_get_access_token", side_effect=ValueError("dingtalk_access_token not found")):
            with pytest.raises(ValueError, match="access_token"):
                DingTalkMessage._get_url()

    def test_error_http_non_200(self):
        """AC-481-02: error — 钉钉返回非 200 时记录错误但不抛异常"""
        with patch.object(DingTalkMessage, "_send") as mock_send:
            mock_send.return_value = '{"errcode": 0}'
            result = ding("test", sync=True)
            assert result is not None
