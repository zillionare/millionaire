# Millionaire CE 代码与部署审查

审查日期：2026-11-02。审查源码：`750614e`，包版本 `0.3.0`。

## 结论

这是一个已经具备较多研究、回测和仿真能力的框架，但不能认定为“三个平台均完成安装及后台服务交付、具备可靠停机恢复能力的完整产品”。建议按研究预览版定位，先修复账户与委托一致性，再完善服务交付和持续运行验收。

| 用户关心的问题 | 判断 |
| --- | --- |
| macOS、Windows 64 位、Ubuntu 安装运行 | 有跨平台源码安装入口；本次在 macOS ARM64 安装并运行测试。Windows、Ubuntu 未做真实机器运行验收，现有 CI 只配置 Ubuntu/Python 3.13。不能声称三个平台最新大版本均已验证。 |
| 后台服务及前台启停控件 | 未交付。现有入口是前台 Uvicorn，`--open` 可以打开浏览器；没有原生托盘控制器、操作系统服务注册、开机恢复安装流程。 |
| 实盘柜台接口 | 已有适配器针对 qmt-gateway 的 HTTP 协议及 QMT 账户语义；通用的是 BrokerPort 扩展边界，现成 GatewayBrokerAdapter 不能直接替换成任意柜台。CE 默认已隐藏、拦截并阻止启动实盘。 |
| 功能完整、连续运行、容错 | 有基础，但未达到可靠无人值守标准。已复现清仓后账户恢复错误、委托恢复缺失、重复下单窗口和同步假成功。 |
| 代码质量及重构 | 有清晰的接口和局部复用，复制率较低；主要问题是少数超大模块、高复杂度流程、持久化边界和验收质量。需要有顺序的局部重构。 |

## 审查范围与验证边界

- 阅读安装、启动、版本开关、账户、撮合、委托持久化、数据同步、调度、优化、归因、示例策略及 CI 的实现。
- 在本机 macOS 15.6.1 ARM64 / Python 3.13.14 下创建独立虚拟环境，按当前安装入口的语义安装 `.[ml30m]` 和测试工具。安装使用当前依赖约束，未使用 Poetry 锁文件；这与普通 `scripts/install.py` 的安装方式一致。
- 对 mini-two 做只读检查，没有启动/停止服务、重启机器、修改部署配置、抓取全市场数据或执行真实委托。
- mini-two 源码目录没有 `.git`。对 `quantide/` 与 `scripts/` 的 220 个 Python 文件逐一比较 SHA-256：219 个一致，仅 `quantide/cli.py` 不同。不能据此给远端赋予一个精确 Git 版本。
- 本次没有 Windows/Ubuntu 实机、真实 QMT 柜台、真实交易日长时间运行和突然断电实验；对这些场景的结论区分了源码证据与实测证据。
- 用户补充环境变量约定后，确认当前 `TUSHARE_TOKEN` 已设置。通过它做了两个小范围真实源请求，均成功，详见下方追加验证；没有抓取全市场或改变部署配置。
- 生成的复现程序和扫描结果在本目录 `evidence/`。产品源码未作修改。测试曾改写仓库中的 `data/stock_list.parquet`，已恢复审查前的 Git 内容。

## 一、需要优先修复的问题

P1 表示会影响账户/委托事实、恢复安全或主要功能正确性；P2 表示重要交付、可维护性或验收缺口。

### F01 · P1：完全卖出后未保存现金和清仓快照，重新加载恢复旧持仓

