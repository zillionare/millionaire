# Test Plan — v0.2-001-strategy-framework

- **Spec ID**: v0.2-001-strategy-framework
- **范围**: FR-010 / FR-013 / FR-014 / FR-015 / FR-020 (FR-011/012 在 spec v0.2-001 修订中删除, 见 acceptance.md / interfaces.md changelog)
- **位置**: 与 [acceptance.md](./acceptance.md) 并列,与 [spec.md](./spec.md) 同源
- **性质**: 黑盒测试方案 — 不依赖框架内部实现,只依赖外部可观测对象

## 0. 立场与边界

### 0.1 黑盒声明

本 test plan 仅声明**从框架外部可观测**的测试方法。可观测对象限于:

| 类别 | 示例 |
|---|---|
| 策略暴露的外部契约 | `on_bar` / `on_day_open` / `get_bars` / `buy` / `sell` / `sell_host_position` / `default_config` 等(均为策略编写时使用的接口,本身即契约) |
| Web service API | 策略发现端点、回测启动端点、账户查询端点、参数查询端点 |
| UI 入口 | v0.2-002-ui 定义的关键交互(本文件仅**观测**,不**验证渲染**) |
| 日志条目 | 框架在关键事件时写入的结构化日志 |
| 数据存盘文件 | 回测结果 JSON/parquet、虚拟账本快照、委托/成交明细、策略枚举缓存 |
| 数据库表 | 框架持久化的所有业务表 |

### 0.2 不可观测对象(测试不直接依赖)

| 类别 | 说明 |
|---|---|
| 框架内部类层次、调度状态机 | 私有模块/类/方法 |
| 中间数据结构 | 仅在内存中存在、未持久化的对象 |
| 内部实现细节 | 调度器内部队列、撮合器内部状态、注册表内部存储 |

> **可观测契约**:凡 acceptance 验证需要的内部状态,实现层必须提供 dump/日志/DB 可观测点。详见 [spec-foundation.md NFR-050](./spec-foundation.md) 与 [acceptance.md 末尾的可观测契约引用](./acceptance.md)。

### 0.3 与 acceptance.md 的关系

| acceptance.md | test-plan.md |
|---|---|
| 锁定**规则** | 锁定**证据** |
| "返回空列表" | "tmp_path 为空目录时,调用 enumerate_strategies API,断言响应 strategies 字段为 [],diagnostics 字段为 []" |
| "记录 SyntaxError" | "tmp_path 含语法错误的 .py 时,断言响应 diagnostics 含 reason='SyntaxError' 的条目,且 details 含文件名+行号" |

### 0.4 与 v0.2-002-ui test plan 的边界

| 在本文件 | 在 002-ui test plan |
|---|---|
| 业务行为(策略发现返回正确数据) | UI 渲染(列表展示顺序、过滤 UI、样式) |
| Web API 行为(枚举端点返回结构) | UI 操作(点击、跳转、表单) |
| 数据文件(枚举结果持久化) | 图表、进度条视觉效果 |
| 日志(枚举成功/失败事件) | UI 错误提示样式 |

### 0.5 与其它 test plan 的边界

| 在范围 | 不在本文件范围 |
|---|---|
| FR-010/011/012/013/014/015/020 的所有 AC | 001 中尚未写 acceptance 的 FR(如 115/120/125/130/140~470) — 待 acceptance 落地后再补 |
| | 性能 NFR(NFR-010/020/030/040) — 独立 perf plan |
| | 真实网关集成(qmt-gateway) — 联调 plan |
| | UI 渲染 — 002-ui test plan |

---

## 1. 测试环境

### 1.1 数据基础

测试环境是一个**离线、确定、可重现**的数据集,基于真实历史快照构建。

#### 1.1.1 数据范围

