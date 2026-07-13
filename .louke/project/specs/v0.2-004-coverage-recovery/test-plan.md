# Millionaire Coverage Recovery — Test Plan

- **Spec ID**: v0.2-004-coverage-recovery
- **创建日期**: 2026-07-13
- **阶段**: M-TESTPLAN
- **关联 acceptance**: `.louke/project/specs/v0.2-004-coverage-recovery/acceptance.md`
- **断言依据**: 本 spec 的固定 corrected production shards，以及继承的 v0.2-001/002/003 `interfaces.md`
- **固定输入**: production index `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe`；production shard manifest `4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39`；test index `3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0`；test shard manifest `f48b15e808737352ad6a5c4d8da2b2a5f9b97fa3fb56a4ca2881463ec2380352`；RW registry `bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088`

## 1. 立场与边界

### 1.1. 黑盒声明

测试只断言锁定合同的可观察结果：公开 Python API 返回值/异常、HTTP 状态/响应、事件、日志、SQLite/Parquet/JSON 持久化、进程退出码及 coverage/trace artifacts。不得依赖私有状态来替代公开行为；确需检查资源释放时，只检查进程、线程、task、subscription、文件句柄或持久化残留等外部后果。

### 1.2. 不可观测对象

- 内部类层次、未声明的私有方法、缓存布局和调度中间态。
- 由被测实现反算的 expected value。
- corrected shard 未声明且无更高优先级合同的“改进”行为。

### 1.3. 作伪模式（阻塞）

以下任一项使 batch 和最终 verdict 为 FAIL：`assert True`、空 `pass` 测试、import-only、self-fulfilling expected、mock 被测主体、无断言 mock、吞异常、无 issue 的 skip、降低阈值、扩大 omit/exclude、批量 `pragma: no cover`、仅为执行行而调用、从失败 run 接受 coverage、generic waiver、删除有效行为来提高数字。正常路径与适用失败/边界路径必须至少各有一个独立实质断言。

### 1.4. 防护机制

1. 每个测试函数第一行 docstring/comment 含带 spec-id 的有效 `AC-FRXXXX-YY` 或 `AC-NFRXXXX-YY`；运行 `lk agent archer ci-scan --acceptance .louke/project/specs/v0.2-004-coverage-recovery/acceptance.md --tests tests/` 关闭双向 trace。
2. 静态 FAKE guard 扫描整个 `tests/**/*.py`，并结合 AST/diff review 拦截 §1.3；静态扫描通过不能替代行为 Green。
3. AC-anchor guard 重建固定 11 个 test shards，要求 240 modules、1651 functions、1651 spec-qualified refs、1455 aligned、196 update、0 needs-Sage-contract；修复后如 function/refs 变化，必须更新 trace 并重新固定 hash。
4. coverage 配置 diff guard 与基线比较 `[tool.coverage.run]`、`[tool.coverage.report]`、CI 参数和所有 `pragma: no cover`；任何放宽阻塞。
5. 当前 `tests/unit/_checkers/per_file_coverage.py` 是集成入口，但现状只支持 overall `>=95`、统一 80% 和较少 waiver 字段，不能单独满足本 spec。Devon 必须按 AC-FR1801 与 AC-NFR1001 扩展该现有 checker：overall 严格 `>95.0`、按 inventory origin 分档、完整 waiver schema、manifest equality、0-statement 处理；不得另造可绕过的平行 gate。

### 1.5. 测试分工

- Devon：修复/补充 unit、integration、既有绑定测试与 checker；保存每个 RW 的 Red/Green/full-suite evidence。
- Shield：复核隔离、反作弊、HTTP/跨组件及 exit artifact 场景；不得替 Devon 发明合同。
- 最终 reviewer：从固定 shard、coverage JSON 和同 revision evidence 重放二进制 verdict。

## 2. 测试环境

### 2.1. 框架与版本

- Python `>=3.13,<4.0`；pytest `>=9.0.2,<10.0.0`；pytest-cov `>=7.0.0,<8.0.0`；pytest-asyncio `>=1.3.0,<2.0.0`；pytest-timeout `>=2.4.0,<3.0.0`；freezegun `>=1.5.5,<2.0.0`，均沿用 `pyproject.toml`。
- canonical runner 是 pytest。顺序基线必须真实执行 `pytest --random-order`；执行环境须提供与 pytest 9 兼容的 `pytest-random-order` plugin。若 pytest 报 unknown option，环境 gate 失败，不允许退化成默认顺序两次运行。当前 `tests/e2e/test_isolation_e2e.py` 的 optional fallback 仅是旧诊断，不能满足 AC-NFR1201-02。
- `tests/conftest.py` 提供旧 fixtures，`tests/unit/conftest.py` 提供离线 `env` 和 PaperBroker cleanup；新增隔离能力应在这些既有 conftest 层实现，不引用不存在的 helper。

