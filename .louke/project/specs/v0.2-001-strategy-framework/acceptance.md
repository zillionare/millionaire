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

<a id="fr-010"></a>
<a id="ac-fr-010"></a>
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

<a id="fr-013"></a>
<a id="ac-fr-013"></a>
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
- ⬜ 将 RiskStrategy 实例提交给 BacktestRunner → BacktestRunner 启动时检测到 RiskStrategy 子类, **拒绝启动**(抛异常 `RiskStrategyNotBacktestable`;HTTP 错误码见 [interfaces.md §5 `RISK_STRATEGY_NOT_BACKTESTABLE`](./interfaces.md))

---

<a id="fr-014"></a>
<a id="ac-fr-014"></a>
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

<a id="fr-015"></a>
<a id="ac-fr-015"></a>
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

<a id="fr-020"></a>
<a id="ac-fr-020"></a>
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

<a id="fr-030"></a>
<a id="ac-fr-030"></a>
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

<a id="fr-040"></a>
<a id="ac-fr-040"></a>
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

<a id="fr-090"></a>
<a id="ac-fr-090"></a>
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

<a id="fr-100"></a>
<a id="ac-fr-100"></a>
### FR-100 内置策略 — 回落卖出（风控）

> 回落卖出契约见 [spec-strategy.md §FR-100](./spec-strategy.md)

#### AC-100-01 默认参数 m=7.0, k=0.5, n=1
- ⬜ 策略类未传参数时, 框架自动用 `[m=7.0, k=0.5, n=1]` 初始化
- ⬜ 验证依据: `quantide/strategies/pullback_sell.py` 的 `default_config()` 返回 `{"m": 7.0, "k": 0.5, "n": 1}`

#### AC-100-02 个股当天上涨至 m% 后 n 分钟内下跌超 k% 立即卖出
- ⬜ T 日 10:00 标的从开盘 10.00 涨至 10.70 (m=7.0%), 10:01 跌至 10.65 (0.5% 内下跌超 k=0.5%) → `on_check` 触发 `sell_host_position`
- ⬜ 验证依据: [interfaces.md §6 日志条目类型](./interfaces.md) 发出 `risk.triggered` event, payload 含 `reason="drawback"`, 订单 `side=sell`

#### AC-100-03 tick 级数据驱动 (FR-125 on_check)
- ⬜ 回落卖出**不**在 `on_bar` 触发, 而在 `on_check(positions, tm)` 触发 (每 tick 一次)
- ⬜ 验证依据: 跑 paper E2E, 注入 tick 序列 (10:00 涨 / 10:01 跌), 断言 `on_check` 被调用 1 次, 卖出单在 10:01 提交

---

<a id="fr-110"></a>
<a id="ac-fr-110"></a>
### FR-110 内置策略 — 成本止损（风控）

> 成本止损契约见 [spec-strategy.md §FR-110](./spec-strategy.md); cost_basis 来自 [spec-strategy.md §FR-185 经典方案 A](./spec-strategy.md) (P1 已解)

#### AC-110-01 默认参数 k=-5.0
- ⬜ 策略类未传参数时, 框架自动用 `k=-5.0` (跌破买入价 5% 触发) 初始化
- ⬜ 验证依据: `quantide/strategies/cost_stop_loss.py` 的 `default_config()` 返回 `{"k": -5.0}`

#### AC-110-02 触发条件 last_price <= cost_basis × (1 + k/100)
- ⬜ 持仓 `cost_basis=10.00, k=-5.0` → `last_price <= 10.00 × (1 + (-5.0)/100) = 9.50` 时触发
- ⬜ last_price=9.49 (≤ 9.50) 触发; last_price=9.51 (> 9.50) **不**触发
- ⬜ 验证依据: 跑 paper E2E, 推进虚拟时钟让 last_price 跌到 9.49, 断言 `sell_host_position` 被调用; 推进到 9.51 时**不**调用

#### AC-110-03 触发后清仓该标的可卖持仓 (受 T+1 约束)
- ⬜ 持仓 `avail=1000, in_transit=200` (T+0 买入 200 在 T+1 才能卖) → 触发后清仓 1000 股, 200 在途不动
- ⬜ 验证依据: 订单 `shares=1000` (清仓可卖, 不动在途), 订单表正确归宿主; [interfaces.md §6](./interfaces.md) `risk.triggered` event 含 `asset=该标的` + `reason="cost_stop"`; T+1 后 `avail=200` (在途变可卖)

#### AC-110-04 卖出走 sell_host_position 归属宿主
- ⬜ 触发时, 框架调 `sell_host_position(asset, shares, reason="cost_stop")` 而非风控自身账户
- ⬜ 验证依据: 订单 `portfolio_id = host_strategy.portfolio_id` (宿主, 不是风控), `fills.qtoid` 的 owner 链指向宿主

---

<a id="fr-115"></a>
<a id="ac-fr-115"></a>
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

<a id="fr-140"></a>
<a id="ac-fr-140"></a>
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

<a id="fr-150"></a>
<a id="ac-fr-150"></a>
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

<a id="fr-160"></a>
<a id="ac-fr-160"></a>
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

<a id="fr-170"></a>
<a id="ac-fr-170"></a>
### FR-170 交易规则 — 特殊状态（停牌）

> 停牌契约见 [spec-trading.md §FR-170](./spec-trading.md)

#### AC-170-01 停牌标的不可下单
- ⬜ 标的 `volume = 0` (停牌) → 框架收到 `buy` / `sell` → 下单**被拒**,`status = rejected`,`status_msg` 含"suspended"
- ⬜ 验证依据: `orders.status = rejected`, `fills` 表**无**新记录

#### AC-170-02 持仓中停牌标的按停牌前最后收盘价估值
- ⬜ 持仓 `shares=100` 的标的在 T+0 14:00 进入停牌 → 估值用 `daily_bars.close` 在停牌前最后一日的值
- ⬜ 验证依据: `positions.price` (持仓成本, FR-185 维护) 不变; `assets.market_value = shares × daily_bars.close[最后非停牌日]`

---

<a id="fr-180"></a>
<a id="ac-fr-180"></a>
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

<a id="fr-190"></a>
<a id="ac-fr-190"></a>
### FR-190 交易规则 — 回测 vs 实盘差异

