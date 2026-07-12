# Code Review — 19:00 以来的变更

- **审阅范围**: `97b589e..HEAD`（14 commits，+3001/-78 lines）
- **审阅重点**: FR 完成度、测试可信度、e2e/unit 分层、代码风格
- **测试运行**: 74 passed, 2 skipped（.venv Python 3.12）

---

## 1. FR 完成度评估

### FR-010 BaseStrategy — 完成度 60%

| AC | 覆盖 | 评价 |
|---|---|---|
| AC-010-01 类型分层 | ⚠️ | 仅 `issubclass` 检查；未验证框架实际识别 |
| AC-010-02 生命周期钩子 | ✅ | 验证存在性、async、签名、on_bar 不在基类 |
| AC-010-03 辅助接口 | ✅ | default_config static + 返回 {} + log/record 存在 |
| AC-010-04 模式无关 | ✅ | 验证无 get_mode/mode/current_mode 方法 |

**缺失**: 无端到端生命周期测试（init→on_start→on_day_open→...→on_stop 完整调用链）。当前只验证"钩子存在"，不验证"钩子按顺序被调度器调用"。

### FR-011 DayStrategy — 完成度 30%

| AC | 覆盖 | 评价 |
|---|---|---|
| AC-011-01 类型层接受 | ❌ 欺骗性 | 仅 `issubclass(MyDayStrategy, BaseStrategy)`，未提交 BacktestRunner |
| AC-011-02 on_bar 触发 | ⚠️ | 仅签名检查，且注释承认 impl 有 3 参数冲突 |
| AC-011-03 数据接口 | ❌ 欺骗性 | `has_get_bars or has_get_history`，两者都接受 |
| AC-011-04 账户隔离 | ⚠️ | 仅验证 broker 有 cash/positions 属性 |

**缺失**: 无实际回测运行（提交策略→跑回测→验证结果）。TestFixtureIntegration 验证 fixture 数据可被消费，但不验证框架行为。

### FR-012 LiveStrategy — 完成度 20%

| AC | 覆盖 | 评价 |
|---|---|---|
| AC-012-01 不可回测 | ❌ 不可测 | LiveStrategy 类不存在；测试仅验证 BacktestRunner.run 签名 |
| AC-012-02 多周期数据 | ⚠️ | 验证 `frame_type` 参数存在；不验证 30m 实际可用 |
| AC-012-03 on_day_open | ✅ | 签名正确 |
| AC-012-04 交易接口一致 | ✅ | Broker 有全部必需方法 |

**核心缺口**: DayStrategy / LiveStrategy / RiskStrategy 三个子类均未实现（interfaces.md C4），FR-012/013 结构性不可测。

### FR-013 RiskStrategy — 完成度 10%

| AC | 覆盖 | 评价 |
|---|---|---|
| AC-013-01 无独立账户 | ⚠️ | 验证 BaseStrategy 无 sell_host_position（反向断言） |
| AC-013-02 只卖不买 | ⚠️ | 验证 Broker 有 sell 方法（与 RiskStrategy 无关） |
| AC-013-03 只读持仓 | ✅ | Broker.positions 是 property |
| AC-013-04 tick 数据 | ⚠️ | 仅验证 synthetic fixture 文件存在 |
| AC-013-05 宿主绑定 | ❌ | 明确文档化为不可测（RiskStrategy 不存在） |

**评价**: 测试基本是"验证 RiskStrategy 不存在的现状"，不是真正的 AC 验证。TestKnownGaps 类诚实记录了缺口。

### FR-014 交易日历 — 完成度 90% ✅

| AC | 覆盖 | 评价 |
|---|---|---|
| AC-014-01 交易日判断 | ✅ | 真实数据：交易日/周末/国庆 |
| AC-014-02 交易日移位 | ✅ | 跨周末跳过、offset=0 |
| AC-014-03 计数与列表 | ✅ | 排序、start>end 异常、start==end |
| AC-014-04 模式无关 | ✅ | 幂等性验证 |

**问题**: AC-014-01 边界"超出数据范围→抛异常"未覆盖。TestOutOfRange 验证 `2099-01-25 → False`，但 acceptance 期望抛异常。这是 **spec vs impl 冲突**（当前实现返回 False 而非抛异常）。

### FR-015 证券列表 — 完成度 85% ✅

| AC | 覆盖 | 评价 |
|---|---|---|
| AC-015-01 已上市列表 | ✅ | exclude_st 过滤、远古日期空列表 |
| AC-015-02 ST/上市天数 | ✅ | 已知 ST → True；上市前 → 0 |
| AC-015-03 名称查询 | ✅ | 已知资产返回名称 |
| AC-015-04 模式无关 | ✅ | 幂等/确定性 |

