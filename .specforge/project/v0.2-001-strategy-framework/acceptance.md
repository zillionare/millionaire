# 验收标准 — v0.2-001-strategy-framework

- **Spec ID**: v0.2-001-strategy-framework
- **创建日期**: 2026-06-15
- **状态**: v0.2 内审中(已对齐 spec + 4 文档同步;spec 已拆 3 分册)
- **对应 spec**: [spec.md](./spec.md) (含索引, 跳转 spec-strategy.md / spec-trading.md / spec-foundation.md)

> **编号规则**: AC-{FR/NFR编号}-{序号}。每条 AC 对应 spec 中一个 FR 或 NFR 的一个可判定场景。
> 标记约定: ⬜ 待确认 | ❌ 需回退修改 spec
> FR 编号不变: 跨分册拆分后, 编号仍指原 FR(FR-011/012 在 v0.2-001 修订中删除, 不写 AC)

---

## 功能验收标准

### FR-010 策略对象模型与 SDK 暴露

#### AC-010-01 策略类型分层可被识别
- ⬜ 用户编写一个继承 `BaseStrategy`（独立策略）或 `RiskStrategy`（风控策略）并实现 `default_config()` 的类 → 框架扫描后识别为合法策略
- ⬜ 直接继承 `Strategy` 抽象根的类 → 不被识别为可调度策略（`Strategy` 为抽象根，用户不直接继承）
- ⬜ 未继承 `Strategy` / `BaseStrategy` / `RiskStrategy` 的类 → 不被识别为策略

#### AC-010-02 生命周期钩子按顺序触发
- ⬜ 一次完整运行的调用顺序为：`init()` → `on_start()` → [`on_day_open()` → … → `on_day_close()`] × D 天 → `on_stop()`
- ⬜ `init()` / `on_start()` / `on_stop()` 各只调用一次
- ⬜ `on_day_open()` / `on_day_close()` 每个交易日各调用一次
- ⬜ `init`/`on_start`/`on_stop`/`on_day_open`/`on_day_close` 在 `Strategy` 抽象根定义（两个基类均继承）
- ⬜ `on_bar(tm)` 在 `BaseStrategy` 专有定义（独立策略决策入口）
- ⬜ `on_check(positions, tm)` 在 `RiskStrategy` 专有定义（风控策略事件入口）

#### AC-010-03 辅助接口可用
- ⬜ 策略覆盖 `default_config()` 返回 `{"fast": 5, "slow": 20}` → 框架扫描时读取参数列表与默认值
- ⬜ 策略未覆盖 `default_config()` → 默认返回 `{}`，框架识别为无参数策略
- ⬜ 策略调用日志接口 → 输出日志，时间戳默认为仿真时间而非系统时间
- ⬜ 策略调用指标记录接口 → 数据可在后续分析/可视化中使用
- ⬜ `get_bars(asset, count, end_dt=None, frame_type="1d", include_forming_bar=True) → pl.DataFrame` 在 `Strategy` 抽象根定义（两个基类均可用）
- ⬜ 策略调用 `get_bars(frame_type="1d")` → 4 模式可用（回测/仿真/实盘/dry-run）
- ⬜ 策略调用 `get_bars(frame_type="30m")` → 回测模式下抛 `UnsupportedFrameTypeForBacktest`；paper/live 正常返回 30m 数据
- ⬜ 独立策略（`BaseStrategy` 子类）调用 `get_prices` / `get_ticks` → 类层**不存在**该方法（继承结构保证，非运行时拦截）
- ⬜ 风控策略（`RiskStrategy` 子类）调用 `get_prices(assets)` → 返回 `dict[str, float]`
- ⬜ 风控策略（`RiskStrategy` 子类）调用 `get_ticks(asset, count)` → 返回 `pl.DataFrame`

#### AC-010-04 同一策略代码跨模式运行
- ⬜ 同一份 `BaseStrategy` 子类代码可分别在回测、仿真、实盘、dry-run 四种模式下成功运行完整生命周期（on_day_open → on_bar → on_day_close），无需任何代码修改
- ⬜ 策略可达对象（Strategy、BaseStrategy、RiskStrategy、Context、Broker）上不存在任何返回当前运行模式的方法（如 get_mode、is_backtest）

### FR-013 RiskStrategy 结构契约（风控策略）

> **不可回测**：v0.2 不支持 RiskStrategy 回测。仅 paper/live 下验证。

#### AC-013-01 风控策略无独立账户
- ⬜ 风控策略不创建 `portfolio_id`，不持有资金
- ⬜ 风控策略**类层不存在** `positions` / `cash`（继承结构保证——`RiskStrategy` 继承 `Strategy` 而非 `BaseStrategy`）

#### AC-013-02 只能卖出不能买入
- ⬜ 风控策略可调用 `sell_host_position` → 订单写入宿主 `portfolio_id`，资金从宿主扣减
- ⬜ 风控策略**类层不存在** `buy` / `buy_amount` / `buy_percent` / `sell`（除 `sell_host_position` 外）等买入/卖自己持仓的接口（继承结构保证，非运行时拦截）

#### AC-013-03 只读访问宿主持仓
- ⬜ 风控策略可查看宿主的持仓快照（通过 `on_check(positions, ...)` 接收） → 只读，不可修改
- ⬜ 风控策略**类层不存在** `positions`（属 BaseStrategy 专有）——通过 `on_check` 参数间接获得宿主持仓

#### AC-013-04 tick 级数据接口可用（风控专有, 仅 paper/live）
- ⬜ 风控策略调用 `get_ticks` → paper/live 返回真实 tick 级行情数据
- ⬜ 风控策略调用 `get_prices` → paper/live 返回当前价格
- ⬜ **类层不存在** `get_prices` / `get_ticks` 于 `BaseStrategy`（独立策略拿不到这些方法）