> 跨模式差异契约见 [spec-trading.md §FR-190](./spec-trading.md); 与 [spec-strategy.md §FR-080 跨模式回测-实盘差异](./spec-strategy.md) 合并覆盖

#### AC-190-01 回测模式下框架仿真所有规则
- ⬜ 回测时 FR-140~180 全部由框架实施 (涨跌停/数量/T+1/停牌/资金)
- ⬜ 验证依据: 跑一组故意违反规则的订单, 断言回测行为与 spec 描述完全一致(全部被拒 / 全部约束)

#### AC-190-02 仿真/实盘框架只做预校验
- ⬜ paper/live 时, 框架**不**仿真涨跌停/数量/T+1(由交易所/柜台强制); 仅在下单前做明显错误预校验(限价超 [low, high] 拒绝, 资金不足拒绝)
- ⬜ 验证依据: paper 模式跑同一组订单, 行为应**几乎**与回测一致(涨跌停/数量/停牌靠柜台, 不靠框架), 但限价/资金预校验仍由框架做

---

<a id="fr-360"></a>
<a id="ac-fr-360"></a>
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

<a id="fr-130"></a>
<a id="ac-fr-130"></a>
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
- ⬜ 验证依据: [interfaces.md §6 日志条目类型](./interfaces.md) 的 `risk.triggered` event payload `activation_id` 字段在重新启动后是新的 UUID

#### AC-130-03 操作他人持仓不改变持仓归属
- ⬜ 风控触发 `sell_host_position(asset, shares, reason)` → 订单的 `portfolio_id` = **宿主** `portfolio_id`, **不**是风控自身
- ⬜ 宿主 `assets.cash` 在成交后被扣减 (回款归宿主, 风控无账户), 风控**无** `assets` 表记录
- ⬜ 验证依据: 跑 paper E2E, 触发后查 `orders.portfolio_id` 等于宿主, 查 `assets.portfolio_id` 不含风控

---

<a id="fr-125"></a>
<a id="ac-fr-125"></a>
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
- ⬜ 每次风控触发卖出后,系统记录一条 `excess_return` 事件,字段含 `sell_price` / `close_price_n` / `n_window` / `excess_return` / `activation_id` / `is_final`(字段定义见 [interfaces.md §4.10](./interfaces.md) excess_returns 表 PR3 目标 schema; v0.2 验证依据为 [interfaces.md §6](./interfaces.md) `risk.excess_return.finalized` event payload)
- ⬜ Triple Barrier 公式按 [spec-trading.md F-TB-1 / F-TB-2 / F-TB-3](./spec-trading.md) 计算:`up` 触发应用 F-TB-1,`down` 触发应用 F-TB-2,未触发应用 F-TB-3;N=0 即当日收盘
- ⬜ N=0: 当日收盘价已知后立即计算并写入,`is_final = true`
- ⬜ N>0: 初始记 `null`,N 日后(仿真/实盘时间)有收盘价时回填;`is_final` 在回填时设为 `true`;数据不足时暂记 `null` 可用后更新（详见 FR-360 AC-360-03）

---

<a id="fr-200"></a>
<a id="ac-fr-200"></a>
### FR-200 运行时参数（框架管理，策略不可见）

> 运行时参数契约见 [spec-strategy.md §FR-200](./spec-strategy.md); 本金存储见 [interfaces.md §4.5 assets.principal](./interfaces.md)

#### AC-200-01 三类运行时参数 (本金/滑点/手续费) 在 4 模式均存在
- ⬜ 启动回测/paper/live/dry-run 时, 用户必须显式提供 `initial_capital` / `slippage` / `commission` 三类参数
- ⬜ 验证依据: 4 模式各跑 1 次启动, 断言配置接口要求这三类参数, 缺则报错

#### AC-200-02 策略代码不可见运行时参数
- ⬜ `BaseStrategy` / `RiskStrategy` 不暴露 `get_initial_capital()` / `get_slippage()` / `get_commission()` / `get_tax_rate()` 等 API
- ⬜ 验证依据: 反射策略基类, 断言无上述方法名

#### AC-200-03 切换模式允许重设, 不被回测结果锁定
- ⬜ 回测 A 跑完后, 用户能在仿真/实盘启动时改 `initial_capital` / `slippage` / `commission` (即不被回测结果锁定)
- ⬜ 验证依据: 跑一次回测后, 改 `initial_capital` 启动 paper → 启动成功, paper 的 `assets.principal` = 新值

#### AC-200-04 本金持久化到 assets.principal
- ⬜ 回测/仿真/实盘启动时, 用户设的 `initial_capital` 写入 `assets.principal` ([interfaces.md §4.5](./interfaces.md))
- ⬜ 验证依据: 跑 1 次 paper, 设 `initial_capital=1000000`, 断言 `assets.principal = 1000000` 在 T 日落库

---

<a id="fr-210"></a>
<a id="ac-fr-210"></a>
### FR-210 虚拟账本（按 qtoid 归因）

> 虚拟账本契约见 [spec-trading.md §FR-210](./spec-trading.md); 存储见 [interfaces.md §4.5 assets / §4.4 positions / §4.2 orders / §4.3 trades](./interfaces.md)

#### AC-210-01 每个独立策略有独立虚拟账户
- ⬜ 同一 base strategy class 实例化 2 次 (不同 `strategy_id`), 在 live/paper 各起一个 → 2 个 `portfolio_id` 各有独立 `assets` 表
- ⬜ 验证依据: 跑 paper E2E, 2 个策略实例 → `assets` 表 2 条记录, 各自 `cash` / `principal` 独立

#### AC-210-02 跨虚拟账户资金分配由用户自保证
- ⬜ Millionaire **不**做跨策略的 `assets.principal` 总和 ≤ 真实账户可用资金的校验
- ⬜ 验证依据: 设 2 个策略 `principal=1000000` 总和 2000000, 真实账户只有 1500000 → 启动不报错 (用户自负责)

#### AC-210-03 策略级数据按 portfolio_id 隔离
- ⬜ `orders` / `trades` / `positions` / `assets` 全部表/文件的 `portfolio_id` 字段与策略实例一一对应, 不串
- ⬜ 验证依据: 跑 2 个策略实例各起 paper, 跑 1 天 → 断言 `orders.portfolio_id` 仅出现在该策略对应的记录里, 跨策略查询为空