| 数据 | 时间范围 | 来源 |
|---|---|---|
| 日线行情(OHLCV + amount + adjust + is_st + up_limit + down_limit) | **2023-01-01 ~ 2025-12-31**(3 年) | tushare 历史 |
| 30 分钟线 | **2025 年最后 2 个交易日** | tushare 历史(若不可得则用 qmt 临时抓取,见 §1.1.2) |
| tick 行情 | **2025 年最后 2 个交易日** | **tushare 不提供**,用 qmt 临时抓取(具体实施时再定) |
| 交易日历 | 2023-01-01 ~ 2025-12-31 | tushare 历史 |
| 证券列表(全市场代码/名称/拼音/上市退市日期) | 截止 2025-12-31 的完整列表 | tushare 历史 |
| ST 标记(ST / *ST) | 2023-01-01 ~ 2025-12-31 | tushare 历史 |
| 涨跌停价 | 2023-01-01 ~ 2025-12-31 | tushare 历史 |
| 复权因子(adjust) | 2023-01-01 ~ 2025-12-31 | tushare 历史 |

#### 1.1.2 关于 30m 与 tick 数据的实施说明

- tushare 不提供 tick 数据;30 分钟线在 3 年区间内也不易全量获取
- 测试只关心框架对**这些粒度的处理逻辑是否正确**,不需要 3 年区间覆盖
- 因此**仅取 2025 年最后 2 个交易日**(代表性窗口,普通交易日,非季报/节假日)
- 若 tushare 提供 30 分钟线则用之;否则临时用 qmt 抓取 2 天的 30m + tick
- **实施细节在落地时确定**,本 test plan 不绑定具体抓取脚本

#### 1.1.3 为什么选 2023-01-01 ~ 2025-12-31

| 原因 | 说明 |
|---|---|
| 真实 | 不是合成的,框架在生产中遇到的市况都在 |
| 跨度足够 | 3 年覆盖牛/熊/震荡/极端行情(若选 2024 单年则可能错过 2023 的某些状态) |
| 可重现 | 截止 2025-12-31 的快照是固定的,不会因运行时间不同而漂移 |
| 包含边界 | 2023-2025 期间有完整的 IPO、退市、ST 标记变更,可覆盖所有边界 |

### 1.2 标的构成(105 个)

100 个核心标的 + 5 个分红除权代表性标的。

#### 1.2.1 类别与数量

| 类别 | 数量 | 覆盖的 AC 边界 |
|---|---|---|
| 普通活跃股 | 50 | 基线场景 |
| ST / *ST | 10 | FR-015 `is_st`、FR-140 涨跌停 ±5% |
| 新 IPO(2023-01-01 ~ 2025-12-31 内上市) | 10 | FR-015 `days_since_ipo` 边界、上市首日规则 |
| 已退市(2023-01-01 ~ 2025-12-31 内退市) | 10 | FR-015 `stocks_listed` 退市边界 |
| 创业板/科创板(±20% 涨跌停) | 10 | FR-140 涨跌停规则差异 |
| 长期停牌(2023-2025 内有过停牌 ≥5 个交易日) | 10 | FR-170 停牌规则 |
| 分红/除权(2023-2025 内有分红送股事件) | 5 | FR-290 复权与除权 |
| **合计** | **105** | — |

#### 1.2.2 选样原则

- 每类至少 5 个标的(避免单点)
- 每类覆盖不同交易所(沪深北)
- 每类覆盖不同行业(避免行业特异性)
- 具体清单存于 `tests/e2e/fixtures/asset_universe.json`(实施时维护)

### 1.3 环境构建

#### 1.3.1 拉取脚本

位置:`tests/e2e/scripts/build_env.py`(实施时落地)

功能:
- 调用 tushare API 拉取上述数据
- 调用 qmt 临时抓取 30m + tick(2 天)
- 写入本地 parquet / 数据库
- 输出 `env_manifest.json` 记录:数据范围、标的清单、生成时间、tushare token hash(用于追溯)

#### 1.3.2 校验脚本

位置:`tests/e2e/scripts/validate_env.py`(实施时落地)

校验内容:
- 完整性:每个标的的日线条数应 ≈ 实际交易日数(±5 容忍因停牌)
- 一致性:OHLCV 字段无空值;ST 标记与涨跌停价一致
- 范围:数据起止日期在预期范围内
- 抽样:对随机 5 个标的随机抽 5 天,人工核对(tushare 网页版/行情软件)

#### 1.3.3 快照与版本