#### AC-013-05 宿主生命周期绑定 + 不可回测
- ⬜ 宿主进入 paper/live → 关联的 RiskStrategy 自动激活
- ⬜ 宿主停止 → RiskStrategy 一并停止
- ⬜ 单独停止 RiskStrategy → 不再监控，已发订单不撤回；重新启动后开启新"开启区间"，超额收益按区间独立累计
- ⬜ 尝试不带宿主账户直接启动 RiskStrategy → 抛出异常，提示必须绑定宿主
- ⬜ 将 RiskStrategy 实例提交给 BacktestRunner → BacktestRunner 启动时检测到 RiskStrategy 子类, **拒绝启动**(抛异常 `RiskStrategyNotBacktestable`;HTTP 错误码见 [interfaces.md §4 `RISK_STRATEGY_NOT_BACKTESTABLE`](./interfaces.md))

---

### FR-014 SDK 元数据接口 — 交易日历

#### AC-014-01 交易日判断
- ⬜ 传入一个已知的交易日 → 返回 true
- ⬜ 传入一个周末 → 返回 false
- ⬜ 传入一个法定节假日 → 返回 false
- ⬜ 传入超出数据范围的日期 → 抛出异常

#### AC-014-02 交易日移位
- ⬜ 从一个交易日向后移 1 天 → 返回下一个交易日(跨周末自动跳过)
- ⬜ 从一个交易日向前移 1 天 → 返回上一个交易日
- ⬜ 移位偏移量为 0(无论当日是否为交易日)→ 返回最近已结束的交易日
- ⬜ 移位结果超出数据范围 → 抛出异常

#### AC-014-03 交易日计数与列表
- ⬜ 查询一个跨越周末的区间 → 返回的交易日数不含周末和节假日
- ⬜ start == end 且为交易日 → 返回 1
- ⬜ start == end 且为非交易日 → 返回 0
- ⬜ 查询某月所有交易日 → 结果中不含非交易日, 按日期升序排列
- ⬜ start > end → 抛出异常

#### AC-014-04 模式无关性
- ⬜ 回测中调用日历接口 → 返回基于仿真时间范围的正确结果
- ⬜ paper/live 中调用日历接口 → 返回基于真实日历的正确结果
- ⬜ 相同接口、相同参数、不同模式 → 行为一致

#### AC-014-05 最近已结束交易日
- ⬜ 在回测中调用 `last_trade_date()` → 返回基于仿真时间的"最近一个已结束的交易日"(≤ 当前仿真时间)
- ⬜ 在 paper/live 中调用 `last_trade_date()` → 返回真实日历的"最近一个已结束的交易日"(≤ 当前真实时间,且 ≤ 数据范围)
- ⬜ 仿真/实盘时间早于数据范围起点 → 抛出异常(无交易日可返回)
- ⬜ `last_trade_date()` 与 `day_shift(some_date, 0)` 语义一致(都返回"最近一个已结束的交易日")

---

### FR-015 SDK 元数据接口 — 证券列表

#### AC-015-01 已上市证券列表
- ⬜ 查询某日已上市证券 → 不包含该日尚未上市的证券
- ⬜ 查询某日已上市证券 → 不包含该日已退市的证券
- ⬜ 使用 exclude_st=True → 结果中不含 ST 股票
- ⬜ 使用 exclude_st=False → 结果中包含 ST 股票

#### AC-015-02 ST 判断与上市天数
- ⬜ 传入一个已知的 ST 股票和对应日期 → 返回 true
- ⬜ 传入一个非 ST 股票 → 返回 false
- ⬜ 传入一个已上市多年的股票 → 返回正确的上市天数
- ⬜ 传入一个尚未上市的日期 → 返回 0
- ⬜ 传入无效证券代码 → 抛出异常

#### AC-015-03 证券名称查询
- ⬜ 传入一个有效证券代码 → 返回该证券名称
- ⬜ 传入无效证券代码 → 抛出异常

#### AC-015-04 模式无关性
- ⬜ 回测 / paper / live 中调用同一接口 → 接口相同、行为一致

---

### FR-020 自动发现策略

> **范围说明**:本节仅覆盖**枚举契约**(识别规则、元数据 schema、模式无关性、容错、安全前提)。
> 内置 vs 用户策略的展示优先级/排序/过滤/搜索等 UI 行为见 [v0.2-002-ui/spec.md](../v0.2-002-ui/spec.md) UI-FR-010 的 acceptance。

#### AC-020-01 识别规则 — 基类判定

- ✅ 用户目录中存在一个继承 `BaseStrategy` 的具体类 → 该类出现在枚举结果中,`strategy_type == "independent"`
- ✅ 用户目录中存在一个继承 `RiskStrategy` 的具体类 → 出现在枚举结果中,`strategy_type == "risk"`
- ✅ 枚举结果中存在一个直接继承 `BaseStrategy`(非三层细分) 的具体类 → 该类出现在枚举结果中,`strategy_type == "independent"`(由最终基类推导,非"MRO 最近具体子类")
- ✅ 枚举结果中存在一个类 `Strategy` 自身 → **不出现**(抽象根,被排除)
- ✅ 枚举结果中存在一个类 `BaseStrategy` 自身 → **不出现**(基类是抽象类,被排除)
- ✅ 枚举结果中存在一个类 `RiskStrategy` 自身 → **不出现**(基类是抽象类,被排除)

#### AC-020-02 识别规则 — 文件范围

- ✅ 目录中存在 `.py` 文件 → 扫描该文件
- ✅ 目录中存在非 `.py` 文件(如 `.txt`、`.md`) → 跳过,不记录错误
- ✅ 目录中存在子目录 → **不递归**(子目录被忽略)
- ✅ 目录中存在 `__pycache__/` → 跳过其中 `.pyc` 文件(不记录错误)

#### AC-020-03 识别规则 — 名称与描述

- ✅ 策略类未定义 `__display_name__` → 元数据 `name = cls.__name__`
- ✅ 策略类定义 `__display_name__` 为非空字符串 → 元数据 `name = __display_name__` 的值(优先级高于 `__name__`)
- ✅ 策略类 docstring 存在 → 元数据 `description = docstring 首行`(strip 后)
- ✅ 策略类无 docstring → 元数据 `description = ""`(空串,非 None)
- ✅ 策略类 docstring 为空(`""`)或仅空白 → 元数据 `description = ""`