---

<a id="fr-220"></a>
<a id="ac-fr-220"></a>
### FR-220 手工交易/补单/风控卖出的归属

> 手工/补单/风控卖出归属契约见 [spec-trading.md §FR-220](./spec-trading.md); 归属字段见 [interfaces.md §4.2 orders.portfolio_id](./interfaces.md)

#### AC-220-01 手工交易/补单/风控卖出必须归属到独立策略账户
- ⬜ 手工交易 UI 提交时, 用户必须选目标策略 (宿主); 提交后订单的 `portfolio_id` = 该宿主
- ⬜ 补单 (手动补) 同上: 必须关联到某个独立策略
- ⬜ 风控卖出由 FR-110 触发的 `sell_host_position` 自动归属宿主 (已在 AC-110-04 覆盖)
- ⬜ 验证依据: 跑 1 次手工交易, 选策略 X → 断言 `orders.portfolio_id = X.portfolio_id`

#### AC-220-02 写入该策略的虚拟账本
- ⬜ 归属到独立策略账户的订单, 成交后写入该策略的 `assets` / `positions` (按 `portfolio_id` 关联, 见 AC-210-03)
- ⬜ 验证依据: 跑 1 次手工交易 + 1 次补单, 成交后查 `assets.cash` 和 `positions` 表, 都按 `portfolio_id` 隔离

---

<a id="fr-230"></a>
<a id="ac-fr-230"></a>
### FR-230 独立策略的回测启动路径

> 回测启动路径契约见 [spec-strategy.md §FR-230](./spec-strategy.md)

#### AC-230-01 必须从回测开始, 才能进入仿真/实盘
- ⬜ 独立策略 (数据粒度可回测) 未跑过回测, 直接尝试进 paper → 报错 (`STRATEGY_NOT_BACKTESTED` 或类似)
- ⬜ 验证依据: 1 次"绕回测直接 paper" 调用, 断言报错

#### AC-230-02 路径 1 (顺序) 回测 → 仿真 → 实盘
- ⬜ 跑完回测 A, 进 paper B (用 A 的参数), 再从 paper B 进 live C → 3 个运行记录, 共享参数 `fast=5, slow=20`
- ⬜ 验证依据: 跑 1 次顺序路径, 断言 live `principal` 来自 paper (paper 来自回测), 不要求用户重设参数

#### AC-230-03 路径 2 (直达) 回测 → 实盘
- ⬜ 跑完回测 A, 直接进 live B (跳过 paper) → live 用 A 的参数
- ⬜ 验证依据: 跑 1 次直达路径, 断言 live 用回测的 `fast=5, slow=20`, 不要求用户重设

#### AC-230-04 每个策略最多保留 30 个回测结果
- ⬜ 同一策略跑 31 次回测 → 第 31 次报错或自动清理第 1 次
- ⬜ 验证依据: 跑 31 次, 断言最后一次 fail, 或前 1 次被清理 (策略仍可访问 30 个)

---

<a id="fr-240"></a>
<a id="ac-fr-240"></a>
### FR-240 独立策略的无回测启动路径

> 无回测启动路径契约见 [spec-strategy.md §FR-240](./spec-strategy.md)

#### AC-240-01 适用场景: 独立策略用 live-only 数据粒度
- ⬜ 独立策略声明 `frame_type="30m"` 等 live-only 粒度 → 不需回测
- ⬜ 验证依据: 跑 1 次"30m 策略直接进 paper" 调用, 启动成功 (不要求先回测)

#### AC-240-02 路径: 仿真 → 实盘, 或直接启动实盘
- ⬜ 30m 策略可经路径 "paper → live" 或直接 "live" 启动
- ⬜ 验证依据: 跑 1 次 30m 策略 paper→live 顺序, 跑 1 次直接 live, 都成功

---

<a id="fr-250"></a>
<a id="ac-fr-250"></a>
### FR-250 风控策略调度

> 风控策略调度契约见 [spec-strategy.md §FR-250](./spec-strategy.md); AC-013-XX 已涵盖风控生命周期

#### AC-250-01 风控无独立调度, 跟随宿主自动激活
- ⬜ 宿主独立策略进 paper → 关联风控**自动**激活 (无需手动启动风控)
- ⬜ 宿主进 live → 风控自动激活; 宿主停止 → 风控停止
- ⬜ 验证依据: 跑 1 次宿主 + 风控组合启动, 断言风控在宿主 paper 启动时**自动**进 paper, 不需要单独调度

---

<a id="fr-260"></a>
<a id="ac-fr-260"></a>
### FR-260 调度 UI

> 调度 UI 已迁移到 [v0.2-002-ui/spec.md UI-FR-040](../v0.2-002-ui/spec.md); 行为规则在 001-FR-230/240/250

> **AC**: 无（UI 契约已迁移；本 FR 仅作引用占位）

---

<a id="fr-440"></a>
<a id="ac-fr-440"></a>
### FR-440 dry-run 模式

> dry-run 行为契约见 [spec-trading.md §FR-440](./spec-trading.md); UI 表现已迁移 [v0.2-002-ui/spec.md UI-FR-060](../v0.2-002-ui/spec.md)

#### AC-440-01 正在实盘的策略可进入 dry-run: 策略正常运行, 但不实际下单
- ⬜ 策略在 live 模式运行, 用户点"进入 dry-run" → 策略继续产生信号 (`on_bar` / `on_check` 仍触发), 但 `buy` / `sell` / `sell_host_position` 调**不**落 `orders` 表
- ⬜ 验证依据: 跑 1 次 live→dry-run 切换, 跑 1 天, 断言 `orders` 表**无**新记录 (dry-run 期间), 但 [interfaces.md §6](./interfaces.md) `risk.triggered` event 仍按触发条件发出

#### AC-440-02 dry-run 期间策略指标参考其并行仿真实例
- ⬜ dry-run 期间, 策略的评估指标 (净值/年化收益/Sharpe 等) **参考**其并行仿真实例, 而**不**直接算 dry-run 自身 (因 dry-run 无成交, 算不出指标)
- ⬜ 验证依据: 跑 1 次 live + 并行 paper 组合, 切到 dry-run, 断言指标 UI 显示的是 paper 数据, 不是 dry-run 的 (空) 数据

