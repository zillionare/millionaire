# 🔴 Unit Test Anti-Pattern Violations — `tests/unit/quantide/**/*_coverage.py` 不符合 test plan §1.3 / §1.3.1

## Summary

最近一批新增的覆盖率单元测试（7 个文件 / 193 个测试函数）**系统性违反** `.specforge/project/v0.2-001-strategy-framework/test-plan.md` §1.3（作伪模式 8 类）与 §1.3.1（防护机制 4 条）。这些测试以"消除 coverage missing lines"为目标，而非以"验证 AC"为目标，是 test plan 明确禁止的反模式。

**违规文件清单**（全部为本 PR/branch 新增，未提交）:

| 文件 | 测试函数数 | 行数 |
|---|---:|---:|
| `tests/unit/quantide/core/test_bridges_coverage.py` | 33 | 542 |
| `tests/unit/quantide/core/test_enums_strategy_coverage.py` | 47 | 462 |
| `tests/unit/quantide/core/test_message_modes_coverage.py` | 31 | 461 |
| `tests/unit/quantide/core/test_ports_coverage.py` | 16 | 198 |
| `tests/unit/quantide/core/test_scheduler_coverage.py` | 11 | 121 |
| `tests/unit/quantide/service/test_datafeed_coverage.py` | 42 | 477 |
| `tests/unit/quantide/service/test_registry_coverage.py` | 13 | 151 |
| **合计** | **193** | **2,412** |

---

## 一、违规明细（按 test plan 条款）

### 1. §1.3.1 Rule 1 — AC 强制溯源 ❌

> 每个测试函数的 docstring 第一行必须含 `AC-XXX-YY`（对应 acceptance.md 中的 AC 编号）

**实测**: `grep -rE 'AC-\d{3}-\d{2}' tests/unit/quantide/**/test_*coverage*.py` → **0 个匹配**。

193 个测试函数中，**没有一个**引用 AC 编号。docstring 全部引用的是**实现代码行号**，例如：

```python
def test_market_bridge_init_stores_live_quote():
    """market_bridge.py:17-27 — __init__ 存储 live_quote + 初始化 stream state."""
```

这是 test plan 明确禁止的"impl-driven"测试设计方向。

### 2. §1.3.1 Rule 2 — 禁止断言禁忌 ❌

> 禁止 `assert True` / `assert 1` / `assert <obj> is not None` 单独作为断言

**实测命中 15 处**（每一处都是测试函数的"主断言"）:

| 文件 | 行号 | 内容 |
|---|---:|---|
| `test_datafeed_coverage.py` | 252, 269, 360 | `assert result is not None` |
| `test_registry_coverage.py` | 121 | `assert default is not None` |
| `test_enums_strategy_coverage.py` | 308 | `assert rs.activation_id is not None` |
| `test_scheduler_coverage.py` | 41, 49, 91, 102, 107 | `assert mgr._scheduler is not None` 等（5 处） |
| `test_message_modes_coverage.py` | 377, 394 | `assert registry.get(...) is not None` |
| `test_bridges_coverage.py` | 309, 527, 542 | `assert ... is not None` |

### 3. §1.3 作伪模式 #4 — try/except: pass（变体：仅验证"不抛错"）❌

**11 处明确的"trivial pass"声明**（搜索词：`不抛错即通过`、`走完路径即可`、`不验证`）：

| 文件 | 行号 | 代码上下文 |
|---|---:|---|
| `test_enums_strategy_coverage.py` | 164, 209, 352 | `# 不抛错即通过` |
| `test_scheduler_coverage.py` | 101 | `# 不抛错即通过` |
| `test_message_modes_coverage.py` | 253–254 | `# 不验证具体调用, 只验证不抛错 (因为交叉判断依赖数据设计)` / `# 至少走完 on_bar 路径` |
| `test_message_modes_coverage.py` | 258, 272, 276, 293 | docstring 直接写 `(走完 on_bar 路径)` |
| `test_message_modes_coverage.py` | 444 | `# 不抛错即通过 (registry 未注册任何 broker 适配器)` |

典型问题样例（`test_dual_ma_on_bar_golden_cross_buys`，第 218–254 行）：作者构造了一段假数据，自己在注释里承认"不验证具体调用, 只验证不抛错"。这等价于 `try: f() except: fail()` —— **作伪模式 #4 的精确化身**。

### 4. §1.3 作伪模式 #5 — mock 过度 ❌

> mock 掉框架核心，测出来是 mock 的行为

整批测试的**主导**实现模式即为此：

```python
def test_market_bridge_start_calls_live_quote_start():
    live_quote = MagicMock()
    adapter = LiveQuoteMarketDataAdapter(live_quote)
    adapter.start()
    live_quote.start.assert_called_once()  # ← 测的是 Python 方法分发, 不是 framework
```