**缺失**: AC-015-02 "无效证券代码→抛异常" 未测试（当前返回 False 而非异常）。AC-015-03 "无效代码→抛异常" 同样缺失。

### FR-020 策略发现 — 完成度 40%

| AC 组 | 覆盖 | 评价 |
|---|---|---|
| AC-020-01 识别规则 | ⚠️ | 仅 BaseStrategy 子类（spec 已改为三类子类）|
| AC-020-02 文件范围 | ✅ | 子目录不递归 |
| AC-020-03 名称与描述 | ⚠️ | 仅 name=cls.__name__；未测 __display_name__ |
| AC-020-04~06 元数据 schema | ❌ | 完全未测（无 StrategyMetadata 结构验证）|
| AC-020-07 模式无关 | ❌ | 未测 |
| AC-020-08 容错（目录） | ✅ | 目录不存在→无用户策略 |
| AC-020-09 容错（单文件） | ✅ | syntax error 不阻塞 |
| AC-020-10 容错（类级） | ⚠️ | 仅 all-fail 场景 |
| AC-020-11~15 | ❌ | 完全未测 |

**关键问题**: 测试使用 `strategy_loader.scan_and_cache()` 返回 `dict[str, StrategyInfo]`，但 spec/acceptance 定义的是 `EnumerationResult(strategies + diagnostics)`。**测试的 API 与 spec 不匹配**。

---

## 2. 测试可信度（欺骗性分析）

### 未发现直接作弊（无 mock 注入期望值）

所有测试使用真实代码路径，无 `MagicMock(return_value=expected)` 式作弊。

### 但存在大量"结构性通过"

以下测试 **永远会通过**，因为它们断言的是代码结构而非行为：

| 文件 | 测试 | 断言 | 问题 |
|---|---|---|---|
| FR-011 | `test_dayasstrategy_subclass_accepted` | `issubclass(MyDayStrategy, BaseStrategy)` | 自己定义的类当然是 BaseStrategy 子类 |
| FR-011 | `test_get_bars_method_signature` | `hasattr(get_bars) or hasattr(get_history)` | 总有一个为 True |
| FR-011 | `test_get_bars_signature_day_strategy` | `has_get_bars or has_get_history` | 同上 |
| FR-012 | `test_backtest_runner_inspects_strategy_type` | `"strategy_cls" in params or len(params) >= 2` | run 方法至少有 2 个参数 |
| FR-013 | `test_no_sell_host_position_method_on_base_strategy` | `not hasattr(BaseStrategy, "sell_host_position")` | BaseStrategy 确实没有 |
| FR-013 | `test_broker_provides_sell_for_risk_strategy` | `hasattr(Broker, "sell")` | Broker 有 sell，但与 RiskStrategy 无关 |
| HTTP | `test_accounts_endpoint_reachable` | `200 <= status < 600` | **任何响应都通过** |
| HTTP | `test_positions_endpoint_accessible` | `status in (200, 400, 422, 500)` | 同上 |

**统计**: 76 个测试中约 **15~20 个（20~26%）** 是"结构性通过"——断言太弱或验证的是已知事实。

### FR-013 整体可信度最低

7 个测试中：
- 2 个验证 BaseStrategy 缺少方法（与 RiskStrategy 无关）
- 1 个验证 Broker 有 sell（与 RiskStrategy 无关）
- 1 个验证 property 类型
- 1 个验证 fixture 文件存在
- 2 个明确文档化为"不可测"

**结论**: FR-013 的测试全部是占位符，无实际验证价值。诚实但无用。

---

## 3. E2E / Unit 分层

### 分层意图正确

test-plan.md §4.0 明确定义了边界：
> E2E 测试**不允许** mock 框架内部实现

实际上没有使用 mock。

### 但黑盒程度不一致

| 测试文件 | 黑盒程度 | 评价 |
|---|---|---|
| test_fr_010 | 灰盒 | 使用 `inspect` 检查类签名、`BaseStrategy.__dict__` |
| test_fr_020 | ✅ 黑盒 | 写文件→调用 enumerate→断言结果 |
| test_fr_011 | 灰盒 | `inspect.signature` + `hasattr` 检查 |
| test_fr_012 | 灰盒 | 同上 |
| test_fr_013 | 灰盒 | 同上 |
| test_fr_014 | ✅ 黑盒 | 调用 Calendar API + 真实数据 |
| test_fr_015 | ✅ 黑盒 | 调用 StockList API + 真实数据 |
| test_http_broker_api | ✅ 黑盒 | HTTP 请求 → 断言响应 |

