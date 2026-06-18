# Test Plan — v0.2-001-strategy-framework

- **Spec ID**: v0.2-001-strategy-framework
- **范围**: FR-010 / FR-013 / FR-014 / FR-015 / FR-020 (FR-011/012 在 spec v0.2-001 修订中删除, 见 acceptance.md / interfaces.md changelog)
- **位置**: 与 [acceptance.md](./acceptance.md) 并列,与 [spec.md](./spec.md) 同源
- **性质**: 黑盒测试方案 — 不依赖框架内部实现,只依赖外部可观测对象

## 1. 立场与边界

### 1.1. 黑盒声明

本 test plan 仅声明**从框架外部可观测**的测试方法。可观测对象限于:

| 类别               | 示例                                                                                                                                     |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 策略暴露的外部契约 | `on_bar` / `on_day_open` / `get_bars` / `buy` / `sell` / `sell_host_position` / `default_config` 等(均为策略编写时使用的接口,本身即契约) |
| Web service API    | 策略发现端点、回测启动端点、账户查询端点、参数查询端点                                                                                   |
| UI 入口            | v0.2-002-ui 定义的关键交互(本文件仅**观测**,不**验证渲染**)                                                                              |
| 日志条目           | 框架在关键事件时写入的结构化日志                                                                                                         |
| 数据存盘文件       | 回测结果 JSON/parquet、虚拟账本快照、委托/成交明细、策略枚举缓存                                                                         |
| 数据库表           | 框架持久化的所有业务表                                                                                                                   |

### 1.2. 不可观测对象(测试不直接依赖)

| 类别                       | 说明                                           |
| -------------------------- | ---------------------------------------------- |
| 框架内部类层次、调度状态机 | 私有模块/类/方法                               |
| 中间数据结构               | 仅在内存中存在、未持久化的对象                 |
| 内部实现细节               | 调度器内部队列、撮合器内部状态、注册表内部存储 |

> **可观测契约**:凡 acceptance 验证需要的内部状态,实现层必须提供 dump/日志/DB 可观测点。详见 [spec-foundation.md NFR-050](./spec-foundation.md) 与 [acceptance.md 末尾的可观测契约引用](./acceptance.md)。

### 1.3. 测试方法

本次需求包含了 SDK/API。对 SDK/API 的测试，测试设计为单元测试，由功能的实施者开发单元测试脚本；但测试负责人要对单元测试脚本进行代码审查，确保不发生以下情况：

| #   | 作伪模式             | 典型表现                                           | 真实案例                                                     |
| --- | -------------------- | -------------------------------------------------- | ------------------------------------------------------------ |
| 1   | 改断言迁就实现       | spec 说"抛异常"，测试改成"返回 False"              | commit 5094d93 改 AC-014-01-04 / AC-015-02-05                |
| 2   | 用 skip 逃避验证     | pytest.skip("see e2e") 但 e2e 永远没写             | commit 8dcf024 改 AC-013-05 三个子 AC                        |
| 3   | 断言退化             | assert issubclass(X, Exception) 替代真正提交并捕获 | commit 5094d93 的 test_backtest_runner_rejects_risk_strategy |
| 4   | try/except: pass     | 异常路径被吞掉                                     | 旧 TestKnownGapsV2                                           |
| 5   | mock 过度            | mock 掉框架核心，测出来是 mock 的行为              | 未发生但常见                                                 |
| 6   | ground truth 用 impl | 期望值 = impl 输出                                 | 未发生但是高风险                                             |
| 7   | 硬编码期望值         | assert result == 0.15 只因当前 impl 输出 0.15      | 未发生                                                       |
| 8   | trivial pass         | assert True / assert 1 == 1                        | 未发生                                                       |

#### 防护机制

仅靠 review 不足以阻挡上述作伪模式，需要以下强制机制（CI 校验 + PR 流程）：

1. **AC 强制溯源**
   - 每个测试函数的 docstring 第一行必须含 `AC-XXX-YY`（对应 acceptance.md 中的 AC 编号）；命名约定见 §2.2
   - CI 在 `tests/unit/` 与 `tests/e2e/` 中扫描所有 `test_*` 函数，校验：
     - (a) 每个函数 docstring 含合法 AC 编号
     - (b) acceptance.md 中每条 AC 至少被一个测试函数引用
   - 任一校验失败阻塞 merge

2. **断言禁忌**（CI 静态检查，违反阻塞 merge）
   - 禁止 `assert True` / `assert 1` / `assert <obj> is not None` 单独作为断言
   - 禁止 `try: ... except: pass` 包裹被测代码
   - 禁止 `pytest.skip(...)` / `@pytest.mark.skip` 不附带 GitHub issue 链接

