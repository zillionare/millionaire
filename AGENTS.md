# Repository instructions for coding agents

## Product names and documentation claims

- `millionaire` is the community edition's product name, repository, distribution
  package, CLI command and runtime edition. The broader product family also includes
  `millionaire pro` (repository `millionaire-pro`); label pro-only features,
  including real trading and built-in triple-barrier risk programs, explicitly.
  The Python import name remains `quantide`.
- Preserve the public package name `millionaire`, CLI command `millionaire` and
  runtime edition identifiers. Product wording is not authorization to rename
  these compatibility contracts.
- Check implementation before presenting a feature as available. Historical
  specs describe requirements, not proof of delivery. Keep the product overview's
  promotional tone while stating current scope and model assumptions accurately.
- Daily Shadow-Run is a two-instance comparison: the paper instance runs on
  current quotes and the backtest instance runs after the daily bar is available.
  The 30-minute instance replays each closed 8-slot session bar (10:00, 10:30,
  11:00, 11:30, 13:30, 14:00, 14:30, 15:00); forming bars never trigger a replay.
  Describe this natural daily cadence directly; reserve limitations for actual
  gaps.
- Native desktop installs provide a macOS menu-bar app and a Windows system-tray
  app, displayed after installation and started at login. Keep their lifetime
  independent of the background service; quitting a UI must leave its service
  process running. Ubuntu desktops retain the window controller.

## Output locations

- Never generate runtime data, temporary files, builds, reports, logs, screenshots,
  browser profiles, coverage files or caches in the source checkout. In particular,
  do not create root `data/`, `dist/`, `packaging/`, `quality-reports/`, `review/`,
  `site/`, `build/`, `.sesskey` or `quantide.db` (including SQLite sidecars).
- Use `python -m scripts.artifact_paths` to get the development artifact directory.
  POSIX defaults to `/tmp/millionaire/<workspace-id>/`; Windows uses its native
  temporary directory. `MILLIONAIRE_ARTIFACTS_DIR` may override it to another location
  outside the checkout. Use `python -m scripts.artifact_paths --run <command...>`
  for test/tool runs so child processes inherit external cache and coverage paths.
- Pass explicit output directories to tools with checkout-local defaults, including
  `python -m build --outdir <artifacts>/dist`, `mkdocs build --strict --site-dir
  <artifacts>/site`, and pytest's `--junitxml`, `--cov-report` outputs. Do not run
  bare build commands that create root output and then clean up afterward.
- Store review notes and development evidence intended for version control under
  `.louke/project/reviews/<date>/`; version plans belong under `.louke/project/specs/`.
  Large generated logs, screenshots, archives and raw tool reports remain in tmp.
- Installer source/templates belong in `scripts/packaging/`; fixed test fixtures
  belong in `tests/assets/`. Treat committed fixtures as read-only during tests;
  copy them to a pytest temporary directory before modifying them.

## Application and test paths

- Reuse `quantide.config.paths` and effective settings. Never use `Path("")`,
  `Path(".")`, `Path.cwd()` or hard-coded `~/.quantide` as an output fallback.
  `init_data()` reads the configured data home. If no data home is configured,
  it uses a per-user `market` directory under system tmp. Explicit runtime output
  inside the source checkout, including symlink aliases, must be rejected.
- `QUANTIDE_DATA_HOME` supplies the data directory when no saved wizard value or
  explicit argument exists. `QUANTIDE_CONFIG_HOME`/the app-factory override select
  the durable configuration/account profile. Keep existing user data there;
  do not move durable credentials, account facts or configured market data to tmp.
- Development console logs use `QUANTIDE_LOG_HOME`, falling back to a project
  subdirectory of system tmp. OS service installers explicitly configure durable
  service directories. Keep service installation and data retention working.
- Tests must use `tmp_path`, `tmp_path_factory` or `TemporaryDirectory` for writes
  and isolate application configuration before importing modules that create
  session keys, databases or model directories. Never use a real user profile
  or a production service's data directory as test scratch space.
- Do not bypass the FastHTML wrapper in `quantide.web.application` unless a test
  explicitly supplies a test-only session secret. The library's default writes
  `.sesskey` to the current working directory.

## Verification

- Before finishing, run `python -m scripts.artifact_paths --check-layout` after
  tests/builds, and inspect `git status --short` including ignored output when
  diagnosing pollution. Fix the producer/configuration instead of merely deleting
  files or adding ignore rules. Keep the layout and distribution gates enabled.
- Follow `docs/quality.md`; do not relax complexity, duplication, line/file size,
  coverage or acceptance requirements to make a change pass.
- Report the checks actually run and their limits. A manual release preflight
  must not publish, merge a PR, create a release tag or deploy a service.
