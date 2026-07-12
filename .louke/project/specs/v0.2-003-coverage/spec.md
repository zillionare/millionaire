# Millionaire Coverage Spec — 契约反推与单元测试覆盖率提升

- **Spec ID**: v0.2-003-coverage
- **创建日期**: 2026-07-09
- **复核日期**: 2026-07-10
- **状态**: 草稿（Sol 二次复核：纠正推测接口并补齐契约来源）
- **Story**: [story.md](./story.md)
- **Acceptance**: [acceptance.md](./acceptance.md)
- **上游设计源**:
  - [v0.2-001 strategy spec](../v0.2-001-strategy-framework/spec.md)
  - [v0.2-001 interfaces](../v0.2-001-strategy-framework/interfaces.md)
  - [v0.2-001 acceptance](../v0.2-001-strategy-framework/acceptance.md)
  - [v0.2-002 UI spec](../v0.2-002-ui/spec.md)
  - [v0.2-002 interfaces](../v0.2-002-ui/interfaces.md)
  - [v0.2-002 acceptance](../v0.2-002-ui/acceptance.md)

本 spec 只定义“如何从已锁定上游合同得到可测试的模块契约”以及发布覆盖率门禁，不重新定义 001/002 的业务规则。

## 已确认决策

- FR/NFR 使用 Louke 可识别的 4 位编号 `FR-XXXX` / `NFR-XXXX`。
- v0.2 发布门禁为整体 statement/line coverage ≥95%。
- 每个含可执行语句的生产 `.py` 文件 ≥80%；例外必须进入临时豁免流程。
- pytest 配置沿用 `pyproject.toml`，不新增 `pytest.ini` 或 `setup.cfg`。
- 空文件/0-statement 文件不需要豁免；不能把含 import/re-export 语句的文件当作空文件。

## 复核基线

2026-07-10 运行：

```bash
.venv/bin/pytest tests/unit \
  --cov=quantide \
  --cov-report=term \
  --cov-report=json:/tmp/coverage-v003-review.json
```

得到 15540 statements、5196 miss、67%，同时出现 15 failed、33 errors。错误包含测试访问真实用户配置目录、依赖开发网关替身状态等隔离问题。因此该数字只是诊断快照，不是可接受的发布基线；只有 pytest 全绿的同一次运行产生的 coverage JSON 才能作为门禁证据。

## 契约判定规则

契约来源优先级：

1. 上游 spec 与 acceptance；
2. 上游 `interfaces.md`；
3. 上游 story；
4. 当前公开实现与已有测试。

适用规则：

- 1~3 与代码冲突：按上游写测试，冲突记为生产代码缺陷。
- 旧测试与 1~3 冲突：修测试，不能把旧断言提升为新规范。
- 上游未规定但已有消费方依赖：可以把当前公开输入/输出写成兼容契约。
- 只有私有实现、无消费方：只允许 characterization test，不新增产品语义。
- 无行为的占位/marker：只测试其声明的 schema/marker；不得虚构 CRUD、序列化或状态机。

## Traceability Matrix


| v0.2-003     | 生产面                | 上游合同                                                    |
| ------------ | --------------------- | ----------------------------------------------------------- |
| FR-0001      | 全域                  | 001/002 spec、interfaces、acceptance                        |
| FR-0101~0104 | 测试基础设施          | 001/002 test-plan、v0.2 DoD                                 |
| FR-0201~0207 | core                  | 001-FR-010~250、NFR-050/060、001 interfaces §2/§3/§6/§7 |
| FR-0301~0304 | data                  | 001-FR-270~330、FR-480/484、001 interfaces §4              |
| FR-0401~0404 | service               | 001-FR-115~360、FR-440/460、001 interfaces §3/§4/§6      |
| FR-0501~0505 | web                   | 002-FR-0010~0460、002-NFR-0010~0070、002 interfaces         |
| FR-0601~0602 | CI                    | v0.2 DoD、NFR-0010                                          |
| FR-0701      | notify/market helpers | 001-FR-481/485                                              |
| FR-0702      | strategies            | 001-FR-090/100/110/115/125/185                              |
| FR-0703      | config/app bootstrap  | 001-FR-470、002-FR-0110/0460                                |

## 范围

在范围内：`quantide/` 下所有 v0.2 生产 Python 文件、`tests/unit/`、pytest/coverage 配置、逐文件覆盖率检查器和 GitHub Actions 单元测试门禁。