#### AC-020-04 元数据 schema — 核心字段

| 字段              | AC                                                                                                                                                                                      |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `strategy_id`     | ✅ `strategy_id == f"{cls.__module__}.{cls.__name__}"`;同一进程内两不同类的 `strategy_id` 不冲突                                                                                         |
| `strategy_type`   | ✅ `strategy_type ∈ {"independent", "risk"}`;BaseStrategy 子类 → `"independent"`;RiskStrategy 子类 → `"risk"`(由最终基类推导)                                                            |
| `module`          | ✅ `module == cls.__module__`                                                                                                                                                            |
| `is_builtin`      | ✅ 当类定义在 Millionaire 框架包内(`quantide.*` 或文档约定的根包名)→ `is_builtin=True`;否则 `False`;判定规则在 acceptance 级别定义为"基于 import 路径前缀",**不依赖运行时 monkey-patch** |
| `skipped_reasons` | ✅ 仅未通过识别条件的**非 BaseStrategy / 非 RiskStrategy 类**携带;通过的策略 `skipped_reasons=[]`                                                                                       |

#### AC-020-05 元数据 schema — `default_config` 转 `ParamSpec`

- ✅ `default_config()` 返回 `{"fast": 5, "slow": 20}` → 元数据 `default_config["fast"]` 是 `ParamSpec`,其 `name="fast"`, `default=5`,其余字段为 `None`
- ✅ `default_config()` 返回 `{}` → 元数据 `default_config == {}`(空 dict)
- ✅ `default_config()` 未定义(子类未覆盖) → 元数据 `default_config == {}`(**不抛异常**)
- ✅ 同一策略类的两次枚举 → `default_config` 内容**稳定一致**(不随时间漂移)

#### AC-020-06 元数据 schema — `ParamSpec` 字段契约(v0.2 范围)

- ✅ `ParamSpec.name` 必填,且等于 `default_config` dict 的 key
- ✅ `ParamSpec.default` 必填,值与 `default_config` dict 的 value **类型一致**(`bool` 不变 `int`)
- ✅ `ParamSpec.type_hint` v0.2 始终为 `None`(底层 dict schema 升级前不消费)
- ✅ `ParamSpec.description` v0.2 始终为 `None`(同上)
- ✅ `ParamSpec.constraints` v0.2 始终为 `None`(同上)

#### AC-020-07 模式无关性

- ✅ 同一策略根目录 + 同一用户代码,在**回测** 模式下调用枚举 → 与在**仿真** 模式下结果**完全一致**(集合相等)
- ✅ 同一条件在**实盘** 模式下结果**完全一致**
- ✅ 同一条件在**dry-run** 模式下结果**完全一致**
- ✅ 枚举结果中**不包含**运行时参数字段(`initial_capital` / `slippage` / `commission` / `tax_rate` / `min_commission` 均不在 schema 内)

#### AC-020-08 容错 — 目录问题

| 场景                         | 期望行为                                                       |
| ---------------------------- | -------------------------------------------------------------- |
| ✅ 目录不存在                 | 枚举返回空列表;不抛异常;记录日志 INFO 级别"策略目录未配置"     |
| ✅ 目录权限不足(无 read 权限) | 枚举返回空列表;记录日志 WARNING 级别;原因 = `PermissionDenied` |
| ✅ 目录存在但为空             | 枚举返回空列表;无错误日志                                      |

#### AC-020-09 容错 — 单文件失败

| 场景                                                              | 期望行为                                                          |
| ----------------------------------------------------------------- | ----------------------------------------------------------------- |
| ✅ `.py` 文件语法错(`SyntaxError`)                                 | 该文件被跳过;不影响其它文件;原因 = `SyntaxError`(含文件名 + 行号) |
| ✅ `.py` 文件 `import` 失败(`ImportError` / `ModuleNotFoundError`) | 该文件被跳过;不影响其它文件;原因 = `ImportError`(不传播到调用方)  |
| ✅ `.py` 文件运行时初始化抛异常(如模块级 `1/0`)                    | 该文件被跳过;不影响其它文件;原因 = `ModuleInitError`              |

#### AC-020-10 容错 — 类级失败

| 场景                                                       | 期望行为                                                    |
| ---------------------------------------------------------- | ----------------------------------------------------------- |
| ✅ 类既不是 `BaseStrategy` 子类,也不是 `RiskStrategy` 子类    | 该类不进入策略列表;原因 = `NotAStrategy`                    |
| ✅ 类是 `BaseStrategy` 子类但 `default_config()` 调用抛异常 | 该类不进入策略列表;原因 = `InvalidConfig`                   |
| ✅ 多个类共享同一 `strategy_id`(同名模块 + 同名类)          | **全部保留**在策略列表中(枚举不去重);展示层优先级见 UI spec |

#### AC-020-11 容错 — 内置 vs 用户冲突

- ✅ 用户目录中存在一个类,其 `strategy_id` 与某内置策略的 `strategy_id` 相同 → **两版本都出现在枚举结果中**(`is_builtin` 分别标记);展示层优先级见 UI-FR-010
- ✅ 上述场景发生时,枚举结果中携带一条 `BuiltinOverridden` 诊断信息(可在诊断接口查询);**枚举本身不报错**

#### AC-020-12 容错 — 整体不阻塞

- ✅ 目录中存在 N 个文件,其中 M 个失败(M < N) → 枚举返回 N-M 个有效策略 + M 条 `skipped_reasons`;**调用方收到完整结果,不抛异常**
- ✅ 目录中**所有**文件都失败 → 枚举返回空策略列表 + N 条 `skipped_reasons`;**调用方收到完整结果,不抛异常**

#### AC-020-13 安全前提(声明性,非可执行)

- ✅ 文档/README/帮助文本中明确声明:"策略根目录中的代码由用户全权负责,框架不执行沙箱隔离"
- ⚠️ 此 AC 为**契约声明**,无运行时断言

#### AC-020-14 排除项(确认不在范围内)