3. **测试改动归类**
   PR 修改已存在的测试断言（非新增）时，PR description 必须勾选改动类别：
   - [ ] 新增 AC（关联 acceptance.md commit）
   - [ ] spec 变更（关联 spec commit）
   - [ ] 修复 flake / 环境问题（关联 issue）

   **禁止类别**：「impl 行为与 spec 不一致 → 改测试」。出现此类需求时，必须先改 spec（如确认 spec 错）或先改 impl（如确认 impl 错），不得改测试。Review 阶段直接 reject。


---

## 2. 测试环境

### 2.1. 目录组织

| 功能              | 根目录               | 组织原则                                     | 编写/维护  | 目的                |
| ----------------- | -------------------- | -------------------------------------------- | ---------- | ------------------- |
| **Unit 测试代码** | `tests/unit/`        | **按源文件目录**(与 `quantide/...` 1:1 镜像) | 开发       | 验证模块内部逻辑    |
| **Unit 资产**     | `tests/assets/unit/` | 存放单元测试所需的数据、fixtures、配置等资产 | 开发       | 使用2022年数据      |
| **E2E 测试代码**  | `tests/e2e/`         | **按场景组织**                               | 测试工程师 | 验证框架外部行为    |
| **E2E 资产**      | `tests/assets/e2e/`  | 存放e2e 测试使用的数据、fixtures、配置等资产 | 测试工程师 | 使用2023~2025年数据 |

> **强制分离**:
> - 单元测试与E2E使用不同的测试数据，它们通过数据采集时间分开；通过这种方式来防止测试对功能实现过拟合。
> - E2E 测试**不允许** mock 框架内部实现(若必须 mock,意味着 AC 应改写为更易观测的形式)
> - E2E 测试**不**依赖 `quantide/` 包内部的任何私有 API


### 2.2. 命名约定(建议)

- 文件:`test_<场景>__<子场景>.py`,例如 `test_enumerate__syntax_error.py`
- 函数:`test_<AC-id>_<子场景>`,例如 `test_ac_020_08_empty_directory`
- 跨场景的共享工具放 `tests/assets/*/conftest.py` 或 `tests/assets/*/utils/`

### 2.3. 执行

- **离线运行**:全部测试不依赖网络(数据已固化)
- **执行顺序**:单测(快速)→ 集成(中等)→ 系统级(慢)
- **并行**:各 `scenarios/` 目录内可并行;场景间可并行
- **CI**:每次 push 必跑完整套;数据更新需触发完整回归
- **E2E 与 unit 测试隔离**:E2E 可用独立 marker(如 `@pytest.mark.e2e`)或独立 pytest 配置(`pytest-e2e.ini`),避免与 unit 测试混跑

### 2.4. 数据基础

测试环境是一个**离线、确定、可重现**的数据集,基于真实历史快照构建。

#### 2.4.1. 测试数据集

| 数据                                                              | E2E 时间范围                      | UNIT 时间范围     | 数据来源 |
| ----------------------------------------------------------------- | --------------------------------- | ----------------- | -------- |
| 日线行情(OHLCV + amount + adjust + is_st + up_limit + down_limit) | **2023-01-01 ~ 2025-12-31**(3 年) | 2022年            | 真实数据 |
| 30 分钟线                                                         | **2025 年最后 2 个交易日**        | 2022年最后2交易日 | 合成数据 |
| tick 行情                                                         | **2025 年最后 2 个交易日**        | 2022年最后2交易日 | 合成数据 |
| 交易日历                                                          | 2023-01-01 ~ 2025-12-31           | 2022年            | 真实数据 |
| 证券列表(全市场代码/名称/拼音/上市退市日期)                       | 截止 2025-12-31 的完整列表        | 2022年            | 真实数据 |
| ST 标记(ST / *ST)                                                 | 2023-01-01 ~ 2025-12-31           | 2022年            | 真实数据 |
| 涨跌停价                                                          | 2023-01-01 ~ 2025-12-31           | 2022年            | 真实数据 |
| 复权因子(adjust)                                                  | 2023-01-01 ~ 2025-12-31           | 2022年            | 真实数据 |

#### 2.4.2. 标的构成(105 个)

100 个核心标的 + 5 个分红除权代表性标的。

- 每类至少 5 个标的(避免单点)
- 每类覆盖不同交易所(沪深北)
- 每类覆盖不同行业(避免行业特异性)
- 具体清单存于 `tests/assets/*/universe.json`(*意味着 unit/e2e，下同)