- 数据存储在 `tests/e2e/fixtures/data/`
- `env_manifest.json` 记录版本,CI 中校验 "测试数据版本 = 预期版本"
- 数据不可变;更新数据需新版本号 + 重新走 §1.5 维护流程

### 1.4 环境使用接口

#### 1.4.1 测试代码加载环境

测试代码通过 fixture 加载环境(伪代码示例):

```
@pytest.fixture(scope="session")
def strategy_env():
    """加载测试环境;若 env_manifest 版本不匹配则报错"""
    env = load_env("tests/e2e/fixtures/data")
    assert env.manifest.version == EXPECTED_VERSION
    return env
```

测试代码访问环境的方式:

| 访问对象 | 接口 |
|---|---|
| 行情数据 | `env.get_bars(asset, frame_type, start, end)` |
| 交易日历 | `env.is_trade_day(dt)` / `env.get_trade_dates(start, end)` |
| 证券列表 | `env.stocks_listed(date)` / `env.is_st(asset, date)` / `env.get_name(asset)` |
| 30m/tick 数据 | `env.get_bars(asset, "30m", date)` / `env.get_ticks(asset, date)` |
| 已加载策略 | `env.strategies`(由 §2 中 ground truth 使用) |

#### 1.4.2 环境生命周期

| 阶段 | 行为 |
|---|---|
| 创建 | `build_env.py` 一次性产出(env_manifest 锁定版本) |
| 复用 | CI 与本地都使用同一份 fixtures,不重新拉取 |
| 销毁 | 一般不销毁;归档至 `data/archive/<version>/` |
| 隔离 | 各测试共享 session 级 fixture;互不修改 |

### 1.5 环境维护

#### 1.5.1 扩展流程

何时需要扩展:
- 新交易日进入测试范围(若 spec 范围从 3 年扩到 5 年)
- 新策略类型需要新边界标的
- 现有数据损坏 / tushare 修订历史数据

扩展步骤:
1. 更新 `build_env.py` 与 `asset_universe.json`
2. 跑 `validate_env.py` 重新校验
3. 更新 `EXPECTED_VERSION`
4. CI 重新跑全套测试;任何 AC 失败需记录在新版本 changelog
5. 旧版本归档至 `data/archive/<old_version>/`

#### 1.5.2 数据漂移应对

- tushare 偶尔修订历史数据(如复权因子);若 CI 失败因数据漂移,先核对 tushare 公告,确认是数据修订而非代码 bug,再更新数据 + 文档化

---

## 2. Ground Truth 方法

### 2.1 总则

**不硬编码期望值**。所有 ground truth 由**独立脚本**在测试运行时计算:

| 类型 | 独立脚本来源 |
|---|---|
| 算法正确(双均线交叉、风控触发、撮合成交价、T+1、涨跌停) | **手算**:编写显式的小脚本(如 §2.2/2.3/2.5) |
| 评估指标(Sharpe / Sortino / Calma / 最大回撤 / 胜率 / 盈亏比 / 年化) | **第三方库 empyrical**(独立实现,非参考实现) |
| 简单规则(是否 ST、是否交易日) | **数据本身**:tushare 历史数据作为单一真相源 |

> 关键设计:ground truth 是**可重算的脚本**,不是文档化的固定值。测试运行时调用同一份数据 + ground truth 脚本,与框架输出对比。

### 2.2 撮合 ground truth

**场景**:1 只标的 / 1 个交易日 / 1 个订单

| 测试点 | 手算方法 |
|---|---|
| cheat-on-close 成交价 | T 日收盘价(直接查日线) |
| 次日开盘成交价 | T+1 open(直接查日线) |
| 涨跌停不撮合 | T+1 open == up_limit → 买单不撮合;T+1 open == down_limit → 卖单不撮合 |
| 限价单是否在 [low, high] 内 | T+1 low ≤ price ≤ T+1 high |
| 数量取整(向下,100 整倍) | 手算:1500 → 1500, 1450 → 1400, 99 → 失败 |
| 印花税 / 佣金 | 手算公式(见 FR-180) |