不在范围内：真实第三方连通性、浏览器 E2E、视觉回归、性能测试、新业务功能、为无消费者代码虚构产品接口。

## 用户故事

### US-0001

作为发布维护者，我需要知道每条新增测试断言来自哪个已锁定合同，以免把当前实现缺陷固化成规范。

### US-0101

作为开发者，我需要一个全绿后才计算覆盖率、并同时检查整体与逐文件阈值的统一命令。

### US-0201

作为策略开发者，我需要 core 的端口、运行时、生命周期和消息契约被单测保护，使 001 的四模式与可注入性成立。

### US-0301

作为数据使用者，我需要数据获取、模型、存储和研究工具按 001 的字段与边界工作。

### US-0401

作为运行维护者，我需要服务层正确完成策略调度、撮合、行情、评估与失败清理。

### US-0501

作为 UI 使用者，我需要页面、认证、API、middleware 和组件按 002 的 HTTP/DOM/降级合同工作。

### US-0601

作为维护者，我需要 CI 自动阻断红测、整体覆盖率不足和未豁免单文件覆盖率不足。

### US-0701

作为 v0.2 用户，我需要通知、内置策略、配置和启动装配这些早期模块有可追踪的契约测试。

<a id="fr-0001"></a>

### FR-0001 契约来源与冲突判定


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

每个新增或修改的测试文件必须引用至少一个上游 FR/AC 或本 spec FR/AC。测试期望值必须来自独立 fixture、公式、schema 或上游示例，不能调用被测实现计算自身期望值。

发现冲突时使用以下输出分类：

- `implementation-defect`：代码不满足 001/002；
- `test-defect`：旧测试不满足 001/002；
- `spec-gap`：001/002 没有足够信息且消费方行为无法唯一推导；
- `dead-or-marker`：无消费方或仅声明 schema/marker，不创造行为接口。

`spec-gap` 不能通过“以现有实现为准”自动关闭；必须补充明确决定或把该行为排除出发布合同。

<a id="fr-0101"></a>

### FR-0101 pytest 配置与规范命令


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

pytest/coverage 配置以 `pyproject.toml` 为唯一来源。规范本地/CI 命令的测试集合固定为 `tests/unit`，coverage source 固定为 `quantide`：

```bash
poetry run pytest tests/unit \
  --cov=quantide \
  --cov-fail-under=95 \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  --cov-report=html:htmlcov
```

命令 exit 0 同时表示测试无 failure/error 且整体覆盖率达标。`asyncio_mode = "auto"` 保留。

<a id="fr-0102"></a>

### FR-0102 逐文件覆盖率检查与豁免清单


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

逐文件检查器读取同一次全绿运行生成的 `coverage.json`：

- 仅检查 `quantide/**/*.py` 且 `num_statements > 0` 的文件；
- 每个文件 `percent_covered >= 80`；
- 包级 `--cov-fail-under=80` 不能替代逐文件检查；
- `coverage-waivers.json` 默认 `waivers=[]`；
- 临时豁免字段至少包括 `module`、`current_coverage`、`reason`、`expires_at`、`followup_issue`；
- 过期、字段缺失、模块不存在或 follow-up issue 不合法时检查失败。

不得通过 `omit`、扩大 `exclude_lines` 或批量 `pragma: no cover` 实现豁免。

<a id="fr-0103"></a>

### FR-0103 Mock 边界与共享 Fixture


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

允许的替身边界：网络/Tushare/qmt-gateway/SMTP/钉钉、时钟、文件系统、SQLite/Parquet、进程/线程调度、下游 port/service。被测函数或类主体不得被 mock。

`tests/unit/conftest.py` 提供版本化 `env` fixture，至少暴露 `manifest`、`universe`、`calendar`、`daily_bars`、`adj_factor`、`st_info`、`limit_price`。Web/app 测试还必须提供临时 app config dir 与临时数据库；调用 app factory 时显式传入隔离路径。

<a id="fr-0104"></a>

### FR-0104 测试隔离与确定性


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

任意测试必须可单独运行且不依赖顺序。测试不得读取或改写真实 HOME、`~/.config/quantide`、`.sesskey`、真实数据目录或已运行的开发网关；临时文件全部位于 pytest `tmp_path` 或 runner temp 下。模块级 singleton、registry、scheduler、message hub、环境变量和 config override 在用例后恢复。