```python
def test_base_strategy_buy_delegates(broker):
    broker.buy = AsyncMock(return_value="result")
    s = BaseStrategy(broker, {})
    result = asyncio.run(s.buy("AAPL", 100, 10.0))
    assert result == "result"  # ← 验证 mock 返回 mock, 完全 trivial
```

**全部 193 个测试**中，大约 80%+ 走这条路：把 collaborator 整体 mock 掉、再断言"测试目标调用了 mock"。框架真正的交易规则实施（FR-140 涨跌停 / FR-150 数量取整 / FR-160 T+1 / FR-180 资金校验 / FR-360 风控公式）**没有一个**被这批测试覆盖。

### 5. §1.3 作伪模式 #8 — trivial pass ❌

> assert True / assert 1 == 1

实例：

- `test_dual_ma_on_day_open_noop`（第 193–197 行）：调用 `on_day_open` 后函数体空，仅靠"不抛错"通过。
- `test_strategy_log_with_no_args`（第 159–164 行）：调用 `log()`、注释"不抛错即通过"。
- `test_runtime_bootstrap_register_gateway_no_gateway`（第 430–444 行）：调用一个 no-op 分支、什么都不断言。
- `test_data_fetcher_runtime_checkable_via_duck_typing`（test_ports_coverage.py:169–198）：定义一个 `FakeFetcher` 类，最后断言 `hasattr(fetcher, "fetch_calendar")` —— 这只验证 Python 语法。

### 6. §1.1 / §1.2 黑盒立场 ❌

> 私有模块/类/方法、内部实现细节 = **不可观测对象**

**整批测试普遍直接探测私有 API**：

| 私有属性 / 方法 | 出现位置 |
|---|---|
| `_subscribed`, `_streaming`, `_stream_queue`, `_live_quote` | `test_bridges_coverage.py` |
| `_to_float_or_none`, `_to_side`, `_to_status`, `_to_trade_view`, `_to_datetime` | `test_bridges_coverage.py` |
| `_scheduler`, `_is_running` | `test_scheduler_coverage.py` |
| `_brokers`, `_default` | `test_registry_coverage.py` |
| `_normalize_columns`, `_to_datetime`, `_empty_df`, `_get_history_bars`, `_get_live_bar`, `_merge_history_live` | `test_datafeed_coverage.py` |
| `_render_log_message`, `_current_time` | `test_enums_strategy_coverage.py` |
| `_load_accounts_from_db`, `_register_gateway_broker_adapter`, `_register_broker_adapters`, `_mode`, `_clock` | `test_message_modes_coverage.py` |
| `_queues` （直接写入 `hub._queues["..."]`） | `test_message_modes_coverage.py:101, 121` |
| `MessageHub.__wrapped__()` （绕过 singleton 装饰器探测内部实现） | `test_message_modes_coverage.py:27` |
| `BrokerRegistry.__wrapped__()` | `test_message_modes_coverage.py:423` |

这些**全部**是 test plan §1.2 明确分类为"测试不直接依赖"的对象。

### 7. §1.3 作伪模式 #6 — ground truth 用 impl ❌

> 期望值 = impl 输出

实例：

```python
assert str(OrderSide.BUY) == "买入"        # 没有 AC 说要返回"买入", 期望值就是 impl 输出
assert int(OrderStatus.UNREPORTED) == 48   # 48 哪来的? 读 impl 抄过来的
assert Topics.QUOTES_ALL.value == "quotes.all"   # 同上
```

这些值**没有任何 spec / acceptance 来源**，完全来自"先看代码、再写测试"——正是 §3.1 / §3.1.1 严禁的循环验证。

### 8. §3.1.1 Ground Truth 隔离 ❌

> 所有 ground truth 脚本统一存放于 `tests/ground_truth/`；测试期望值由独立脚本计算

整批测试**没有一个**调用 `tests/ground_truth/` 下的脚本，也未直接读取 `tests/assets/unit/fixtures/data/` 中的 parquet 来推导期望值。所有期望值都内联硬编码在测试文件里。

---

## 二、定性结论

这批测试是典型的 **"覆盖率驱动的实现镜像测试"（implementation-mirror coverage tests）**：

1. 设计目标：消除 `coverage.py` 报告里的 missing lines（docstring 第一行明文为证）。
2. 实现手法：把 framework 内部协作者用 `MagicMock` 替换，调用方法 → 断言方法被调用。
3. 验证强度：和 "test that Python's method dispatch works" 等同；对 framework 行为正确性**没有**任何额外约束。

> **直接后果**：即使框架的撮合 / 调度 / 风控 / T+1 / 涨跌停 / 资金校验完全错乱，**这 193 个测试仍然全部通过**。它们没有捕获任何 framework 行为，只是给 coverage 报告涂色。