### 2.2. 目录与数据

- unit：`tests/unit/`；HTTP/跨组件合同：既有 `tests/e2e/`；离线数据：`tests/assets/unit/fixtures/data/` 与既有 e2e fixtures；独立 oracle：`tests/ground_truth/`。
- 每次 invocation 将 `HOME`、`XDG_CONFIG_HOME`、应用 config/data/db/log/pid/runtime-state 路径指向 pytest `tmp_path`/CI 临时目录。测试不得写用户 HOME 或仓库生产数据。
- 合成 gateway/SMTP/Tushare/network responses 固定输入、状态码和 payload；禁止真实 gateway、SMTP、DingTalk、Tushare 和公网 DNS/socket。测试替换外部边界，不替换被测业务主体。
- SQLite 每测试或明确隔离 scope 使用临时文件；Parquet fixture 只读，写出至临时目录；随机数、UUID 和 wall clock 在合同需要时固定。

### 2.3. 执行合同与 same-run 证据

最终接受 run 的 pytest 命令形态为：

```bash
HOME="$RUN_TMP/home" XDG_CONFIG_HOME="$RUN_TMP/xdg" \
COVERAGE_PROCESS_START=pyproject.toml \
python3 -m pytest tests/unit --timeout=120 \
  --cov=quantide --cov-branch --cov-fail-under=95 \
  --cov-report=term-missing --cov-report=json:coverage.json
```

`--cov-fail-under=95` 只是早期保护；最终 checker 必须从同一 pytest exit-0 invocation 的 `coverage.json` 验证严格 `totals.percent_covered >95.0`。pytest exit 非 0、failed 非 0 或 errors 非 0 时，该 coverage 只能标记 diagnostic，不能输入任何 acceptance gate。pytest 完成后只允许对该 immutable artifact 做 hash、manifest、per-file、waiver、trace 和 closure 校验，不得合并另一测试 run 的数据。

### 2.4. subprocess coverage（grid_search）

`quantide/service/grid_search.py` 使用子进程时必须启用 coverage.py 的原生 subprocess measurement：`[tool.coverage.run] branch=true` 保持，配置 `parallel=true`、`concurrency=["multiprocessing"]` 与 coverage.py 支持的 subprocess patch，且子进程继承 `COVERAGE_PROCESS_START=pyproject.toml`。pytest-cov 负责同一 invocation 收集/合并 `.coverage.*` 后生成一个 `coverage.json`；测试断言 worker 执行的已知行进入 `grid_search.py` 报告，并在退出后无 ProcessPool worker。不得用 in-process monkeypatch 绕过 pool 来声称 subprocess coverage。

### 2.5. 顺序和资源 gate

先对代表性模块建立正常顺序与 `pytest --random-order` 两次摘要/statement totals 基线，再允许 batch 开始；最终全量 unit suite 也必须完成默认顺序、重复及 random-order 一致性验证。teardown 后检查无存活 MessageHub owner subscription、ProcessPool worker、scheduler、async task、client/websocket/database handle 或仓库残留文件。

## 3. Ground Truth 方法

### 3.1. 独立来源

- 日期、行情调整、交易限制和指标：小型固定 fixture + 独立公式/`tests/ground_truth/`，不得 import 被测函数生成 expected。
- HTTP/DTO/schema：锁定 interfaces、corrected shard 和显式字段集合。
- gateway/SMTP/Tushare：协议 fixture 的 request/response transcript；断言请求参数、状态和 fallback。
- RETAIN characterization：只用 corrected-shard 当前实现合同及精确 consumer evidence，不把实现偶然输出推广为新行为。

### 3.2. Ground Truth 隔离

`tests/ground_truth/**/*.py` 不得 import `quantide.*`。oracle 仅使用标准库、固定 fixtures 和既有独立指标库。任何 expected 从被测调用结果拷贝、镜像内部常量而无合同来源，均按 self-fulfilling 处理。

## 4. 测试范围与 FR family 模式