**测试做法**:
- 从测试数据挑出代表性的 1 只标的 1 天
- 跑框架的回测,捕获实际成交价/数量/费率
- 与 ground truth(手算)对比,容差 0.01 元 / 0.01%

### 2.3 回测 ground truth

**场景**:1 只标的 / 5 天 / 双均线(2,3)简化版

**手算脚本**(伪代码):
```
# 给定 asset, start, end
prices = env.get_bars(asset, "1d", start, end).close
ma_fast = prices.rolling(2).mean()
ma_slow = prices.rolling(3).mean()

# 简化交叉判断:ma_fast > ma_slow 买入,反之卖出
signals = []
for i in range(1, len(prices)):
    if ma_fast[i] > ma_slow[i] and ma_fast[i-1] <= ma_slow[i-1]:
        signals.append(("buy", prices.index[i]))
    elif ma_fast[i] < ma_slow[i] and ma_fast[i-1] >= ma_slow[i-1]:
        signals.append(("sell", prices.index[i]))

# 用 cheat-on-close 撮合
trades = apply_cheat_on_close(signals, prices)

return final_pnl, trades
```

**测试做法**:
- 在测试数据上挑 1 只普通股 + 5 天
- 跑框架的双均线策略回测,捕获输出(成交明细 + 净值)
- 与手算脚本输出对比
- 容差:成交价 < 0.01 元、成交数量一致、净值差异 < 1 元

### 2.4 评估指标 ground truth

| 指标 | 来源 |
|---|---|
| Sharpe | empyrical.sharpe_ratio(returns) |
| Sortino | empyrical.sortino_ratio(returns) |
| Calma | empyrical.calmar_ratio(returns) |
| 最大回撤 | empyrical.max_drawdown(returns) |
| 胜率 | 手算:盈利交易数 / 总交易数 |
| 盈亏比 | 手算:平均盈利 / 平均亏损 |
| 年化收益 | empyrical.annual_return(returns) 或手算 `(1+total)^(252/n)-1` |

**测试做法**:
- 跑框架回测,捕获 returns 序列(由框架导出,可从回测结果 JSON 读取)
- 调用 empyrical 计算各项指标
- 对比框架计算的指标值
- 容差:相对误差 < 1e-6

### 2.5 风控 ground truth

#### 2.5.1 成本止损

**场景**:cost_basis=10, k=-5%, 当日 close=9.4

**手算**:
- 触发条件:`close ≤ cost_basis × (1 + k/100)` → `9.4 ≤ 10 × 0.95 = 9.5` → 触发
- 应清仓该标的全部可卖持仓(T+1 约束下)
- 超额收益(N=0):**Triple Barrier 公式**(详见 [spec-trading.md F-TB-2](./spec-trading.md); N=0 即当日收盘)
  - 触发了 down 屏障 → 应用 F-TB-2:`+down_threshold`(百分点,正数;因触发的是下界)
  - 假设 down_threshold=5%(由策略 `default_config` 声明)→ `excess_return = +0.05`

**测试做法**:
- 构造 cost=10 的持仓
- 输入当日 tick 数据触发 close ≤ 9.5
- 跑框架,捕获:是否触发卖出、卖出价、超额收益事件(`excess_return = +down_threshold` 验证)
- 与手算对比

#### 2.5.2 回落卖出

**场景**:当日 +5%, 5 分钟内 -2%

**手算**:
- 触发条件:日内 high 达到 m%,随后 n 分钟内跌幅 > k%
- 取 tick 数据,手算日内最大涨幅与最大回撤

**测试做法**:
- 输入当日的 tick 数据
- 跑框架,捕获触发事件
- 与手算对比

### 2.6 SDK 元数据 ground truth

#### 2.6.1 交易日历

- **单一真相源** = 测试数据中的交易日历 parquet
- 框架调用 `is_trade_day(dt)` / `get_trade_dates(start, end)` → 与 parquet 直接查询对比
- 容差:0

#### 2.6.2 证券列表

- **单一真相源** = 测试数据中的证券列表 parquet
- 框架调用 `stocks_listed(date)` / `is_st(asset, date)` / `days_since_ipo(asset, date)` → 与 parquet 对比

---

## 3. 黑盒观测点

### 3.1 观测渠道清单

