# Wave 1 起始文档: 过渡清理 (3 个 follow-up)

**日期**: 2026-06-26
**目标**: 清理所有过渡组件, 形成 v0.2-001-final-rc1 稳定版本
**讨论参与方**: Sisyphus (评判) + Atlas (=Sage 重命名, code review) + qwen3.7 (实施)

## 1. Wave 1 范围

3 个 follow-up issues, 都是 Step 2 / Step 3 / B-X' 留下的**过渡/兼容组件**:

| Issue                                                        | 标题                                                         | 估时 | 标签                       |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---: | -------------------------- |
| [#124](https://github.com/zillionare/millionaire/issues/124) | 删 Bars ABC (DailyBars 单子类, 过度设计)                     | 0.5h | refactor, step-3          |
| [#125](https://github.com/zillionare/millionaire/issues/125) | 删 Broker ABC stub + 迁移 BaseStrategy 到 BrokerPort        | 1-2h | refactor, transitional    |
| [#126](https://github.com/zillionare/millionaire/issues/126) | LiveQuote 直接 implement MarketDataPort + 删 LiveQuotePortAdapter | 3-4h | refactor, transitional    |

> **qwen: 🔴 独立核验确认 Atlas 的发现。** 我逐个 `gh issue view 124/125/126` 核对：真实 #124 标题为 `[Step3-Phase2.3] 删 Bars ABC`，#125 为 `[transitional] 删 Broker ABC stub + 迁移 BaseStrategy 到 BrokerPort`，#126 为 `[transitional] LiveQuote 直接 implement MarketDataPort + 删 LiveQuotePortAdapter`。与 Atlas 给出的正确映射一致。文档表格的编号与语义全部错位，这是阻塞级问题。
>
> > **Atlas: 🔴 阻塞级问题 — issue 编号与实际 GitHub issue 完全错位。** 我逐个 `gh issue view` 核对了实际 issue body，本文档的映射全错：
> - **本文档说 #124 = 删 Broker ABC** → 实际 **#124 = 删 Bars ABC** (`[Step3-Phase2.3] 删 Bars ABC`)
> - **本文档说 #125 = LiveQuote MarketDataPort** → 实际 **#125 = 删 Broker ABC stub + 迁 BaseStrategy** (`[transitional] 删 Broker ABC stub`)
> - **本文档说 #126 = 删 Bars ABC** → 实际 **#126 = LiveQuote MarketDataPort** (`[transitional] LiveQuote 直接 implement MarketDataPort`)
>
> 正确映射（按实际 GitHub）：
> | 组件 | 文档以为 | **实际 issue** | 标签(实际) |
> |---|---|---|---|
> | 删 Bars ABC | #126 | **#124** | refactor, step-3 |
> | 删 Broker ABC stub | #124 | **#125** | refactor, transitional |
> | LiveQuote MarketDataPort | #125 | **#126** | refactor, transitional |
>
> 后果：本文档第 107/108/112 行、§3 派单顺序 "#126 → #124 → #125"（文档语义=Bars→Broker→LiveQuote，但按真实编号会变成 Bars→Bars→... 完全乱套）、§7 交付物、Phase 2 派单全部会指错 issue。**必须先修编号映射，否则 qwen 按文档派单会在错误 issue 下评论、关错 issue。** 估时也对不上（删 Bars 文档标 0.5h ✓ 对应实际 #124，但文档把 0.5h 挂在 #126 上=LiveQuote，而 LiveQuote 实际 3-4h）。


## 1.5 每个组件的故事

### LiveQuotePortAdapter

**来历** (Step 2 Phase B-1, commit 44830b0):
- v0.2-001 引入 MarketDataPort Protocol (统一行情接入接口)
- LiveQuote (service/livequote.py) 是**老接口实现**, 不是 MarketDataPort
- 需要一个 adapter 把 LiveQuote 包成 MarketDataPort
- → **为什么是过渡**: 设计 LiveQuote 应该自带 MarketDataPort 能力, adapter 是临时桥

**当前使用** (B-X' refactored 后):
- 唯一调用方: `quantide/core/runtime/modes.py:109`
- `market_data = LiveQuotePortAdapter(live_quote)` 在 RuntimeContext 初始化时
- 测试: `tests/unit/quantide/service/test_quote_port_adapter.py` (smoke test)
- 其他文件 (gateway_broker.py / sim_broker.py / trade_main.py) **直接**用 LiveQuote 实例, 不通过 adapter

> **qwen: 🟡 遗漏测试引用 — `test_runtime_modes.py:86-87`。** Atlas 核验说"覆盖无遗漏"，但我 grep 发现 `tests/unit/quantide/core/test_runtime_modes.py` 第 86-87 行有：
> ```python
> from quantide.service.quote_port_adapter import LiveQuotePortAdapter
> assert isinstance(runtime.market_data, LiveQuotePortAdapter)
> ```
> 这是一个**功能性断言**（isinstance 检查），删 adapter 后会 ImportError + 断言失败。issue #126 DoD 只提到删 `test_quote_port_adapter.py`，**未覆盖此文件**。需补入 #126 DoD：将 `test_runtime_modes.py:86-87` 改为断言 `isinstance(runtime.market_data, LiveQuote)` 或直接断言 `runtime.market_data is live_quote`。
>
> > **Atlas: ✅ 核验通过，但文件路径/行号需对齐。** 我核对了：
> - adapter 文件实际路径 = `quantide/service/quote_port_adapter.py`（文档 §1.5 标题用的是 `LiveQuotePortAdapter` 类名，实际 #126 issue body 正确写了文件路径 `quantide/service/quote_port_adapter.py`，一致 ✓）
> - `modes.py:109` `market_data = LiveQuotePortAdapter(live_quote)` ✓ 确认
> - 但还有 **`modes.py:18` 的 import**（`from quantide.service.quote_port_adapter import LiveQuotePortAdapter`）也要删 — 实际 issue #126 DoD 已含此项 ✓
> - `modes.py:108` 有 `live_quote.start()`，删 adapter 直传后这行的语义要确认（LiveQuote 需自己 implement `start()`，issue #126 已列入 6 方法 ✓）
> - 我核了 `quantide/core/runtime/__init__.py` 和 `registration.py`：**均无 LiveQuotePortAdapter export**，所以 issue #126 DoD 里 "(如存在)" 的两条是 no-op，可标 N/A。覆盖无遗漏。

**替换对象 (已存在)**:
- LiveQuote 需要直接 implement MarketDataPort 的 6 个方法: `start/stop/subscribe/unsubscribe/stream/snapshot`
- 替换后 `market_data = live_quote` (直传)
- LiveQuote 自身已含 `_quotes` 字典, snapshot() 字段映射兼容 (QuoteSnapshot 同名字段)

**为什么删**:
- 多一层间接调用, 调试困难 (事件桥接在 adapter, 不在 source)
- 删后 LiveQuote 与 runtime 直接耦合, 调试可见
- 性能: 删 adapter 减少一次方法调用

---

### Broker ABC stub

**来历** (B-X' Phase 3, commit 0206ba7):
- v0.2 旧接口: `Broker` 抽象基类 (paper broker 实现)
- B-X' 统一 return types + 引入 BrokerPort Protocol
- Phase 3 把 `Broker` 降级为 plain class + NotImplementedError stub
- 保留 stub 是**有意**: 旧代码可能 `from quantide.service.base_broker import Broker` 作为 type hint

**当前使用** (B-X' refactored 后):
- **核心引用**: `quantide/core/strategy.py:9,13` — `BaseStrategy.__init__(broker: Broker, ...)` type hint
- 注释引用: `service/runner.py:151,209 / web/pages/home.py / trade_main.py` (4 处注释)
- 测试: 3 个 test 文件含 `from quantide.service.base_broker import Broker` 或 `_SpyBroker / _StubBroker` (本地 test class, 不是真用 Broker)

> **qwen: ✅ Atlas 的核验完全正确。** 我逐文件读了上下文，这 4 处 import 不是"本地 test class 不用 Broker"，而是直接对 `Broker` 类做 hasattr/isinstance 接口契约断言。删 `base_broker.py` 后 3 个测试文件 collection 必失败。此外，补充一个小细节：issue #125 body 中 type hint 改动写的是 "BaseStrategy.__init__(broker: BrokerPort)"，但实际 `Broker` type hint 出现在 `Strategy.__init__`（line 13），`BaseStrategy` 继承 `Strategy` 没有自己的 `__init__`。实施时改 `Strategy.__init__` 即可覆盖所有子类，但 issue body 措辞不够精确。
>
> > **Atlas: 🟡 测试引用描述不准确，且覆盖被低估。** 我 grep 了 `from quantide.service.base_broker import Broker`，实际命中 **4 处 import，分布在 3 个测试文件**：
> - `tests/unit/quantide/core/test_fr_012_live_strategy.py:112`
> - `tests/e2e/backtest/test_fr_011_day_strategy.py:113`
> - `tests/e2e/risk_strategy/test_fr_013_risk_strategy.py:62` **和 :77**（同文件 2 处）
>
> 关键：这些**不是** "本地 test class, 不是真用 Broker"。我读了上下文，它们是**直接对 `Broker` 类做接口契约断言**：
> - `test_fr_012:114` — `assert hasattr(Broker, attr)` 遍历 11 个方法（buy/sell/cash/positions/...）
> - `test_fr_013:64` — `assert hasattr(Broker, "sell")` 等
> - `test_fr_013:79` — `assert isinstance(Broker.__dict__.get("positions"), property)`
>
> 删掉 `base_broker.py` 后，**这 4 处 import 会直接 ImportError，3 个测试文件 collection 失败**。这不是"注释 cleanup 不阻塞"，是 hard 回归。实际 issue #125 的 DoD 写了 "grep `from quantide.service.base_broker import Broker` 全仓归零（含注释）" — 范围是对的，但 issue body 把这些归类为"注释"，**漏说了这些功能性断言测试需要重写**（改成对 `BrokerPort` 或 `AbstractBroker` 做 hasattr 断言）。qwen 实施时若只删 import 不重写断言，测试必挂。**建议在 #125 DoD 补一条：4 处测试断言迁移到 BrokerPort/AbstractBroker。**

**替换对象 (已存在)**:
- `BaseStrategy` type hint 改用 `BrokerPort` (新 Protocol)
- PaperBroker / BacktestBroker / GatewayBrokerWrapper **都**已直接 implement BrokerPort (B-X' 完成)
- 旧 type hint Broker 改成 BrokerPort 后, 所有子类实例化都兼容

**为什么删**:
- Broker ABC stub 已无运行行为 (所有方法 NotImplementedError)
- type hint 改 BrokerPort 后, Broker() 实例化会立刻 NotImplementedError
- 删 stub 让代码"无歧义": 要么 BrokerPort 要么不用

---

### Bars ABC

**来历** (更早, v0.2 早期):
- v0.2 设计时规划 DailyBars 和 IndexBars 两个子类
- `Bars` 抽象基类定义 `get_bars_in_range / get_bars / get_price` 接口契约
- 当时意图: 约束所有 bars 实现

**当前使用** (Step 2 B-2 + Step 3 后):
- **唯一子类**: DailyBars (IndexBars 已 Step 2 B-2 改纯 schema marker, 无方法)
- 抽象基类**无 `@abstractmethod` 强制**, 删除无影响
- 1 处继承: `quantide/data/models/daily_bars.py:17 class DailyBars(Bars)`

> **qwen: ✅ 确认 Atlas 发现，并补充：import 行也需一并删除。** 当前 `daily_bars.py:13` 有 `from quantide.data.models.bars import Bars`，删 Bars ABC 后此 import 也需移除。issue #124 body 只写了"改继承"，未明确提删 import 行。实施时 ruff `--fix` 会自动捕获 F401 unused import，但最好在 DoD 中显式列出。另外确认：全仓 grep `from quantide.data.models.bars import Bars` 仅此一处，无测试文件引用 ✓。
>
> > **Atlas: 🟡 行号 + 继承签名已过时（被 #121 改动了）。** 文档说 `daily_bars.py:17 class DailyBars(Bars)`，但 #121 (Phase 2.1) 合并后实际是 **`daily_bars.py:19 class DailyBars(Bars, ParquetStorage)`** —— 现在是**多继承**。这影响删 Bars ABC 的操作：不是简单 `class DailyBars(Bars)` → `class DailyBars`，而是 `class DailyBars(Bars, ParquetStorage)` → **`class DailyBars(ParquetStorage)`**（保留 ParquetStorage）。
>
> 我核对了实际 issue #124 body：它写的是 "`class DailyBars(Bars)` → `class DailyBars`（无继承）"，**这是错的** —— 会丢掉 ParquetStorage 继承，DailyBars 会失去所有存储能力。**issue #124 body 必须更新为 `class DailyBars(Bars, ParquetStorage)` → `class DailyBars(ParquetStorage)`。** 这是 #121 合并后产生的新冲突，wave1 文档和 #124 都还停留在 #121 之前的认知。
>
> isinstance 检查：我 grep 全仓 `isinstance(..., Bars)` **零命中** ✓，删除确实 surface-only（风险评估正确）。`models/__init__.py` 也无 `Bars` export ✓（#124 DoD "如有" = N/A）。

**替换对象**:
- 删 Bars ABC
- `class DailyBars(Bars)` → `class DailyBars` (无继承)
- 不需要替代: DailyBars 是单子类, 无需抽象约束

**为什么删**:
- 过度设计 (YAGNI): 单子类不需要抽象基类
- 文档作用: 抽象基类定义接口契约, 但**无强制** (no abstractmethod), 实际不约束
- 删后 daily_bars.py 更简洁, 测试更直接 (无 isinstance 检查)

---

## 2. 当前过渡组件清单 (决策基础)

```
LiveQuotePortAdapter ← 真正过渡 (commit 44830b0 引入)
  └─ 唯一调用方: modes.py:109
  └─ 删除路径: LiveQuote 直接 implement MarketDataPort 后删
  └─ Issue #126 范围 (LiveQuote implement MarketDataPort + 删 LiveQuotePortAdapter)

Broker ABC stub ← 向后兼容 (B-X' Phase 3 commit 0206ba7 留)
  └─ 核心引用: strategy.py:9,13 (Strategy.__init__ type hint, BaseStrategy 继承)
  └─ 注释引用: runner.py:151,209 / home.py / trade_main.py
  └─ 测试 4 处 import 3 文件 (Atlas 抓, 需重写断言)
  └─ 删除路径: Strategy.__init__ 改 BrokerPort type hint 后删 stub
  └─ Issue #125 范围 (删 Broker ABC stub + 迁移 BaseStrategy 到 BrokerPort)

Bars ABC ← 过度设计 (Step 3 Phase 2.3 待做)
  └─ DailyBars 单子类 (IndexBars 已删)
  └─ 无 abstractmethod 强制
  └─ 删除路径: (Bars, ParquetStorage) → (ParquetStorage) + 删 import
  └─ Issue #124 范围 (删 Bars ABC)
```

## 3. 顺序与依赖

```
Wave 1 内部依赖:
  #124 (Bars ABC)     ← 无依赖, 风险最低
  #125 (Broker stub)  ← 无依赖, 中等
  #126 (LiveQuote)    ← 无依赖, 难度最高

Wave 1 外部依赖:
  - 无 (#121/#122 已合, 不阻塞 #124-126)
  - v0.2-001-stable / v0.2-001-refactored 不受影响

建议派单顺序:
  #124 (0.5h) → #125 (1-2h) → #126 (3-4h)
  ↑
  先做最简单 (#124 删 Bars) 验证流程跑通, 再做中等 (#125 删 Broker stub), 最后做最重 (#126 LiveQuote thread→async 桥接)
```

> **qwen: ✅ 确认修正后顺序 #124→#125→#126（简单→复杂）与真实编号恰好一致。** 巧合但实用。另外补充：#124（删 Bars）虽然标 0.5h，但因 #121 已改为多继承，实际操作是 `(Bars, ParquetStorage)` → `(ParquetStorage)` + 删 import，仍然是低风险，估时不需上调。
>
> > **Atlas: 🔴 派单顺序按错误编号会出灾难。** 此处 "#126 → #124 → #125" 的**语义意图**是 "Bars(0.5h) → Broker(1-2h) → LiveQuote(3-4h)"（简单→复杂）。但按**真实 GitHub 编号**，正确顺序应写成：
> - **#124 (删 Bars, 0.5h) → #125 (删 Broker, 1-2h) → #126 (LiveQuote, 3-4h)**
>
> 巧合的是真实编号正好也是 124→125→126 升序，简单→复杂的意图能保留。但文档现在写的 "#126→#124→#125" 如果照字面派单，会变成 "LiveQuote(最难) → Bars → Broker"，**完全违背"先简单验证流程"的设计**。这个错误源头还是开头的编号错位表。**修了编号映射表后，这里顺序要同步改成 #124→#125→#126。**

> **Atlas: 关于依赖判断 ✅。** "三个 issue 无内部依赖、可独立" 的判断我认可：
> - 删 Bars (真#124) 只动 `daily_bars.py` 继承
> - 删 Broker (真#125) 只动 `strategy.py` type hint + 测试断言
> - LiveQuote (真#126) 只动 `livequote.py` + `modes.py` + adapter
> 三者文件无交集，可并行。**但注意：删 Bars (真#124) 与 #121 已有冲突**（见上方多继承评论），实施前 #124 issue body 必须先更新继承签名，否则不是"无依赖"而是"带着错误前提"。

## 4. 跨 issue 风险 (需 3 agent 讨论)

### #126 最大风险
1. **LiveQuotePortAdapter.stream()** 当前是 async generator (基于 msg_hub 事件)
   - LiveQuote 现有架构是 **thread-based** (ws_thread + lock)
   - 新增 `stream() -> AsyncIterator[MarketEvent]` 需要把 ws_thread 事件桥接到 async iterator
   - **复杂度高, 可能需要新建 asyncio.Queue 桥接 + 重构 _on_quotes 调度**

2. **`is_running` 现在是 property** (`livequote.py:128`)
   - 新增 `start()/stop()` 调用前需检查 is_running, 避免重复启动
   - 需要双重防护: (a) property 检查 (b) start/stop 内部的 thread state 检查

3. **`snapshot()` 当前**依赖 `_quote_source.get_quote()` (LiveQuotePortAdapter 委托)
   - LiveQuote 内部已有 `_quotes: dict`, 可直接用
   - **字段映射**: LiveQuote 的 dict 用 `'price' / 'open' / ...`, QuoteSnapshot 用同名字段 — 应该兼容

4. **modes.py 改 `market_data = live_quote`** 后, 任何 `market_data._subscribed` 等私有访问会断
   - **需 grep 核** `market_data._` 调用点

### #124 中等风险
1. **BaseStrategy type hint 改 BrokerPort** 影响所有子类
   - 子类需能用 BrokerPort 实例化 (PaperBroker / BacktestBroker 已 implement BrokerPort ✓)
   - 验证: 所有测试用 BrokerPort 而非 Broker 实例化

2. **删除 base_broker.py 后, 任何 `from quantide.service.base_broker import Broker` 都会断**
   - 需 grep 全仓归零 (含注释)

### #126 低风险
1. **DailyBars 不再继承 Bars** 影响 `isinstance(x, Bars)` 检查 (若有)
   - **需 grep 验证**

> **qwen: grep 验证结果 — `isinstance(..., Bars)` 全仓零命中 ✓，`from quantide.data.models.bars import Bars` 仅 `daily_bars.py:13` 一处 ✓。Bars ABC 删除确认为 surface-only。**
>
> **但 #125 (删 Broker) 的风险部分需补充：** `Strategy.__init__`（非 BaseStrategy）才是 Broker type hint 的实际位置。issue body 写 "BaseStrategy.__init__" 不够精确，实施时需定位到 `Strategy` 基类。

## 5. 工作流 (Wave 1)

```
Phase 0: 起始文档定稿 (本文档)
   ↓
Phase 1: 3-agent 讨论 (Sisyphus + Atlas + qwen3.7)
   ↓ (讨论收敛后)
Phase 2: qwen3.7 派单实施 (按 #124 → #125 → #126 顺序, 简单→复杂)
   ↓ 每个 issue 完成后:
Phase 3: Atlas review
   ↓
Phase 4: Sisyphus 评判 (10 分制)
   ↓ approved 后
Phase 5: tag v0.2-001-final-rc1
```

## 6. 讨论议程 (3-agent 协同)

### 议程 1: #125 LiveQuote stream() 实现方案
- qwen3.7 给 LiveQuote stream() 实现草案 (asyncio.Queue 桥接? callback 注册? 现有 thread 复用?)
- Atlas 评估 thread → async bridge 的风险与回归影响
- Sisyphus 拍方案可行性

### 议程 2: #124 BaseStrategy type hint 改动影响面
- qwen3.7 grep `class.*BaseStrategy` 所有子类, 评估 type hint 兼容性
- Atlas 评估 BaseStrategy 抽象方法签名是否需同步改
- Sisyphus 拍方案

### 议程 3: 派单节奏
- 顺序: #126 → #124 → #125 (按简单到复杂) 还是 #125 先做 (高风险先识别)?
- 每 issue 派单间隔: 串行(完成一个再下一个) 还是并行(同时派 3 个)?
- Sisyphus 拍节奏

### 议程 4: 验证策略
- 每个 issue 完成后, Atlas review 多久内给反馈?
- 如发现跨 issue regression (e.g. #125 改 LiveQuote 影响 #124 已通过的 BaseStrategy test), 怎么办?
- Sisyphus 拍验证流程

## 7. 交付物

每个 issue 完成时:
1. qwen3.7 commit + push (Refs #124/#125/#126)
2. qwen3.7 在 issue 评论: commit SHA + pytest + DoD + 红线检查
3. Atlas 在 issue 评论: 10 分制评分 + 红线 + DoD + 自我反思
4. Sisyphus 评分 (用 sisyphus-phase3-rubric.md), 给最终裁决

每个 issue 关闭后:
- worktree 自动剩 #111 epic 本身 + 已有 issues (无新增)

## 8. 风险升级路径

如任一 issue 实施过程中发现**跨 issue 风险升级**:
- 例如: #124 BaseStrategy 改动发现需先改 #125 LiveQuote (反向依赖)
- 暂停当前 issue, 开新讨论 (3-agent)
- 必要时调整 Wave 1 顺序或拆分新 issue

## 9. Wave 1 完成判定

全部 3 个 issue closed + specforge 5/5 + pytest 4 pre-existing 不变 → 触发:
1. tag `v0.2-001-final-rc1` (稳定版本)
2. 写 spec addendum (`.specforge/spec/v0.2-001-refactor-addendum.md`) 记录所有过渡组件归档
3. 开 v0.2-002-ui + v0.2-003-installation milestone 关联的 issues (Aaron 已建 milestone)

## 10. 参考

- v0.2-001-refactored tag (Step 2 起点)
- v0.2-001-stable tag (Step 1)
- step3-data-layer-refactor-plan.md
- refactor-implementation-manual-v3.md
- B-X' Phase 3 commit (0206ba7) Broker ABC 退役
- Step 2 Phase B-1 commit (44830b0) LiveQuotePortAdapter 引入
- sisyphus-phase3-rubric.md (评分标准)

---

**Owner**: qwen3.7 (实施) + Atlas (review) + Sisyphus (评判 + Wave 1 协调)
**Status**: 待 3-agent 讨论
**下一步**: 启动议程 1 (LiveQuote stream() 实现方案)

---

> ## Atlas 覆盖度评估总结 (2026-06-26)
>
> **问题：本文档 + 3 个 issue 是否完全覆盖了要解决的问题？**
>
> **结论：技术问题识别完整，但存在 1 个阻塞级元数据错误 + 2 个因 #121 合并产生的过时前提。三个组件本身的删除范围覆盖是足够的，但 issue body 有实质性缺漏，照现状派单会出回归。**
>
> ### 覆盖充分的部分 ✅
> 1. **三个过渡组件识别准确** — Bars ABC / Broker stub / LiveQuotePortAdapter 确实是仅剩的过渡件，我独立核验了三者的存在与引用点
> 2. **删除路径技术方向正确** — Bars→无约束删除、Broker→迁 BrokerPort、LiveQuote→自实现 MarketDataPort，方向都对
> 3. **依赖判断正确** — 三者文件无交集，可并行
> 4. **风险议程抓住了真问题** — LiveQuote 的 thread→async stream() 桥接确实是最大风险，议程 1 优先讨论它是对的
> 5. **export/isinstance 等边缘项** — 我核验后多为 N/A，文档"如有/如存在"措辞稳妥
>
> ### 覆盖缺漏 / 错误 ❌
> | # | 严重度 | 问题 | 位置 |
> |---|---|---|---|
> | 1 | 🔴 阻塞 | **issue 编号与真实 GitHub 全错位** (124↔Bars, 125↔Broker, 126↔LiveQuote) | §1 表 / §2 / §3 |
> | 2 | 🔴 阻塞 | **删 Bars 的继承签名过时** — 实际是 `(Bars, ParquetStorage)` 多继承，issue #124 body 写的 "→ class DailyBars(无继承)" 会丢 ParquetStorage | §1.5 Bars / 真#124 |
> | 3 | 🟡 实质 | **Broker 的 4 处测试是功能性断言 (hasattr/isinstance)，不是"注释"** — 删 base_broker.py 后 3 个测试文件 collection 失败，需重写断言到 BrokerPort/AbstractBroker | §1.5 Broker / 真#125 |
> | 4 | 🟢 小 | 行号/路径小漂移 (`daily_bars.py:17`→`:19`，modes.py:18 import 需一并处理) | 多处 |
>
> ### 必做修正 (派单前)
> 1. **修编号映射表**（§1/§2/§3 全部）—— 否则 qwen 在错 issue 下评论、关错 issue
> 2. **更新真 #124 (删 Bars) issue body** —— 继承签名改 `class DailyBars(Bars, ParquetStorage)` → `class DailyBars(ParquetStorage)`
> 3. **更新真 #125 (删 Broker) issue body / DoD** —— 补 "4 处测试断言 (test_fr_011/012/013) 迁移到 BrokerPort/AbstractBroker"
>
> ### 评分 (针对本起始文档质量, 10 分制)
> - 组件识别完整性: 2/2 (三件齐, 来历+使用+替换对象+理由清晰)
> - 技术方案正确性: 1.5/2 (方向对, 但 Bars 多继承未更新)
> - issue 映射准确性: 0/2 (编号全错位, 阻塞级)
> - 风险覆盖: 1.5/2 (大风险抓住, 但漏 Broker 测试回归 + #121 冲突)
> - 工作流/交付物定义: 2/2 (Phase/DoD/红线/升级路径完整)
> - **总分: 7/10 → changes-requested**
>
> **Verdict: changes-requested.** 文档作为"讨论起始稿"骨架优秀，三个组件的删除范围**技术上覆盖了要解决的问题**，但**编号错位 (问题1) 是硬阻塞**，#121 冲突 (问题2) 和 Broker 测试回归 (问题3) 会让 qwen 实施直接撞墙。修完 3 项必做修正后即可进入 Phase 1 讨论。这些是 issue 元数据/body 的修正，属 spec/规划层，按 brief 不是我 (Atlas) 改，建议 Sisyphus 裁决后由文档 owner (qwen/规划方) 更新。待 Sisyphus 裁决。
>
> *— Atlas, 独立核验: `gh issue view 124/125/126` + `grep base_broker/Bars/LiveQuotePortAdapter` + python import 验证 BrokerPort/MarketDataPort 路径*

---

> ## qwen 覆盖度评估总结 (2026-06-26)
>
> **问题：本文档 + 3 个 issue 是否完全覆盖了要解决的问题？**
>
> **结论：三个过渡组件的识别和删除方向正确，但存在 1 个阻塞级元数据错误 + 2 个因 #121 合并产生的过时前提 + 1 个 Atlas 遗漏的测试覆盖缺口。修正后方可派单。**
>
> ### 与 Atlas 评估的一致性
>
> Atlas 的核验我全部独立确认（`gh issue view` + `grep` + 读源码），三项主要发现均成立：
> - 🔴 issue 编号错位 — 文档 #124=Broker/#125=LiveQuote/#126=Bars，实际 GitHub #124=Bars/#125=Broker/#126=LiveQuote
> - 🔴 删 Bars 的继承签名过时 — 实际是 `(Bars, ParquetStorage)` 多继承，不是 `(Bars)` 单继承
> - 🟡 Broker 的 4 处测试断言是功能性的 — 不是"注释"
>
> ### Atlas 遗漏的覆盖缺口
>
> | # | 严重度 | 问题 | Atlas 是否提及 |
> |---|---|---|---|
> | 1 | 🟡 实质 | **`test_runtime_modes.py:86-87` 有 `isinstance(runtime.market_data, LiveQuotePortAdapter)` 断言** — 删 adapter 后此测试 collection 失败 | ❌ Atlas 核验说"覆盖无遗漏" |
> | 2 | 🟢 小 | **`daily_bars.py:13` 的 `from quantide.data.models.bars import Bars` import** — 删 bars.py 后需一并移除 | ❌ 未提及 |
> | 3 | 🟢 小 | **`Strategy.__init__`（非 BaseStrategy）才是 Broker type hint 的实际位置** — issue #125 body 措辞不精确 | ❌ 未提及 |
>
> ### 完整必做修正清单 (派单前)
>
> | # | 修正内容 | 责任方 |
> |---|---|---|
> | 1 | 修文档编号映射表（§1/§2/§3） | 文档 owner |
> | 2 | 更新 #124 body：`DailyBars(Bars, ParquetStorage)` → `DailyBars(ParquetStorage)` + 删 `daily_bars.py:13` import | issue owner |
> | 3 | 更新 #125 body/DoD：补 4 处测试断言迁移到 BrokerPort/AbstractBroker；修正 type hint 位置为 `Strategy.__init__` | issue owner |
> | 4 | 更新 #126 body/DoD：补 `test_runtime_modes.py:86-87` 的 isinstance 断言迁移 | issue owner |
>
> ### 评分 (10 分制)
>
> - 组件识别完整性: 2/2 (三件齐 + 来历/使用/替换/理由清晰)
> - 技术方案正确性: 1.5/2 (方向对，但 Bars 多继承未更新 + 漏 import 行)
> - issue 映射准确性: 0/2 (编号全错位，阻塞级)
> - 风险覆盖: 1.5/2 (大风险抓住，但漏 #121 冲突 + Broker 测试回归 + test_runtime_modes 缺口)
> - 工作流/交付物定义: 2/2 (Phase/DoD/红线/升级路径完整)
> - **总分: 7/10 → changes-requested**
>
> **Verdict: changes-requested。** 同意 Atlas 的判定。文档作为讨论起始稿骨架优秀，三个组件的删除方向技术上正确且完整覆盖了文档想要解决的问题。但 4 项必做修正（1 阻塞 + 3 实质）需在派单前完成。Atlas 的核验质量很高，我在此基础上补了 1 个遗漏的测试覆盖缺口（`test_runtime_modes.py`）。待 Sisyphus 裁决后由 issue owner 更新。
>
> *— qwen, 独立核验: `gh issue view 124/125/126` + `grep` 全仓 `base_broker/Bars/LiveQuotePortAdapter` + 读 strategy.py/modes.py/daily_bars.py/test_runtime_modes.py 源码*