| Family | 测试模式与主要断言 |
|---|---|
| FR-01xx infra | pytest/config/coverage artifact、分档 checker、isolated HOME、same-run provenance；synthetic artifact 只测 gate 正反例，真实 PASS 必须来自 green run。 |
| FR-02xx core | ports、runtime、strategy、gateway、MessageHub；纯 DTO/enum 单元测试，adapter/worker 集成测试，异常、超时、cleanup 与 consumer contract。 |
| FR-03xx data | Calendar/Stocks/SQLite/Parquet/Tushare；固定 data fixture、独立日期/公式 oracle、空/坏输入、事务与文件隔离，无真实 Tushare。 |
| FR-04xx service | broker/runner/grid search/metrics/runtime；正常与拒绝路径、状态/持久化、subprocess coverage、pool/MessageHub cleanup。 |
| FR-05xx web | FastHTML renderer、middleware、routes、services；HTTP status/header/body/schema、safe redirect、ErrorEnvelope、账户隔离，不验证像素渲染。 |
| FR-06xx CI | canonical command、blocking exit、Python 3.13、coverage JSON、per-file checker、无 `continue-on-error`，并运行 `lk agent archer ci-scan`。 |
| FR-07xx notify/strategies/config | SMTP/DingTalk 外部替身、策略独立 fixture、config path/env isolation；断言输入、输出、错误和 cleanup。 |
| FR-0801 | 对 production index exact bytes、13 shard bytes/record counts/IDs/path uniqueness 和 manifest hash 做 pinning；任何漂移 FAIL。 |
| FR-0802 | inventory origin 驱动 35 个 v0.2-added executable files 每文件 `>=95.0`；无 waiver；pre-v0.2 retained executable files `>=80.0`。 |
| FR-1001 | disk `quantide/**/*.py` = inventory = `coverage.json.files`；每个文件须由所属 batch 的实质合同测试 import 并 exercise，marker/schema 文件则断言声明的 facade/schema；`--cov=quantide` source discovery 确保未执行文件也不会从 manifest 消失，但不能靠无断言 import-only 测试制造通过。 |
| FR-1101 | 169 行 classification 字段、计数和决定权限重算；六个 AD 路径仍在 manifest。 |
| FR-1201 | 读取全部 corrected shards，逐行验证 public surface/input/output/failure/state/source；冲突按 precedence 归因。 |
| FR-1301 | 复核 1651 functions，196 update 的 defect category、独立断言和 RW 一一绑定。 |
| FR-1401 | 每个 RW 保存 Red、Green、同 revision full-suite/per-file gate；production diff 只能来自 implementation-defect。 |
| FR-1501 | AD-01..AD-06 的 RETAIN test direction 见 §6，六文件同一接受 run 均 `>=80.0`。 |
| FR-1601 | 全 `tests/**/*.py` 双向 AC trace、helper consumer、删除五证据；本计划不授权删除。 |
| FR-1701 | 每轮重算 closure matrix；blocker 并集生成下一 batch，直到零。 |
| FR-1801 | 空 waiver registry 正例；synthetic 完整 pre-v0.2 waiver 正例与缺字段/过期/重复/未知/non-Aaron/v0.2-added 反例。当前不得接受任何实际 waiver。 |
| FR-1901 | 聚合所有信号输出唯一 PASS/FAIL；注入任一缺失信号必须 FAIL，失败 run coverage 不可接受。 |

## 5. 验收标准与 coverage 策略

1. 同一完整 unit invocation：pytest exit 0，0 failed，0 errors；overall statement/line `>95.0`。
2. coverage branch measurement 保持开启；branch 数用于诊断缺口，DoD 百分比口径仍是 statement/line。
3. disk、inventory、coverage manifest 三集合完全相等且均 169。0-statement 文件仍出现并标记 `threshold_not_applicable`；可执行但未记录的文件直接 FAIL。
4. v0.2-added executable 每文件 `>=95.0`；pre-v0.2 retained executable 每文件 `>=80.0`，当前 `coverage-waivers.json` 必须为 `waivers=[]`。
5. checker 从固定 inventory 读取 origin/target，不从文件名猜分类；overall 恰好 95.0 必须 FAIL。
6. FAKE、incomplete、import-only、self-fulfilling、conflicting、spec-gap 的 open count 最终为 0；双向 AC orphan 为 0；AD obligations 为 0；closure blockers 为 0。

## 6. 外部依赖、batch 与 RW closure