- ✅ 枚举结果**不验证**策略的业务逻辑正确性(回测正确性由 FR-115 / FR-125 acceptance 负责)
- ✅ 枚举结果**不执行**回测运行(运行由调度器负责)
- ✅ 枚举结果**不验证**策略参数的类型/范围(运行时校验由 FR-200 负责)
- ✅ 枚举结果**不发起**远程网络请求(仅本地 `.py` 文件)

#### AC-020-15 联动接口契约

- ✅ 枚举调用方的契约:接收 `Path | str | None`(None 表示未配置)→ 返回 `EnumerationResult`
- ✅ `EnumerationResult` 含两个字段:`strategies: list[StrategyMetadata]`(通过的策略) + `diagnostics: list[SkippedEntry]`(失败的文件/类及原因)
- ✅ `SkippedEntry` 含字段:`path: str`(文件路径)、`class_name: str | None`(类名,文件级失败时为 None)、`reason: SkippedReason`、`detail: str`(原因详情,如异常消息)

---

### FR-030 策略参数跨模式透传

> 策略参数跨模式透传契约见 [spec-strategy.md §FR-030](./spec-strategy.md)

#### AC-030-01 回测参数透传到仿真/实盘/dry-run
- ⬜ 回测启动时 `fast=5, slow=20` → 切到 paper 模式时,这俩参数仍是 5, 20
- ⬜ 切到 live 模式时,仍是 5, 20
- ⬜ 切到 dry-run 模式时,仍是 5, 20

#### AC-030-02 仿真/实盘/dry-run 禁止单独修改策略参数
- ⬜ 切到 paper 模式后,框架不暴露修改 `fast` / `slow` 的入口(无 setter / 无 API / 无 UI 字段)
- ⬜ 切到 live / dry-run 同上
- ⬜ 如果用户绕过框架直接改 `default_config()` 返回值,后果自负(此 AC 是框架契约,不是用户行为约束)

---

### FR-040 一次开发四模式无感迁移

> 四模式无感迁移契约见 [spec-strategy.md §FR-040](./spec-strategy.md)

#### AC-040-01 同一代码在四模式跑通
- ⬜ 同一 `BaseStrategy` 子类,在 backtest / paper / live / dry-run 四模式下分别跑一天,均**无异常**完成
- ⬜ 四模式产出的 `positions` 表记录**等价**(同一时点、同一价格、同一撮合规则下,持仓结构一致)
- ⬜ 跨模式切换不需重启策略实例(同一 `strategy_id` 实例可被复用)

#### AC-040-02 策略不可感知运行模式
- ⬜ 策略代码内调 `self.get_mode()` 抛 `AttributeError`(基类不暴露)
- ⬜ 调 `self.is_backtest()` / `self.is_paper()` / `self.is_live()` / `self.is_dry_run()` 同上
- ⬜ 策略代码内 inspect `runtime` / `mode` 等属性(通过 `self.context.mode` 之类),值是 None 或抛错(无 mode 探测入口)
- ⬜ 4 模式的 `on_bar(tm)` / `on_day_open(tm)` 行为**完全一致**(参数语义、调用时序、返回值)

---

### FR-090 内置策略 — 双均线（日线策略）

> 双均线契约见 [spec-strategy.md §FR-090](./spec-strategy.md)

#### AC-090-01 默认参数 fast=5, slow=20
- ⬜ 策略类未传参数时, 框架自动用 `[5, 20]` 初始化
- ⬜ 验证依据: `quantide/strategies/dual_ma.py` 的 `default_config()` 返回 `{"fast": 5, "slow": 20}`

#### AC-090-02 fast 上穿 slow 触发买入
- ⬜ T-1 收盘: MA5 < MA20, T 收盘: MA5 > MA20 → 策略在 T 日 `on_bar` 产生买入信号
- ⬜ 验证依据: 回测跑 1 年, 验证上穿点对应的 `orders` 表 `side=buy` 且 `filled > 0`

#### AC-090-03 slow 上穿 fast 触发卖出
- ⬜ T-1 收盘: MA5 > MA20, T 收盘: MA5 < MA20 → 策略在 T 日 `on_bar` 产生卖出信号
- ⬜ 验证依据: 回测跑 1 年, 验证下穿点对应的 `orders` 表 `side=sell` 且 `filled > 0`

#### AC-090-04 回测结果含净值/买卖点/MA 指标
- ⬜ 回测完成产出 [interfaces.md §4.1 回测结果 JSON](./interfaces.md), 含 `nav_curve` (净值序列) + `trades` (买卖点) + 8 项评估指标
- ⬜ MA 指标由 UI 渲染层根据 `trades` + `nav_curve` 计算, 框架不内置 MA 渲染
- ⬜ 验证依据: 跑一次 2022 年双均线回测, 断言 §4.1 JSON 含 `nav_curve[0].date` 是起始日, `trades` 至少有 1 笔

---

### FR-100 内置策略 — 回落卖出（风控）

> 回落卖出契约见 [spec-strategy.md §FR-100](./spec-strategy.md)

#### AC-100-01 默认参数 m=7.0, k=0.5, n=1
- ⬜ 策略类未传参数时, 框架自动用 `[m=7.0, k=0.5, n=1]` 初始化
- ⬜ 验证依据: `quantide/strategies/drawback_sell.py` 的 `default_config()` 返回 `{"m": 7.0, "k": 0.5, "n": 1}`

#### AC-100-02 个股当天上涨至 m% 后 n 分钟内下跌超 k% 立即卖出
- ⬜ T 日 10:00 标的从开盘 10.00 涨至 10.70 (m=7.0%), 10:01 跌至 10.65 (0.5% 内下跌超 k=0.5%) → `on_check` 触发 `sell_host_position`
- ⬜ 验证依据: `risk_events` 表 [interfaces.md §4.9](./interfaces.md) 新增一条 `reason=drawback`, 订单 `side=sell`

#### AC-100-03 tick 级数据驱动 (FR-125 on_check)
- ⬜ 回落卖出**不**在 `on_bar` 触发, 而在 `on_check(positions, tm)` 触发 (每 tick 一次)
- ⬜ 验证依据: 跑 paper E2E, 注入 tick 序列 (10:00 涨 / 10:01 跌), 断言 `on_check` 被调用 1 次, 卖出单在 10:01 提交