时间相关断言使用显式注入时钟、monkeypatch 或 freezegun；异步后台任务、线程、数据库连接和 websocket/client 在 teardown 完成关闭。

<a id="fr-0201"></a>

### FR-0201 core/domain 事件 DTO


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`MarketEvent`、`QuoteSnapshot`、`OrderEvent`、`TradeEvent`、`ErrorEvent` 是 dataclass DTO。测试合同为：

- 构造输入按公开字段名/类型传入，读取时字段值不丢失；
- `MarketEvent.source="unknown"`、`event_id=""`；
- OrderEvent 的 filled/reason 默认值正确；
- ErrorEvent 的 `retryable=False`，每个实例拥有独立 `details` dict；
- 不要求不存在的 `to_dict/from_dict/to_json/from_json`。

这些 DTO 支撑 001 interfaces §6 日志/事件和 MarketDataPort 输出。

<a id="fr-0202"></a>

### FR-0202 core/runtime 时钟适配


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`SystemClockAdapter.now()` 返回墙钟；`set_now(tm)` 抛 `RuntimeError`。`BacktestClockAdapter.set_now(tm)` 后 `now()` 精确返回 `tm`。两类 adapter 的 `iter_frames(start,end,frame_type)` 均把参数不变地委托给交易日历并返回其 iterable。

初始 BacktestClock 的墙钟 fallback 仅作兼容行为；业务测试必须先注入/设置确定性时间，不能依赖真实当前时间。

<a id="fr-0203"></a>

### FR-0203 core/runtime 网关客户端与 BrokerPort 适配


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`GatewayClient` 输入 `base_url/username/password/timeout`：

- 首次请求先 POST `/auth/login`，后续请求复用登录状态；
- `get_json(path, params)` / `post_form(path, data)` 对 2xx JSON/text/plain 返回解析对象，空 body 返回 `None`；
- HTML 或未知 content type 抛 `GatewayProtocolError`；
- `cookie_header()` 输出 cookie，`ws_url(path)` 按 http→ws、https→wss 转换。

`GatewayBrokerAdapter` 把 BrokerPort 的 submit/buy/sell/cancel/query 输入转换为网关表单/查询，把响应转换为 `OrderAck`、`ExecutionResult`、`CancelAck`、`PositionView`、`AssetView`、`OrderView`、`Trade`。订单内部/外部标识冲突必须抛一致性错误，不能静默归因到错误账户。

<a id="fr-0204"></a>

### FR-0204 core/runtime 装配与兼容 Broker


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`RuntimeBootstrap(mode=None, clock=None)` 是装配器，不是模式状态机：

- 显式 mode 原样进入 `RuntimeContext.mode`；自动模式只产生 `live|paper|backtest`；
- 显式 clock 原样进入 context；默认使用 SystemClockAdapter；
- bootstrap 输出 `RuntimeContext(mode, registry, adapters, market_data, clock)`；
- 只加载数据库中的 simulation portfolio；单个坏账户不能阻止其他账户装配；
- 网关启用时注册 gateway BrokerPort，禁用时不注册。

`PortBackedBroker` 把一个 BrokerPort 适配为旧 broker/UI 句柄：资产空结果产生同 portfolio 的零值 Asset；positions 以 asset 为 key；orders 映射 side/status，未知值映射 UNKNOWN；所有交易与撤单参数透传。它不提供端口注册/注销或一对多路由。

<a id="fr-0205"></a>

### FR-0205 core 策略、发现与调度


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`Strategy` / `BaseStrategy` / `RiskStrategy` 按 001-FR-010/013/115/125：生命周期钩子默认 no-op；`BaseStrategy.on_bar(self, tm)` 只有 tm；交易/record/get_bars 委托给 broker；RiskStrategy 无 buy API，只能 `sell_host_position` 并读取宿主数据。

`StrategyDiscovery.discover(root)` 非递归扫描 `.py`，只枚举 BaseStrategy/RiskStrategy 具体子类，输出 001-FR-020 元数据与 skipped 条目；损坏文件、重复 ID、根目录外导入不使整次扫描崩溃。

`SchedulerManager` 只承诺惰性 `init`、幂等 `start/stop`、`add_job`、`add_listener` 透传。不存在的 `remove_job/list_jobs` 不属于本合同；如需移除/列举，通过底层 scheduler 公开对象或另立需求。