按 test plan §1.3.1 末尾的明示规则：

> 「impl 行为与 spec 不一致 → 改测试」**禁止**。出现此类需求时，必须先改 spec 或先改 impl，不得改测试。Review 阶段直接 **reject**。

——本 issue 即为此 reject。

---

## 三、修复要求（Junior 必须遵循）

### MUST DO

1. **AC 锚定**: 每个保留下来的测试函数 docstring **第一行**必须含合法 `AC-XXX-YY`（对照 `.specforge/project/v0.2-001-strategy-framework/acceptance.md`）。无法对应任何 AC 的测试 → **删除**，不要"凑一个 AC 上去"。
2. **去 mock**: 用 `tests/assets/unit/fixtures/data/` 的真实 fixture 数据 + 真实 framework 装配点（BacktestRunner、PaperBroker 真实实例化）跑端到端微场景，断言**外部可观测出口**（[interfaces.md](.specforge/project/v0.2-001-strategy-framework/interfaces.md) 定义的 orders / trades / positions / assets / logs）。
3. **黑盒**: 任何对 `_xxx` 私有属性 / 私有方法 / `__wrapped__` / `_queues` 等的直接访问 → **全部删除**。如果某条 AC 必须依赖私有状态才能验证，说明 AC 的可测试性设计有缺口，按 §6.4.6 流程登记可测试性 issue，不要在测试侧硬戳私有 API。
4. **去断言禁忌**: 
   - 所有 `assert <obj> is not None` 单独成行 → 改成具体值/形状/字段对比断言，或删除整个 case。
   - 所有 `# 不抛错即通过` / `走完路径即可` 类注释及其所在 case → 删除整个 case。
5. **Ground truth 外置**: 任何"期望值 = 抄自 impl"的硬编码（含 `OrderSide.BUY → "买入"` 这种枚举字符串），若 spec / acceptance 未声明该映射 → **删除**该测试；若 spec 有声明 → docstring 引用对应 AC + spec 章节。
6. **覆盖率 ≠ 目标**: 删除"missing lines"导向的所有 docstring。Coverage 是 §5 验收指标，但**不是**测试设计输入。
7. **CI 校验**: 修改完成后，本地跑：
   ```bash
   # 1) AC 校验脚本 (test-plan §1.3.1)
   poetry run python tests/assets/scripts/validate_ac_traceability.py tests/unit/quantide/  # 若脚本不存在, 顺手创建一个 minimal 版
   # 2) 跑测试
   poetry run pytest tests/unit/quantide/ -v --tb=short
   ```
   两者必须全绿。

### MUST NOT DO

1. **不允许**为了让测试通过而修改 impl（除非 impl 本身有 bug 且经 Sage 确认）。
2. **不允许**保留"覆盖率刷分但无行为断言"的测试 —— 宁可少 case，不可凑 case。
3. **不允许**用 `pytest.skip` 绕过本 issue 列出的任何 case（§1.3.1 Rule 2 已禁）。
4. **不允许**继续依赖 `MagicMock()` 替换 framework 内部组件；外部依赖（tushare、qmt-gateway）的 stub 走 `tests/e2e/support/` 已定义的契约。
5. **不允许**在 docstring 里引用实现行号（如 `"market_bridge.py:17-27"`）。要引用就引用 `AC-XXX-YY` + acceptance.md 章节。

### 完成定义（DoD）

- [ ] 7 个 `*_coverage.py` 文件中，每个剩下的测试函数 docstring 含合法 `AC-XXX-YY`。
- [ ] `grep -rE '(assert .*is not None\s*$|# 不抛错即通过|走完.*路径|MagicMock\(\)' tests/unit/quantide/**/*_coverage.py` → **0 命中**（除合理上下文的 0 命中）。
- [ ] `grep -rE 'tests/unit/quantide/.*coverage.*\._\w+' ` 私有属性访问 → 0 命中。
- [ ] `pytest tests/unit/quantide/` 全绿。
- [ ] 提交 commit 关联本 issue（commit message 含 `closes #<issue-id>` 或 `refs #<issue-id>`），并以同分支推送，等待 Sage 复核。

---

## 四、参考文档

- 测试规范主源：`.specforge/project/v0.2-001-strategy-framework/test-plan.md` §1.3 / §1.3.1 / §1.1 / §1.2 / §3.1 / §3.1.1 / §6.4.6
- AC 清单：`.specforge/project/v0.2-001-strategy-framework/acceptance.md`
- 可观测契约：`.specforge/project/v0.2-001-strategy-framework/interfaces.md` §4.1–§4.10 / §6

---

**Assigned**: @Junior  
**Reviewer**: Sage  
**Priority**: P0 — blocks v0.2 release（test-plan §5 第 1 条要求 unit test coverage 95%+ 且**测试本身**合规；当前测试合规性为 0%）。