| 类别                                       | 数量    | 覆盖的 AC 边界                             |
| ------------------------------------------ | ------- | ------------------------------------------ |
| 普通活跃股                                 | 50      | 基线场景                                   |
| ST / *ST                                   | 10      | FR-015 `is_st`、FR-140 涨跌停 ±5%          |
| 新 IPO(2023-01-01 ~ 2025-12-31 内上市)     | 10      | FR-015 `days_since_ipo` 边界、上市首日规则 |
| 已退市(2023-01-01 ~ 2025-12-31 内退市)     | 10      | FR-015 `stocks_listed` 退市边界            |
| 创业板/科创板(±20% 涨跌停)                 | 10      | FR-140 涨跌停规则差异                      |
| 长期停牌(2023-2025 内有过停牌 ≥5 个交易日) | 10      | FR-170 停牌规则                            |
| 分红/除权(2023-2025 内有分红送股事件)      | 5       | FR-290 复权与除权                          |
| **合计**                                   | **105** | —                                          |


### 2.5. 环境构建

#### 2.5.1. 拉取脚本

位置:`tests/assets/*/scripts/build_env.py`

功能:
- 调用 tushare API 拉取上述数据
- 调用 qmt 临时抓取/数据合成 30m + tick(2 天)
- 写入本地 parquet / 数据库
- 输出 `env_manifest.json` 记录:数据范围、标的清单、生成时间(用于追溯)

#### 2.5.2. 校验脚本

位置:`tests/assets/*/scripts/validate_env.py`

校验内容:
- 完整性:每个标的的日线条数应 ≈ 实际交易日数(±5 容忍因停牌)
- 一致性:OHLCV 字段无空值;ST 标记与涨跌停价一致
- 范围:数据起止日期在预期范围内
- 抽样:对随机 5 个标的随机抽 5 天,人工核对(tushare 网页版/行情软件)

#### 2.5.3. 快照与版本

- 数据存储在 `tests/assets/*/fixtures/data/`
- `env_manifest.json` 记录版本,CI 中校验 "测试数据版本 = 预期版本"
- 数据不可变;更新数据需新版本号 + 重新走 §2.5 环境构建流程

### 2.6. 环境使用接口

#### 2.6.1. 测试代码加载环境

测试代码通过 fixture 加载环境(伪代码示例):

```
@pytest.fixture(scope="session")
def strategy_env():
    """加载测试环境;若 env_manifest 版本不匹配则报错"""
    env = load_env("tests/assets/*/...")
    assert env.manifest.version == EXPECTED_VERSION
    return env
```

测试代码访问环境的方式(示例)

| 访问对象      | 接口                                                                         |
| ------------- | ---------------------------------------------------------------------------- |
| 行情数据      | `env.get_bars(asset, frame_type, start, end)`                                |
| 交易日历      | `env.is_trade_day(dt)` / `env.get_trade_dates(start, end)`                   |
| 证券列表      | `env.stocks_listed(date)` / `env.is_st(asset, date)` / `env.get_name(asset)` |
| 30m/tick 数据 | `env.get_bars(asset, "30m", date)` / `env.get_ticks(asset, date)`            |
| 已加载策略    | `env.strategies`(由 §3 中 ground truth 使用)                                 |

#### 2.6.2. 环境生命周期

| 阶段 | 行为                                             |
| ---- | ------------------------------------------------ |
| 创建 | `build_env.py` 一次性产出(env_manifest 锁定版本) |
| 复用 | CI 与本地都使用同一份 fixtures,不重新拉取        |
| 隔离 | 各测试共享 session 级 fixture;互不修改           |


---

## 3. Ground Truth 方法

Ground Truth 脚本由测试工程师完成。

### 3.1. 总则

**不硬编码期望值**。所有 ground truth 由**独立脚本**在测试运行时计算:

| 类型                                                                 | 独立脚本来源                                |
| -------------------------------------------------------------------- | ------------------------------------------- |
| 算法正确(双均线交叉、风控触发、撮合成交价、T+1、涨跌停)              | **手算**:编写显式的小脚本(如 §3.2/3.3/3.5)  |
| 评估指标(Sharpe / Sortino / Calma / 最大回撤 / 胜率 / 盈亏比 / 年化) | **第三方库 empyrical**(独立实现,非参考实现) |
| 简单规则(是否 ST、是否交易日)                                        | **数据本身**:tushare 历史数据作为单一真相源 |

> 关键设计:ground truth 是**可重算的脚本**,不是文档化的固定值。测试运行时调用同一份数据 + ground truth 脚本,与框架输出对比。

#### Ground Truth 隔离（强制规则）