---

### FR-110 内置策略 — 成本止损（风控）

> 成本止损契约见 [spec-strategy.md §FR-110](./spec-strategy.md); cost_basis 来自 [spec-strategy.md §FR-185 经典方案 A](./spec-strategy.md) (P1 已解)

#### AC-110-01 默认参数 k=-5.0
- ⬜ 策略类未传参数时, 框架自动用 `k=-5.0` (跌破买入价 5% 触发) 初始化
- ⬜ 验证依据: `quantide/strategies/cost_stop.py` 的 `default_config()` 返回 `{"k": -5.0}`

#### AC-110-02 触发条件 last_price <= cost_basis × (1 + k/100)
- ⬜ 持仓 `cost_basis=10.00, k=-5.0` → `last_price <= 10.00 × (1 + (-5.0)/100) = 9.50` 时触发
- ⬜ last_price=9.49 (≤ 9.50) 触发; last_price=9.51 (> 9.50) **不**触发
- ⬜ 验证依据: 跑 paper E2E, 推进虚拟时钟让 last_price 跌到 9.49, 断言 `sell_host_position` 被调用; 推进到 9.51 时**不**调用

#### AC-110-03 触发后清仓该标的可卖持仓 (受 T+1 约束)
- ⬜ 持仓 `avail=1000, in_transit=200` (T+0 买入 200 在 T+1 才能卖) → 触发后清仓 1000 股, 200 在途不动
- ⬜ 验证依据: `risk_events.asset_shares=1000`, 订单 `shares=1000`, T+1 后 `avail=200` (在途变可卖)

#### AC-110-04 卖出走 sell_host_position 归属宿主
- ⬜ 触发时, 框架调 `sell_host_position(asset, shares, reason="cost_stop")` 而非风控自身账户
- ⬜ 验证依据: 订单 `portfolio_id = host_strategy.portfolio_id` (宿主, 不是风控), `fills.qtoid` 的 owner 链指向宿主

---

### FR-115 BaseStrategy 驱动契约

> 驱动契约见 [spec-strategy.md §FR-115](./spec-strategy.md)

#### AC-115-01 回调时序 (单日)
- ⬜ 一个交易日按 `on_day_open(tm=T 09:30) → on_bar(tm=T) → on_day_close(tm=T 15:00)` 顺序驱动
- ⬜ 验证依据: 跑 paper E2E 一天, 断言 3 个回调按顺序触发, 且 `tm` 字段为对应时刻

#### AC-115-02 frame_type="1d" 在 4 模式均可用
- ⬜ 策略调 `get_bars(asset, count, frame_type="1d")` 在 backtest/paper/live/dry-run 均返回 `pl.DataFrame` (≥ 1 行)
- ⬜ 验证依据: 跑 4 模式各 1 天, 断言 4 次调用都成功

#### AC-115-03 frame_type="30m" 仅 paper/live 可用, 回测抛异常
- ⬜ paper/live 调 `get_bars(asset, count, frame_type="30m")` → 成功
- ⬜ backtest 调同样接口 → 抛 `UnsupportedFrameTypeForBacktest` (HTTP 错误码 `UNSUPPORTED_FRAME_TYPE_FOR_BACKTEST`)
- ⬜ 验证依据: 跑 1 次回测调用, 断言异常; 跑 1 次 paper 调用, 断言成功

#### AC-115-04 on_bar 不携带 quote 参数, 策略通过 get_bars 拉取
- ⬜ 策略 `on_bar(tm)` 方法签名**只有** `tm` 参数 (无 `quote` / `bars` / 等行情参数)
- ⬜ 验证依据: 策略基类 `BaseStrategy.on_bar` 反射签名, 断言只有 `self` + `tm` 2 个参数

#### AC-115-05 paper/live 默认 15:05 触发 (盘后 5 分钟)
- ⬜ paper/live 下 `on_bar` 在 T 日 15:05 触发 (默认配置, 可配)
- ⬜ 验证依据: 跑 paper E2E 一天, 断言 `on_bar.tm.hour == 15 and on_bar.tm.minute == 5`

#### AC-115-06 信号与撮合解耦 (FR-050/060/070 决定撮合)
- ⬜ 策略在 `on_bar` 调 `buy(...)` 仅产生**信号**; 实际撮合时点与价格由下单方式决定
- ⬜ 验证依据: cheat-on-close 模式下, `on_bar` 在 15:05 触发, 订单 `tm` 在 14:57 (FR-050 撮合时点); 次日开盘模式下, 订单 `tm` 在 T+1 09:30

---

### FR-140 交易规则 — 价格（涨跌停）

> 涨跌停契约见 [spec-trading.md §FR-140](./spec-trading.md); 验证通过 [interfaces.md §4.17 limit_price.up_limit / down_limit](./interfaces.md)

#### AC-140-01 限价买单超出 up_limit 被拒
- ⬜ 标的当前 `up_limit = 11.00`,框架收到 `buy(asset, shares=100, price=11.01)` → 下单**被拒**,`orders.status = rejected`,`status_msg` 包含"price > up_limit"语义
- ⬜ 验证依据: `orders` 表新增记录但 `filled = 0` 且 `status = rejected`

#### AC-140-02 限价卖单低于 down_limit 被拒
- ⬜ 标的当前 `down_limit = 9.00`,框架收到 `sell(asset, shares=100, price=8.99)` → 下单**被拒**,`status = rejected`
- ⬜ 验证依据: `orders` 表新增记录但 `filled = 0` 且 `status = rejected`

#### AC-140-03 开盘即涨停的标的, 买单不撮合
- ⬜ T+0 09:30 标的以 `open == high == up_limit` 开盘 → 任何买单 (`buy` / `buy_percent` / `buy_amount`) **不撮合**,`orders.status = rejected`,`status_msg` 含"limit up"
- ⬜ 验证依据: `fills` 表**无**新记录; `positions` 表**无**买入变化

