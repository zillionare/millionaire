# Millionaire Coverage — Story

## 0. 背景与目标

v0.2-001 与 v0.2-002 建立在一批更早开发的模块之上。这些模块已有代码和部分单元测试，却没有独立、完整的 story/spec/acceptance。v0.2-003 的目标不是让当前实现自动成为规范，而是从已锁定的上游需求反推出这些模块必须提供的输入、输出、状态变化和失败语义，再用单元测试保护这些契约，使 v0.2 可以在整体行覆盖率 ≥95% 的门禁下发布。

契约来源按以下优先级解释：

1. v0.2-001 / v0.2-002 的 spec 与 acceptance；
2. 两个上游 spec 的 `interfaces.md`；
3. 两个上游 story；
4. 当前公开实现与已有测试，只用于补充上游没有规定、但已被上游消费方依赖的细节。

如果当前实现或旧测试与 1~3 冲突，应把它记录为代码/测试缺陷，不能把冲突行为写进 v0.2-003 使其合法化。如果某段代码既没有上游需求、没有消费方，也没有可观察行为，则不能为了覆盖率虚构接口；应提供 dead-code 证据后另行决定删除、实现或临时豁免。

## 1. 测试基础设施与发布口径

作为开发者，我需要一个唯一、可复现的单元测试入口，使测试失败与覆盖率不足都能阻断发布。

- 规范命令以 `tests/unit` 为测试集合，以 `quantide` 为 coverage source。
- 覆盖率口径为 statement/line coverage：整体 ≥95%。
- “单模块”指 coverage JSON 中每个含至少 1 条可执行语句的生产 `.py` 文件；每个单模块 ≥80%。
- 单模块门禁必须解析 `coverage.json` 逐文件判断，不能用包级 `--cov-fail-under=80` 冒充逐文件检查。
- 空文件或 0-statement 文件不进入分母，也不需要豁免；含 import/re-export 语句的 `__init__.py` 仍是普通生产模块。
- pytest 配置集中在 `pyproject.toml`；共享 fixture 放在 `tests/unit/conftest.py` 或必要的就近 `conftest.py`。
- 测试只能 mock 网络、时钟、文件系统、数据库、进程和下游端口等边界，不能 mock 被测主体。
- 每个测试必须隔离用户 HOME、配置数据库、运行时状态、开发网关替身和环境变量，不读取或改写开发者真实配置。

## 2. quantide/core/ 契约测试

作为开发者，我需要核心端口、运行时装配、策略生命周期和消息分发的单元测试与上游契约一致。

### 2.1 领域事件与端口

- `core/domain/events.py`：验证事件 dataclass 的必填字段、默认字段、字段保真和每实例独立的可变默认值；不假设不存在的 `to_dict/from_dict` API。
- `core/ports/broker.py`：验证 `OrderRequest`、view/ack/result 数据结构，以及 BrokerPort 的 submit/buy/sell/cancel/query 契约。
- `core/ports/clock.py`：验证 `now/set_now/iter_frames` 端口可被虚拟时钟替换。
- `core/ports/data_fetcher.py`：验证 calendar/stock/adjust/bars/limit/ST/bars_ext 七类数据获取签名和返回形状。
- `core/ports/market_data.py`：验证 start/stop、symbols 批量订阅、异步 `MarketEvent` 流和 `QuoteSnapshot` 快照。

### 2.2 运行时

- `clock_bridge.py`：系统时钟不可被设置；回测时钟可注入并把 frame 迭代委托给交易日历。
- `gateway_client.py`：登录只执行一次，GET/POST 返回 JSON 或空体；HTML/未知 content type 作为协议错误；cookie 与 ws/wss URL 转换可观察。
- `gateway_broker.py`：交易/查询在 qmt-gateway HTTP payload 与 BrokerPort DTO 之间正确转换，并保护订单标识一致性。
- `modes.py`：它是运行时装配器，不是模式状态机。验证 mode 解析、时钟注入、行情/经纪人注册和数据库账户加载隔离。
- `port_broker.py`：它是 BrokerPort 到旧 broker/UI 模型的兼容适配器，不是端口注册表。验证资产/持仓/委托转换、交易方法透传和未知枚举映射。

