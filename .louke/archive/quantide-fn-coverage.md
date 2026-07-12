# Quantide function-to-FR reverse coverage map

- **Spec ID**: v0.2-001-strategy-framework
- **Purpose**: Reverse-map public code symbols to FR/NFR coverage so missing product/spec requirements can be added before tests are rewritten.
- **Source inputs**: `sage-phase2-spec-gaps.md`, `sage-input-reverse-coverage.md`, spot verification against `quantide/` and `.specforge/project/v0.2-001-strategy-framework/spec*.md`.
- **Scope**: The precomputed low-coverage file set plus the supplemental files. This is an analysis artifact only; no `quantide/` or `tests/` code is changed.

## Summary

| Bucket | Count | Notes |
|---|---:|---|
| Covered by existing FR after semantic verification | 45 | Includes false negatives such as `DualMAStrategy` → FR-090 and `StrategyLoader`/`enumerate_strategies` → FR-020 |
| Newly covered by proposed FRs | 31 | Mapped to FR-480 / FR-481 / FR-484 / FR-485; excludes legacy bridge adapters that must not be spec'd |
| internal implementation, pending deletion | 22 | Legacy broker/market bridge and registration path from the removed FR-482/483 candidate scope |
| Internal helper details / no standalone FR needed | 19 | Private helpers, app route wrapper helpers, and copy/cache plumbing |
| Ambiguous / should be revisited after broader full-repo scan | 6 | Mostly UI-migrated app factory and low-level query adapter details |

## Covered public symbols

| file:line | symbol | Coverage decision | Rationale |
|---|---|---|---|
| `quantide/data/services/stock_sync.py:19` | `StockSyncService` | FR-310 | Data sync task service implementation |
| `quantide/data/services/stock_sync.py:43` | `sync_stock_list` | FR-310 / FR-280 | Syncs securities reference data |
| `quantide/data/services/stock_sync.py:63` | `sync_daily_bars` | FR-310 / FR-270 | Syncs daily bars |
| `quantide/data/services/stock_sync.py:105` | `sync_daily` | FR-310 | Daily incremental sync |
| `quantide/data/services/stock_sync.py:130` | `sync_full_history` | FR-310 | Full historical backfill |
| `quantide/service/discovery.py:28` | `ScanSource` | FR-020 | Scan source value object for strategy enumeration |
| `quantide/service/discovery.py:36` | `ExampleCopyResult` | FR-020 | Support output for strategy/example discovery workflow; not a new product capability |
| `quantide/service/discovery.py:54` | `StrategyLoader` | FR-020 | Strategy scan/cache/load manager |
| `quantide/service/discovery.py:64` | `get_builtin_scan_directory` | FR-020 | Builtin scan source |
| `quantide/service/discovery.py:68` | `get_user_scan_directory` | FR-020 | User scan source |
| `quantide/service/discovery.py:78` | `get_scan_directory` | FR-020 | Resolves active scan source |
| `quantide/service/discovery.py:85` | `get_scan_directories` | FR-020 | Enumerates scan sources |
| `quantide/service/discovery.py:97` | `has_scan_directory_config` | FR-020 | Scan directory config check |
| `quantide/service/discovery.py:108` | `set_scan_directory` | FR-020 | Scan directory configuration for enumeration |
| `quantide/service/discovery.py:126` | `load_from_cache` | FR-020 | Cached strategy enumeration |
| `quantide/service/discovery.py:166` | `scan_and_cache` | FR-020 | Enumerate and persist strategy metadata |
| `quantide/service/discovery.py:329` | `load` | FR-020 | Main strategy loading entrypoint |
| `quantide/service/discovery.py:341` | `get_strategy_info` | FR-020 | Metadata lookup |
| `quantide/service/discovery.py:351` | `list_strategies` | FR-020 | Metadata list |
| `quantide/service/discovery.py:456` | `is_builtin_path` | FR-020 | Builtin path classification |
| `quantide/service/discovery.py:467` | `enumerate_strategies` | FR-020 | Explicit v0.2 enumeration API |
| `quantide/strategies/example/dual_ma.py:8` | `DualMAStrategy` | FR-090 | Semantic match: built-in dual moving-average strategy |
| `quantide/data/helper.py:8` | `qfq_adjustment` | FR-290 | Forward adjustment based on adjust factor |
| `quantide/data/helper.py:76` | `hfq_adjustment` | FR-290 | Backward adjustment based on adjust factor |
| `quantide/app.py:36` | `main` | FR-470 | CLI/application launch entrypoint |
| `quantide/app_factory.py:212` | `create_app` | FR-470 / FR-460 | Application factory and init-wizard runtime assembly |
| `quantide/app_factory.py:497` | `trade_set_active` | FR-410 / UI-FR-420/430 | Active trading account route wrapper; backend state belongs account/trade UI contract |
| `quantide/core/scheduler.py:9` | `SchedulerManager` | FR-310 | Scheduling infrastructure for sync/runtime jobs |
| `quantide/core/scheduler.py:24` | `scheduler` | FR-310 | Scheduler instance access |
| `quantide/core/scheduler.py:41` | `add_job` | FR-310 | Adds scheduled sync/runtime jobs |
| `quantide/core/scheduler.py:45` | `add_listener` | FR-310 | Scheduler event listener support |
| `quantide/service/datafeed.py` | `BarsFeed` / `BarsFeedImpl` | FR-010 / FR-115 / FR-230 / FR-270 | Strategy datafeed implementation for get_bars and backtest data access |
| `quantide/data/stores/index_bars.py:18` | `IndexBarsStore` | FR-270 / FR-330 | Index daily bars storage/query support |
| `quantide/data/stores/index_bars.py:83` | `fetch` | FR-270 / FR-330 | Fetch index bars |
| `quantide/data/stores/index_bars.py:103` | `rec_counts_per_date` | FR-320 | Completeness/record-count support |
| `quantide/data/models/index_bars.py` | `IndexBars` model and data accessors | FR-270 / FR-330 | Index bars model/query path |