#### AC-140-04 开盘即跌停的标的, 卖单不撮合
- ⬜ T+0 09:30 标的以 `open == low == down_limit` 开盘 → 任何卖单 (`sell` / `sell_percent` / `sell_amount`) **不撮合**,`orders.status = rejected`,`status_msg` 含"limit down"
- ⬜ 验证依据: `fills` 表**无**新记录; `positions.shares` / `avail` 不变

#### AC-140-05 is_st=true 的标的, 框架不做下单限制
- ⬜ 标的 `is_st = true`, 涨跌幅按数据 ±5% → 限价单价格在 ±5% 边界**内**时正常撮合;**不**因 `is_st` 拒绝
- ⬜ 验证依据: `fills` 表按 ±5% 数据计算成交价; 框架**不**因 `is_st` 增加拒绝逻辑(策略自行决定是否过滤 ST)

---

### FR-150 交易规则 — 数量

> 数量契约见 [spec-trading.md §FR-150](./spec-trading.md)

#### AC-150-01 买入非整百股自动向下取整
- ⬜ 框架收到 `buy(asset, shares=250, price=10.00)` → 实际撮合 `shares=200`(250 向下取整到 100 整倍数)
- ⬜ 验证依据: `fills.shares = 200`, `orders.shares = 250`(委托数量, 撮合后 filled=200)

#### AC-150-02 买入不足 100 股下单失败
- ⬜ 框架收到 `buy(asset, shares=50, price=10.00)` → 50 向下取整为 0 → 下单**失败**,`orders.status = rejected`,`status_msg` 含"shares < 100 after floor"
- ⬜ 验证依据: `fills` 表**无**新记录

#### AC-150-03 清仓卖出不受 100 整倍数限制
- ⬜ 持仓 `shares=1000`, 框架收到 `sell(asset, shares=1000, ...)` → 正常撮合 1000 股
- ⬜ 验证依据: `fills.shares = 1000`, 卖出后 `positions.shares = 0` (清仓)

#### AC-150-04 零股卖出不受 100 整倍数限制
- ⬜ 持仓 `shares=150`, 框架收到 `sell(asset, shares=50, ...)` → 正常撮合 50 股(零股例外)
- ⬜ 验证依据: `fills.shares = 50`, 卖出后 `positions.shares = 100`

#### AC-150-05 回测订单要么全成要么作废
- ⬜ 回测模式下, 任何委托**不部分成交**: `orders.filled ∈ {0, orders.shares}`(全成或全废)
- ⬜ 验证依据: 跑一组混合订单的回测, 断言 `orders` 表的 `filled` 字段全部为 0 或等于 `shares`

---

### FR-160 交易规则 — 时间

> 时间契约见 [spec-trading.md §FR-160](./spec-trading.md); T+1 验证通过 [interfaces.md §4.4 positions.avail](./interfaces.md)

#### AC-160-01 T+1 约束 — 当日买入当日不可卖
- ⬜ T+0 09:35 买入 100 股 → T+0 14:55 调用 `positions(asset).avail` 返回 0
- ⬜ 验证依据: `positions.shares = 100, positions.avail = 0` (按 T+1 规则)

#### AC-160-02 T+1 约束 — 次日起可卖
- ⬜ T+0 09:35 买入 100 股, 推进虚拟时钟到 T+1 09:30 → `positions(asset).avail` 返回 100
- ⬜ 验证依据: 跨日后 `positions.avail = positions.shares = 100`

#### AC-160-03 非交易时段发单顺延
- ⬜ T+0 11:45 (午休时段) 框架收到买单 → 实际下单时间推迟到 T+0 13:00 (下午开盘)
- ⬜ 周末 / 节假日 (calendar.is_open = 0) 框架收到任何订单 → 顺延到下一交易日
- ⬜ 验证依据: `orders.tm` 字段反映顺延后的实际下单时间, 而非策略信号触发的原始时间

---

### FR-170 交易规则 — 特殊状态（停牌）

> 停牌契约见 [spec-trading.md §FR-170](./spec-trading.md)

#### AC-170-01 停牌标的不可下单
- ⬜ 标的 `volume = 0` (停牌) → 框架收到 `buy` / `sell` → 下单**被拒**,`status = rejected`,`status_msg` 含"suspended"
- ⬜ 验证依据: `orders.status = rejected`, `fills` 表**无**新记录

#### AC-170-02 持仓中停牌标的按停牌前最后收盘价估值
- ⬜ 持仓 `shares=100` 的标的在 T+0 14:00 进入停牌 → 估值用 `daily_bars.close` 在停牌前最后一日的值
- ⬜ 验证依据: `positions.price` (持仓成本, FR-185 维护) 不变; `assets.market_value = shares × daily_bars.close[最后非停牌日]`

---

### FR-180 交易规则 — 资金

> 资金契约见 [spec-trading.md §FR-180](./spec-trading.md); 资金校验通过 [interfaces.md §4.5 assets.cash / principal / frozen_cash](./interfaces.md)

#### AC-180-01 卖出回款当日可用于买入
- ⬜ T+0 09:35 卖出 1000 股 @ 10.00, T+0 14:00 买入 500 股 @ 10.00 → 资金即时可用, 不需等 T+1
- ⬜ 验证依据: T+0 14:00 资金校验 `assets.cash` 含卖出回款 (扣减佣金后), 足够覆盖买入 500 股 @ 10.00

#### AC-180-02 买入资金不足下单被拒
- ⬜ `assets.cash = 5000`, 框架收到 `buy(asset, shares=100, price=100.00)` (需 10000 + 佣金) → 下单**被拒**,`status = rejected`,`status_msg` 含"insufficient cash"
- ⬜ 验证依据: `assets.cash` 不变 (无扣减), `orders.status = rejected`

#### AC-180-03 印花税仅卖方收
- ⬜ 买入 100 股 @ 10.00 → `fills.amount = 1000`, 佣金扣减, **无**印花税扣减
- ⬜ 卖出 100 股 @ 10.00 → `fills.amount = 1000`, 佣金 + 印花税(按 FR-200 配置比率) 扣减
- ⬜ 验证依据: 跑一组买卖对, 断言 `assets.cash` 扣减差额 = 佣金(双方) + 印花税(仅卖方)