### 2.3 策略、发现、调度与消息

- `strategy.py`：验证 Strategy/BaseStrategy/RiskStrategy 的公开生命周期和交易/数据委托符合 001-FR-010/013/115/125；不创造“重复初始化状态机”。
- `strategy_discovery.py`：验证非递归扫描、合法子类识别、元数据 schema、损坏/重复/越界文件的 skipped 结果。
- `scheduler.py`：验证惰性初始化、幂等 start/stop、`add_job` 与 `add_listener` 透传；不要求不存在的 remove/list API。
- `message.py`：验证 pub/sub、无订阅者时 pull queue、取消订阅、订阅者异常隔离、队列满策略和 stop；它不是编解码协议。
- `sdk_metadata.py`：验证 001-FR-014/015 的 CalendarSDK 与 SecurityListSDK 输入输出。
- `enums.py`、`errors.py` 及其它 core 辅助模块：验证公开枚举值、转换、异常字段和上游引用的 DTO/规则。

## 3. quantide/data/ 契约测试

作为开发者，我需要历史数据、参考数据和研究工具的单元测试保护 001-FR-270~330、FR-480、FR-484。

### 3.1 数据获取

- `fetchers/tushare.py`：在 mock Tushare SDK 边界下验证交易日历、证券列表、复权、日线、涨跌停、ST 与扩展日线的标准列、日期边界、分批错误收集和空结果。
- `fetchers/registry.py`：验证名称注册、默认项、覆盖规则、获取与列举；不假设类级 `register/resolve` API。

### 3.2 数据模型与存储

- `models/calendar.py`、`stocks.py`、`daily_bars.py`、`app_state.py`：各自按真实公开 API 测试，不能统一假设所有模型都有 `from_dict/to_dict`。
- `models/index_bars.py`：仅是 `IndexBars.SCHEMA` marker；验证字段与类型，不虚构构造、查询或序列化方法。
- `stores/base.py`：验证 Parquet 分区写入、日期范围/列选择、空 store、进度与错误收集。
- `stores/index_bars.py`：验证本地 Parquet 查询、symbols/date/eager 过滤和按日计数；主体中的远程指数抓取已退休，`fetch` 必须明确失败。
- `sqlite.py`：验证 001 interfaces 中 portfolio/asset/position/order/trade/log schema 的读写、更新、过滤和级联删除，使用隔离临时数据库。

### 3.3 研究工具

- `helper.py`：验证前/后复权和按时间顺序的 train/valid/test 切分，输出类型与输入类型一致。
- `utils/resampler.py`：验证周/月 OHLCV 聚合、空输入、非法频率和移动平均。

## 4. quantide/service/ 契约测试

作为开发者，我需要服务层单测保护上游策略调度、撮合、行情和评估规则。

- `strategy_runtime.py`：验证回测 runtime 创建/完成/移除，paper/live 部署、start/stop/block/unblock、持久化恢复和对外 summary/row。
- `discovery.py`：这是策略加载服务，不是网络服务发现。验证内置/用户目录优先级、缓存、扫描、元数据、示例复制和错误隔离。
- `registry.py`：验证 BrokerRegistry 按 `(kind, portfolio_id)` 注册、注销、查询、列举和默认账户。
- `runner.py`：验证 BacktestRunner 的日期对齐、回调时序、RiskStrategy 拒绝和清理。
- `abstract_broker.py`、`backtest_broker.py`、`sim_broker.py`：验证 BrokerPort DTO、001-FR-140~220 的价格/数量/T+1/停牌/资金规则，以及回测全成或拒绝、paper 部分成交生命周期。
- `datafeed.py`：验证 pull-style `BarsFeed` 的历史/形成中 bar 合并、列标准化、价格/涨跌停/复权查询；不虚构订阅者或重连接口。
- `livequote.py`：验证 websocket payload 解析、缓存、start/stop、subscribe/unsubscribe、stream/snapshot 与格式错误隔离。
- 其它服务：按各自真实公开接口验证回测日志、网格搜索、init-wizard、指标、闪电交易配置 CRUD/参考价、Triple Barrier。