#### 3.1.1 Web API(框架暴露的 HTTP/WebSocket endpoint)

具体 endpoint 由实现层定义,本 test plan 给出**功能需求**,不绑定 URL。

| 功能 | 用途 | 涉及 FR |
|---|---|---|
| 策略枚举端点 | 触发枚举、返回元数据 | FR-020 |
| 策略参数查询端点 | 返回 `default_config` 解析结果 | FR-010, FR-020 |
| 回测启动端点 | 提交回测参数,返回 task_id | FR-010 |
| 回测进度端点 | 查询进度、当前净值 | FR-010 |
| 回测结果端点 | 查询最终结果(指标 + 净值曲线 + 交易明细) | FR-010 |
| 账户查询端点 | 返回 cash / positions | FR-010/013 |
| 委托/成交查询端点 | 返回历史委托/成交 | FR-010/013 |
| 交易日历 API | `is_trade_day` / `get_trade_dates` 等 | FR-014 |
| 证券列表 API | `stocks_listed` / `is_st` / `days_since_ipo` / `get_name` | FR-015 |

#### 3.1.2 UI 入口(002-ui 范围,本 test plan 仅观测)

| UI 入口 | 用于观察 |
|---|---|
| 策略选择器 | FR-020 枚举结果可视化 |
| 策略参数编辑表单 | FR-010 `default_config` 可视化 |
| 启动回测表单 | FR-010 触发 |
| 账户详情页 | FR-010/013 实时账户 |
| 风控事件列表 | FR-013 触发事件 |

#### 3.1.3 日志条目类型

| 事件类型 | 关键字段 | 用途 |
|---|---|---|
| `strategy.enumerated` | strategy_id, is_builtin, default_config_size | FR-020 枚举成功 |
| `strategy.skipped` | path, class_name, reason, detail | FR-020 跳过 |
| `backtest.started` | strategy_id, params, interval | FR-010 启动 |
| `backtest.progress` | strategy_id, current_day, total_days | FR-010 进度 |
| `backtest.completed` | strategy_id, metrics | FR-010 完成 |
| `risk.triggered` | asset, trigger_price, cost, reason, ts | FR-013 触发 |
| `order.filled` | strategy_id, asset, qty, price | 撮合验证 |
| `order.rejected` | strategy_id, asset, reason | 涨跌停/T+1 边界 |

#### 3.1.4 数据存盘文件

| 文件 | 格式 | 用途 |
|---|---|---|
| 回测结果 | JSON + Parquet | FR-010 完整结果 |
| 虚拟账本快照 | Parquet/DB 表 | FR-010/013 账户 |
| 委托明细 | Parquet/DB 表 | FR-140/150/160 规则验证 |
| 成交明细 | Parquet/DB 表 | 撮合验证 |
| 风控触发事件 | Parquet/DB 表 | FR-013/125 验证 |
| 超额收益事件 | Parquet/DB 表 | FR-013 验证 |
| 枚举缓存 | JSON | FR-020 验证 |
| 交易日历缓存 | Parquet | FR-014 验证 |
| 证券列表缓存 | Parquet | FR-015 验证 |

### 3.2 FR → 观测点映射

| FR | 主要观测点 |
|---|---|
| FR-010 策略对象模型 | 枚举端点 + 参数查询端点 + 枚举缓存文件 + 策略编写接口(`on_bar`/`default_config`) + 回测启动/进度/结果端点 + 账户/委托/成交 DB + 日志 |
| FR-013 RiskStrategy | 风控触发事件 DB + 超额收益 DB + 宿主持仓查询端点 + tick 日志 |
| FR-014 交易日历 | 日历 API + 日历缓存 Parquet + 单一日历文件 |
| FR-015 证券列表 | 证券列表 API + 证券列表缓存 Parquet |
| FR-020 策略发现 | 枚举端点 + 枚举缓存 + skipped diagnostics + `strategy.enumerated/skipped` 日志 |

---

## 4. 测试组织

### 4.0 Unit 测试 vs E2E(黑盒)测试的边界

仓库内有两类测试,**组织原则不同**:

| 测试类型 | 路径 | 组织原则 | 编写者 | 目的 |
|---|---|---|---|---|
| **Unit 测试** | `tests/unit/`(沿用各项目惯例) | **按源文件目录**(与 `quantide/...` 1:1 镜像) | 开发 | 验证模块内部逻辑 |
| **E2E / 黑盒测试**(本文件) | `tests/e2e/` | **按场景** | 测试工程师 | 验证框架外部行为 |

> **强制分离**:
> - Unit 测试**不允许**依赖 `tests/e2e/fixtures/data/`(测试数据)
> - E2E 测试**不允许** mock 框架内部实现(若必须 mock,意味着 AC 应改写为更易观测的形式)
> - E2E 测试**不**依赖 `quantide/` 包内部的任何私有 API

### 4.1 目录结构

```
tests/e2e/
├── conftest.py                      # session 级 fixture(加载 env)
├── fixtures/
│   ├── data/                        # 测试数据(由 §1.3 产出)
│   │   ├── env_manifest.json
│   │   ├── daily/
│   │   ├── 30m/
│   │   ├── tick/
│   │   ├── calendar/
│   │   └── stocks/
│   ├── asset_universe.json          # 105 个标的清单
│   └── strategies/                  # 测试用策略代码 fixture
│       ├── valid_day_strategy.py
│       ├── valid_live_strategy.py
│       ├── valid_risk_strategy.py
│       ├── invalid_syntax.py
│       ├── invalid_import.py
│       └── non_strategy_class.py
├── scripts/
│   ├── build_env.py                 # §1.3 数据构建
│   └── validate_env.py              # §1.3 校验
├── ground_truth/                    # §2 独立 ground truth 脚本
│   ├── matching.py                  # 撮合 ground truth
│   ├── backtest.py                  # 回测 ground truth
│   ├── risk.py                      # 风控 ground truth
│   └── metrics.py                   # empyrical 评估指标
└── scenarios/                       # **按场景组织**(覆盖 §5 矩阵)
    ├── strategy_discovery/          # FR-010 + FR-020 策略枚举与发现
    │   ├── test_enumerate_basic.py
    │   ├── test_enumerate_recognition.py
    │   ├── test_enumerate_metadata.py
    │   ├── test_enumerate_fault_tolerance.py
    │   ├── test_enumerate_mode_agnostic.py
    │   ├── test_default_config.py
    │   └── test_strategy_lifecycle.py
    ├── backtest/                    # FR-010 回测场景
    │   ├── test_backtest_acceptance.py
    │   ├── test_data_interface.py
    │   ├── test_account_isolation.py
    │   ├── test_matching.py         # 撮合规则(cheat-on-close / 次日开盘 / 限价)
    │   ├── test_evaluation_metrics.py  # Sharpe / 最大回撤 / 等
    │   └── test_t_plus_1.py         # T+1 与持仓记账
    ├── live_strategy/               # FR-010 实时(30m/live-only) 场景
    │   ├── test_live_strategy_rejection.py
    │   ├── test_multiframe_data.py
    │   └── test_paper_live_account.py
    ├── risk_strategy/               # FR-013 RiskStrategy 场景
    │   ├── test_risk_no_account.py
    │   ├── test_risk_tick_driven.py
    │   ├── test_risk_excess_return.py
    │   └── test_risk_cost_stop.py   # 成本止损场景
    ├── calendar/                    # FR-014 交易日历场景
    │   ├── test_trade_day.py
    │   ├── test_day_shift.py
    │   └── test_mode_agnostic.py
    └── securities/                  # FR-015 证券列表场景
        ├── test_stocks_listed.py
        ├── test_is_st.py
        ├── test_days_since_ipo.py
        └── test_boundary_categories.py  # IPO / 退市 / ST / 停牌 / 创科
```

### 4.2 命名约定(建议)

- 文件:`test_<场景>__<子场景>.py`,例如 `test_enumerate__syntax_error.py`
- 函数:`test_<AC-id>_<子场景>`,例如 `test_ac_020_08_empty_directory`
- 跨场景的共享工具放 `tests/e2e/conftest.py` 或 `tests/e2e/utils/`

### 4.3 执行