### 6.1. 外部依赖分层

| 层 | 用途 | 允许替身 | 禁止 |
|---|---|---|---|
| L1 unit | 纯函数、DTO、策略、renderer、service policy | clock/random/fixture/storage boundary | mock 被测主体 |
| L2 integration | SQLite/Parquet、HTTP adapter、MessageHub、subprocess | 临时存储、protocol stub | 真实网络/gateway/SMTP/Tushare |
| L3 recovery exit | 完整 unit suite + artifact gates | 同上 | nightly/真实服务结果替代 release gate |

### 6.2. 每个 batch 的统一 entry/exit gate

**Entry（四项全满足）**：(a) batch 中当前 test file 在 current HEAD 存在；(b) 每个待改 test module/function 在隔离 invocation 中可 collect 并运行，现有失败记录为 Red baseline 而非跳过；(c) `pytest --random-order` baseline 已真实建立且无 unknown option；(d) 上游 batch API/fixture gate 已 green。若绑定函数在 `tests/e2e/`，其隔离 Green 也必须保存，但最终 DoD coverage 仍只取 canonical unit run。

**Exit（五项全满足）**：(a) batch 所有测试 Green；(b) batch 所列 production files 在 batch diagnostic coverage 达各自 80/95 target，0-statement 仅跳过百分比；(c) 无新增 FAKE/incomplete/import-only/self-fulfilling/conflicting/spec-gap；(d) 每个绑定 RW 有 R、G、F evidence，或双向 superseding item 保留 function ID/AC/evidence obligations；(e) trace 如发生测试函数或 AC 变化已更新。Batch diagnostic 不能替代最终 same-run gate。

### 6.3. 169-path dependency-correct batch plan

顺序固定为 config → core foundation/runtime → core strategy → data → notify → service → strategies → app composition → web foundation → web middleware/pages → web system pages → web services → web orchestration。每行路径来自对应 fixed shard，合计 169。