---

<a id="fr-450"></a>
<a id="ac-fr-450"></a>
### FR-450 消息通知（微信）— 事件定义

> 通知事件定义见 [spec-trading.md §FR-450](./spec-trading.md); 通知配置 UI 已迁移 [v0.2-002-ui/spec.md UI-FR-450](../v0.2-002-ui/spec.md)
>
> **本 FR 仅定义事件枚举** (5 个事件: 委托提交 / 成交 / 委托失败 / 成交失败 / 网关断开); 通知触发 / 发送 / 用户配置 UI 等行为 AC 已迁移到 [v0.2-002-ui/spec.md UI-FR-450](../v0.2-002-ui/spec.md).

#### AC-450-01 事件枚举与 NotificationEvent 映射 (v0.2 范围)
- ⬜ 5 个事件在 `quantide/core/notifications.py:NotificationEvent` 枚举中, 值与 spec §FR-450 表格一致
- ⬜ 验证依据: 5 个枚举常量存在 + 值 (snake_case strings)
- 行为 AC (通知触发 / 发送 / 配置 UI): 迁移到 [v0.2-002-ui/spec.md UI-FR-450](../v0.2-002-ui/spec.md)

---

<a id="fr-050"></a>
<a id="ac-fr-050"></a>
### FR-050 下单方式 — cheat-on-close

> 下单方式契约见 [spec-strategy.md §FR-050](./spec-strategy.md); 撮合 ground truth 见 [test-plan.md §3.2](./test-plan.md)。

#### AC-050-01 回测按 T+0 收盘价撮合
- ⬜ 回测中策略在 T+0 收盘价信号触发买入或卖出 → 订单以 T+0 `daily_bars.close` 作为成交价
- ⬜ 验证依据: 使用 test-plan §3.2 独立手算脚本读取同一日线数据, 断言 `trades.price == close[T]` 且成交记录写入 [interfaces.md §4.3 trades](./interfaces.md)

#### AC-050-02 paper/live 尾盘集合竞价前发单
- ⬜ paper/live 中选择 cheat-on-close, T+0 触发信号 → 系统在默认 14:57 或用户配置的尾盘执行时点提交委托
- ⬜ 验证依据: 结构化日志 `order.submitted` 或 [interfaces.md §4.2 orders](./interfaces.md) 的 `tm` 字段等于配置时点; 策略自身仍不感知运行模式

---

<a id="fr-060"></a>
<a id="ac-fr-060"></a>
### FR-060 下单方式 — 次日开盘（正常模式）

> 下单方式契约见 [spec-strategy.md §FR-060](./spec-strategy.md); 撮合 ground truth 见 [test-plan.md §3.2](./test-plan.md)。

#### AC-060-01 回测按 T+1 开盘价成交
- ⬜ 回测中 T+0 收盘信号产生订单 → T+1 以 `daily_bars.open` 成交
- ⬜ 验证依据: 独立手算脚本读取 T+1 open, 断言 [interfaces.md §4.3 trades](./interfaces.md) 的成交价等于 `open[T+1]`

#### AC-060-02 开盘涨跌停时不撮合
- ⬜ T+1 `open == up_limit` 时买单不成交; T+1 `open == down_limit` 时卖单不成交
- ⬜ 验证依据: [interfaces.md §4.2 orders](./interfaces.md) 状态为 rejected 或 filled=0, [interfaces.md §4.3 trades](./interfaces.md) 无对应成交记录

---

<a id="fr-070"></a>
<a id="ac-fr-070"></a>
### FR-070 下单方式 — 次日限价

> 下单方式契约见 [spec-strategy.md §FR-070](./spec-strategy.md); 撮合 ground truth 见 [test-plan.md §3.2](./test-plan.md)。

#### AC-070-01 回测限价落入 T+1 日内区间才成交
- ⬜ 回测中 T+0 收盘信号指定限价 `price` 且 `low[T+1] <= price <= high[T+1]` → 全部成交, 成交价为指定限价
- ⬜ `price < low[T+1]` 或 `price > high[T+1]` → 不成交
- ⬜ 验证依据: test-plan §3.2 手算脚本读取 T+1 `[low, high]`, 对比 [interfaces.md §4.2 orders](./interfaces.md) 与 [interfaces.md §4.3 trades](./interfaces.md)

#### AC-070-02 paper/live 次日集合竞价发出限价委托
- ⬜ paper/live 中选择次日限价, T+0 盘后信号产生订单 → T+1 开盘集合竞价发出限价委托, 委托价格等于策略信号指定价
- ⬜ 验证依据: [interfaces.md §4.2 orders](./interfaces.md) 的 `tm` 为 T+1 开盘时点, `price` 等于指定限价

---

<a id="fr-080"></a>
<a id="ac-fr-080"></a>
### FR-080 跨模式回测-实盘差异

> 跨模式差异契约见 [spec-strategy.md §FR-080](./spec-strategy.md) 与 [spec-trading.md §FR-190](./spec-trading.md); 三层测试策略见 [test-plan.md §6.3](./test-plan.md)。

#### AC-080-01 同一信号跨模式允许因撮合源不同产生差异
- ⬜ 同一策略、同一信号、同一下单方式在 backtest 与 paper/live 中运行 → 成交时点或成交结果可因历史日线撮合、仿真撮合、真实/假网关撮合不同而不同
- ⬜ 验证依据: 测试只断言各模式分别满足对应 FR-050/060/070/190 的外部契约, 不要求跨模式成交价/成交状态完全相等

#### AC-080-02 差异不得暴露给策略代码
- ⬜ 策略生命周期、参数、数据接口名称在四模式保持一致; 策略代码内不存在可读取当前运行模式的公开 API
- ⬜ 验证依据: 反射策略基类无 `get_mode` / `is_backtest` / `is_live` 等模式探测入口, 且 [interfaces.md §6](./interfaces.md) 生命周期日志字段语义一致

---

<a id="fr-185"></a>
<a id="ac-fr-185"></a>
### FR-185 持仓成本基准（加权均价算法 — 经典方案 A）

> 成本基准算法见 [spec-strategy.md §FR-185](./spec-strategy.md); 存储字段见 [interfaces.md §4.4 positions.price](./interfaces.md)。