位置：[sim_broker.py:924](../../quantide/service/sim_broker.py#L924)，以及 `_on_quote_update` 中只有 `traded_assets` 非空才保存账户状态的逻辑。

`_apply_trade_to_portfolio()` 会删除股数归零的持仓。随后 `_handle_trade_execution()` 只有在该持仓仍存在时才执行 `traded_assets.add(asset)`。如果一轮行情只有完全清仓的成交，这个集合仍然为空，现金和完整持仓快照均不保存；成交记录和订单完成状态却已经分别写入数据库。

最小复现：初始现金 10000，以 10 元买 100 股，下一日以 11 元全部卖出，费用设为零。

| 状态 | 现金 | 持仓 |
| --- | ---: | --- |
| 卖出后内存 | 10100 | 空 |
| 卖出后数据库 | 9000 | 100 股 |
| PaperBroker.load 后 | 9000 | 100 股 |

数据库中已经存在两笔成交。此问题无需服务器崩溃即可出现，重启使其直接变成错误的账户状态。

还存在第二个恢复缺陷：[sqlite.py:301](../../quantide/data/sqlite.py#L301) 以 positions 表自身的 `MAX(dt)` 判断最新持仓日，无法表达“最新一天是空仓”。在同一复现中强制保存卖出日的空快照后，现金恢复为正确的 10100，但重新加载仍取出前一日的 100 股。仅把 `traded_assets.add()` 移出条件分支不能完整修复这个问题。

建议：任何成交均标记账户发生变化；用明确的快照版本/日期记录空仓，恢复时按该版本读取持仓。成交、订单、持仓、现金应在一个明确事务中提交。当前 `insert_trades`、`update_order`、`replace_positions`、`upsert_asset` 是分开的操作，崩溃窗口也需一并处理。

证据：`evidence/reproduce_paper_reload.py`。

### F02 · P1：日线 next-open 委托缺少领取和幂等提交，崩溃后可能重复下单

位置：[strategy_runtime.py:1539](../../quantide/service/strategy_runtime.py#L1539)。

`process_next_open_intents()` 读取 pending intent，调用 broker，然后才写 processed。与 30 分钟路径不同，日线路径没有先调用 `claim_next_open_intent()`。已有的 processing 检查无法覆盖这条路径的崩溃窗口，也没有把稳定 intent ID 贯穿到 broker 订单幂等键。

在“broker 已接受，但尚未标记 processed”处模拟进程中断后，该 intent 仍为 pending。再次运行恢复流程，同一 intent 触发了第二次 broker 调用，最后只有一条 processed intent。持久化 intent 本身并不能保证下单只执行一次。

建议：先原子领取 intent，订单使用稳定幂等 ID；恢复时对账后再决定完成、重试或阻断。仅增加 processing 状态仍需处理“已成交但未确认”的恢复。

证据：`evidence/reproduce_next_open.py`。复现使用本地假 broker 记录接受次数，不涉及真实交易。

### F03 · P1：重载 PaperBroker 没有恢复未完成委托

位置：[sim_broker.py:91](../../quantide/service/sim_broker.py#L91)、[sim_broker.py:662](../../quantide/service/sim_broker.py#L662)。

构造函数创建空 `_active_orders`。`_init_or_sync_state()` 只加载账户资产和持仓，没有重建数据库中未成交/部分成交订单及其已成交数量对应的队列状态。

复现：提交一个尚未成交的买单，关闭 broker 后重新 `load()`。数据库订单仍是 `48/UNREPORTED`，内存撮合队列为空，因此后续行情不再撮合这笔委托。

建议：启动时明确恢复未完成订单及成交事实，或者以可审计方式取消它们；不能让订单在数据库中保持活动状态而运行时丢失。

证据：`evidence/reproduce_paper_reload.py` 的第二段。

### F04 · P1：分钟线抓取失败被误判为同步成功，并清除尚未落盘的内存行情

位置：[multi.py:68](../../quantide/data/fetchers/multi.py#L68)、[data_sync.py:432](../../quantide/service/data_sync.py#L432)、[data_sync.py:467](../../quantide/service/data_sync.py#L467)。

`BaostockMinuteAdapter.fetch_minute_bars()` 捕获所有 Exception，返回空 DataFrame 和错误列表，包括 `BaostockThrottledError`。调用者忽略 `_errors`，只在抛异常时增加 `failures`。因此外层的限频异常处理实际不能处理被适配器吞掉的错误。

模拟 BaoStock 冻结，结果为：

```text
run_return=true, task_status=done, task_error=""
writes=0, aggregator_clear_calls=1
```

这既会把缺失数据报告为成功，又会调用 `clear_between()` 删除相应日期的盘中合成数据。默认安装还将 baostock 与机器学习一起设为 optional，缺少 baostock 时也可能进入同类错误列表路径。

建议：保留限频异常类别，消费每个标的的错误与覆盖率；只有确认相应区间已完整落盘，才允许清除内存数据。缺少可选依赖应在启动该任务前明确提示。

证据：`evidence/reproduce_minute_sync.py`。

### F05 · P1：把任何数据库初始化异常当成损坏，可能把健康数据库换成空库

位置：[app_factory.py:150](../../quantide/app_factory.py#L150)。

`_initialize_app_database()` 对任意 Exception 都把现有数据库改名为 `.corrupt.*`，然后创建新数据库。临时的锁竞争、权限/磁盘问题或迁移程序异常都不等于数据库损坏。

在健康的临时数据库上模拟一次 `sqlite3.OperationalError("database is locked")`，函数将健康库改名为 corrupt，新的活动数据库不再含原始记录。原库仍有备份，但用户看到的是新库，恢复需要额外人工处理。

建议：只在确认 SQLite 损坏时走隔离恢复；锁竞争重试，其他初始化错误明确停止或进入只读诊断。备份需考虑 WAL/SHM 和恢复流程。

证据：`evidence/reproduce_database_reset.py`。

### F06 · P1：关键状态文件直接覆盖，异常关机缺少一致性保护

位置：[strategy_runtime.py:1615](../../quantide/service/strategy_runtime.py#L1615)、[strategy_runtime.py:1652](../../quantide/service/strategy_runtime.py#L1652)、[stores/base.py:480](../../quantide/data/stores/base.py#L480)、[stores/base.py:610](../../quantide/data/stores/base.py#L610)。

运行时清单、账户/策略封锁和风险事件共用一个 JSON，通过 `write_text()` 直接覆盖。写入中断可能产生截断文件；读取异常又会静默清空这几类状态。行情 Parquet 同样直接覆盖正式文件，旧文件缺少原子替换保护。

建议：小型运行状态优先纳入 SQLite 事务；文件采用同目录临时文件、校验、原子替换、必要的 fsync 与上一代备份。读取损坏时应告警并阻止自动运行，不能当成空状态。Parquet 需要发布快照/manifest 和读写并发约束。

此项依据代码中的写入及异常路径，未对 mini-two 做断电实验。

### F07 · P2：持续数据维护与任务状态存在缺口

位置：[system/jobs.py:29](../../quantide/web/pages/system/jobs.py#L29)、[system/jobs.py:278](../../quantide/web/pages/system/jobs.py#L278)、[optimization_tasks.py:228](../../quantide/service/optimization_tasks.py#L228)。

- 预置日线同步只调用 `daily_bars.store.update()`。统一 `DataSyncService` 的分钟、市值、指数和成分阶段没有作为完整的每日维护任务接入；它目前从数据页面触发。
- “日终快照”和“行情快照”两个预置任务仍然只有 TODO，却写入 success/快照完成。另有策略级 EOD 跟踪任务，不能据此把这两个空任务算作完成。
- 参数优化运行于 daemon 线程，虽然结果落库，但没有发现启动时对旧 running 任务统一标记 interrupted 或恢复的流程；重启后 UI 可能继续显示历史 running，而取消函数只能找到当前进程中的任务。
- 数据同步有阶段记录和重跑时跳过已完成阶段的能力，但没有发现启动时统一接管遗留 pending/running 任务的流程。
- 应用工厂没有统一 ASGI shutdown/lifespan 清理流程，把策略停止、调度器、发布者、消息队列和数据库收尾串起来。单个组件有 stop/close 方法，不等于服务退出已调用它们。

建议：将每日维护、任务恢复和进程关闭归入独立服务层，明确 missed-job 补跑及 interrupted 状态；空任务先显示“未实现”。

### F08 · P2：“全 A”实时行情覆盖尚不成立

位置：[tencent.py:41](../../quantide/data/fetchers/tencent.py#L41)。

`to_tencent_symbol()` 对带后缀的代码只区分 SH 和其他市场，导致 `920000.BJ` 转为 `sz920000`。因此北交所证券的实时请求市场前缀错误。本次不据此推断 BaoStock 的全部市场覆盖，需要另做供应商能力矩阵验收。

此外，腾讯发布者默认从股票列表选取标的，主要指数需要明确订阅或纳入标的集合；不能把“fetcher 能读取指数”直接等同于“默认全市场发布包含主要指数”。

建议：使用明确的市场映射，对 SH/SZ/BJ、指数、无行情、退市及 ST 情况分别验证，并公开实际覆盖范围。

### F09 · P2：验收证据弱于功能声明

位置：[three_mode/test_dual_ma_parity.py:37](../../tests/e2e/three_mode/test_dual_ma_parity.py#L37)、[three_mode/test_dual_ma_parity.py:543](../../tests/e2e/three_mode/test_dual_ma_parity.py#L543)、[paper/test_dual_ma_accuracy.py:138](../../tests/e2e/paper/test_dual_ma_accuracy.py#L138)。

- 文档推荐的三模式一致性测试，整个模块标记为 private_only，CE 下直接跳过；用例本身还带有 `xfail(strict=False)`。
- paper 准确性发布门禁也带非严格 xfail。本次执行确实得到 xfailed，不能作为准确性通过的证据。
- 某些标为 happy/error/edge 的测试只检查类、属性或模块存在，例如 `test_fr_300_gateway.py`。测试数量和覆盖率不等价于业务正确性。
- 单元测试会启动真实外部请求并出现超时；部分测试的断言只是返回值非空。隔离性和行为断言需要加强。
- tag release 工作流直接 build/publish，没有在同一工作流中依赖测试或准确性门禁成功。主测试 CI 只有 Ubuntu/Python 3.13，没有 Windows/macOS 矩阵。

建议：把 CE 回测/仿真一致性作为独立、不可跳过的硬门禁；真实柜台测试单列。发布依赖门禁通过，业务测试默认断网且只用可控源。新增故障注入用例应覆盖 F01–F06。

## 二、安装、后台服务和前台控制

源码已有 `scripts/install.py` 的 Windows/Unix 路径分支、配置目录的平台分支、PID 存活检查分支。`millionaire-ce` console script 也已定义。这些是跨平台的基础实现。

但 [installation.md](../../docs/installation.md) 明确称其为 developer setup，且明确没有原生安装器或服务注册。

| 交付能力 | 当前状态 |
| --- | --- |
| venv + pip 源码安装 | 已实现；本次 macOS 安装成功 |
| macOS 最新大版本、Intel/ARM 验收 | 本次仅 15.6.1 ARM64；没有最新版或 Intel 实机证据 |
| Windows 最新 64 位版验收 | 有路径兼容代码，没有实机/CI 验收证据 |
| Ubuntu 验收 | 有 Ubuntu CI 配置；本次未运行 Ubuntu 虚拟机，也未读取远端 CI 的成功记录 |
| wheel/sdist | 有构建和内容检查流程；产物是 Python 包，不能当成桌面安装器 |
| 操作系统后台服务 | 没有内置注册、卸载、自启、升级迁移和健康监控流程 |
| 前台托盘/菜单栏启停 | 没有 |
| 打开 Web UI | `--open` / `QUANTIDE_OPEN_BROWSER` 已实现 |
| Web 中启停策略 | 有；这控制策略运行时，不是操作系统服务 |

普通启动最终执行 `uvicorn.run()`，进程仍占用前台。调度器和行情的后台线程也不能当成独立操作系统服务。

依赖方面，polars、pyarrow、polars-talib、LightGBM 等需要按平台验证原生二进制。Windows Python 3.13 的仅二进制依赖解析还遇到 `empyrical-reloaded -> peewee<3.17.4` 没有匹配 wheel，表明可能需要源码安装/构建路径；这不等于实际安装必然失败，但不宜承诺无需编译的安装体验。当前 Python 约束还允许 3.14 及后续 3.x，CI 却仅验证 3.13。

建议交付一个共用服务 CLI（install/start/stop/status/open-ui），分别接 launchd、Windows Service、systemd；轻量前台控制器只负责调用这些操作、显示健康状态、打开浏览器。服务在用户关闭控制器后仍应独立运行。把三平台干净安装、升级、重启恢复纳入验收矩阵。

## 三、qmt-gateway 关系与 CE 实盘边界

当前调用链是：

```text
策略 → BrokerPort → GatewayBrokerAdapter → qmt-gateway HTTP 接口
```

[GatewayClient](../../quantide/core/runtime/gateway_client.py) 有固定登录会话和 JSON 协议；[GatewayBrokerAdapter](../../quantide/core/runtime/gateway_broker.py#L918) 调用 `/api/trade/buy`、sell、cancel、positions 等端点，使用 qtoid、QMT 订单状态和 `BrokerKind.QMT`。它是一个特定网关适配器，不是任意柜台通用连接器。

通用扩展点是 [BrokerPort](../../quantide/core/ports/broker.py) 与适配器注册机制。另一种柜台可以实现这个接口，或者做一个完全兼容现有 HTTP 契约的服务；仍需订单状态、可卖数量、费用和幂等等语义适配。改一个 URL 不足以完成柜台替换。

本仓库没有 qmt-gateway 服务端或 xtquant 实现，因此不能确认上游具体券商 QMT 版本、兼容列表或真实柜台可靠性。应用侧未直接依赖 xtquant Python 包，能部署在 macOS 并不说明柜台服务端也能脱离 QMT 环境运行。

CE 现有隔离做得比较完整：

- [features.py](../../quantide/config/features.py) 集中控制实盘能力。
- 导航、实盘账户、gateway 设置、部署按钮按版本隐藏；直接访问受限路由返回 503。
- 初始化不要求真实 gateway，paper/simulation 可独立于柜台工作。
- bootstrap 不注册实盘 adapter；持久化 live runtime 会被标记 edition blocked，不恢复运行。
- 实时行情走 MarketDataHub/Tencent，不必为了仿真引入 QMT。

仍有两个需要明确的产品边界：

1. 发布包保留实际 gateway/live 实现，并允许 `QUANTIDE_ENABLE_EDITION_OVERRIDE=1` 配合 `QUANTIDE_EDITION=zillionaire` 启用版本覆盖。这是显式开发后门，不是不可开启的 CE 编译隔离。若政策要求 CE 分发物本身不提供实盘，建议把真实实盘适配器拆为独立可选包，测试 override 限于开发环境。
2. `middleware_feature.get_feature_status()` 的仿真 description/required 等旧文字仍称需要 gateway，与当前 CE 仿真实现不一致，应统一为本地账户和行情源条件。

内置腾讯发布者默认关闭，需要 `QUANTIDE_QUOTE_PUBLISHER=tencent` 或进程内自行启动发布者。[modes.py:138](../../quantide/core/runtime/modes.py#L138)。README 的普通启动命令没有启用它，因此“页面可打开”不代表仿真已经收到实时行情。另起 `python -m quantide.providers.tencent_publisher` 是另一个进程，而当前 MessageHub 是进程内总线；没有额外跨进程桥接时，它不会把行情送到已经运行的 Web 进程。发行默认配置应明确启用并检查行情健康状态。

## 四、mini-two 的实际状态

2026-11-02 上海时间约 09:20 的只读观察：

| 项目 | 观察 |
| --- | --- |
| 部署位置 | `/Users/quantide/apps/millionaire`，源码、venv 和 wheel 均存在 |
| Python | 3.13.13 |
| 运行进程 | 未发现 Millionaire/Uvicorn 进程 |
| Web 端口 | 默认 8000 和数据库配置的 8130 均连接失败；监听列表也没有对应服务 |
| 系统服务 | 没有发现对应应用的 LaunchAgent/LaunchDaemon 或已加载 launchd 任务；同名 WireGuard 配置不属于应用服务 |
| PID 文件 | 残留 PID 23432，但该进程不存在 |
| 初始化状态 | init_completed=1；持久化 runtime_mode=live、gateway_enabled=0；CE 应由 gate 转为安全路径 |
| SQLite quick_check | ok |
| 账户和交易 | portfolios、assets、positions、orders、trades 均为 0 条 |
| 同步任务 | 18 条：9 pending、9 failed；失败阶段为 8 次 stock_list、1 次 daily_basic |
| 日历 | 2005-01-01 至 2024-12-31，7305 行 |
| 股票列表 | 5432 个证券 |
| 个股日线 | 2024 年，1293893 行、5433 个代码 |
| 分钟线、指数、成分、独立涨跌停存储 | 对应目录没有 Parquet 文件 |
| 策略运行状态 | 没有持久化策略实例；只有一条关于不存在策略的旧错误事件 |

这证明代码和部分历史数据已复制/安装到机器，但没有证明完成真实数据初始化、后台服务交付或连续仿真运行。未根据 pending/failed 记录推断一定发生过崩溃，因为没有相应日志证据。

## 五、功能覆盖判断

| 功能 | 源码中的能力与边界 |
| --- | --- |
| Tushare 日线及扩展字段 | 有日线、复权、ST、涨跌停等抓取与本地存储实现；依赖 token、接口权限和覆盖质量；不能由 stub 测试证明真实源完整 |
| BaoStock 30 分钟历史 | 有适配器、存储与关联日频属性的路径；依赖 optional 包，存在 F04，且供应商全市场覆盖仍需实测 |
| Tencent 实时 | 有抓取、发布、Hub；默认启用关系、BJ 映射和指数订阅需要完善 |
| 日历、证券列表、查询库 | 有具体实现和大量测试；部署数据当前过期 |
| 回测、仿真 | 有共用策略接口、runner、broker 与运行管理；账户/恢复正确性问题阻碍无人值守使用 |
| 实盘 | CE 默认不可用，符合当前暂不开放的方向 |
| 风控叠加 | 有通用 RiskOverlay / adapter 注册扩展；CE 默认注册表为空，没有随包提供可直接选用的内置风控程序 |
| 模式一致性 | 架构方向具备；目前关键准确性测试跳过/xfail，不能宣布端到端一致性已经验证 |
| 参数优化 | 有网格、随机搜索、样本内外切分及后台任务；重启生命周期需补齐 |
| 策略归因 | 有策略声明驱动的预测解释/SHAP 路径；不应扩大解释为所有策略均支持完整收益归因 |
| LightGBM 示例 | 有日线和 30 分钟示例、模型持久化等实现；本次 extra 安装与 LightGBM 导入成功；没有实测全市场长期训练效果或收益 |

连续运行已有的正面基础包括 SQLite WAL 和线程连接、单个消息回调异常隔离、同步阶段持久化、策略恢复、行情健康检查、显式风控扩展及模型文件原子替换。这些应保留并补强边界。

另外，调度器默认 Asia/Shanghai，但策略循环、腾讯交易时段和多处日期判断使用系统本地 `datetime.now()`；部署到其他时区的机器需要统一交易时区，不能仅修改 scheduler timezone。30 分钟盘中合成数据只在内存，源码也明确说明进程中途重启无法恢复已过去的桶，这应列为功能限制或补入可靠恢复方案。

## 六、代码质量量化

扫描范围仅 `quantide/**/*.py`，排除测试和第三方依赖。

| 指标 | 结果 | 解释 |
| --- | ---: | --- |
| Python 文件 | 211 | 另有 9 个 scripts 文件 |
| 物理行数 / SLOC | 63671 / 47047 | 物理行包括空行和注释 |
| 超过 500 / 1000 行的文件 | 35 / 11 | 大模块集中在 UI、runtime、broker、示例策略 |
| 函数超过 100 行 | 48 | 部分包含较长的 HTML/JS 内容，不能等同于同样规模的算法逻辑 |
| 超过 88 / 120 字符的行 | 1029 / 188 | 行宽问题存在，但优先级低于状态一致性与模块职责 |
| Ruff | 0 条问题 | 当前配置忽略 E501，且未开启认知复杂度限制；不代表架构质量已经合格 |
| 圈复杂度均值 | 4.11 | 2202 个 Radon 函数/方法块 |
| 圈复杂度 >10 / >20 | 162 / 31 | 平均数掩盖了少数关键高复杂度流程 |
| 认知复杂度 >15 / >30 | 103 / 28 | `cognitive-complexity 1.3.0` 的近似量化，不等同于官方 Sonar 分数 |
| 复制检测 | 44 组，839 行，约 1.32% | jscpd，阈值 10 行、70 token；这是复制率，不是“代码复用率” |

最大的文件：

| 文件 | 物理行 |
| --- | ---: |
| `web/pages/strategy.py` | 4870 |
| `web/pages/trade_main.py` | 2628 |
| `web/pages/init_wizard.py` | 2138 |
| `strategies/example/ml_momentum_reversal.py` | 1939 |
| `service/strategy_runtime.py` | 1870 |
| `service/sim_broker.py` | 1664 |
| `service/backtest_broker.py` | 1560 |

复杂度最高的几个关键函数：

| 函数 | 认知复杂度 | 圈复杂度 |
| --- | ---: | ---: |
| `trade_main.place_order_trade` | 80 | 50 |
| `strategy_runtime._strategy_loop` | 77 | 49 |
| `ml_momentum_reversal._rank_for_bar` | 72 | 50 |
| `init_wizard.handle_step` | 68 | 32 |

`LightningTradePanel()` 跨 1046 行，大量内容是 UI/JS；`backtest_result()` 跨 498 行。这种规模仍显著增加阅读和修改成本。

复用方面，BrokerPort、MarketDataPort、统一策略接口、bar_views、order_execution 和通用 store 都是正面设计。重复片段主要见于网关/仿真历史数据包装和若干 UI 组件，整体复制率不高。不能用“100%-复制率”推导复用率，也不建议为降低这 1.32% 而引入复杂继承。

真正应重构的是职责混杂：runtime 同时处理部署、恢复、调度、策略循环、委托状态、风控事件；页面模块承担渲染、JavaScript、表单验证、业务调用；legacy 同步入口与统一服务并存。针对这些边界拆分能直接降低认知复杂度，也有助于防止 F01–F06 再次出现。

## 七、本次测试结果

| 验证 | 结果 |
| --- | --- |
| 新虚拟环境安装 `.[ml30m]` | 成功；LightGBM 4.7.0 导入成功 |
| `TUSHARE_TOKEN` 真实源小范围验证（追加） | 日历和 `000001.SZ` 日线各返回两条，HTTP 200 |
| `ruff check quantide scripts` | 通过 |
| 全部 `tests/unit`，单项 60 秒超时 | **4549 passed、2 failed、3 skipped、1 error**，约 311 秒 |
| CE release_gate E2E（排除 private/live smoke） | **5 passed、1 xfailed、276 deselected** |
| 文档推荐的三模式 parity，在默认 CE 执行 | **1 skipped**，原因 private_only |
| F01/F03 账户与委托重载复现 | 确认 |
| F02 日线 intent 崩溃窗口复现 | 确认；同一 intent 两次 broker 接受 |
| F04 分钟线异常复现 | 确认；零写入、任务 done、清内存一次 |
| F05 数据库临时锁异常复现 | 确认；健康库被改名并替换为新库 |

失败项：

- `tests/unit/quantide/web/pages/system/test_v0204_b08_datasource.py::test_ds_sync_data`
- `tests/unit/quantide/web/pages/test_v0204_b08_trade_main_helpers.py::test_build_asset_stats_for_empty_asset`
- `tests/unit/quantide/web/pages/test_v0204_b08_data_market.py::test_do_update_valid_date`（teardown error）

这些失败涉及真实外部请求及超时，不能直接归因为交易算法错误，但它们表明默认单元测试不能稳定离线完成。空证券代码仍进入历史数据 fallback 也是应收紧的 UI 读取边界。

没有计算新的覆盖率；不能把仓库 CI 里的 80% 门槛描述为本次实测覆盖率。测试及扫描版本见 `evidence/environment.json`，摘要见 `evidence/verification.json`。

### 追加验证：环境变量 TUSHARE_TOKEN

当前安装的 Tushare SDK 1.4.29 在 `upass.get_token()` 中优先读取 `TUSHARE_TOKEN`，其次 `TS_TOKEN`，然后才读取本地 token 文件。应用自身的 `get_tushare_token()` 读取配置数据库，但随后无参数 `ts.pro_api()` 的 SDK 路径可以读取上述环境变量，因此无须为本次审查修改产品代码。

在独立进程中仅从 `TUSHARE_TOKEN` 取得 token，以参数传给 SDK，没有打印或另外持久化 token。两个请求都限制在 2024-01-02 至 2024-01-03，单次超时设为 6 秒：

| 请求 | 参数范围 | HTTP | 数据行 | 耗时 |
| --- | --- | ---: | ---: | ---: |
| trade_cal | SSE，两个自然日 | 200 | 2 | 0.16 秒 |
| daily | 000001.SZ，两个自然日 | 200 | 2 | 0.09 秒 |

这证明 token 可用，日历和普通日线接口在本环境可访问。不能据此证明 ST、涨跌停、指数等全部权限，也不能证明完整历史覆盖。之前单元测试仍保留原始失败结果，未将它们归因为缺少 token，亦未把这两个小范围请求计为三个失败测试重跑通过。F01–F06 的账户、委托及故障处理问题不依赖真实 Tushare token。

程序与无密钥输出：`evidence/verify_tushare_env.py`、`evidence/tushare_smoke.json`。

## 八、建议实施顺序与放行条件

1. **先修复事实一致性。** F01–F06 建立回归用例；统一账户成交事务、稳定委托 ID、领取/对账/重试规则。覆盖清仓、部分成交、提交前后中断、写库中断和损坏状态文件。
2. **统一数据与任务生命周期。** 保留一个同步编排器，明确每个数据集的覆盖标准、失败状态和补跑；完成快照任务或去掉假成功；恢复优化和同步任务状态；补齐应用 shutdown。
3. **完成 CE 的交付边界。** 明确实盘适配器是否移出分发物，清理 gateway 相关旧文案，默认启用可用行情路径并显示健康状态；供应商市场覆盖以实测矩阵说明。
4. **局部拆分大模块。** 先拆 runtime 的持久化/委托执行/策略循环，再拆 strategy、trade_main、init_wizard 的页面和业务，再整理大示例策略。现有通用接口保持稳定。
5. **补三平台服务交付与硬门禁。** 干净安装、运行、关闭控制器、服务自动重启、系统重启、升级迁移和卸载都需验收；CE parity 不允许 skip/xfail，发布必须依赖门禁。

建议连续运行验收至少覆盖多个完整交易日：每日数据补齐、盘前就绪、盘中断网恢复、午休与收盘、隔夜 T+1、服务正常重启和模拟突然退出。验收标准应比较订单、成交、持仓、现金和待执行意图的持久化事实，而不仅是进程是否重新启动或页面是否返回 200。