| Batch | Fixed shard | Paths |
|---|---|---|
| B01 | `quantide-config.json` | `quantide/config/__init__.py`<br>`quantide/config/branding.py`<br>`quantide/config/dev_stubs.py`<br>`quantide/config/paths.py`<br>`quantide/config/settings.py` |
| B02 | `quantide-core-01.json` | `quantide/core/domain/__init__.py`<br>`quantide/core/domain/events.py`<br>`quantide/core/enums.py`<br>`quantide/core/errors.py`<br>`quantide/core/init_wizard_steps.py`<br>`quantide/core/message.py`<br>`quantide/core/notifications.py`<br>`quantide/core/order_execution.py`<br>`quantide/core/ports/__init__.py`<br>`quantide/core/ports/broker.py`<br>`quantide/core/ports/clock.py`<br>`quantide/core/ports/data_fetcher.py`<br>`quantide/core/ports/market_data.py`<br>`quantide/core/risk_events.py`<br>`quantide/core/runtime/__init__.py`<br>`quantide/core/runtime/adapter_registry.py`<br>`quantide/core/runtime/clock_bridge.py`<br>`quantide/core/runtime/gateway_broker.py`<br>`quantide/core/runtime/gateway_client.py`<br>`quantide/core/runtime/modes.py`<br>`quantide/core/runtime/port_broker.py`<br>`quantide/core/runtime/registration.py`<br>`quantide/core/scheduler.py`<br>`quantide/core/sdk_metadata.py` |
| B03 | `quantide-core-02.json` | `quantide/core/singleton.py`<br>`quantide/core/strategy_discovery.py`<br>`quantide/core/strategy.py`<br>`quantide/core/utils.py`<br>`quantide/core/wizard_steps_v2.py` |
| B04 | `quantide-data.json` | `quantide/data/__init__.py`<br>`quantide/data/fetchers/__init__.py`<br>`quantide/data/fetchers/registry.py`<br>`quantide/data/fetchers/tushare.py`<br>`quantide/data/helper.py`<br>`quantide/data/models/__init__.py`<br>`quantide/data/models/app_state.py`<br>`quantide/data/models/base.py`<br>`quantide/data/models/calendar.py`<br>`quantide/data/models/daily_bars.py`<br>`quantide/data/models/entities.py`<br>`quantide/data/models/index_bars.py`<br>`quantide/data/models/stocks.py`<br>`quantide/data/models/strategy_config.py`<br>`quantide/data/services/__init__.py`<br>`quantide/data/sqlite.py`<br>`quantide/data/stores/base.py`<br>`quantide/data/stores/index_bars.py`<br>`quantide/data/utils/__init__.py`<br>`quantide/data/utils/resampler.py` |
| B05 | `quantide-notify.json` | `quantide/notify/__init__.py`<br>`quantide/notify/dingtalk.py`<br>`quantide/notify/mail.py` |
| B06 | `quantide-service.json` | `quantide/service/abstract_broker.py`<br>`quantide/service/backtest_broker.py`<br>`quantide/service/backtest_logs.py`<br>`quantide/service/datafeed.py`<br>`quantide/service/discovery.py`<br>`quantide/service/grid_search.py`<br>`quantide/service/init_wizard.py`<br>`quantide/service/livequote.py`<br>`quantide/service/metrics.py`<br>`quantide/service/registry.py`<br>`quantide/service/runner.py`<br>`quantide/service/sim_broker.py`<br>`quantide/service/strategy_runtime.py`<br>`quantide/service/trade_lightning.py`<br>`quantide/service/triple_barrier.py` |
| B07 | `quantide-strategies.json` | `quantide/strategies/cost_stop_loss.py`<br>`quantide/strategies/example/dual_ma.py`<br>`quantide/strategies/pullback_sell.py` |
| B08 | `quantide-root.json` | `quantide/__init__.py`<br>`quantide/app_factory.py`<br>`quantide/app.py` |
| B09 | `quantide-web-01.json` | `quantide/web/__init__.py`<br>`quantide/web/apis/__init__.py`<br>`quantide/web/apis/analysis/__init__.py`<br>`quantide/web/apis/analysis/kline.py`<br>`quantide/web/apis/analysis/search.py`<br>`quantide/web/apis/broker.py`<br>`quantide/web/auth/__init__.py`<br>`quantide/web/auth/admin_routes.py`<br>`quantide/web/auth/database.py`<br>`quantide/web/auth/forms.py`<br>`quantide/web/auth/init.py`<br>`quantide/web/auth/manager.py`<br>`quantide/web/auth/middleware.py`<br>`quantide/web/auth/models.py`<br>`quantide/web/auth/repository.py`<br>`quantide/web/auth/routes.py`<br>`quantide/web/auth/utils.py`<br>`quantide/web/components/__init__.py`<br>`quantide/web/components/analysis/__init__.py`<br>`quantide/web/components/analysis/backtest_charts.py`<br>`quantide/web/components/analysis/kline_chart.py`<br>`quantide/web/components/analysis/stock_list.py`<br>`quantide/web/components/asset_label.py`<br>`quantide/web/components/header.py`<br>`quantide/web/components/runtime_params.py` |
| B10 | `quantide-web-02.json` | `quantide/web/components/sidebar.py`<br>`quantide/web/components/toast.py`<br>`quantide/web/degradation.py`<br>`quantide/web/errors.py`<br>`quantide/web/events.py`<br>`quantide/web/layouts/__init__.py`<br>`quantide/web/layouts/base.py`<br>`quantide/web/layouts/main.py`<br>`quantide/web/local_storage.py`<br>`quantide/web/middleware_feature.py`<br>`quantide/web/middleware_init.py`<br>`quantide/web/middleware.py`<br>`quantide/web/nfr_accessibility.py`<br>`quantide/web/nfr_error_degradation.py`<br>`quantide/web/nfr_long_task.py`<br>`quantide/web/nfr_partial_refresh.py`<br>`quantide/web/nfr_responsive.py`<br>`quantide/web/nfr_visual.py`<br>`quantide/web/pages/__init__.py`<br>`quantide/web/pages/accounts.py`<br>`quantide/web/pages/analysis.py`<br>`quantide/web/pages/data_calendar.py`<br>`quantide/web/pages/data_db.py`<br>`quantide/web/pages/data_market.py`<br>`quantide/web/pages/data_stocks.py`<br>`quantide/web/pages/history_orders.py` |
| B11 | `quantide-web-03.json` | `quantide/web/pages/history_positions.py`<br>`quantide/web/pages/history_trades.py`<br>`quantide/web/pages/home.py`<br>`quantide/web/pages/init_wizard.py`<br>`quantide/web/pages/live.py`<br>`quantide/web/pages/paper.py`<br>`quantide/web/pages/strategy.py`<br>`quantide/web/pages/system/__init__.py`<br>`quantide/web/pages/system/calendar.py`<br>`quantide/web/pages/system/datasource.py`<br>`quantide/web/pages/system/gateway.py`<br>`quantide/web/pages/system/jobs.py`<br>`quantide/web/pages/system/market.py`<br>`quantide/web/pages/system/risk_events.py` |
| B12 | `quantide-web-04.json` | `quantide/web/pages/system/runtime_monitor.py`<br>`quantide/web/pages/system/runtime_support.py`<br>`quantide/web/pages/system/stocks.py`<br>`quantide/web/pages/trade_lightning.py`<br>`quantide/web/pages/trade_main.py`<br>`quantide/web/services/__init__.py`<br>`quantide/web/services/account_overview.py`<br>`quantide/web/services/accounts.py`<br>`quantide/web/services/auth_session.py`<br>`quantide/web/services/backtest_progress.py`<br>`quantide/web/services/backtest_reports.py`<br>`quantide/web/services/dashboard.py`<br>`quantide/web/services/gateway.py`<br>`quantide/web/services/integrity.py`<br>`quantide/web/services/layout.py`<br>`quantide/web/services/notifications.py`<br>`quantide/web/services/risk_events.py`<br>`quantide/web/services/routing.py` |
| B13 | `quantide-web-05.json` | `quantide/web/services/runtime_control.py`<br>`quantide/web/services/scheduling.py`<br>`quantide/web/services/stock_query.py`<br>`quantide/web/services/strategy_management.py`<br>`quantide/web/services/tasks.py`<br>`quantide/web/services/trade_history.py`<br>`quantide/web/services/trade.py`<br>`quantide/web/theme.py` |