## Uncovered public functions requiring new or expanded FRs

| file:line | symbol | Purpose | Proposed FR |
|---|---|---|---|
| `quantide/data/utils/resampler.py:10` | `Resampler` | OHLCV resampling utility | FR-480 数据重采样与移动平均工具 |
| `quantide/data/utils/resampler.py:14` | `daily_to_weekly` | Daily-to-weekly OHLCV aggregation | FR-480 |
| `quantide/data/utils/resampler.py:63` | `daily_to_monthly` | Daily-to-monthly OHLCV aggregation | FR-480 |
| `quantide/data/utils/resampler.py:104` | `resample` | Frequency-dispatching resample API | FR-480 |
| `quantide/data/utils/resampler.py:127` | `calculate_ma` | Moving average columns | FR-480 |
| `quantide/notify/mail.py:24` | `mail_notify` | Config-driven mail notification | FR-481 通知通道扩展（邮件 / 钉钉） |
| `quantide/notify/mail.py:92` | `send_mail` | SMTP send primitive | FR-481 |
| `quantide/notify/mail.py:166` | `compose` | MIME email composition | FR-481 |
| `quantide/notify/dingtalk.py:22` | `DingTalkMessage` | DingTalk robot message client | FR-481 |
| `quantide/notify/dingtalk.py:115` | `ding` | DingTalk notification send API | FR-481 |
| `quantide/data/helper.py:134` | `train_test_split` | Time-series train/valid/test splitting | FR-484 数据研究辅助工具 |
| `quantide/data/helper.py:219` | `convert_output` | Preserve input dataframe type when splitting | FR-484 |
| `quantide/notify/__init__.py` | `get_stock_type`, `id_hson`, `id_xt`, `id_jq`, `high_low_limit`, `open_time_delta` | Security identifier conversion and market utility helpers | FR-485 证券代码与市场规则工具 |

## Internal implementation, pending deletion

| file:line | symbol | Reason |
|---|---|---|
| `quantide/core/runtime/broker_bridge.py:22` | `LegacyBrokerPortAdapter` | Legacy broker bridge from an architecture migration; not a valid product requirement and must not be spec'd |
| `quantide/core/runtime/broker_bridge.py:45` | `submit` | Legacy adapter submit path, pending deletion with broker bridge |
| `quantide/core/runtime/broker_bridge.py:198` | `cancel` | Legacy adapter cancellation path, pending deletion |
| `quantide/core/runtime/broker_bridge.py:206` | `cancel_all` | Legacy adapter cancellation path, pending deletion |
| `quantide/core/runtime/broker_bridge.py:211` | `query_positions` | Legacy adapter query path, pending deletion |
| `quantide/core/runtime/broker_bridge.py:233` | `query_assets` | Legacy adapter query path, pending deletion |
| `quantide/core/runtime/broker_bridge.py:247` | `query_orders` | Legacy adapter query path, pending deletion |
| `quantide/core/runtime/broker_bridge.py:272` | `query_trades` | Legacy adapter query path, pending deletion |
| `quantide/core/runtime/broker_bridge.py:286` | `_dispatch_submit` and conversion helpers | Legacy adapter internals, pending deletion |
| `quantide/core/runtime/market_bridge.py:14` | `LiveQuoteMarketDataAdapter` | Legacy market bridge from an architecture migration; not a valid product requirement and must not be spec'd |
| `quantide/core/runtime/market_bridge.py:38` | `subscribe` | Legacy market adapter subscription path, pending deletion |
| `quantide/core/runtime/market_bridge.py:44` | `unsubscribe` | Legacy market adapter subscription path, pending deletion |
| `quantide/core/runtime/market_bridge.py:49` | `stream` | Legacy market adapter stream path, pending deletion |
| `quantide/core/runtime/market_bridge.py:67` | `snapshot` | Legacy market adapter snapshot path, pending deletion |
| `quantide/core/runtime/market_bridge.py:90` | `_on_quotes`, `_put_event_safe`, `_to_float_or_none` | Legacy adapter internals, pending deletion |
| `quantide/core/runtime/registration.py:51` | `register_legacy_broker` | Legacy broker registration path, pending deletion |
| `quantide/core/runtime/modes.py:41` | `RuntimeModeRegistry.register_legacy_broker` | Legacy broker registration wrapper, pending deletion |
| `quantide/core/runtime/modes.py:156` | `register_legacy_broker` call path | Legacy registration usage, pending deletion |
| `quantide/service/strategy_runtime.py:293` | `runtime.register_legacy_broker(...)` | Legacy runtime usage to remove during pre-release cleanup |
| `quantide/web/pages/accounts.py:622` | `runtime.register_legacy_broker(...)` | Legacy account-page usage to remove during pre-release cleanup |
| `quantide/core/runtime/__init__.py:11` | `register_legacy_broker` export | Legacy public export to remove during pre-release cleanup |
| `quantide/core/runtime/__init__.py:25` | `"register_legacy_broker"` | Legacy public export to remove during pre-release cleanup |