<a id="fr-0206"></a>

### FR-0206 core 枚举、消息、SDK 与辅助规则


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

- `enums.py`：验证 BidType/OrderSide/OrderStatus/FrameType/BrokerKind/Topics 的公开值，FrameType int 转换与比较的合法/非法输入。
- `message.py`：验证 subscribe 去重、unsubscribe、异步 publish、无订阅者进入 pull queue、subscriber 异常隔离、满队列丢弃策略和 stop；不要求 encode/decode。
- `errors.py`：验证公开异常层次、字段和消息保真。
- `sdk_metadata.py`：CalendarSDK 严格满足 001-FR-014 的五个方法；SecurityListSDK 满足 001-FR-015 的四个方法，未知证券 `get_name` 给出可判定错误。
- `notifications.py`、`order_execution.py`、`risk_events.py`、wizard steps 等辅助 DTO/规则按引用它们的 001/002 字段和边界测试。

<a id="fr-0207"></a>

### FR-0207 core/ports 结构契约


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

Protocol 使用结构化替身验证，不要求“实例化抽象类抛 TypeError”：

- BrokerPort：record、submit、六类买卖、target pct、cancel/cancel_all、四类 query；
- ClockPort：now/set_now/iter_frames；
- DataFetcherPort：calendar/stock/adjust/bars/limit/ST/bars_ext；
- MarketDataPort：start/stop、批量 subscribe/unsubscribe、async stream、snapshot。

端口 DTO 的 mutable default（如 `OrderRequest.extra`、ack/result trades）必须实例隔离。

<a id="fr-0301"></a>

### FR-0301 data/fetchers


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`TushareDataFetcher` 实现 DataFetcherPort。测试在 Tushare SDK 边界截获调用，验证：

- 交易日历、证券列表、复权、日线、涨跌停、ST、扩展日线返回约定 DataFrame/错误列表；
- 日期或日期批次正确传递，空结果保持可消费的标准列；
- 分批单次失败被收集并允许其余批次继续，鉴权/整体失败可判定；
- `fetch_bars_ext` 输出支撑 001-FR-270/290 的 OHLCV、amount、adjust、is_st、up_limit、down_limit。

`DataFetcherRegistry` 按实例 `register(name, fetcher, make_default=...)`、`get(name|None)`、`has`、`list_names` 工作；未知/重复/默认项行为按公开实现断言，不虚构类级 resolve API。

<a id="fr-0302"></a>

### FR-0302 data/models


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

- Calendar：load/save、日期/时间互转、day/week/month shift、frames、trade dates/count 与开闭市判断。
- StockList：load/save、上市/退市/ST、名称/拼音模糊搜索、上市天数。
- DailyBars：connect、范围/count 查询、撮合价、涨跌停和复权因子。
- AppState：字段校验、to_dict/from_dict、feature readiness 与 Settings 转换。
- base/entities/strategy_config：数据库 schema、字段默认值、日期类型和元数据 DTO。
- IndexBars：只承诺 `SCHEMA`，字段为 `sector_id,date,open,high,low,close,volume,amount` 及对应 Polars 类型；不承诺实例 CRUD/序列化。

每个模型按自身 API 测试，不允许统一套用不存在的 Model.from_dict/to_dict。

<a id="fr-0303"></a>

### FR-0303 data/stores 与 SQLite


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

ParquetStorage 在临时目录验证：空 store、单文件/按年分区、append、日期范围、列选择、eager/lazy、available dates、分组日期和 fetch progress/error collection。

IndexBarsStore 输入 `symbols/start/end/eager_mode`，输出本地 Polars DataFrame/LazyFrame；symbols 对存储列 `sector_id` 过滤，日期闭区间过滤；空 store 返回相应空对象；`rec_counts_per_date` 返回 `dict[date,int]`；远程 `fetch` 明确抛“主体已移除”错误。

SQLiteDB 按 001 interfaces §4 验证 portfolio/asset/position/order/trade/strategy log/backtest log 的 insert/upsert/get/query/update/delete 与 portfolio cascade。所有数据库位于 tmp_path，连接在测试后关闭。

<a id="fr-0304"></a>

### FR-0304 data/helper 与 resampler


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`qfq_adjustment` / `hfq_adjustment` 对给定 OHLC 与 adjust fixture 输出独立手算结果，处理空输入与缺列。`train_test_split` 按时间顺序、可选 group、train/valid 比例切分，返回类型与 pandas/Polars/LazyFrame 输入一致。

