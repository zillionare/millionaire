# Aaron decision record — AD-01..AD-06

> Aaron decided on 2026-07-13 that all six legacy files are **RETAIN**. This record does not approve a waiver or change production behavior. Tests must be added for the current implementation contract, not invented behavior.

## Resolution summary

| ID | Exact path | Status | Decision | approved_by | approved_at | Corrected-shard evidence | Coverage target |
|---|---|---|---|---|---|---|---|
| AD-01 | `quantide/web/auth/admin_routes.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-f4c5b6766c15`, source anchors `admin_routes.py:14-294,779-783` | `percent_covered >=80.0` |
| AD-02 | `quantide/web/auth/forms.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-2222692b50e2`, source anchors `forms.py:51-727` | `percent_covered >=80.0` |
| AD-03 | `quantide/web/auth/repository.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-5793dc5849e8`, source anchors `repository.py:5-209` | `percent_covered >=80.0` |
| AD-04 | `quantide/web/auth/utils.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-478f19f91ad5`, source anchors `utils.py:8-48` | `percent_covered >=80.0` |
| AD-05 | `quantide/core/utils.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-core-02.json`, `prod-5c4b6a15a6b7`, source anchors `utils.py:7-40` | `percent_covered >=80.0` and present in the coverage manifest |
| AD-06 | `quantide/web/pages/analysis.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-02.json`, `prod-da64e6c5652e`, source anchors `analysis.py:15-74`; route `app_factory.py:409` | `percent_covered >=80.0` |

## Evidence contract applying to every retained row

- **Required Red evidence:** a failing test that references and expects the row's current-implementation behavior below. A failure caused only by an invented expectation, coverage threshold, import error, or unrelated setup does not qualify.
- **Required Green evidence:** the same test passes while asserting the same behavior under isolated and deterministic dependencies/state.
- **Required full-suite regression evidence:** the same traceable revision records a green full-suite run, with the normative `--timeout` option, in the same accepted coverage run used for the per-file threshold.
- **Threshold:** each executable retained file must report `percent_covered >=80.0`; no threshold is loosened.
- **Test direction:** tests must be added for the current implementation contract, not invented behavior.
- **Prohibitions:** follow current implementation; no invented behavior; no coverage tricks; no broad exclusions. `coverage-waivers.json` remains empty.

## AD-01 — optional multi-user admin registrar

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain `AdminRoutes(auth_manager)` and its optional registrar exactly as recorded in corrected shard `prod-f4c5b6766c15`. The shipped app leaves `include_admin=False`, so the default app has no admin routes. Explicit `include_admin=True` registers the coded GET/POST user list/create/edit/delete handlers and preserves the current decorator asymmetry, HTML results, query-string 303 error redirects, and absence of transaction cleanup.
- **required evidence:** Red must fail while referencing this default-disabled/explicitly-enabled route behavior; Green must assert that same behavior with isolated auth/repository state; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-02 — mixed active and legacy auth form renderers

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain the current FastHTML renderers in corrected shard `prod-2222692b50e2`: active login/profile forms emit their coded actions, fields, selected login errors, redirect field, and password/profile fields; registration/forgot/reset forms remain gated legacy renderers; `create_message_alert` remains a renderer helper; this module registers no route and performs no persistence or auth decision.
- **required evidence:** Red must fail while referencing those current rendered nodes/fields/actions; Green must assert the same output under deterministic isolated rendering; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-03 — consumed authentication repository

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain `UserRepository` as recorded in corrected shard `prod-5793dc5849e8`: parameterized username lookup; hashing during create and non-hash password update; authentication updates `last_login` and returns the pre-update user; CRUD/search/list/count produce the coded mutations and materialized values; last-admin deletion is refused; coded broad exceptions return `None`, `False`, empty collections, or zero counts, while create/password-verification failures may propagate.
- **required evidence:** Red must fail while referencing one of these current repository outcomes/fallbacks; Green must assert the same outcome against isolated deterministic storage; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-04 — unconsumed auth helper module

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain the four source callables from corrected shard `prod-478f19f91ad5`: `generate_token` returns a random alphanumeric string of requested length and returns empty for a negative length; `validate_email` applies the source regex; `validate_password` requires non-empty input, length at least 8, a digit, and uppercase and returns the coded `(bool, message)`; `sanitize_username` removes non-alphanumeric/non-underscore characters and lowercases; regex/type errors propagate. The module has no product route, facade export, persistence, or cleanup.
- **required evidence:** Red must fail while referencing those current values/errors; Green must assert the same behavior with randomness controlled and all state isolated; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-05 — legacy date/time conversion helpers

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain all five pure helpers from corrected shard `prod-5c4b6a15a6b7`: `str2date` accepts exactly 8 `YYYYMMDD` characters; `str2time` accepts exactly 14 `YYYYMMDDhhmmss` characters; formatters zero-pad to 8/14 digits; `time2minute` forces seconds to `00`; wrong lengths, non-digits, and invalid calendar values raise `ValueError`; missing object fields raise `AttributeError`; there is no mutation or cleanup.
- **required evidence:** Red must fail while referencing those current conversions or built-in failures; Green must assert the same pure deterministic behavior in isolation; the same revision must have a green full suite with `--timeout`, the file present in the coverage manifest, and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-06 — registered analysis retirement notice

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain corrected shard `prod-da64e6c5652e`: authenticated `GET /analysis` calls the current renderer and returns HTTP 200 HTML stating sector/index analysis is retired while pointing to the remaining stock/strategy/paper/gateway-live paths. Optional session auth affects header display; the page accepts no query/form input, performs no analysis data read/write, and has no event or cleanup behavior.
- **required evidence:** Red must fail while referencing that current routed HTTP response/message; Green must assert the same response under isolated deterministic branding/session state; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## Final disposition

All six rows are **RESOLVED RETAIN**. No file is deleted, quarantined, redirected, promoted to new behavior, or waived. The empty waiver registry is authoritative.