- **离线运行**:全部测试不依赖网络(数据已固化)
- **执行顺序**:单测(快速)→ 集成(中等)→ 系统级(慢)
- **并行**:各 `scenarios/` 目录内可并行;场景间可并行
- **CI**:每次 push 必跑完整套;数据更新需触发完整回归
- **与 unit 测试隔离**:E2E 可用独立 marker(如 `@pytest.mark.e2e`)或独立 pytest 配置(`pytest-e2e.ini`),避免与 unit 测试混跑

### 4.4 scenario ↔ FR 的覆盖矩阵(用于跟踪)

| Scenario 目录 | 覆盖 FR | 主要 AC |
|---|---|---|
| `strategy_discovery/` | FR-010, FR-020 | AC-010-01 ~ 04, AC-020-01 ~ 15 |
| `backtest/` | FR-010 | (回测场景, 已被 acceptance.md FR-010 覆盖) |
| `live_strategy/` | FR-010 | (实时场景, 已被 acceptance.md FR-010 覆盖) |
| `risk_strategy/` | FR-013 | AC-013-01 ~ 05 |
| `calendar/` | FR-014 | AC-014-01 ~ 05 |
| `securities/` | FR-015 | AC-015-01 ~ 04 |

---

## 5. 与 acceptance 的覆盖矩阵

| FR | AC 组 | 主要观测点 | Ground truth 类型 |
|---|---|---|---|
| FR-010 | AC-010-01 ~ 04 | 枚举端点 + 策略接口 + 缓存 | §2.6 数据本身 |
| FR-011 | ⏸ 暂缓（已并入 FR-010） | — | — |
| FR-012 | ⏸ 暂缓（已并入 FR-010） | — | — |
| FR-013 | AC-013-01 ~ 05 | 风控事件 DB + 超额收益 DB + tick 日志 + BacktestRunner 拒绝启动 | §2.5 风控 |
| FR-014 | AC-014-01 ~ 05 | 日历 API + 日历 Parquet | §2.6.1 日历 |
| FR-015 | AC-015-01 ~ 04 | 证券列表 API + 证券列表 Parquet | §2.6.2 证券列表 |
| FR-020 | AC-020-01 ~ 15 | 枚举端点 + 缓存 + skipped diagnostics + 日志 | §2.6 数据本身 |
| FR-185 | ⏸ 暂缓（占位说明） | — | — |
| FR-360 | AC-360-01 ~ 03 | 风控评估 DB (`activation_id` 持久化) + Triple Barrier 公式 + N 日窗口回填 | §2.5 风控 |

每个 AC 至少 1 个测试用例;负面/边界 AC 至少 1 个负面测试。

> **⏸ 暂缓项说明**:
> - **FR-011/FR-012**: 已在 v0.2-001 修订中合并入 FR-010（独立策略 = 单一 `BaseStrategy`，数据粒度由 `get_bars(frame_type)` 区分）。原 AC 迁移到 AC-010-03。
> - **FR-013 风控可回测性**: 已决定（v0.2 **不支持** RiskStrategy 回测,见 spec FR-013）。`get_prices` / `get_ticks` 仅 paper/live 可用;BacktestRunner 检测到 RiskStrategy 实例则拒绝启动。
> - **FR-360 风控评估**: 已解除 ⏸ 暂缓（2026-06-17）。评估仅在 paper/live 下进行;AC-360-01 ~ 03 已写。
> - **FR-185 加权均价算法**: 占位说明，acceptance 待 v0.2 review 单独决定。

---

## 6. 范围与非范围

### 6.1 在范围

- FR-010 / FR-013 / FR-014 / FR-015 / FR-020 的所有 AC（FR-011/FR-012 已并入 FR-010）
- 与上述 FR 直接相关的观测点(API、日志、数据文件)
- 与上述 FR 直接相关的 ground truth 脚本

### 6.2 不在范围

- v0.2-002-ui 的 UI 渲染细节(转给 002-ui test plan)
- v0.2-001-strategy-framework 中尚未写 acceptance 的 FR:
  - FR-115 / FR-125(驱动契约)
  - FR-130(风控契约)
  - FR-140 ~ FR-470(交易规则 / 调度 / 数据源 / 评估指标 / 安装)
  - FR-185(加权均价算法;⏸ 暂缓)
  - 这些 FR 的 acceptance 落地后,test plan 需补充对应章节