Resampler 按 001-FR-480：周/月 open=首、high=max、low=min、close=末、volume/amount=sum、adjust=末；空输入为空；未知 freq 抛可判定错误；`calculate_ma(periods)` 产生 `maN` rolling mean。

<a id="fr-0401"></a>

### FR-0401 service 策略加载、Runtime 与 Runner


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`service/discovery.py` 是策略加载服务：验证 built-in/user/workspace 扫描源、用户同名优先、cache load/save/clear、list/get strategy info、坏文件隔离和示例复制计数。不得测试不存在的网络服务健康检查。

BrokerRegistry 按 `(BrokerKind, portfolio_id)` 注册、覆盖/拒绝规则、注销、get/list/list_by_kind/get_default。

StrategyRuntimeManager 验证 backtest runtime create/complete/get/remove，paper/live deploy，start/stop/block/unblock，risk/runtime summary、row schema、状态持久化恢复；失败原因通过对外 state/row/risk event 可观察。

BacktestRunner 按 001-FR-115/230：拒绝 RiskStrategy 回测，日期对齐，生命周期顺序，完成/异常都清理资源。

<a id="fr-0402"></a>

### FR-0402 service Broker 与交易规则


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

AbstractBroker 实现 BrokerPort adapter：submit/cancel/query DTO 语义、wait/awake 超时、status/trade 转换和未知值错误。

BacktestBroker 与 PaperBroker 使用独立行情、时钟和临时 SQLite，至少保护：

- 001-FR-140 涨跌停与限价；
- FR-150 手数、清仓、回测全成或作废、paper 部分成交；
- FR-160 T+1 与非交易时点；
- FR-170 停牌；
- FR-180 现金、佣金、印花税；
- FR-185 加权成本；
- FR-210/220 portfolio/qtoid 归属；
- cancel/cancel_all 和订单状态生命周期。

<a id="fr-0403"></a>

### FR-0403 service BarsFeed 与 LiveQuote


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

BarsFeed 是 pull-style 接口：`get_bars`、`get_price_limits`、`get_current_price`、`get_price_for_match`、`get_close_adjust_factor`。BarsFeedImpl 合并历史数据与形成中 live bar，规范化列并在无数据时返回空 DataFrame；边界错误按端口合同传播或转为空结果，必须由具体方法明确，不能笼统吞异常。

LiveQuote 输入 websocket payload/订阅 symbols，输出 quote/limit/minute/daily cache、`MarketEvent` async stream 和 `dict[symbol,QuoteSnapshot]` snapshot。验证 start/stop 幂等、ws/wss URL、payload 格式错误、subscribe/unsubscribe、queue 停止哨兵和数值转换。它不承诺 callback subscriber API 或 tick→bar 聚合，除非当前公开方法明确提供。

<a id="fr-0404"></a>

### FR-0404 service 辅助能力


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

- backtest_logs：record/list/load/delete 与文件失败降级；
- GridSearch：参数笛卡尔积、任务输入、结果 DataFrame、save_logs；
- InitWizardService：默认状态、必填/可选步骤、配置保存、网关测试、完成/重置/redirect/progress；
- metrics：001-FR-340/350 的指标，固定输入独立手算并定义 NaN/空交易边界；
- trade_lightning：entry 校验与 record、CRUD、cached price reference、空/未知标的；
- triple_barrier：001-FR-360 F-TB-1~5、同日双触障选择、expire 和非法配置。

“闪电交易性能”不属于 unit acceptance；本 FR 测其输入、持久化、价格引用和 broker 边界。

<a id="fr-0501"></a>

### FR-0501 web/components/analysis


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

KlineChart 构造输入 `chart_id/data/width/height`，`render()` 输出可序列化 FastHTML 节点并包含唯一 chart target、OHLCV 数据和更新脚本；`freq_buttons` / `ma_buttons` 输出可识别 action/target 与当前选择。

StockList 输入 stocks/selected_symbol，`render()` 输出代码、名称、选中态与空状态；`toolbar()` 输出 sector 标题/工具。搜索、过滤和排序由 page/API/service 负责，不要求 StockList 内部提供不存在的方法。

Backtest chart spec 按 002-FR-0370 输出 equity/drawdown/monthly heatmap 的 type、series、labels、render target；不把 Python spec 对象误断言为真实 SVG/canvas DOM。

