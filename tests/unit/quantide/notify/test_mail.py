from email.message import EmailMessage

import quantide.notify.mail as mail_module
from quantide.config.branding import Branding


def test_mail_notify_resolves_default_subject_at_send_time(monkeypatch):
    sent: dict[str, EmailMessage] = {}

    monkeypatch.setattr(
        mail_module,
        "get_branding",
        lambda: Branding(
            edition="zillionaire",
            runtime_name="quantide",
            product_name="Zillionaire",
            release_package="quantide-zillionaire",
            company_name="Zillionare",
            support_email="business@quantide.cn",
        ),
    )
    monkeypatch.setattr(mail_module, "get_mail_sender", lambda: "sender@example.com")
    monkeypatch.setattr(mail_module, "get_mail_server", lambda: "smtp.example.com")
    monkeypatch.setenv("QUANTIDE_MAIL_PASSWORD", "secret")

    def fake_send_mail(*args, **kwargs):
        sent["msg"] = args[3]
        return object()

    monkeypatch.setattr(mail_module, "send_mail", fake_send_mail)

    mail_module.mail_notify(body="hello", receivers=["receiver@example.com"])

    assert sent["msg"]["Subject"] == "Zillionaire 交易通知"


def test_mail_notify_keeps_explicit_subject(monkeypatch):
    sent: dict[str, EmailMessage] = {}

    monkeypatch.setattr(
        mail_module,
        "get_branding",
        lambda: Branding(
            edition="zillionaire",
            runtime_name="quantide",
            product_name="Zillionaire",
            release_package="quantide-zillionaire",
            company_name="Zillionare",
            support_email="business@quantide.cn",
        ),
    )
    monkeypatch.setattr(mail_module, "get_mail_sender", lambda: "sender@example.com")
    monkeypatch.setattr(mail_module, "get_mail_server", lambda: "smtp.example.com")
    monkeypatch.setenv("QUANTIDE_MAIL_PASSWORD", "secret")

    def fake_send_mail(*args, **kwargs):
        sent["msg"] = args[3]
        return object()

    monkeypatch.setattr(mail_module, "send_mail", fake_send_mail)

    mail_module.mail_notify(
        subject="Custom subject",
        body="hello",
        receivers=["receiver@example.com"],
    )

    assert sent["msg"]["Subject"] == "Custom subject"