#### AC-180-04 佣金按 FR-200 配置比率 + 单笔最低佣金保底
- ⬜ 佣金率 = 0.025% (FR-200 配置), 单笔最低 = 5.00 元
- ⬜ 买入 100 股 @ 1.00 (成交额 100) → 理论佣金 0.025 元 < 5.00 → 实际扣 5.00
- ⬜ 买入 1000 股 @ 100.00 (成交额 100000) → 理论佣金 25.00 > 5.00 → 实际扣 25.00
- ⬜ 验证依据: `fills.fee` 字段 (interfaces §4.3 trades.fee) 反映保底后金额

---

### FR-190 交易规则 — 回测 vs 实盘差异

> 跨模式差异契约见 [spec-trading.md §FR-190](./spec-trading.md); 与 [spec-strategy.md §FR-080 跨模式回测-实盘差异](./spec-strategy.md) 合并覆盖

#### AC-190-01 回测模式下框架仿真所有规则
- ⬜ 回测时 FR-140~180 全部由框架实施 (涨跌停/数量/T+1/停牌/资金)
- ⬜ 验证依据: 跑一组故意违反规则的订单, 断言回测行为与 spec 描述完全一致(全部被拒 / 全部约束)

#### AC-190-02 仿真/实盘框架只做预校验
- ⬜ paper/live 时, 框架**不**仿真涨跌停/数量/T+1(由交易所/柜台强制); 仅在下单前做明显错误预校验(限价超 [low, high] 拒绝, 资金不足拒绝)
- ⬜ 验证依据: paper 模式跑同一组订单, 行为应**几乎**与回测一致(涨跌停/数量/停牌靠柜台, 不靠框架), 但限价/资金预校验仍由框架做

---

### FR-360 评估指标 — 风控策略

> 评估仅在 paper/live 下进行(v0.2 不支持 RiskStrategy 回测)。

#### AC-360-01 评估维度齐全
- ⬜ 每次风控触发卖出后,系统记录一条触发事件 `event_id`,字段含 `risk_strategy_id` / `host_strategy_id` / `asset` / `trigger_ts` / `trigger_price` / `reason`(`sell_host_position` 的 `reason` 参数)
- ⬜ 每条事件计算 Triple Barrier 超额收益 `excess_return`(公式详见 [spec-trading.md F-TB-1 / F-TB-2 / F-TB-3](./spec-trading.md)),`finalized_at = trigger_ts + n 日`;`n` 来自风控策略的 `default_config()`(策略作者在风控策略类中声明,默认 0 = 当日收盘)
- ⬜ 触发次数统计按 `risk_strategy_id` 聚合
- ⬜ 触发原因分布按 `reason` 字段分组计数

#### AC-360-02 按开启区间切分
- ⬜ 风控被激活时分配新 `activation_id`(UUID)
- ⬜ 同一 `activation_id` 内的所有 `excess_return` 求和,作为该区间的总贡献
- ⬜ 风控被"单独停止" → 当前 `activation_id` 立即关闭;已发订单不撤回
- ⬜ 风控重新启动 → 分配**新** `activation_id`,新事件归新区间
- ⬜ 不同 `activation_id` 的 `excess_return` **不合并**(每个区间独立)

#### AC-360-03 N 日窗口回填
- ⬜ `n = 0` 时,`excess_return` 在 `trigger_ts` 当日(仿真/实盘时间)的收盘价已知后立即计算并写入
- ⬜ `n > 0` 时,`excess_return` 初始写入 `null`,N 日后(仿真/实盘时间)有收盘价时回填
- ⬜ N 日窗口内数据不足(如接近年末、尚未有 N 日收盘数据)→ 暂记 `null`,数据可用后更新最终值

---

### FR-130 风控策略契约

> 风控策略契约见 [spec-strategy.md §FR-130](./spec-strategy.md); 账户/不可回测/不可独立启动 已在 AC-013 段, 本节只补 AC-013 外的 3 条新行为

#### AC-130-01 BacktestRunner 启动时检测到 RiskStrategy 拒绝
- ⬜ 启动回测任务时, 若传入的策略类型是 `RiskStrategy` (或子类), BacktestRunner 抛 `RiskStrategyNotBacktestable` 异常
- ⬜ HTTP 入口返回 `code=RISK_STRATEGY_NOT_BACKTESTABLE, status=409` (参见 [interfaces.md §5 异常错误码表](./interfaces.md))
- ⬜ 验证依据: 跑 1 次 `BacktestRunner.run(strategy=RiskStrategy_instance)` → 断言异常; 跑 1 次 HTTP POST 启动 → 断言 409

#### AC-130-02 重新启动记新 activation_id (按开启区间独立累计)
- ⬜ 风控首次启动 → 分配 `activation_id=uuid1`, 触发事件归 `activation_id=uuid1`
- ⬜ 风控被"单独停止" → 当前 `activation_id=uuid1` 关闭, 已发订单**不**撤回
- ⬜ 风控重新启动 → 分配**新** `activation_id=uuid2` (新事件归 `uuid2`, **不**与 `uuid1` 合并)
- ⬜ 验证依据: [interfaces.md §4.9 risk_events.activation_id](./interfaces.md) 字段在重新启动后是新的 UUID

#### AC-130-03 操作他人持仓不改变持仓归属
- ⬜ 风控触发 `sell_host_position(asset, shares, reason)` → 订单的 `portfolio_id` = **宿主** `portfolio_id`, **不**是风控自身
- ⬜ 宿主 `assets.cash` 在成交后被扣减 (回款归宿主, 风控无账户), 风控**无** `assets` 表记录
- ⬜ 验证依据: 跑 paper E2E, 触发后查 `orders.portfolio_id` 等于宿主, 查 `assets.portfolio_id` 不含风控

---

### FR-125 风控策略驱动契约

> **不可回测**：v0.2 不支持 RiskStrategy 回测。FR-125 全部 AC 在 paper/live 下验证。