#### AC-185-01 买入时按加权均价更新 cost_basis
- ⬜ 已有持仓 `old_qty > 0`, 再次买入 `buy_qty` → `positions.price = (old_qty × old_cost_basis + buy_qty × buy_price) / (old_qty + buy_qty)`
- ⬜ 首次建仓 (`old_qty == 0`) → `positions.price = buy_price`
- ⬜ 验证依据: 成交后查询 [interfaces.md §4.4 positions](./interfaces.md) 的 `price` 字段, 与 spec-strategy.md F-CB-1/F-CB-4 手算结果一致

#### AC-185-02 卖出时剩余持仓成本不变或清仓删除
- ⬜ 部分卖出 (`0 < sell_qty < old_qty`) → 剩余持仓 `positions.price` 保持卖出前成本不变
- ⬜ 全部卖出 (`sell_qty == old_qty`) → 删除该标的持仓记录或持仓数量为 0 且不再保留可用于风控触发的 cost_basis
- ⬜ 验证依据: 成交后查询 [interfaces.md §4.4 positions](./interfaces.md), 与 spec-strategy.md F-CB-2/F-CB-3 一致

---

<a id="fr-270"></a>
<a id="ac-fr-270"></a>
### FR-270 数据源 — 行情（tushare）

> 行情数据源契约见 [spec-trading.md §FR-270](./spec-trading.md); 测试数据字段契约见 [test-plan.md §2.4.1](./test-plan.md)。

#### AC-270-01 日线行情字段完整且按年分区存储
- ⬜ 同步个股或指数日线后, 本地 Parquet 至少包含 OHLCV、amount、adjust、is_st、up_limit、down_limit 中该资产类型适用的字段
- ⬜ 数据按年份分区或可按年份范围读取, 不要求保存 tick/分钟/30m 生产行情
- ⬜ 验证依据: 读取落盘 Parquet schema 与分区路径, 对比 spec-trading.md §FR-270 字段清单

#### AC-270-02 回测仅消费本地历史日线
- ⬜ 回测运行时读取本地 tushare 历史日线数据, 不发起网络行情请求
- ⬜ 验证依据: 回测日志/配置记录数据源为本地 Parquet; 测试环境断网时仍可读取 fixture 完成回测数据加载

---

<a id="fr-280"></a>
<a id="ac-fr-280"></a>
### FR-280 数据源 — 参考数据（tushare）

> 参考数据契约见 [spec-trading.md §FR-280](./spec-trading.md); SDK 元数据验收见 FR-014/FR-015。

#### AC-280-01 交易日历与证券列表可从 tushare 同步并落盘
- ⬜ 同步任务完成后, 本地参考数据包含交易日历、全市场证券代码/名称/拼音/上市退市日期、ST 标记
- ⬜ 验证依据: 读取本地参考数据文件或数据库表, 字段覆盖 spec-trading.md §FR-280 清单; SDK 查询结果与落盘数据一致

#### AC-280-02 参考数据作为 SDK 元数据单一真相源
- ⬜ `is_trade_day` / `stocks_listed` / `is_st` / `get_name` 等 SDK 查询结果来自已同步参考数据, 与 fixture parquet 直接查询一致
- ⬜ 验证依据: test-plan §3.6 ground truth 直接读取 parquet 与 SDK 输出逐项对比

---

<a id="fr-290"></a>
<a id="ac-fr-290"></a>
### FR-290 数据源 — 复权与涨跌停

> 复权与涨跌停契约见 [spec-trading.md §FR-290](./spec-trading.md); 涨跌停撮合验收见 FR-140。

#### AC-290-01 复权因子可用于前复权/后复权计算
- ⬜ 给定未复权 OHLC 与 adjust 因子 → 前复权/后复权输出与独立公式计算结果一致
- ⬜ 验证依据: 直接读取测试 fixture 中的 OHLC + adjust, 用 ground truth 脚本计算复权价格, 对比框架数据工具输出

#### AC-290-02 涨跌停价进入撮合判断
- ⬜ 日线数据存在 `up_limit` / `down_limit` 时, FR-140 限价与开盘涨跌停判断以数据字段为准, 不以内置百分比规则硬编码为准
- ⬜ 验证依据: 构造普通/ST/创科标的 fixture, 断言订单拒绝/成交行为与字段值一致

---

<a id="fr-300"></a>
<a id="ac-fr-300"></a>
### FR-300 数据源 — 实时行情（qmt-gateway）

> 实时行情契约见 [spec-trading.md §FR-300](./spec-trading.md); L2 网关契约测试见 [test-plan.md §6.3.2](./test-plan.md)。

#### AC-300-01 paper/live 通过 qmt-gateway 获取 tick 与分钟线
- ⬜ paper/live 模式启动实时行情后, 框架能通过 gateway 协议接收 tick 或分钟线事件, 并将其用于策略 `get_bars(frame_type="30m")` / 风控 `on_check`
- ⬜ 验证依据: L2 假网关推送行情后, [interfaces.md §6](./interfaces.md) 日志或行情流事件可观测到同一标的/时间戳/价格

#### AC-300-02 实时行情不作为生产历史数据落盘
- ⬜ tick/分钟/30m 实时行情仅用于 paper/live 当日运行; 生产数据同步不把它们写入历史行情库
- ⬜ 验证依据: 运行一次实时行情订阅后, 历史日线 Parquet/数据库无新增 tick/分钟/30m 生产历史分区

---

<a id="fr-310"></a>
<a id="ac-fr-310"></a>
### FR-310 数据同步任务

> 数据同步任务契约见 [spec-trading.md §FR-310](./spec-trading.md)。

#### AC-310-01 定时同步覆盖行情与参考数据
- ⬜ 定时同步任务可同步日线行情、证券列表、交易日历、ST、涨跌停历史数据
- ⬜ 验证依据: 执行同步任务后, 每类数据的落盘行数或更新时间出现在同步报告中, 且本地存储可查询到新增数据

#### AC-310-02 支持错过任务重跑与补录
- ⬜ 某个交易日同步失败或错过执行后, 用户可重新执行该日期或日期范围的数据同步
- ⬜ 验证依据: 删除或标记缺失某日数据后运行补录, 完成报告显示该日被补齐, 数据完整性校验通过

---