## Internal helper details (no standalone FR)

| file:line | symbol | Reason |
|---|---|---|
| `quantide/app_factory.py:129` | `cleanup_pid` | Nested single-instance cleanup implementation detail of FR-470 |
| `quantide/app_factory.py:136` | `_initialize_app_database` | Private app startup recovery detail |
| `quantide/app_factory.py:162` | `_attach_runtime_to_app_states` | Private application wiring detail |
| `quantide/app_factory.py:187` | `_attach_root_app_to_app_states` | Private application wiring detail |
| `quantide/service/discovery.py:197` | `_clear_cache` | Private cache maintenance |
| `quantide/service/discovery.py:206` | `_add_scan_dir_to_sys_path` | Private import-path setup |
| `quantide/service/discovery.py:213` | `_get_scan_sources` | Private scan assembly |
| `quantide/service/discovery.py:241` | `_scan_source` | Private enumeration implementation |
| `quantide/service/discovery.py:272` | `_get_module_name` | Private module naming helper |
| `quantide/service/discovery.py:285` | `_load_module_and_get_info` | Private scan implementation |
| `quantide/service/discovery.py:393` | `_iter_copyable_example_files` | Private copy helper |

## Ambiguous / follow-up list

| file:line | symbol | Current call | Follow-up |
|---|---|---|---|
| `quantide/app_factory.py:497` | `trade_set_active` | FR-410 / UI migrated trade screens | Decide whether this belongs v0.2-001 backend account contract or v0.2-002 UI-only AC |
| `quantide/data/helper.py:134` | `train_test_split` | FR-484 proposed | Confirm whether data research helpers are in product scope or should be marked utility/internal |
| `quantide/notify/__init__.py` helpers | market code helpers | FR-485 proposed | Confirm whether this should merge into FR-470 installation/runtime utility scope |

## Proposed new FR list

| FR | Title | Target file | Coverage |
|---|---|---|---|
| FR-480 | 数据重采样与移动平均工具 | `spec-trading.md` | `Resampler` daily/week/month/MA APIs |
| FR-481 | 通知通道扩展（邮件 / 钉钉） | `spec-trading.md` | `notify/mail.py`, `notify/dingtalk.py` |
| FR-484 | 数据研究辅助工具 | `spec-trading.md` | `train_test_split` |
| FR-485 | 证券代码与市场规则工具 | `spec-trading.md` | `notify/__init__.py` market helper functions |

### Removed candidates

| Removed FR | Reason |
|---|---|
| FR-482 BrokerPort 桥接与账户查询接口 | Legacy broker bridge is an internal implementation pending deletion, not a valid product requirement |
| FR-483 行情订阅 / 快照端口 | Legacy market bridge is an internal implementation pending deletion, not a valid product requirement |

## Junior handoff

P0 (Phase 2 part 2):
- Add AC tests for FR-050/060/070/080 order modes and cross-mode differences.
- Add AC tests for FR-300 realtime market data; existing gateway broker coverage needs explicit AC references.
- Add standard NFR-060 `AC-NFR-060-01` reference while preserving existing `AC-CLOCK-INJ-01~06` detailed tests.

P1:
- Add AC tests for FR-270/280/290 tushare data source, reference data, adjustment and limit-price behavior.
- Add AC tests for FR-410/420/430 backend account/order/trade observability.
- Add tests for new FR-480/481/484/485 APIs.
- Track legacy broker/market bridge deletion separately; do not add AC tests for removed FR-482/483 candidates.

P2:
- Repair existing tests whose docstring lacks an AC reference.
- Decide whether FR-484/485 are product scope or internal utilities before writing tests.
