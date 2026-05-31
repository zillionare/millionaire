# Millionaire

Millionaire is the free and open-source edition built on the shared `quantide` runtime.

The published package name for this edition is `quantide-millionaire`. Internal technical
identifiers such as the Python import namespace, runtime paths, and local state directories
remain `quantide` by design.

This repository is in active architectural refactoring.

The release-facing README is intentionally kept minimal until the codebase, runtime model, and deployment model are stable enough to publish without misleading users or automation.

Current status:

- the project is not using FastAPI + Vue as its target stack
- the application stack is being consolidated around FastHTML + MonsterUI
- release documentation has not been finalized yet
- development-stage notes are stored under `.dev/`

Until the refactor settles, treat `.dev/` as draft engineering notes rather than release documentation.

For local startup guidance and minimum developer-side acceptance, see `docs/developer-acceptance.md`.

## Development Stub Mode

When you want to demo the real UI and runtime flow without connecting a real gateway or real Tushare,
start Millionaire with the environment variable `QUANTIDE_ENABLE_DEV_STUBS=1`.

Example:

```bash
QUANTIDE_ENABLE_DEV_STUBS=1 uvicorn quantide.app:app --reload
```

If you prefer starting from a shell that has not activated the `quantide` environment,
the equivalent command is:

```bash
QUANTIDE_ENABLE_DEV_STUBS=1 conda run -n quantide uvicorn quantide.app:app --reload
```

With this switch enabled, the process will automatically:

- start a local `gateway` stub and route effective gateway settings to it
- replace the default `tushare` fetcher with fixture-backed local data
- expose simulation and live-trading feature gates as available after the app has already completed initialization once

Notes:

- This switch is development-only and has no effect unless `QUANTIDE_ENABLE_DEV_STUBS` is truthy.
- It does not rewrite your persisted database settings; the override only exists in the running process.
- The app still expects initialization to have been completed at least once, because `app_home`, auth, and other base runtime state still come from normal initialization.
- The local gateway stub will be started on a random localhost port and logged at startup.
- If an already-running dev server was started without the switch, its old logs are not evidence against stub mode; restart that process with the switch on the actual startup command.

## Edition Override Mode

Runtime edition identity is resolved from the installed release package, or from the local `pyproject.toml` when you are running from the source tree. A stray `QUANTIDE_EDITION` in your shell is ignored by default.

For development-only branding checks, you can explicitly opt into an override for a single process:

```bash
QUANTIDE_ENABLE_EDITION_OVERRIDE=1 QUANTIDE_EDITION=zillionaire conda run -n quantide uvicorn quantide.app:app --reload
```

Use this only for local development. It deliberately overrides edition-specific branding and release-package diagnostics for that process.
*** Add File: /Users/aaronyang/workspace/quantide/tests/notify/test_mail.py
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
		sent["msg"] = kwargs["msg"]
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
		sent["msg"] = kwargs["msg"]
		return object()

	monkeypatch.setattr(mail_module, "send_mail", fake_send_mail)

	mail_module.mail_notify(
		subject="Custom subject",
		body="hello",
		receivers=["receiver@example.com"],
	)

	assert sent["msg"]["Subject"] == "Custom subject"
