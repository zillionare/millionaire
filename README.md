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