### 6.4. 196 RW normative projection and batch map

本表不是 generic mapping。对表中每个 canonical ID `id`，其 **function ID(s)**、**test module**、**production targets**、**defect category/quality finding**、**target ACs** 分别精确取自固定 registry 的 `work_items[work_item_id=id].{function_ids,test_modules,production_targets,defect_category/quality_finding,ac_refs}`；不得改名、合并或从 prose 猜测。每项要求：**R**=registry `required_red_evidence`；**G**=registry `required_green_evidence`；**F**=registry `full_suite_regression_evidence`。若 function/AC/assertion 变化则更新 test trace；`fake|import-only|conflicting|spec-gap` 必须更新。Exit 是 R+G+F、该 batch gate、RW status closed 或合规 superseded 全满足。Registry 中唯一以 `pyproject.toml` 为 target 的 infra item 归 B01，不冒充 production path。

| Batch | Canonical work items（每项均使用上述完整字段投影与 R+G+F exit） |
|---|---|
| B01 | `RW-0049`, `RW-0050`, `RW-0063`, `RW-0145` |
| B02 | `RW-0004`, `RW-0005`, `RW-0047`, `RW-0052`, `RW-0053`, `RW-0054`, `RW-0055`, `RW-0056`, `RW-0058`, `RW-0059`, `RW-0060`, `RW-0061`, `RW-0062`, `RW-0065`, `RW-0089`, `RW-0090`, `RW-0091`, `RW-0092`, `RW-0093`, `RW-0105`, `RW-0106`, `RW-0107`, `RW-0111`, `RW-0112`, `RW-0113`, `RW-0114`, `RW-0115`, `RW-0116`, `RW-0117`, `RW-0118`, `RW-0119`, `RW-0120`, `RW-0121`, `RW-0122`, `RW-0123`, `RW-0124`, `RW-0125`, `RW-0126`, `RW-0127`, `RW-0128`, `RW-0131`, `RW-0132`, `RW-0133`, `RW-0134`, `RW-0135`, `RW-0136`, `RW-0138`, `RW-0140`, `RW-0146`, `RW-0177`, `RW-0192`, `RW-0193` |
| B03 | `RW-0001`, `RW-0008`, `RW-0009`, `RW-0010`, `RW-0012`, `RW-0013`, `RW-0014`, `RW-0015`, `RW-0016`, `RW-0017`, `RW-0018`, `RW-0020`, `RW-0021`, `RW-0022`, `RW-0023`, `RW-0025`, `RW-0026`, `RW-0027`, `RW-0028`, `RW-0029`, `RW-0030`, `RW-0031`, `RW-0032`, `RW-0033`, `RW-0034`, `RW-0035`, `RW-0036`, `RW-0037`, `RW-0038`, `RW-0039`, `RW-0040`, `RW-0041`, `RW-0042`, `RW-0043`, `RW-0044`, `RW-0045`, `RW-0051`, `RW-0094`, `RW-0095`, `RW-0096`, `RW-0097`, `RW-0098`, `RW-0099`, `RW-0100`, `RW-0101`, `RW-0103`, `RW-0104`, `RW-0108`, `RW-0109`, `RW-0110` |
| B04 | `RW-0002`, `RW-0003`, `RW-0011`, `RW-0046`, `RW-0064`, `RW-0066`, `RW-0067`, `RW-0068`, `RW-0073`, `RW-0074`, `RW-0075`, `RW-0076`, `RW-0077`, `RW-0078`, `RW-0082`, `RW-0083`, `RW-0084`, `RW-0085`, `RW-0144` |
| B05 | `RW-0086`, `RW-0087`, `RW-0088` |
| B06 | `RW-0006`, `RW-0007`, `RW-0019`, `RW-0024`, `RW-0079`, `RW-0080`, `RW-0081`, `RW-0102`, `RW-0129`, `RW-0130`, `RW-0137`, `RW-0139`, `RW-0141`, `RW-0142`, `RW-0143`, `RW-0147`, `RW-0148`, `RW-0176` |
| B07 | `RW-0195`, `RW-0196` |
| B08 | `RW-0194` |
| B09 | `RW-0048`, `RW-0149` |
| B10 | `RW-0173`, `RW-0174`, `RW-0175`, `RW-0178`, `RW-0179`, `RW-0180`, `RW-0181`, `RW-0182`, `RW-0183`, `RW-0184`, `RW-0185`, `RW-0186`, `RW-0187`, `RW-0188`, `RW-0189`, `RW-0190`, `RW-0191` |
| B11 | `RW-0057` |
| B12 | `RW-0069`, `RW-0070`, `RW-0071`, `RW-0072`, `RW-0150`, `RW-0151`, `RW-0152`, `RW-0153`, `RW-0154`, `RW-0155`, `RW-0156`, `RW-0157`, `RW-0158`, `RW-0159`, `RW-0160`, `RW-0161`, `RW-0162`, `RW-0163`, `RW-0164`, `RW-0165`, `RW-0166`, `RW-0167` |
| B13 | `RW-0168`, `RW-0169`, `RW-0170`, `RW-0171`, `RW-0172` |