**真正黑盒的**: FR-014、FR-015、HTTP 集成、FR-020（部分）
**名义黑盒实际灰盒**: FR-010、FR-011、FR-012、FR-013 — 大量 `inspect.signature` 和 `hasattr` 检查

### 灰盒检查的问题

`inspect` 检查本质上是验证 **API 签名契约**，而非 **API 行为**。对于黑盒测试，应该：
- ✅ 调用 API → 验证返回结果/副作用
- ⚠️ 检查签名 → 仅在类/子类不存在时作为临时手段

### 位置组织

tests/e2e/ 目录与现有 tests/e2e/{backtest,live,paper,web} 并行，未冲突。test-plan.md 已更新路径从 `tests/strategy-framework/` 到 `tests/e2e/`。

---

## 4. 代码风格

### 优点
- 清晰的 docstring 标注 FR/AC 对齐
- 分隔符注释按 AC 分区
- `pytest.skip()` 标注已知缺口（不假装通过）
- generate_synthetic.py 确定性数据（固定 seed）

### 需修正

| 位置 | 问题 |
|---|---|
| test_fr_011 L38 | `test_dayasstrategy_subclass_accepted` → 拼写错误（双 a） |
| test_fr_015 L38 | `StockList.__init__(StockList())` 调用两次初始化（fragile hack）|
| test_fr_011 L74 | 注释说"spec: 纯时序"但断言 `"tm" in params`（现有 impl 有 3 参数） |
| test_fr_020 L67 | `strategy_loader.scan_and_cache()` 返回 `dict` 而非 spec 定义的 `EnumerationResult` |
| test_http L185 | `200 <= status < 600` 太宽（任何 HTTP 响应都通过） |

### 源码变更

3 处修改，均合理：

1. **strategy.py**: 删除 `BaseStrategy.on_bar`（spec C1）— **破坏性变更**，需确认 DualMAStrategy 等不受影响
2. **calendar.py**: 添加 `count_trading_days` 别名 + `start > end` 校验 — 好改动
3. **stocks.py**: 修复 `stocks_listed(exclude_st=False)` 始终走 daily_bars 路径 — **真实 bug fix**（之前 exclude_st=False 走 StockList 全量，不检查日期）
4. **discovery.py**: `os.walk` → `iterdir()`（不递归）— spec AC-020-02 对齐

---

## 5. 总结

### 评分

| 维度 | 评分 | 说明 |
|---|---|---|
| FR-014 日历 | ⭐⭐⭐⭐ | 最佳：真实数据、行为验证、边界覆盖 |
| FR-015 证券 | ⭐⭐⭐⭐ | 优秀：真实数据、行为验证 |
| FR-020 发现 | ⭐⭐⭐ | 中等：行为测试为主，但覆盖不足、API 不匹配 spec |
| HTTP 集成 | ⭐⭐ | 弱：端点可达性验证，断言太宽 |
| FR-010 基类 | ⭐⭐ | 弱：签名检查为主 |
| FR-011 日线 | ⭐ | 很弱：自证子类、无回测运行 |
| FR-012 实时 | ⭐ | 很弱：LiveStrategy 不存在，全部占位 |
| FR-013 风控 | ⭐ | 很弱：RiskStrategy 不存在，全部占位 |

### 核心发现

1. **三类策略子类（DayStrategy/LiveStrategy/RiskStrategy）是最大阻塞项**。没有它们，FR-011/012/013 的所有行为测试都无法编写。interfaces.md §6.1 C4 已识别此冲突，但未排期。

2. **FR-020 测试使用了与 spec 不匹配的 API**。spec 定义 `EnumerationResult(strategies + diagnostics)`，测试使用 `dict[str, StrategyInfo]`。这意味着要么 spec 需要修订，要么测试需要重写。

3. **源码改动质量高**。discovery.py 不递归修复、stocks.py exclude_st 修复、calendar.py 别名添加都是有价值的 bug fix/spec 对齐。strategy.py 删除 on_bar 是正确的 spec 对齐。

4. **interfaces.md 是优秀的工程产出**。590 行，结构清晰，包含冲突清单和变更记录。但它推测了 Web API URL（§2 注明"需实现层确认"）。

### 建议优先行动

1. **实现三类策略子类**（DayStrategy/LiveStrategy/RiskStrategy）— 解锁 FR-011/012/013 真实测试
2. **重写 FR-020 测试**以使用 spec 定义的 `EnumerationResult` API
3. **加强 FR-011 回测测试**：提交策略 → 跑回测 → 验证结果（ground truth §2.3）
4. **收窄 HTTP 断言**：拒绝 `200 <= status < 600` 式万能断言
