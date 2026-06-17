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

> **⏸ 暂缓范围**：本节 AC 中与"风控可回测"相关的部分暂缓（FR-013 §回测状态未确定）。仅"结构性"AC 立即可验证（账户无/无 buy 接口/类层归属等）。

#### AC-013-01 风控策略无独立账户
- ⬜ 风控策略不创建 `portfolio_id`，不持有资金
- ⬜ 风控策略**类层不存在** `positions` / `cash`（继承结构保证——`RiskStrategy` 继承 `Strategy` 而非 `BaseStrategy`）

#### AC-013-02 只能卖出不能买入
- ⬜ 风控策略可调用 `sell_host_position` → 订单写入宿主 `portfolio_id`，资金从宿主扣减
- ⬜ 风控策略**类层不存在** `buy` / `buy_amount` / `buy_percent` / `sell`（除 `sell_host_position` 外）等买入/卖自己持仓的接口（继承结构保证，非运行时拦截）

#### AC-013-03 只读访问宿主持仓
- ⬜ 风控策略可查看宿主的持仓快照（通过 `on_check(positions, ...)` 接收） → 只读，不可修改
- ⬜ 风控策略**类层不存在** `positions`（属 BaseStrategy 专有）——通过 `on_check` 参数间接获得宿主持仓

#### AC-013-04 tick 级数据接口可用（风控专有）
- ⬜ 风控策略调用 `get_ticks` → paper/live 返回 tick 级行情数据；**回测下的行为 ⏸ 暂缓**（实现层决定从 OHLC 派生，约束：价格 ∈ [min(O,L,C,H), max(O,L,C,H)]）
- ⬜ 风控策略调用 `get_prices` → paper/live 返回当前价格；**回测下的行为 ⏸ 暂缓**
- ⬜ **类层不存在** `get_prices` / `get_ticks` 于 `BaseStrategy`（独立策略拿不到这些方法）

#### AC-013-05 宿主生命周期绑定
- ⬜ 宿主进入 paper/live → 关联的 RiskStrategy 自动激活
- ⬜ 宿主停止 → RiskStrategy 一并停止
- ⬜ 单独停止 RiskStrategy → 不再监控，已发订单不撤回；重新启动后开启新"开启区间"，超额收益按区间独立累计
- ⬜ 尝试不带宿主账户直接启动 RiskStrategy → 抛出异常，提示必须绑定宿主
- ⬜ **⏸ 暂缓**：RiskStrategy 提交给 BacktestRunner 的行为 / 风险策略可回测性 — 见 FR-013 §回测状态

---

### FR-014 SDK 元数据接口 — 交易日历

#### AC-014-01 交易日判断
- ⬜ 传入一个已知的交易日（如周二）→ 返回 true
- ⬜ 传入一个周末 → 返回 false
- ⬜ 传入一个法定节假日（如春节）→ 返回 false
- ⬜ 传入超出数据范围的日期 → 抛出异常

#### AC-014-02 交易日移位
- ⬜ 从一个交易日向后移 1 天 → 返回下一个交易日（跨周末自动跳过）
- ⬜ 从一个交易日向前移 1 天 → 返回上一个交易日
- ⬜ 移位偏移量为 0（无论当日是否为交易日）→ 返回最近已结束的交易日
- ⬜ 移位结果超出数据范围 → 抛出异常

#### AC-014-03 交易日计数与列表
- ⬜ 查询一个跨越周末的区间 → 返回的交易日数不含周末和节假日
- ⬜ start == end 且为交易日 → 返回 1
- ⬜ start == end 且为非交易日 → 返回 0
- ⬜ 查询某月所有交易日 → 结果中不含非交易日，按日期升序排列
- ⬜ start > end → 抛出异常

#### AC-014-04 模式无关性
- ⬜ 回测中调用日历接口 → 返回基于仿真时间范围的正确结果
- ⬜ paper/live 中调用日历接口 → 返回基于真实日历的正确结果
- ⬜ 相同接口、相同参数、不同模式 → 行为一致

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

- ✅ 用户目录中存在一个继承 `BaseStrategy` 的具体类 → 该类出现在枚举结果中
- ✅ 用户目录中存在一个继承 `DayStrategy` / `LiveStrategy` / `RiskStrategy` 之一的类 → 出现在枚举结果中,`strategy_type` 正确标注
- ✅ 枚举结果中存在一个直接继承 `BaseStrategy`(非三类子类) 的类 → 该类的 `strategy_type` 由运行时实际继承链推导(非"必须是三类之一");**只要是 BaseStrategy 子类即合法**,`strategy_type` 字段值由 MRO 中最近的具体子类决定
- ✅ 枚举结果中存在一个类 `BaseStrategy` 自身 → **不出现**(基类是抽象类,被排除)

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
| `module`          | ✅ `module == cls.__module__`                                                                                                                                                            |
| `is_builtin`      | ✅ 当类定义在 Millionaire 框架包内(`quantide.*` 或文档约定的根包名)→ `is_builtin=True`;否则 `False`;判定规则在 acceptance 级别定义为"基于 import 路径前缀",**不依赖运行时 monkey-patch** |
| `skipped_reasons` | ✅ 仅未通过识别条件的**非 BaseStrategy 类**携带;通过的策略 `skipped_reasons=[]`                                                                                                          |

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
| ✅ 类不是 `BaseStrategy` 子类                               | 该类不进入策略列表;原因 = `NotAStrategy`                    |
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

- ✅ 枚举结果**不验证**策略的业务逻辑正确性(回测正确性由 FR-115/120/125 acceptance 负责)
- ✅ 枚举结果**不执行**回测运行(运行由调度器负责)
- ✅ 枚举结果**不验证**策略参数的类型/范围(运行时校验由 FR-200 负责)
- ✅ 枚举结果**不发起**远程网络请求(仅本地 `.py` 文件)

#### AC-020-15 联动接口契约

- ✅ 枚举调用方的契约:接收 `Path | str | None`(None 表示未配置)→ 返回 `EnumerationResult`
- ✅ `EnumerationResult` 含两个字段:`strategies: list[StrategyMetadata]`(通过的策略) + `diagnostics: list[SkippedEntry]`(失败的文件/类及原因)
- ✅ `SkippedEntry` 含字段:`path: str`(文件路径)、`class_name: str | None`(类名,文件级失败时为 None)、`reason: SkippedReason`、`detail: str`(原因详情,如异常消息)

---

### FR-125 风控策略驱动契约

> **⏸ 暂缓范围**：本节 AC 中与"风控回测/Triple Barrier"相关的部分暂缓（FR-013 §回测状态未确定）。仅 paper/live 下的行为立即可验证。

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

#### AC-125-05 超额收益记录 — ⏸ 暂缓
- ⬜ ⏸ Triple Barrier 公式与"按开启区间切分"逻辑暂不固化（FR-013 §回测状态）
- ⬜ ⏸ N 日窗口回填行为暂不写 acceptance
- ⬜ ⏸ 等 FR-013 §回测状态确定后，本 AC 重新展开

---

## 可观测性契约引用

本文件中每条 AC 的验证,需通过 [spec.md NFR-050](./spec.md) 定义的可观测点(结构化日志 / 数据存盘文件 / 数据库表 / Web API)完成。完整的观测点清单见 [test-plan.md §3.1](./test-plan.md)。

凡 AC 涉及的内部状态,实现层**必须**提供对应可观测出口;此为 PR 评审的强制 checklist。