### 6.5. AD-01..AD-06 RESOLVED RETAIN test-direction

所有项保留 `approved_by=Aaron`、`approved_at=2026-07-13`、精确 consumer/source anchors。每项均须 AC-derived Red、断言同一行为的 isolated deterministic Green、同 revision `--timeout` 完整 suite Green、文件 `>=80.0`。不删除、不 waiver、不发明行为、不做 coverage trick、不扩大 exclusion。

| AD | Exact consumer evidence retained | 当前实现合同与 required test surface |
|---|---|---|
| AD-01 RESOLVED RETAIN | `prod-f4c5b6766c15`; `admin_routes.py:14-294,779-783`; optional registrar | 默认 `include_admin=False` 无 admin routes；显式启用注册 coded GET/POST handlers，断言当前 role guard、HTML/303 fallback；隔离 auth/repository。 |
| AD-02 RESOLVED RETAIN | `prod-2222692b50e2`; `forms.py:51-727` | login/profile 与 gated legacy FastHTML renderer 的 coded fields/actions/errors；模块不注册 route、不持久化；断言 rendered nodes。 |
| AD-03 RESOLVED RETAIN | `prod-5793dc5849e8`; `repository.py:5-209`; real repository consumer | parameterized lookup、hash/create/update、authentication/`last_login`、CRUD/search/list/count、last-admin refusal、coded fallbacks；临时 deterministic storage。 |
| AD-04 RESOLVED RETAIN | `prod-478f19f91ad5`; `auth/utils.py:8-48`; unconsumed legacy callables retained | token alphabet/length/negative empty、source email regex、password tuple/messages、username sanitize、type/regex propagation；控制 randomness。 |
| AD-05 RESOLVED RETAIN | `prod-5c4b6a15a6b7`; `core/utils.py:7-40`; retained conversion surface | 五个 helper 的严格 8/14 parsing、zero padding、minute seconds `00`、`ValueError`/`AttributeError`；纯 deterministic tests；coverage manifest 必须含文件。 |
| AD-06 RESOLVED RETAIN | `prod-da64e6c5652e`; `analysis.py:15-74`; route `app_factory.py:409` | authenticated `GET /analysis` 返回当前 HTTP 200 retirement HTML，可选 session header，无 analysis data I/O；隔离 branding/session。 |