#### AC-125-01 tick 级独立驱动（paper/live）
- ⬜ 风控策略的 `on_check` 由 tick 触发，与宿主的 `on_bar` 周期无关
- ⬜ 宿主为日线策略（一天一次 `on_bar`）时，风控仍为 tick 级监控
- ⬜ 宿主为实时策略（30m `on_bar`）时，风控同样为 tick 级监控

#### AC-125-02 持仓快照在 on_day_open 确定
- ⬜ `on_day_open` 时读取前一日可卖持仓（受 T+1 约束）
- ⬜ 当日买入的持仓不在可卖持仓快照中
- ⬜ 持仓快照在日内不变（宿主当日卖出也不改变风控的快照）

#### AC-125-03 监控列表管理
- ⬜ 风控触发卖出某标的 → 该标的从监控列表移除，当日不再重复触发
- ⬜ 宿主主动卖出某标的 → 该标的也从风控监控列表移除
- ⬜ 被移除的标的仍纳入超额收益统计

#### AC-125-04 即时市价成交
- ⬜ 风控调用 `sell_host_position` → 即时市价成交，不延迟到次日开盘
- ⬜ 标的当日跌停 → 卖单提交但无法成交，不阻塞后续标的的风控监控

#### AC-125-05 超额收益事件记录
- ⬜ 每次风控触发卖出后,系统记录一条 `excess_return` 事件,字段含 `sell_price` / `close_price_n` / `n_window` / `excess_return` / `activation_id` / `is_final`(字段定义见 [interfaces.md §3.7](./interfaces.md))
- ⬜ Triple Barrier 公式按 [spec-trading.md F-TB-1 / F-TB-2 / F-TB-3](./spec-trading.md) 计算:`up` 触发应用 F-TB-1,`down` 触发应用 F-TB-2,未触发应用 F-TB-3;N=0 即当日收盘
- ⬜ N=0: 当日收盘价已知后立即计算并写入,`is_final = true`
- ⬜ N>0: 初始记 `null`,N 日后(仿真/实盘时间)有收盘价时回填;`is_final` 在回填时设为 `true`;数据不足时暂记 `null` 可用后更新（详见 FR-360 AC-360-03）

---

## 运行时可注入性验收 (NFR-060 联动)

> **范围**: 本节 AC 验证 [spec-foundation.md NFR-060](./spec-foundation.md) 的运行时可注入契约, 是 [test-plan.md §5](./test-plan.md) L1/L2 E2E 测试的前置条件。
> **关联 test-plan 章节**: §5.4.1 (虚拟时钟), §5.4.5 (装配器), §5.4.6 (可测试性回退)
> **FR 编号决策**: 本节不绑定单一 FR, 而是为 NFR-060 提供可判定场景。编号 AC-CLOCK-INJ-N (N=01~06)。

### AC-CLOCK-INJ-01 RuntimeContext 暴露 clock 字段
- ⬜ `RuntimeContext` 实例具有公开属性 `clock: ClockPort` (类型注解存在, 可读)
- ⬜ 默认注入的 `clock` 是 `SystemClockAdapter` (生产语义: 返回墙钟)
- ⬜ 测试侧可构造 `RuntimeContext(clock=VirtualClock())` 替换为测试时钟, **不**抛异常

### AC-CLOCK-INJ-02 RuntimeBootstrap 接线
- ⬜ `RuntimeBootstrap.bootstrap()` 返回的 `RuntimeContext` 实例的 `clock` 字段非 None
- ⬜ 未显式传入 clock 时, `context.clock` 是 `SystemClockAdapter` 实例 (生产默认)
- ⬜ 显式传入 `RuntimeBootstrap(clock=...)` 时, `context.clock` 是传入的实例 (测试注入)

### AC-CLOCK-INJ-03 paper/live 运行时读 context.clock
- ⬜ 构造一个 `StrategyRuntime` 在 paper 模式下运行一个空策略一天
- ⬜ 在运行前 `set_now(T0)` 到一个测试时刻 T0
- ⬜ 策略的 `on_day_open(tm)` 收到的 `tm` 等于 T0 (而非墙钟)
- ⬜ 类似地, `on_day_close` / `on_bar` 收到的 `tm` 与 `context.clock.now()` 一致

### AC-CLOCK-INJ-04 行情时间戳读 context.clock
- ⬜ 构造一个 `LiveQuoteMarketDataAdapter` 注入测试时钟
- ⬜ 调用 `start()` + `subscribe([asset])` + 模拟推送一次行情
- ⬜ 行情事件 (从 msg_hub / stream 消费) 的时间戳 == `context.clock.now()`, 而非墙钟

### AC-CLOCK-INJ-05 虚拟时钟下 T+1 跨日结算可观测
- ⬜ 测试场景: T0 买入 → T0 当日 sellable=0; 推进虚拟时钟到 T1 → T1 当日 sellable=持仓数
- ⬜ 断言依据: [interfaces.md §4.4 positions 表](./interfaces.md) 的 `avail` 字段
- ⬜ 框架**不**需要知道这是测试场景; 走的是生产 T+1 结算代码路径

### AC-CLOCK-INJ-06 装配点违规检测 (反测试)
- ⬜ 扫描 `quantide/service/strategy_runtime.py` 与 `quantide/core/runtime/market_bridge.py`, **不应**出现 `datetime.datetime.now()` 调用 (排除注释/字符串)
- ⬜ 扫描 `quantide/service/sim_broker.py` 的 `PaperBroker._now()` 与 `quantide/core/runtime/gateway_broker.py` 的 `GatewayBrokerAdapter._now()`, **不应**出现 `datetime.datetime.now()` 兜底分支
- ⬜ 此 AC 由 CI 自动扫描保证 (PR2 在 pyproject.toml 或 CI workflow 中加 grep 规则)

---

## 可观测性契约引用

本文件中每条 AC 的验证,需通过 [spec-foundation.md NFR-050](./spec-foundation.md) 定义的可观测点(结构化日志 / 数据存盘文件 / 数据库表 / Web API)完成。完整的观测点清单见 [test-plan.md §3.1](./test-plan.md)。

凡 AC 涉及的内部状态,实现层**必须**提供对应可观测出口;此为 PR 评审的强制 checklist。