## 5. quantide/web/ 契约测试

作为开发者，我需要在不启动真实浏览器或外部服务的情况下，通过 FastHTML 节点、HTTP response、redirect、session 和 service 边界断言 v0.2-002。

- `web/components/analysis/`：K 线节点/JS 更新契约、频率与 MA 控件、股票列表和空状态；颜色规则以 002-NFR-0040 为准，不引入不存在的组件内搜索/排序 API。
- 通用 components/layouts/theme：验证导航、告警、toast、运行参数、资产标签、主布局和语义样式。
- `web/pages/`：按 002 interfaces §2 的路由、表单输入、页面/fragment 输出、局部降级和动作边界进行测试。
- `web/auth/`：按 002-FR-0110~0140 验证单管理员登录、登出、改密、session 和 redirect。旧的注册/忘记密码/admin 多用户代码不因存在而成为 v0.2 产品需求。
- `web/apis/`：按 001 interfaces 与 002 interfaces 验证 status code、redirect、JSON/HTML fragment、ErrorEnvelope 和 payload schema。
- middleware/degradation/events/local_storage/NFR helpers：验证初始化、认证、A/B 降级、异常转换、PushEvent、允许的 localStorage key 和 002 NFR。
- `web/services/`：已有高覆盖模块仍需作为 002 业务规则的纯函数/DTO 合同保留，不得通过删测让整体覆盖率达标。

## 6. notify、strategies、config 与启动装配

- `notify/mail.py`、`notify/dingtalk.py`：按 001-FR-481 验证 MIME/payload、配置、签名、成功与失败可观察性，不发真实网络请求。
- `notify/__init__.py`：该模块实际承载 001-FR-485 的证券代码和市场规则 helper，不是通知通道工厂；测试按代码转换、涨跌停和开盘时间差契约编写。
- `strategies/`：按 001-FR-090/100/110/115/125 验证默认参数、上穿/下穿、n 分钟回落窗口、成本止损、可卖持仓与宿主账户归属。
- `config/`、`app.py`、`app_factory.py`：验证配置覆盖、路径隔离、初始化分流、单实例检查、依赖装配、route/middleware 注册；单测必须向 `create_app(app_config_dir=tmp_path, enforce_single_instance=False)` 提供隔离目录。

## 7. CI/CD 与质量门禁

作为维护者，我需要 GitHub Actions 在 push/PR 上运行完整单元测试与覆盖率门禁，并上传可审查报告。

- 单元测试有任何 failure/error 时立即失败，覆盖率数字不能掩盖红测。
- 整体行覆盖率 <95% 时失败。
- 任一非豁免生产文件 <80% 时失败；检查器解析 `coverage.json`。
- HTML/JSON 报告作为 artifact 上传；报告上传即使使用 `if: always()`，也不能让主门禁变绿。
- 增量覆盖率 ≥95% 可作为非阻断增强项，不能替代整体和逐文件门禁。

## 8. 反作弊与测试质量

- 每个低覆盖模块至少有一个正常路径和一个失败或边界路径。
- 只 import、只断言常量存在或 mock 被测主体的用例不算有效行为测试。
- 禁止扩大 omit/exclude、批量增加 `pragma: no cover`、降低阈值或删除有效代码来提高百分比。
- 每个测试文件至少引用一个上游 FR/AC 或 v0.2-003 FR/AC。
- 临时豁免必须有模块、当前覆盖率、理由、到期日和 follow-up issue；空文件不是豁免项。

## 9. 排除项

- 真实 qmt-gateway、Tushare、SMTP、钉钉/微信连通性；
- 浏览器 E2E、视觉回归和性能测试；
- 001/002 未定义的新业务规则、新 UI 或新通知渠道；
- 为无消费者的占位代码虚构产品接口。
