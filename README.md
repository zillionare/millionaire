# Millionaire

Millionaire is Zillionare's flagship quantitative trading platform.

The published package name is `millionaire`. The Python import namespace
is `quantide` — this is an internal name, not a brand; if you fork and
rename, you can rename the import namespace to match.

This repository is in active architectural refactoring.

The release-facing README is intentionally kept minimal until the codebase, runtime model, and deployment model are stable enough to publish without misleading users or automation.

Current status:

- the project is not using FastAPI + Vue as its target stack
- the application stack is being consolidated around FastHTML + MonsterUI
- release documentation has not been finalized yet
- development-stage notes are stored under `.dev/`

Until the refactor settles, treat `.dev/` as draft engineering notes rather than release documentation.

For local startup guidance and minimum developer-side acceptance, see `docs/developer-acceptance.md`.

## Local Setup

This project uses a standard Python virtual environment (not conda).

```bash
# 1. Create the virtual environment (one-time)
python3.13 -m venv .venv --prompt=millionaire-py3.13

# 2. Activate it
source .venv/bin/activate

# 3. Install dependencies (Poetry is configured as the build backend)
pip install poetry
poetry install

# 4. Run the app
uvicorn quantide.app:app --reload
```

Or use the bundled helper script (creates the venv on first run if needed):

```bash
./start.sh
```

## Development Stub Mode

When you want to demo the real UI and runtime flow without connecting a real gateway or real Tushare,
start Millionaire with the environment variable `QUANTIDE_ENABLE_DEV_STUBS=1`.

Example:

```bash
QUANTIDE_ENABLE_DEV_STUBS=1 uvicorn quantide.app:app --reload
```

Or, with the helper script:

```bash
./start.sh --stub
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
QUANTIDE_ENABLE_EDITION_OVERRIDE=1 QUANTIDE_EDITION=zillionaire uvicorn quantide.app:app --reload
```

Use this only for local development. It deliberately overrides edition-specific branding and release-package diagnostics for that process.