为防止"期望值 = 被测实现的输出"导致的循环验证（§1.3 作伪模式 #6），ground truth 脚本必须满足以下强制约束：

1. **代码位置**：所有 ground truth 脚本统一存放于 `tests/ground_truth/` 目录（unit/e2e 共享）
2. **导入禁忌**：`tests/ground_truth/**/*.py` **禁止** `import quantide.*`（含子模块）；CI 静态检查违反则阻塞 merge
3. **允许依赖**：仅可使用 `polars` / `pandas` / `numpy` / `empyrical` / 标准库 / 测试数据文件（parquet / json）
4. **数据访问**：通过直接读取 `tests/assets/*/fixtures/data/` 中的 parquet 文件获得行情/日历/证券，**不**经由被测框架的 SDK
5. **审查归口**：ground truth 脚本变更需由测试负责人审查；与对应 AC 的语义一致性是审查重点

### 3.2. 撮合 ground truth

**场景**:1 只标的 / 1 个交易日 / 1 个订单

| 测试点                      | 手算方法                                                              |
| --------------------------- | --------------------------------------------------------------------- |
| cheat-on-close 成交价       | T 日收盘价(直接查日线)                                                |
| 次日开盘成交价              | T+1 open(直接查日线)                                                  |
| 涨跌停不撮合                | T+1 open == up_limit → 买单不撮合;T+1 open == down_limit → 卖单不撮合 |
| 限价单是否在 [low, high] 内 | T+1 low ≤ price ≤ T+1 high                                            |
| 数量取整(向下,100 整倍)     | 手算:1500 → 1500, 1450 → 1400, 99 → 失败                              |
| 印花税 / 佣金               | 手算公式(见 FR-180)                                                   |

**测试做法**:
- 从测试数据挑出代表性的 1 只标的 1 天
- 跑框架的回测,捕获实际成交价/数量/费率
- 与 ground truth(手算)对比,容差 0.01 元 / 0.01%

### 3.3. 回测 ground truth

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

### 3.4. 评估指标 ground truth

| 指标     | 来源                                                          |
| -------- | ------------------------------------------------------------- |
| Sharpe   | empyrical.sharpe_ratio(returns)                               |
| Sortino  | empyrical.sortino_ratio(returns)                              |
| Calma    | empyrical.calmar_ratio(returns)                               |
| 最大回撤 | empyrical.max_drawdown(returns)                               |
| 胜率     | 手算:盈利交易数 / 总交易数                                    |
| 盈亏比   | 手算:平均盈利 / 平均亏损                                      |
| 年化收益 | empyrical.annual_return(returns) 或手算 `(1+total)^(252/n)-1` |

**测试做法**:
- 跑框架回测,捕获 returns 序列(由框架导出,可从回测结果 JSON 读取)
- 调用 empyrical 计算各项指标
- 对比框架计算的指标值
- 容差:相对误差 < 1e-6

### 3.5. 风控 ground truth

#### 3.5.1. 成本止损

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

#### 3.5.2. 回落卖出

**场景**:当日 +5%, 5 分钟内 -2%

**手算**:
- 触发条件:日内 high 达到 m%,随后 n 分钟内跌幅 > k%
- 取 tick 数据,手算日内最大涨幅与最大回撤

**测试做法**:
- 输入当日的 tick 数据
- 跑框架,捕获触发事件
- 与手算对比

### 3.6. SDK 元数据 ground truth

#### 3.6.1. 交易日历

- **单一真相源** = 测试数据中的交易日历 parquet
- 框架调用 `is_trade_day(dt)` / `get_trade_dates(start, end)` → 与 parquet 直接查询对比
- 容差:0

#### 3.6.2. 证券列表

- **单一真相源** = 测试数据中的证券列表 parquet
- 框架调用 `stocks_listed(date)` / `is_st(asset, date)` / `days_since_ipo(asset, date)` → 与 parquet 对比

---

## 测试范围

本测试计划对应同级目录下 spec.md 文档、以及它导入的其它同级 spec 文档中，所有『有效需求』、『可测试性』和『是否已决定』均为绿灯的需求。

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

---

## 验收标准

1. 单元测试通过率95%以上
2. Story和 Spec 中的用户场景全覆盖并且通过。


---


## 4. 附录 — 相关文档

- [spec.md](./spec.md) — 策略框架 spec
- [acceptance.md](./acceptance.md) — 验收标准
- [../v0.2-002-ui/spec.md](../v0.2-002-ui/spec.md) — UI spec
- empyrical — 第三方评估指标库(https://github.com/quantopian/empyrical)