<a id="fr-0502"></a>

### FR-0502 web 通用组件与布局


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

header/sidebar/toast/runtime_params/asset_label/layouts/theme 按 002-FR-0150~0170、NFR-0020/0040：导航与 active 状态、告警 unread/recent、用户菜单、toast level/ARIA/自动关闭、运行参数边界、资产名 fallback、HTMX fragment 与 full layout、语义按钮/颜色/间距。

已有 100% 覆盖的模块必须保持等价行为测试；允许重构测试，不允许只删测试。

<a id="fr-0503"></a>

### FR-0503 web/pages 路由与页面输出


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

页面测试以 002 interfaces §2 为路由/表单权威源：

- strategy/accounts/trade/history 页面消费 mock service/registry/port，输出规定字段、按钮、状态与确认动作；
- system/data 页面消费 task/integrity/calendar/stock/gateway fixture，输出表格、过滤、进度与局部错误；
- init-wizard 按 002-FR-0460 的步骤、恢复、skip、progress 和完成分流；
- HTMX 请求返回 fragment，普通请求返回完整 layout；
- 单个区域失败按 002-NFR-0050 只替换该区域，其他区域保留。

测试观察 FastHTML 节点、HTML 字符串、Response status/header/body 或下游 service 调用，不 mock 当前 page handler。

<a id="fr-0504"></a>

### FR-0504 web/auth、API 与 middleware


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

认证只以 002-FR-0110~0140 为产品合同：单管理员登录、失败、主动登出、旧密码+两次新密码改密、session 与 `/login?next=...`。注册、忘记密码和多用户 admin route 是遗留实现，不因覆盖率任务自动进入 v0.2 产品验收；其可执行代码仍需 characterization 或经 dead-code 决策处理。

API 以 001/002 interfaces 为权威，断言 method/path、输入 schema、2xx/3xx/4xx/5xx、redirect、body/ErrorEnvelope 和 service 边界。broker 与 analysis API 必须覆盖有效、空、非法、下游失败。

Init/Auth/Feature/BrokerRegistry middleware 验证 public/protected path、未初始化、未认证、A/B 降级、HTMX fragment/full page、registry 注入和异常转换；不得读取真实凭证或真实用户数据库。

<a id="fr-0505"></a>

### FR-0505 web 跨切面与 service 合同


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`web/services/` 的 DTO/纯函数继续作为 002 的业务合同层，覆盖 strategy management、runtime control、accounts、dashboard、tasks、trade、history、notifications、gateway、risk events、backtest progress/report、stock query 和 routing。

`degradation.py`、`errors.py`、`events.py`、`local_storage.py`、`nfr_*.py` 分别保护 002-FR-0180、ErrorEnvelope、PushEvent payload、localStorage allowlist/敏感 key 和 002-NFR-0010~0070。输入非法时返回明确 False/default 或抛约定错误，不能导致页面启动失败。

<a id="fr-0601"></a>

### FR-0601 CI 单元测试与双重覆盖率门禁


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

GitHub Actions 在 `push` 与 `pull_request` 的 `main`、`releases/**` 上：

1. 使用项目声明支持的 Python 版本；
2. 安装 test dependency group；
3. 在隔离 HOME/config/data 环境运行 FR-0101 规范命令；
4. pytest 红测或整体 <95% 时失败；
5. 解析 `coverage.json`，任一非豁免生产文件 <80% 时失败；
6. 上传 coverage JSON/HTML 作为诊断证据。

不得依赖当前 `dev.yml` 中过时的 Python 3.8~3.11 matrix 作为 v0.2 门禁；`pyproject.toml` 要求 Python >=3.13。

<a id="fr-0602"></a>

### FR-0602 覆盖率 Artifact 与可选增量检查


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

CI 上传 `coverage.json` 与 `htmlcov/`，保留期 30 天。即使主测试失败，也可用 `if: always()` 尝试上传已生成报告；artifact 上传失败是否阻断由 workflow 明确，但不能改变主测试/阈值结论。

diff-cover ≥95% 是可选、非阻断增强项。启用时使用同次运行生成的 XML，并明确 compare branch；它不能替代整体 95% 与逐文件 80%。

<a id="fr-0701"></a>

### FR-0701 notify 通道与遗留市场 helper


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