<a id="fr-320"></a>
<a id="ac-fr-320"></a>
### FR-320 数据完整性校验

> 数据完整性契约见 [spec-trading.md §FR-320](./spec-trading.md)。

#### AC-320-01 完整性报告覆盖缺日、重复日与字段空值率
- ⬜ 对已同步数据运行完整性校验 → 报告至少包含缺失交易日、重复交易日、关键字段空值率
- ⬜ 验证依据: 对 fixture 注入缺日/重复日/空值样本, 断言报告中对应问题类型和标的/日期可观测

#### AC-320-02 完整性校验可作为同步后验收门禁
- ⬜ 同步任务完成后可触发完整性校验; 校验失败时报告失败原因, 不把失败伪装为成功
- ⬜ 验证依据: 同步报告或结构化日志包含 `success=false` 与失败项列表

---

<a id="fr-330"></a>
<a id="ac-fr-330"></a>
### FR-330 数据查询支持

> 数据查询契约见 [spec-trading.md §FR-330](./spec-trading.md)。

#### AC-330-01 支持交易日历与证券信息查询
- ⬜ 用户可查询交易日历; 可按名称、数字代码或拼音模糊查询个股基本信息
- ⬜ 验证依据: 对固定 fixture 发起查询, 返回结果与 parquet/数据库 ground truth 一致, 且模糊查询覆盖名称/代码/拼音三类输入

#### AC-330-02 支持个股历史行情查询
- ⬜ 用户指定标的和日期范围 → 返回该标的历史 OHLCV 数据; K 线图绘制属于 UI spec, 本 FR 只验数据查询结果
- ⬜ 验证依据: 查询结果行数、日期范围、OHLCV 字段值与本地 Parquet 直接读取一致

---

<a id="fr-340"></a>
<a id="ac-fr-340"></a>
### FR-340 评估指标 — 回测

> 回测评估契约见 [spec-trading.md §FR-340](./spec-trading.md); 指标 ground truth 见 [test-plan.md §3.4](./test-plan.md)。

#### AC-340-01 回测结果包含完整独立策略指标
- ⬜ 独立策略回测完成后, 结果包含年化收益率、最大回撤、Sharpe、Sortino、Calma、胜率、盈亏比、交易次数、基准对比
- ⬜ 验证依据: [interfaces.md §4.1 回测结果 JSON](./interfaces.md) 中指标字段齐全

#### AC-340-02 指标值与独立 ground truth 一致
- ⬜ 对同一 returns/trades 序列, 框架输出的指标与 `empyrical-reloaded` 或手算脚本结果一致
- ⬜ 验证依据: test-plan §3.4, 相对误差 < 1e-6; 胜率/盈亏比/交易次数由手算脚本计算

---

<a id="fr-350"></a>
<a id="ac-fr-350"></a>
### FR-350 评估指标 — 实盘/仿真

> 实盘/仿真评估契约见 [spec-trading.md §FR-350](./spec-trading.md)。

#### AC-350-01 paper/live 使用成交记录计算独立策略指标
- ⬜ 独立策略在 paper/live 运行时, 使用实际成交记录计算与 FR-340 相同的指标集合
- ⬜ 验证依据: 从 [interfaces.md §4.3 trades](./interfaces.md) 与资产曲线可观测出口重算指标, 与系统输出一致

#### AC-350-02 日线和日内策略评估字段一致
- ⬜ 日线策略与使用 live-only 粒度的独立策略在 paper/live 下输出同一套指标字段; 数据来源不同不改变指标 schema
- ⬜ 验证依据: 分别运行日线与 30m 策略, 对比评估结果 JSON/数据库字段集合一致

---

<a id="fr-370"></a>
<a id="ac-fr-370"></a>
### FR-370 可视化 — 核心图表

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-370](../v0.2-002-ui/spec.md); 本节仅验 v0.2-001 数据出口是否足以支撑 UI。

#### AC-370-01 核心图表所需数据出口可用
- ⬜ 回测/运行结果可提供净值曲线、基准曲线、买卖点、指标序列等 UI-FR-370 所需输入数据
- ⬜ 验证依据: [interfaces.md §4.1 回测结果 JSON](./interfaces.md) 或对应运行结果出口字段齐全; 不验证 UI 渲染像素

---

<a id="fr-380"></a>
<a id="ac-fr-380"></a>
### FR-380 可视化 — 回测进度

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-380 / UI-FR-080](../v0.2-002-ui/spec.md); 本节仅验回测进度事件出口。

#### AC-380-01 回测进度可被外部观察
- ⬜ 回测运行中按阶段或进度百分比发出可观察事件, 至少包含当前日期/已处理数量/总数量或等价进度信息
- ⬜ 验证依据: [interfaces.md §6](./interfaces.md) 结构化日志或 backtest_logs 出口存在 progress 事件; UI 渲染不在本 FR 验证

---

<a id="fr-390"></a>
<a id="ac-fr-390"></a>
### FR-390 账户总览

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-390](../v0.2-002-ui/spec.md); 本节仅验多策略账户数据出口。

#### AC-390-01 多策略账户总览数据可查询
- ⬜ 系统可按策略账户维度查询现金、总资产、市值、冻结资金、本金与更新时间
- ⬜ 验证依据: [interfaces.md §4.5 assets](./interfaces.md) 按 `portfolio_id` 查询结果字段齐全, 多策略之间不串账

---

<a id="fr-400"></a>
<a id="ac-fr-400"></a>
### FR-400 委托与成交记录

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-400](../v0.2-002-ui/spec.md); 本节仅验委托/成交数据出口。

#### AC-400-01 委托与成交记录可按策略账户查询
- ⬜ 用户可按 `portfolio_id` 查询委托记录与成交记录, 字段覆盖订单号、标的、方向、数量、价格、状态、时间与错误信息
- ⬜ 验证依据: [interfaces.md §4.2 orders](./interfaces.md) 与 [interfaces.md §4.3 trades](./interfaces.md) 查询结果符合 schema

---

<a id="fr-410"></a>
<a id="ac-fr-410"></a>
### FR-410 paper/live 账户

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-410](../v0.2-002-ui/spec.md); 本节仅验账户状态出口。