### 6.6. 断言依据闭合

每个 production path 的断言由 corrected shard `normative_contract` + 其 `governing_upstream_references` 提供；每个 recovery gate 的出口是 coverage JSON、hash report、manifest equality report、per-file report、waiver validation、trace matrix 和 closure summary。若测试需要这些出口之外的内部状态，不在测试侧窥探；回到合同层补公开出口。

## 7. 迭代闭合、CI 与 exit evidence

### 7.1. 迭代规则

每个 batch 后在当前 revision 重算 coverage diagnostic 和 RW registry/status，并重建 closure matrix。将 below-target file、failed/error、manifest mismatch、AC orphan、未满足 AD evidence、invalid waiver、FAKE/incomplete/import-only/self-fulfilling/conflicting/spec-gap 的并集转成下一 batch。只要任一文件无合法 waiver 且低于目标，就必须生成新 batch；完成任何有限 issue/RW 列表都不是 completion。只有最终 same-run evidence 的 blocker 各类别均为 0 才停止。

### 7.2. 必须存在的 safety/isolation tests

- `pytest --random-order` 真实 determinism 与默认/重复 totals 一致。
- HOME/XDG/app config/data/db/log/pid/runtime-state 全隔离，仓库与真实 HOME 无残留。
- socket/HTTP/SMTP/DingTalk/Tushare/gateway deny guard；命中真实目标立即失败。
- MessageHub subscriptions/thread、scheduler、async tasks、client/websocket/database 与 ProcessPool worker leak guard。
- `grid_search` 子进程执行和 coverage attribution guard。
- disk/inventory/coverage source-manifest equality guard，169/169。
- FAKE anti-pattern AST/diff guard。
- AC-anchor 双向 trace guard与固定 index/shard/registry hash/count guard。

### 7.3. CI 顺序

1. 固定 artifact hashes/counts；2. isolation/network deny；3. unit + integration batch Green；4. canonical full unit pytest run；5. 仅在 exit 0 后 hash `coverage.json`；6. 执行扩展后的 `python3 tests/unit/_checkers/per_file_coverage.py coverage.json .louke/project/specs/v0.2-004-coverage-recovery/coverage-waivers.json`，完成 manifest/per-file/waiver gate；7. FAKE 与 `lk agent archer ci-scan`；8. trace/closure binary verdict。任一步失败即 FAIL，后续 artifact 仅诊断。

### 7.4. Exit evidence package

必须包含：完整 commit SHA；原样 command/env；Python、pytest、pytest-cov、coverage 版本；pytest exit 与 passed/failed/errors/skipped summary；`coverage.json` 及 SHA-256；disk/inventory/coverage 三集合 canonical manifest 及 SHA-256；169 行 per-file statements/covered/percent/target/status report；waiver file hash及 validation（当前 empty）；test trace index+shard manifest+matrix hash；RW registry hash/status；AD-01..06 evidence links；closure summary与唯一 PASS/FAIL。

一致性规则：所有 artifacts 标同一 commit、同一 run ID、同一 canonical command；coverage JSON hash必须是 pytest exit 0 后立即固定的文件；manifest/per-file totals 必须与该 JSON 重算一致；trace/RW/AD hashes 必须与 spec pin 相符或已有同步 review 后的新 pin；缺任一字段、跨 revision 拼接、失败 run coverage、人工改写 summary 均 FAIL。

## 8. Judge 评审清单

- [ ] pytest/cov/subprocess/random-order 合同可直接执行，环境缺 plugin 会阻塞而非 fallback。
- [ ] 13 batches 覆盖固定 169 production paths，entry/exit gate 明确。
- [ ] 196 canonical RW IDs 恰好一次映射到 batch，并通过固定 registry 投影全部 function/test/target/defect/AC/evidence 字段。
- [ ] AD-01..AD-06 均有 RESOLVED RETAIN current-implementation test direction。
- [ ] 同一 green run 同时产生 overall、per-file、manifest evidence。
- [ ] source manifest equality、FAKE、AC-anchor、isolation、network deny、resource cleanup 均阻塞。
- [ ] 当前 waiver registry 为空，未引入 broad exclusion、threshold reduction 或 generic waiver。
- [ ] closure 是 blocker=0，而非 issue list exhausted。