`mail.py` 按 001-FR-481：`compose` 支持 plain/html/attachment EmailMessage；subject/body 与 msg 的互斥/必填错误可判定；`send_mail` 组装 From/To/Cc/Bcc/subject/body 并在 async loop 创建发送任务；SMTP 边界全 mock。

`dingtalk.py`：string→text payload，`{title,text}`→markdown payload；access token 必填、secret 签名、HTTP 2xx+errcode=0 成功；HTTP/业务失败留下可观察失败且不得报告成功；HTTP 边界全 mock。

`notify/__init__.py` 实际属于 001-FR-485：验证沪/深/北市场识别、hson/xt/jq 代码转换、普通/创科涨跌停 helper 与开盘时间差。它不是通道导出/工厂。

<a id="fr-0702"></a>

### FR-0702 内置策略


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

DualMAStrategy 必须满足 001-FR-090/115：default `{fast:5,slow:20}`；公开 `on_bar(self,tm)` 签名与 BaseStrategy 一致并通过 `get_bars` 拉取；窗口不足/非交叉不下单；上穿买、下穿卖。

PullbackSellStrategy 满足 001-FR-100/125：默认 `m=7.0,k=0.5,n=1`；涨至 m% 后只在 n 分钟窗口内从峰值回落超过 k% 才卖宿主持仓；无价/无可卖持仓/已触发不重复卖。

CostStopLossStrategy 满足 001-FR-110/185：默认 k=-5.0；`last_price <= cost_basis*(1+k/100)` 时仅卖 `avail`，使用 reason=`cost_stop`，无有效成本/价格不卖，同日不重复触发。

若当前实现签名或 n 窗口与上述冲突，分类为 `implementation-defect`，不能把现实现状写成 v0.2-003 期望。

<a id="fr-0703"></a>

### FR-0703 config 与 app bootstrap


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

config 验证默认值、环境覆盖、品牌、data home 规范化、app config override、dev stub start/stop/幂等与非法配置。所有环境变量和模块 override 在 teardown 恢复。

`create_app(app_config_dir, enforce_single_instance)` 的可观察合同：

- 使用给定 app_config_dir 创建 SQLite/PID/runtime state，不触碰真实用户目录；
- 未初始化时可创建 app 并由 middleware 分流 init-wizard；
- 已初始化时装配 data/runtime/registry/auth；单个运行时错误降级到 wizard 而非使 factory 崩溃；
- 注册 002 interfaces 所需 route、mount、middleware 与 exception handler；
- `enforce_single_instance=False` 不创建/检查真实 PID；True 的重复实例错误可在临时目录断言。

<a id="nfr-0010"></a>

### NFR-0010 发布覆盖率与豁免


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

- 同一次全绿 unit run 的整体 statement/line coverage ≥95%；
- 每个 `quantide/**/*.py` 且 `num_statements>0` 的文件 ≥80%，或有未过期合法临时豁免；
- 空/0-statement 文件自然跳过，不列为永久豁免；
- 主门禁阈值不得使用 `continue-on-error`；
- coverage 数据必须包含所有生产模块，不能仅统计被 import 的子集。

<a id="nfr-0020"></a>

### NFR-0020 隔离、确定性与资源清理


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

测试任意单独/重复/顺序运行结果一致；不访问外网和用户真实状态；所有线程、task、client、websocket、scheduler、SQLite connection 与临时文件在用例后释放。等待异步结果使用 event/condition/可控时钟，不使用依赖机器速度的长 sleep。

<a id="nfr-0030"></a>

### NFR-0030 有意义覆盖与反作弊


| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅       | ✅     | ✅         |

每个从 <80% 提升的模块至少新增一个正常路径和一个失败/边界路径，并断言输出、状态、持久化、异常、日志或边界调用。禁止 import-only、self-fulfilling expected value、mock 被测主体、扩大 coverage 排除、无依据删代码或降低阈值。

对 marker/dead code 的处理必须有消费方搜索与上游追踪证据；删除属于独立代码变更评审，不由覆盖率百分比单独授权。

## 实施阶段交付物

1. 与源码路径对应的单元测试；
2. 全绿 pytest 输出、coverage JSON/HTML；
3. 逐文件阈值检查器及其自身测试；
4. CI workflow；
5. FR/AC → test 映射；
6. 如有豁免，更新 `coverage-waivers.json` 与 follow-up issue。