#### AC-410-01 paper/live 虚拟账户状态可查询
- ⬜ paper/live 策略启动后, 系统为策略提供独立虚拟账户状态, 包含资产、持仓、委托、成交四类可观测数据
- ⬜ 验证依据: [interfaces.md §4.2~§4.5](./interfaces.md) 中同一 `portfolio_id` 的数据可关联查询

---

<a id="fr-420"></a>
<a id="ac-fr-420"></a>
### FR-420 实盘交易界面

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-420](../v0.2-002-ui/spec.md); 本节仅验实盘交易后端契约。

#### AC-420-01 live 模式委托链路可观察
- ⬜ live 模式提交委托后, 系统记录委托提交、柜台回报、成交或失败结果
- ⬜ 验证依据: L2 假网关或 L3 live smoke 中, [interfaces.md §4.2 orders](./interfaces.md)、[interfaces.md §4.3 trades](./interfaces.md) 与 [interfaces.md §6](./interfaces.md) 日志事件形成同一订单链路

---

<a id="fr-430"></a>
<a id="ac-fr-430"></a>
### FR-430 仿真交易界面

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-430](../v0.2-002-ui/spec.md); 本节仅验仿真交易后端契约。

#### AC-430-01 paper 模式委托链路可观察
- ⬜ paper 模式提交委托后, 系统通过本地仿真撮合生成订单与成交结果, 并写入策略虚拟账本
- ⬜ 验证依据: L1 确定性仿真中, [interfaces.md §4.2 orders](./interfaces.md)、[interfaces.md §4.3 trades](./interfaces.md)、[interfaces.md §4.4 positions](./interfaces.md) 和 [interfaces.md §4.5 assets](./interfaces.md) 按 `portfolio_id` 一致

---

<a id="fr-460"></a>
<a id="ac-fr-460"></a>
### FR-460 系统配置（init-wizard）

> 本 FR 已迁移到 [v0.2-002-ui/spec.md UI-FR-460](../v0.2-002-ui/spec.md); 本节仅验配置结果对 v0.2-001 运行可见。

#### AC-460-01 init-wizard 写入运行所需配置
- ⬜ 初始化向导完成后, 系统配置包含数据目录、tushare token、gateway_url、通知配置、虚拟环境/服务启动所需路径中的适用项
- ⬜ 验证依据: 配置读取 API 或配置文件可观测到上述字段; 依赖这些字段的数据同步或 gateway 连接能读取同一配置值

---

<a id="fr-470"></a>
<a id="ac-fr-470"></a>
### FR-470 安装与运行

> 安装与运行契约见 [spec-trading.md §FR-470](./spec-trading.md)。

#### AC-470-01 支持三类操作系统安装路径
- ⬜ mac/linux 使用 shell 安装流程; windows 使用图形界面安装流程; 安装产物包含 embedded python/get-pip 或等价虚拟运行环境
- ⬜ 验证依据: 安装脚本或安装日志显示创建虚拟运行环境, 启动命令使用该环境而非系统 Python

#### AC-470-02 支持服务化运行与开机自启动
- ⬜ 安装完成后可将程序注册为服务, 并配置随开机自动启动
- ⬜ 验证依据: 对应平台服务管理器中存在服务定义; 启动日志显示从虚拟运行环境加载应用

---

<a id="fr-480"></a>
<a id="ac-fr-480"></a>
### FR-480 数据重采样与移动平均工具

> 数据工具契约见 [spec-trading.md §FR-480](./spec-trading.md)。

#### AC-480-01 周线/月线 OHLCV 聚合规则正确
- ⬜ 给定多日 OHLCV 数据, 周线或月线输出满足 open=周期首个交易日开盘、high=max、low=min、close=周期最后交易日收盘、volume/amount=sum
- ⬜ 存在 `adjust` 字段时, 输出周期末 `adjust`; 空输入返回空 DataFrame
- ⬜ 验证依据: 独立手算 fixture 周/月聚合结果, 对比框架重采样输出

#### AC-480-02 移动平均列按窗口生成
- ⬜ 给定 close 序列和 periods `[5, 20]` → 输出包含 `ma5` / `ma20`, 值等于 close rolling mean
- ⬜ 验证依据: 用 Polars/Pandas 独立 rolling mean 计算结果对比, 不使用被测实现作为期望值

---

<a id="fr-481"></a>
<a id="ac-fr-481"></a>
### FR-481 通知通道扩展（邮件 / 钉钉）

> 通知通道契约见 [spec-trading.md §FR-481](./spec-trading.md); 通知事件枚举见 FR-450。

#### AC-481-01 邮件消息可组装为纯文本、HTML 或附件 MIME
- ⬜ 提供 subject + plain text → 生成 MIME 邮件含 Subject 与 text/plain 内容
- ⬜ 提供 HTML 内容 → 生成 MIME 邮件 subtype 为 html
- ⬜ 提供附件路径 → MIME 邮件包含附件 part
- ⬜ 验证依据: 检查 `EmailMessage` headers、content type 与 payload; 不发送真实邮件

#### AC-481-02 钉钉通道支持文本和 markdown 消息
- ⬜ 输入字符串 → 发送 payload 为 text 类型
- ⬜ 输入含 `title` / `text` 的 dict → 发送 payload 为 markdown 类型
- ⬜ 验证依据: 使用外部 HTTP stub 捕获请求 JSON, 断言 msgtype 与 markdown/text 字段; access_token/secret 来自配置

---

<a id="fr-484"></a>
<a id="ac-fr-484"></a>
### FR-484 数据研究辅助工具

> 数据研究辅助契约见 [spec-trading.md §FR-484](./spec-trading.md)。

#### AC-484-01 时间序列切分保持时间顺序与输入类型
- ⬜ 对 pandas DataFrame、Polars DataFrame、Polars LazyFrame 分别调用切分 → 返回类型与输入类型一致
- ⬜ 每个 train/valid/test 子集内按 date 保持时间顺序, 不做随机打乱
- ⬜ 验证依据: 构造多资产 fixture, 独立计算预期索引范围后对比输出

#### AC-484-02 分组切分按每个 asset 独立执行
- ⬜ `group_id="asset"` 时, 每个 asset 内独立按 cuts 切分; 不同 asset 的样本不会互相影响边界
- ⬜ `group_id=None` 时, 全体数据按时间整体切分
- ⬜ 验证依据: 多资产不同长度 fixture 对比每组 train/valid/test 行数与日期范围