- 性能 NFR(NFR-010 / NFR-020 / NFR-030 / NFR-040)— 独立 perf plan
- 真实 qmt-gateway 联调 — 联调 plan
- 真实行情实时性测试 — 在线 plan
- **风控策略回测验证**: v0.2 不支持(已决定),无相关测试

---

## 7. 已知缺口与待补

### 7.1 spec 真空导致的不可测点

acceptance 中标注为声明性或基于假设的 AC,在 test plan 中需要**标注 ⚠️ 待补**。具体清单见各 FR 的 acceptance 中 ⬜/⚠️ 标注。

### 7.2 待补 acceptance 的 FR

以下 FR 当前**无 acceptance**,因此本 test plan **不覆盖**:

- FR-115 日线策略驱动
- FR-125 风控策略驱动
- FR-130 ~ FR-470

这些 FR 的 acceptance 落地后,test plan 需补充对应章节(目录结构 §4.1 已预留 `fr-115/` 等占位)。

### 7.3 实现层契约跟踪

本 test plan 隐含一个**实现层责任**:凡 AC 验证需要的内部状态,实现层必须提供 dump/日志/DB 可观测点。详见 [spec-foundation.md NFR-050](./spec-foundation.md)。

实现层 PR 评审需对照 §3.1 观测点清单,确认所有可观测点已实现。

---

## 8. 维护与演进

### 8.1 版本

- 当前 test plan 版本与 v0.2-001-strategy-framework 同步
- 修订 test plan 需更新本文档版本号

### 8.2 与 acceptance 同步

- acceptance 增/删 AC 时,test plan 覆盖矩阵(§5)同步更新
- 标 ⚠️ 的 AC 经 spec 修订后可解除;test plan 同步落地测试

### 8.3 与实现同步

- 实现层若调整 API endpoint / 日志格式 / 数据文件 schema,需更新 §3.1 观测点清单
- 若新增观测点(test plan 派生),需更新 spec-foundation.md NFR-050

---

## 附录 A — 关键决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 数据范围 | 2023-01-01 ~ 2025-12-31 | 3 年覆盖多市况 + 截止 2025-12-31 固定快照 |
| 标的数量 | 105(100 + 5 分红除权) | 覆盖所有 AC 边界类别 |
| 30m/tick | 2025 年最后 2 个交易日 | tushare 不提供 tick;2 天够覆盖风控 |
| Ground truth | 手算 + empyrical | 不硬编码期望值;empyrical 是独立算法实现 |
| 黑盒视角 | 外部契约可观测,内部不可观测 | 测试与实现解耦 |
| `get_bars` 归属 | `Strategy` 抽象根(所有策略) | 抽象根定义数据接口;子类继承 |
| `get_prices` / `get_ticks` 归属 | `RiskStrategy` 专有(类层) | 兄弟类结构保证独立策略拿不到;仅 paper/live 可用 |
| 风控可回测性 | ❌ 否 (v0.2 不支持) | BacktestRunner 启动时检测到 RiskStrategy 实例则拒绝;仅 paper/live 评估 |
| Triple Barrier 公式 | ✅ 已固化 (F-TB-1/2/3, [spec-trading.md](./spec-trading.md)) | 屏障触发: ±threshold; 未触发: P_sell/Close_n - 1 |
| 按开启区间切分 | ✅ 已固化 (FR-013/FR-360) | stop → start 分配新 `activation_id`;区间内 `excess_return` 独立累计 |
| 加权均价(FR-185) | ⏸ 暂缓(占位说明) | 算法待 v0.2 review 单独决定 |

## 附录 B — 相关文档

- [spec.md](./spec.md) — 策略框架 spec
- [acceptance.md](./acceptance.md) — 验收标准
- [../v0.2-002-ui/spec.md](../v0.2-002-ui/spec.md) — UI spec
- empyrical — 第三方评估指标库(https://github.com/quantopian/empyrical)