---

<a id="fr-485"></a>
<a id="ac-fr-485"></a>
### FR-485 证券代码与市场规则工具

> 证券代码工具契约见 [spec-trading.md §FR-485](./spec-trading.md)。

#### AC-485-01 证券代码格式转换结果可判定
- ⬜ 给定沪深北代表性证券代码 → hson / xt / jq 等目标格式转换结果与明确规则表一致
- ⬜ 无效或不支持代码 → 返回可判定错误或空结果, 不返回错误市场的合法格式
- ⬜ 验证依据: 独立规则表 fixture 对比转换输出

#### AC-485-02 市场规则辅助值与行情字段一致
- ⬜ 涨跌停辅助结果以行情数据或规则表为输入, 输出不与 FR-140 使用的 up_limit/down_limit 字段冲突
- ⬜ 开盘时间差等交易时段辅助值与交易日历/交易时段规则一致
- ⬜ 验证依据: 普通/ST/创科标的 fixture 与交易时段 fixture 对比工具输出

---

## 非功能验收标准

<a id="nfr-010"></a>
<a id="ac-nfr-010"></a>
### NFR-010 性能 — 1000 标的日线回测 < 60s

> 性能契约见 [spec-foundation.md §NFR-010](./spec-foundation.md); 指标 ground truth 见 [test-plan.md §3.4](./test-plan.md)。

#### AC-NFR-010-01 1000 标的 3 年日线回测性能达标
- ⬜ 在 CI 标准机上运行 1000 个 A 股日线、3 年区间、双均线回测端到端耗时 < 60s
- ⬜ 验证依据: CI 性能基准记录总耗时, 含数据加载、策略执行、撮合与指标计算阶段耗时

---

<a id="nfr-020"></a>
<a id="ac-nfr-020"></a>
### NFR-020 类型完备

> 类型契约见 [spec-foundation.md §NFR-020](./spec-foundation.md)。

#### AC-NFR-020-01 公共 API 类型检查 0 报错
- ⬜ 所有公共 API 具有参数与返回值类型标注; 严格类型检查在项目配置下 0 error
- ⬜ 验证依据: CI 运行 pyright/mypy 严格检查通过; 新增公共 API 未标注时报错

---

<a id="nfr-030"></a>
<a id="ac-nfr-030"></a>
### NFR-030 单一职责原则

> 单一职责契约见 [spec-foundation.md §NFR-030](./spec-foundation.md)。

#### AC-NFR-030-01 方法长度门禁可执行
- ⬜ 每个方法 ≤ 50 行, 最长 ≤ 120 行; docstring 与注释不计入业务行数
- ⬜ 验证依据: CI 静态检查或 code review checklist 输出超限方法列表; 超限时 PR 阻塞

---

<a id="nfr-040"></a>
<a id="ac-nfr-040"></a>
### NFR-040 不留冗余代码

> 冗余代码契约见 [spec-foundation.md §NFR-040](./spec-foundation.md)。

#### AC-NFR-040-01 一次性 stub 与未使用代码不进入主线
- ⬜ 新增代码中不存在仅为占位的 stub、未调用的实验函数或“以备将来用”的分支
- ⬜ 验证依据: code review checklist + 静态未使用检查; 删除 stub 后测试仍通过

---

<a id="nfr-050"></a>
<a id="ac-nfr-050"></a>
### NFR-050 可观测性契约（黑盒测试基础）

> 可观测性契约见 [spec-foundation.md §NFR-050](./spec-foundation.md); 外部可观测边界见 [test-plan.md §1.1](./test-plan.md)。

#### AC-NFR-050-01 每条 AC 所需内部状态有外部可观测出口
- ⬜ acceptance.md 中任一 AC 若需要验证内部状态, 实现层必须通过结构化日志、数据文件、数据库表或 Web API 至少一种渠道暴露该状态
- ⬜ 验证依据: test-plan §6.6 可观测契约清单能映射到 interfaces.md 或日志事件; 缺失出口时按 NFR 缺口处理

---

<a id="nfr-060"></a>
<a id="ac-nfr-060"></a>
### NFR-060 运行时可注入性（test-plan §6 可测试性基础）

> 运行时可注入契约见 [spec-foundation.md §NFR-060](./spec-foundation.md); 详细场景保留下方“运行时可注入性验收 (NFR-060 联动)”节。

#### AC-NFR-060-01 paper/live 外部依赖可通过公开装配点注入
- ⬜ paper/live 运行时组件的墙钟、行情源、网关地址可通过公开协议或配置注入测试替身, 不需要 `mock.patch` 框架内部符号
- ⬜ 验证依据: 下方 AC-CLOCK-INJ-01~06 全部通过; [interfaces.md §7](./interfaces.md) 声明的 ClockPort / MarketDataPort / gateway_url 装配点可观察

---

## 运行时可注入性验收 (NFR-060 联动)

> **范围**: 本节 AC 验证 [spec-foundation.md NFR-060](./spec-foundation.md) 的运行时可注入契约, 是 [test-plan.md §6](./test-plan.md) L1/L2 E2E 测试的前置条件。
> **关联 test-plan 章节**: §6.4.1 (虚拟时钟), §6.4.5 (装配器), §6.4.6 (可测试性回退)
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
---

## No Acceptance

按 specforge 0.5.1 L7 三模式 (v0.5-006): 字面值 "无" + acceptance.md ## No Acceptance 列表.

以下 FR 无专属 acceptance 章节:

### FR — 已迁移 / 无专属 v0.2-001 acceptance

- FR-260 (调度 UI): UI 契约已迁移到 [v0.2-002-ui/spec.md UI-FR-260](../v0.2-002-ui/spec.md); 001 分册仅保留调度规则引用位

### NFR — 无

- 当前 NFR-010 ~ NFR-060 均已有标准 `### NFR-XXX` acceptance 节；NFR-060 的详细场景保留在上方 `运行时可注入性验收 (NFR-060 联动)`。

> **Lex 阶段一审核依据**: 这些 FR 的 acceptance 来源 (test-plan §3.2 / spec FR 章节) 已由 spec 阶段锁定, Lex 验证 spec.md + test-plan.md 引用完整后, 视为 AC 已落地. 不需 acceptance.md 占位章节.
