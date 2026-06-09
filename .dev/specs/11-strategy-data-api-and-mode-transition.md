# 11. 策略数据 API 与跨模式无缝切换

> **状态**：设计稿（2026-06-09）
> **适用范围**：backtest / paper / live 三模式下的策略层数据访问 API、UI 部署流程、形成行（forming bar）补齐、`cheat_on_close` 信号时机、broker 字段收敛

---

## 1. 背景与目标

Millionaire 的核心定位是"策略一次编写，跨 backtest / paper / live 三模式运行"——这是和其它量化框架的关键差异。`releases/v0.1` 已经实现基础三模式运行，但有若干问题：

1. **数据源语义混乱**：paper broker 有 `_market_data`，live broker 有 `_history_provider`，看似不同，实际都是冗余包装或死路径。
2. **形成行（forming bar）字段缺失**：paper/live 下今日 forming 行的 `up_limit` / `down_limit` / `is_st` / `adjust` 为 `None`，策略拿不到涨跌停价、ST 标志、复权因子。
3. **信号时机只有一种模式**：当前 1d 框架天然是"盘后触发、9:30 开盘交易"；不支持"尾盘集合竞价触发"模式（回测需要 cheat-on-close 支持）。
4. **回测与 paper/live 撮合价差异未声明**：回测用 daily_bars 15:00 close，paper/live 用盘中价，两者没有对齐说明。

本文档定义：

- 策略层数据访问的唯一 API
- 三模式下的统一数据源
- forming bar 字段补齐方案
- `cheat_on_close` 模式与时机配置
- broker 字段收敛（删除冗余）
- 实施路线图

---

## 2. 策略 API 入口

### 2.1 唯一推荐入口

策略代码里**只**用 `BaseStrategy.get_history(...)`，不直接调 broker、datafeed、LiveQuote。

```python
# 策略代码里 on_bar() 内部
async def on_bar(self, tm, quote, frame_type):
    if frame_type != FrameType.DAY:
        return
    hist = self.get_history(
        asset=self.symbol,
        count=self.slow_window + 5,
        end_dt=tm,
        frame_type="1d",
        include_forming_bar=True,   # 默认就是 True，省略亦可
    )
```

`BaseStrategy.get_history`（`quantide/core/strategy.py:61-85`）是**一行委托**：

```python
return self.broker.get_history(
    asset, count, end_dt, frame_type, include_forming_bar=include_forming_bar
)
```

### 2.2 不要直接调用的内部 API

| 内部 API | 原因 |
|---|---|
| `self.broker.get_history(...)` | 跳过策略基类封装，破坏可移植性 |
| `self._data_feed.get_bars(...)` | 数据层是 broker 私有资产 |
| `live_quote.get_daily_bar(...)` | LiveQuote 不在策略上下文保证可用；schema 不全 |
| `daily_bars.get_bars(...)` | 同上，且直接调会绕过 `include_forming_bar` 合并逻辑 |

### 2.3 `BarsFeed.get_bars` 的角色

`quantide/service/datafeed.py:42` 的 `BarsFeed.get_bars` 是历史回测的数据层抽象。**仅在 backtest broker 内部调用**，策略不应直接调，无 `include_forming_bar` 概念，也不出现在 paper/live 路径。

---

## 3. UI 部署流程

### 3.1 触发位置

`/strategy/backtest/{portfolio_id}` 页面（`quantide/web/pages/strategy.py:880-955`）的回测报告列表操作列：

- **"转仿真"** → POST `/backtest/{portfolio_id}/deploy/paper`
- **"转实盘"** → POST `/backtest/{portfolio_id}/deploy/live`

点击弹确认模态框（`_paper_deploy_modal` / `_live_deploy_modal`），用户输入仿真本金或选择实盘账户后提交。

### 3.2 后端处理

POST 路由（`strategy.py:1900, 1950`）最终调：

- `strategy_runtime_manager.deploy_to_paper(...)`（`quantide/service/strategy_runtime.py:227-267`）
- `strategy_runtime_manager.deploy_to_live(...)`（`strategy_runtime.py:269-296`）

两者复用同一条启动路径 `_start_strategy_runtime(...)`（`strategy_runtime.py:649-732`）：

- **deploy_to_paper**：`PaperBroker.create(...)`（`sim_broker.py:85`）造新 PaperBroker，注册到 `BrokerKind.SIMULATION`。
- **deploy_to_live**：拿 `self._gateway_broker`（`strategy_runtime.py:152`），注册到 `BrokerKind.QMT`。

`StrategyRuntime` 上挂的 `strategy_name` / `config` / `interval` 完全一样——**策略代码 0 改动**，只是底层 broker 换了。

### 3.3 策略循环

策略循环在 `StrategyRuntimeManager._run_strategy_loop` 启动（`strategy_runtime.py:734-738`），落到 `strategy_runner._strategy_loop`。每个 `on_bar` 触发时，策略用 `self.get_history(...)`，`self.broker` 自动是 paper 或 gateway broker，路径自动切换。

### 3.4 paper / live 运行时序 + 委托单发出时机

回测转 paper / live 后，runtime 切换到**真实时钟**（不再是回测模拟时钟）：

| 维度 | 回测 | paper | live |
|---|---|---|---|
| Clock | 回测模拟时钟（`backtest_broker._clock`） | 真实 wall clock + 交易日历 | 真实 wall clock + 交易日历 |
| 运行时段 | `start_date..end_date` 一次性跑完 | 从回测 `end_date + 1` 起，**持续运行**到 portfolio 被手动停止 | 同 paper |
| on_bar 触发时间 | 9:30（cheat_on_close=False）/ 14:57（cheat_on_close=True） | 9:30（cheat_on_close=False）/ 14:57（cheat_on_close=True） | **15:00 收盘后**（cheat_on_close=False，盘后触发）/ 14:57（cheat_on_close=True） |
| 撮合时机 | cheat_on_close=False：runner 在每个交易日 9:30 都触发 on_bar，可严格实现 execution_offset=1（次日 9:30 open 撮合） | cheat_on_close=True：**立即**按当前价撮合；cheat_on_close=False：等到次日 9:25 集合竞价结束撮合 | cheat_on_close=True：**立即**按当前价撮合；cheat_on_close=False：broker **截图订单** + 延迟到次日指定时间下柜台（见 §3.6） |
| 撮合价 | cheat_on_close=False：次日 9:30 open；cheat_on_close=True：当根 close | cheat_on_close=True：14:57 forming close；cheat_on_close=False：次日 9:25 集合竞价 close | cheat_on_close=True：14:57 forming close；cheat_on_close=False：**限价单**（昨收/今开 + 滑点），废单允许 |

**on_bar 触发时间的设计洞察**：

cheat_on_close=False 模式是"盘后决策、次日开盘成交"——触发时间应该是**当日 15:00 收盘后**（此时当日 K 线已确定，看到的就是真 K 线）。但 cheat_on_close=True 模式是"尾盘集合竞价触发"——触发时间应该是 14:57（在 close 撮合前一刻）。

Aaron 提出：**`on_day_close` hook 不做交易**（仅用于日志/对账等），所以盘后触发**不能用** on_day_close，必须由 on_bar 驱动 → 策略代码**自己** 在 15:00 触发时根据 cheat_on_close 决定行为。

**回测 vs paper/live 的 on_bar 时间差异**：

- 回测 cheat_on_close=False：runner 当前把 bar_tm 锁 9:30（`runner.py:277`），但**严格按"盘后触发"语义应改成 15:00**——待 P1 实施时讨论
- paper cheat_on_close=False：wall clock 15:00 触发
- live cheat_on_close=False：wall clock 15:00 触发

**委托单发出时机**（分模式分情况）：

- **paper / cheat_on_close=True**：on_bar 14:57 触发 → 立即发单 → broker 立即按 14:57 forming close 撮合
- **paper / cheat_on_close=False**：on_bar 15:00 触发 → 立即发单 → broker 等待次日 9:25 集合竞价结束 → 按集合竞价 close 撮合（**若 qmt-gateway 拿不到集合竞价数据**，fallback 到次日第 1 根 bar 撮合价）
- **live / cheat_on_close=True**：on_bar 14:57 触发 → 立即发单（14:57-15:00 集合竞价撮合时段，发单合法）→ qmt-gateway 撮合
- **live / cheat_on_close=False**（**见 §3.6 最终方案**）：on_bar 15:00 触发 → broker **截图订单**放进内部队列 → 次日指定时间下柜台（限价单，昨收/今开 + 滑点）

### 3.5 策略 config 在 UI 中显示和修改

转 paper / live 模态框（`_paper_deploy_modal` / `_live_deploy_modal`，`quantide/web/pages/strategy.py:1674, 1729`）当前**只**让用户填仿真本金或选择实盘账户。**新设计**：模态框同时显示策略 config，**允许用户修改**。

**表格列**：

| 列 | 来源 |
|---|---|
| `key` | 策略 config 的键名 |
| `default` | 策略类的默认 config（来自 `StrategyClass.default_config()` 静态方法） |
| `custom` | 当前回测 run 用的 config（来自 `BacktestRun.config`）—— 用户可在此列编辑覆盖 |

**继承语义**：

- 转 paper / live 时，默认 config = `BacktestRun.config`（回测时实际用的值）
- 用户在对话框里修改 `custom` 列后，提交时用**修改后的 config** 启动 paper/live runtime
- 修改后的 config 持久化到 `StrategyRuntime.config`，跟随 portfolio

**数据格式限制**：

- **当前只支持无嵌套的 dict**（key 和 value 都是简单数据类型：int / float / str / bool）
- 嵌套 dict（如 `{"risk": {"max_pos": 0.1}}`）暂不支持，UI 模态框里只显示扁平化 key
- 嵌套支持延后到后续 issue（P5+）

**实施细节**：

- `BaseStrategy` 新增类方法 `default_config() -> dict`（默认空 dict `{}`）；各策略覆盖
- `BacktestRun.config` 已存（`strategy_runtime.py:259, 288`），部署时直接拿
- UI 模态框渲染时遍历 `BacktestRun.config` 的 key，每个 key 一行（key | default | custom），custom 列默认等于 BacktestRun.config[key]
- 提交时 form 把 `custom_*` 字段合并回 config dict，调用 `deploy_to_paper(live)` 时传入

**示例**：

策略 `dual_ma.py` 的 config：
```python
class DualMAStrategy(BaseStrategy):
    @staticmethod
    def default_config() -> dict:
        return {
            "symbol": "000001.SZ",
            "fast": 5,
            "slow": 10,
            "invest": 100000,
        }
```

回测 run.config = `{"symbol": "688371.SH", "fast": 8, "slow": 20, "invest": 50000}`（用户改了 fast=8, slow=20, invest=50000）。

模态框显示：
| key | default | custom |
|---|---|---|
| symbol | 000001.SZ | 688371.SH |
| fast | 5 | 8 |
| slow | 10 | 20 |
| invest | 100000 | 50000 |

用户可编辑 `custom` 列。提交后 deploy 用修改后的 config。

### 3.6 cheat_on_close=False + live 模式：broker 截图订单 + 限价单（最终方案）

**Aaron 决策**：

不需要 `effective_at` 字段（**不**对策略暴露）。live broker 在 `cheat_on_close=False` 时**自动**：

1. **截图订单**（on_bar 15:00 触发时立即捕获 buy/sell 调用，不真送 qmt-gateway）
2. **放进 broker 内部 DeferredOrderQueue**（含 asset / side / value / style / execution_window）
3. **在次日指定时间下柜台**（broker 内部 scheduler 线程到点后调 `submit()` 送 qmt-gateway）
4. **订单类型：限价单**（bid_type=LIMIT，price 由 broker 自动算）
5. **价格估算**（按 execution_window 二选一）：
   - `auction`（集合竞价，次日 9:25）：price = 昨收 × (1 + slippage)
   - `post_auction`（集合竞价后立即，次日 9:30:00.001）：price = 今开 × (1 + slippage)
6. **废单允许**（限价单偏离市价时不会成交，broker 不强制撮合）

**execution_window 配置**：

- 策略 config 新增 `live_execution_window: Literal["auction", "post_auction"] = "auction"`
- 默认 `auction`（次日 9:25 集合竞价撮合）
- 策略作者根据策略需要选：
  - "盘后决策、希望次日开盘价成交" → `auction`（昨收 + 滑点）
  - "盘后决策、希望次日开盘后立即成交" → `post_auction`（今开 + 滑点）

**slippage 配置**：

- 策略 config 新增 `live_execution_slippage: float = 0.001`（默认 0.1%）
- 实际含义：限价单 price = (昨收/今开) × (1 ± slippage)，给市价波动留 buffer
- slippage = 0：完全按昨收/今开，下跌行情可能废单
- slippage = 0.001：给 0.1% 缓冲

**broker 实现细节**：

- `OrderRequest` **不**新增字段（effective_at 留在 broker 内部）
- broker 接 buy/sell 时检查 `runtime_mode == "live" and strategy.cheat_on_close == False`：
  - 是 → 把 `(request, execution_window, slippage, scheduled_at=...)` 放进 `DeferredOrderQueue`
  - 否 → 立即 `submit()`（与现在一致）
- broker 启动时起 `asyncio.create_task(self._deferred_order_loop())`：每 1 秒扫队列
  - 队列项 `scheduled_at` ≤ wall clock → 取出，计算 price，调 `submit()`，从队列删除
- `scheduled_at` 计算：
  - execution_window=auction → 次日 9:25
  - execution_window=post_auction → 次日 9:30:00.001
- 持久化：`DeferredOrderQueue` 可选存 SQLite（broker 重启不丢订单）—— **v0.1 不做**，broker 重启 pending 订单丢失，仅在文档说明

**paper 模式不需要这个机制**：

- paper broker 立即撮合（mock）
- cheat_on_close=False + paper：on_bar 15:00 触发 → 立即发单 → broker 等 wall clock 到次日 9:25/9:30 → 撮合
- 不需要"截图订单"语义（paper 撮合是 mock，不会变成废单）

**回测模式严格实现 execution_offset=1**：

- runner 跑每日 9:30 都触发 on_bar（虚拟时钟）
- cheat_on_close=False 时 runner 在每个交易日 9:30 触发，策略发单，broker 在 runner 的虚拟时间流中按"次日 9:30"撮合
- 与 live 行为**有差异**（live 是 broker 内部 scheduler 延迟；回测是 runner 循环实现 execution_offset=1）
- 文档需明确这一差异，但**结果一致**（都是次日 9:30 附近撮合）

### 3.7 已知风险：多策略 live 抢资金

**问题**：live 模式下允许多个策略同时运行，**共享一个 gateway 账户**，策略之间会**抢资金**（一个策略买入占满可用资金，另一个策略买入时失败）。

**当前设计（v0.1）**：

- 资金不分仓（多个策略共享账户）
- 文档需明确：v0.1 不做策略分仓
- 策略分仓是 **billionaire**（后续产品）的功能
- 当前建议：
  - 用户在多个策略之间**手工协调**资金分配
  - 或者每个策略用**独立子账户**（qmt-gateway 支持多账户，但当前 Millionaire 还没接）

**文档位置**：写入 spec "已知风险"小节，告知用户"v0.1 不做分仓，billionaire 才做"。

### 3.5 策略 config 在 UI 中显示和修改

转 paper / live 模态框（`_paper_deploy_modal` / `_live_deploy_modal`，`quantide/web/pages/strategy.py:1674, 1729`）当前**只**让用户填仿真本金或选择实盘账户。**新设计**：模态框同时显示策略 config，**允许用户修改**。

**表格列**：

| 列 | 来源 |
|---|---|
| `key` | 策略 config 的键名 |
| `default` | 策略类的默认 config（来自 `StrategyClass.default_config()` 静态方法） |
| `custom` | 当前回测 run 用的 config（来自 `BacktestRun.config`）—— 用户可在此列编辑覆盖 |

**继承语义**：

- 转 paper / live 时，默认 config = `BacktestRun.config`（回测时实际用的值）
- 用户在对话框里修改 `custom` 列后，提交时用**修改后的 config** 启动 paper/live runtime
- 修改后的 config 持久化到 `StrategyRuntime.config`，跟随 portfolio

**数据格式限制**：

- **当前只支持无嵌套的 dict**（key 和 value 都是简单数据类型：int / float / str / bool）
- 嵌套 dict（如 `{"risk": {"max_pos": 0.1}}`）暂不支持，UI 模态框里只显示扁平化 key
- 嵌套支持延后到后续 issue（P5+）

**实施细节**：

- `BaseStrategy` 新增类方法 `default_config() -> dict`（默认空 dict `{}`）；各策略覆盖
- `BacktestRun.config` 已存（`strategy_runtime.py:259, 288`），部署时直接拿
- UI 模态框渲染时遍历 `BacktestRun.config` 的 key，每个 key 一行（key | default | custom），custom 列默认等于 BacktestRun.config[key]
- 提交时 form 把 `custom_*` 字段合并回 config dict，调用 `deploy_to_paper(live)` 时传入

**示例**：

策略 `dual_ma.py` 的 config：
```python
class DualMAStrategy(BaseStrategy):
    @staticmethod
    def default_config() -> dict:
        return {
            "symbol": "000001.SZ",
            "fast": 5,
            "slow": 10,
            "invest": 100000,
        }
```

回测 run.config = `{"symbol": "688371.SH", "fast": 8, "slow": 20, "invest": 50000}`（用户改了 fast=8, slow=20, invest=50000）。

模态框显示：
| key | default | custom |
|---|---|---|
| symbol | 000001.SZ | 688371.SH |
| fast | 5 | 8 |
| slow | 10 | 20 |
| invest | 100000 | 50000 |

用户可编辑 `custom` 列。提交后 deploy 用修改后的 config。

---

## 4. 三模式 broker 的 `get_history` 实现

### 4.1 共同契约

| 维度 | 一致性 |
|---|---|
| 签名 | `asset, count, end_dt=None, frame_type="1d", include_forming_bar=True` |
| 返回 schema | 12 列固定：`date, asset, open, high, low, close, volume, amount, adjust, is_st, up_limit, down_limit` |
| `_empty_history_frame` schema | sim_broker.py:370-386；gateway_broker.py:219-225（两处一致 12 列） |
| Lookahead 防护 | end_dt ≤ 9:30 → 回退一天 / 不挂 forming |
| 静默 fallback | LiveQuote 无 tick → 回退昨日 |
| `_previous_trade_date` | `calendar.day_shift(today, -1)`，失败则 `today - 1` |

### 4.2 `BacktestBroker.get_history`

`quantide/service/backtest_broker.py:1061-1106`

```python
def get_history(self, asset, count, end_dt=None, frame_type="1d",
                skip_suspended=True, fill_value=True, include_forming_bar=True):
    _ = skip_suspended
    _ = fill_value
    _ = include_forming_bar     # no-op：回测无实时 tick
    if frame_type != "1d":
        raise NotImplementedError(...)
    end_date = self.as_date(end_dt) if end_dt else self.as_date(self._clock)
    if isinstance(end_dt, datetime.datetime) and end_dt.time() <= datetime.time(9, 30):
        end_date = calendar.day_shift(end_date, -1)   # 防前视
    return self._data_feed.get_bars(
        n=count, end=end_date, assets=[asset], adjust="qfq",
    )
```

- **数据源**：`self._data_feed.get_bars` → `daily_bars.get_bars`（`quantide/data/models/daily_bars.py:90-113`）→ `DailyBarsStore.get`（`quantide/data/stores/base.py`）→ parquet 读
- **时钟**：`self._clock` 是回测模拟时钟；`end_dt=None` 时自动用 `_clock`
- **Lookahead 防护**：`end_dt.time() <= 9:30` 时回退前一交易日
- **字段**：daily_bars 落盘 schema 是 12 列（OHLCV + adjust + is_st + up_limit + down_limit，见 `quantide/data/fetchers/tushare.py:499`）。`adjust` 已是应用后的前复权结果，列里恒为 1.0
- **forming**：no-op

### 4.3 `PaperBroker.get_history`（simulation 模式）

`quantide/service/sim_broker.py:193-240`

```python
def get_history(self, asset, count, end_dt=None, frame_type="1d",
                include_forming_bar=True):
    end_date = self._resolve_history_end_date(end_dt)
    if not include_forming_bar and end_date == self._get_today():
        end_date = self._previous_trade_date(end_date)
        hist = self._get_history_bars(asset, count, end_date, frame_type)
    else:
        hist = self._get_history_bars(asset, count, end_date, frame_type)

    if include_forming_bar and self._should_attach_forming_bar(end_date, end_dt):
        forming = self._extract_forming_bar(asset, end_date)
        if forming is not None:
            hist = self._concat_with_forming(hist, forming, count)
        elif end_date == self._get_today():
            # LiveQuote 还没收到今日 tick，回退到昨日
            hist = self._get_history_bars(
                asset, count, self._previous_trade_date(end_date), frame_type
            )
    return hist
```

- **数据源**（实际只有一条会走通）：`daily_bars.get_bars(...)`（`sim_broker.py:269`）
  - 上面两条 `hasattr(self._market_data, "get_history"/"get_bars")` 是死路径（`MarketDataPort` 协议无此方法，参见 §7 字段收敛）
- **时钟**：`self._get_today()`（通常等于 `datetime.date.today()`，可被 `pin_today` fixture monkeypatch）
- **Lookahead 防护**：end_dt ≤ 9:30 时不挂 forming bar
- **forming bar 来源**：`live_quote.get_daily_bar(asset)`（`livequote.py:270`），返 9 字段 dict：`asset, frame, dt, open, high, low, close, volume, amount`
- **合并**：`_concat_with_forming`（`sim_broker.py:306-356`）把 forming dict 折成一行，缺失列置 None

### 4.4 `GatewayBrokerWrapper.get_history`（live 模式）

`quantide/core/runtime/gateway_broker.py:97-132`

```python
def get_history(self, asset, count, end_dt=None, frame_type="1d",
                include_forming_bar=True):
    if getattr(daily_bars, "_store", None) is None:
        return self._empty_history_frame()
    end_date = self._resolve_history_end_date(end_dt)
    if not include_forming_bar and end_date == self._today():
        end_date = self._previous_trade_date(end_date)
        hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)
    else:
        hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)
    if include_forming_bar:
        hist = self._maybe_attach_forming_bar(asset, hist, end_date, end_dt, count)
    return hist
```

- **数据源**：永远走 `daily_bars`（`history_provider` 字段将在 §7 中删除）
- **forming 合并**：委托给 `_maybe_attach_forming_bar` → `_concat_forming_with_history`，与 PaperBroker 逻辑对称

---

## 5. 字段集与已知 gap

### 5.1 字段集对比

| 字段 | backtest | paper/live 历史行 | paper/live forming 行 |
|---|---|---|---|
| `date` | ✓ | ✓ | ✓（来自 LiveQuote.dt） |
| `asset` | ✓ | ✓ | ✓ |
| `open` | ✓ | ✓ | ✓（首 tick 锁定） |
| `high` | ✓ | ✓ | ✓（max 累计） |
| `low` | ✓ | ✓ | ✓（min 累计） |
| `close` | ✓ | ✓ | ✓（最新 tick） |
| `volume` | ✓ | ✓ | ✓（1d 累计，非 1m） |
| `amount` | ✓ | ✓ | ✓（1d 累计） |
| `adjust` | ✓（恒 1.0） | ✓ | **None**（**待 P0 修复**） |
| `is_st` | ✓ | ✓ | **None**（**待 P0 修复**） |
| `up_limit` | ✓ | ✓ | **None**（**待 P0 修复**） |
| `down_limit` | ✓ | ✓ | **None**（**待 P0 修复**） |

### 5.2 形成行 4 个 None 的原因

- `live_quote.get_daily_bar`（`livequote.py:270-272`）只返 9 字段（`asset, frame, dt, open, high, low, close, volume, amount`）
- `_concat_with_forming`（`sim_broker.py:336`）和 `_concat_forming_with_history` 都用 `{k: v for k, v in forming_clean.items() if k in hist.columns}` 过滤，缺的列被置 None
- `LiveQuote._limits` 字典（`livequote.py:215-227`）单独维护了 `up_limit` / `down_limit`，但**没合并到 `_daily_bars`**
- `is_st` / `adjust` 在 LiveQuote 数据源中本就没有定义

### 5.3 影响

- 用 `up_limit` / `down_limit` 做"价格逼近涨跌停不下单"判断时，forming 行的判断会失真
- `is_st` 在回测里用于"ST 股票过滤"，forming 行会漏掉"今日是否仍为 ST"——实盘里 ST 状态变化极少，常见做法是从昨日 is_st 沿用，目前 forming 行 None 是真值丢失
- `adjust` 在回测里恒为 1.0（前复权已应用），paper/live 下 forming 行 None 不会影响价格计算（价格已是复权后），但**类型上不一致**（None vs Float64），策略用 `hist["adjust"].fill_null(1.0)` 兜底即可

### 5.4 临时 workaround

策略代码里：

```python
last = hist.row(-1, named=True)
up_limit = last["up_limit"] if last["up_limit"] is not None else float("inf")
is_st = bool(last["is_st"]) if last["is_st"] is not None else False
```

或者把 forming 行的 limits 现取：

```python
from quantide.service.livequote import live_quote
limits = live_quote.all_limits.get(asset, {})
up_limit = limits.get("up_limit", float("inf"))
down_limit = limits.get("down_limit", 0.0)
```

### 5.5 daily_bars 落盘数据可能未同步到最新

tushare 每天盘后更新 daily_bars parquet。盘中（特别是早盘）调 `get_history` 时：

- end_date 落在今天 → daily_bars 没有今日行
- 行为：daily_bars 返 N-1 行历史 + 空尾行
- paper/live 下：LiveQuote.get_daily_bar 补 forming 行为 1 行 → 总共 N 行
- backtest 下：直接返 N-1 行，策略可能误以为"今天没行情"

**当前处理**：以错误日志 / toast 提示（**P3 实施，本设计稿不展开**）。

---

## 6. 数据源真相（统一调用链）

### 6.1 历史数据

```
broker.get_history(asset, count, end_dt, frame_type, include_forming_bar)
    ↓
    ↓ （三模式内部都走这条）
    ↓
daily_bars.get_bars(n=count, end=end_date, assets=[asset], adjust='qfq')
    ↓
DailyBarsStore.get(...) → parquet
```

**三个模式的"历史数据"全部来自 `daily_bars`（tushare 落盘 parquet）**。forming bar 部分由 `LiveQuote` 提供（live/paper）或不提供（backtest no-op）。

### 6.2 Forming bar 合并

```
if include_forming_bar and end_date == 今日 and end_dt.time() > 9:30:
    forming = live_quote.get_daily_bar(asset)  # 9 字段 OHLCV
    bar = _concat_with_forming(hist, forming, count)  # 补 4 字段 (up/down_limit, is_st, adjust)
```

### 6.3 下单快照（broker 内部，不暴露给策略）

```
PaperBroker.get_quote(asset)              →  live_quote.get_quote(asset)
GatewayBrokerAdapter.get_quote(asset)     →  live_quote.get_quote(asset)
```

两个 broker 用**同一接口名**（`get_quote(asset)`）、**同一数据源**（LiveQuote 累积的 qmt gateway tick）。

### 6.4 stub 模式下的统一性

Stub 模式（`QUANTIDE_ENABLE_DEV_STUBS=1`）行为：
- `quantide/config/dev_stubs.py:67-83` 启 `start_gateway_stub(prefix="/qmt")` 在 localhost 随机 port 启 mock gateway
- `runtime.gateway_base_url` 被设置为这个 localhost URL
- tushare fetcher 被 patch 为 fixture-backed
- `runtime.gateway_enabled` 仍为 True（stub 假装"启用 gateway"）
- `LiveQuote._build_ws_url`（`livequote.py:75-81`）拼 `ws://127.0.0.1:xxxxx/ws/quotes`
- LiveQuote 启动 WebSocket 连 localhost stub → 收 mock tick → 累积成 forming bar

| 维度 | 真实 live | 真实 paper | stub 模式 |
|---|---|---|---|
| WebSocket 连接 | 真实 qmt gateway | 真实 qmt gateway | localhost mock gateway |
| LiveQuote 启动 | 是 | 是 | 是 |
| `get_quote` 接口 | `live_quote.get_quote(asset)` | `live_quote.get_quote(asset)` | `live_quote.get_quote(asset)` ✓ |
| `get_daily_bar` 接口 | `live_quote.get_daily_bar(asset)` | `live_quote.get_daily_bar(asset)` | `live_quote.get_daily_bar(asset)` ✓ |
| 数据真实性 | 真实 tick | 真实 tick | mock tick (fixture) |
| 接口签名 | 一致 | 一致 | **一致** ✓ |

**唯一差异是数据本身（mock vs 真实）**——这正是 stub 模式的设计目的。broker 接口、LiveQuote 累积路径、WebSocket 协议**完全一致**。

---

## 7. broker 字段收敛（删除冗余）

### 7.1 字段消除范围

| 字段 | 当前用法 | 收敛动作 |
|---|---|---|
| `PaperBroker._market_data` | `sim_broker.py:171-172, 189` 拿 tick 快照做下单价估算；`sim_broker.py:257, 260` 拿历史（**死路径**） | **删除**。两处 fallback 已存在（`sim_broker.py:182, 191` 直接调 `live_quote`）。`get_history` 路径完全走 `daily_bars` |
| `GatewayBrokerWrapper._history_provider` | `gateway_broker.py:114-118` fallback 到 `daily_bars` | **删除**。永远走 `daily_bars` |
| `GatewayBrokerAdapter._market_data` | `gateway_broker.py:917-920, 933-935` 拿 qmt gateway tick 快照做下单价 / 涨跌停估算 | **删除**。下单价改走 `live_quote.get_quote(asset)` / `live_quote.get_price_limits(asset)`（统一接口名） |
| `GatewayMarketDataAdapter`（`gateway_market.py`） | live 模式下独立 WebSocket 给 GatewayBrokerAdapter 喂下单价 | **删除**。理由：与 LiveQuote 都从同一 qmt gateway 拿 tick，差异无特别意义 |
| `runtime_market_adapter` 配置项（`settings.py:133`） | `"gateway"` / `"live_quote"` 二选一，决定 `_build_market_data` 走 GatewayMarketDataAdapter 还是 LiveQuoteMarketDataAdapter | **删除**。永远走 LiveQuote |
| `RuntimeContext.market_data` | `modes.py:37` 全局行情端口 | **保留为内部 runtime 配置**（提供 `LiveQuoteMarketDataAdapter` 给策略代码查询），但不再注入到 PaperBroker / GatewayBrokerWrapper 的 `__init__` |

### 7.2 统一后的数据流

**历史数据**：

```
broker.get_history(asset, count, end_dt, frame_type, include_forming_bar)
    ↓
daily_bars.get_bars(n=count, end=end_date, assets=[asset], adjust='qfq')
```

**Forming bar 合并**（仅 paper/live）：

```
if include_forming_bar and end_date == 今日 and end_dt.time() > 9:30:
    forming = live_quote.get_daily_bar(asset)
    bar = _concat_with_forming(hist, forming, count)
```

**Tick 快照**（broker 内部）：

```
PaperBroker.get_quote(asset)              →  live_quote.get_quote(asset)
GatewayBrokerAdapter.get_quote(asset)     →  live_quote.get_quote(asset)
```

### 7.3 删除 `GatewayMarketDataAdapter` 的影响

`runtime_market_adapter="gateway"` 是**默认值**（`settings.py:133`），当前 live 模式下 LiveQuote **不**启动，forming bar **不可用**——这与 #20 的"paper/live forming bar 合并"语义直接冲突。

删除 `GatewayMarketDataAdapter` + 永远启 LiveQuote 后，paper/live **真正完全一致**：

- 历史数据：`daily_bars.get_bars(...)`
- forming bar：`live_quote.get_daily_bar(asset)`
- 下单快照：`live_quote.get_quote(asset)`
- 涨跌停价：`live_quote.get_price_limits(asset)`

**前提**：`runtime.gateway_enabled=True`（用于连接 qmt gateway WebSocket）。`runtime.livequote_mode` 配置项保留（用于决定是否启 LiveQuote），但默认应为 `"gateway"`（"none" 时回退到 backtest）。

### 7.4 具体代码改动

```diff
# quantide/service/sim_broker.py
- self._market_data = market_data
+ # 历史数据走 daily_bars，tick 快照走 live_quote

  def _get_quote(self, asset: str) -> dict[str, Any] | None:
-     if self._market_data is not None:
-         snap = self._market_data.snapshot([asset]).get(asset)
-         if snap is not None:
-             return {...}
-     return live_quote.get_quote(asset)
+     return live_quote.get_quote(asset)

  def _get_price_limits(self, asset: str) -> tuple[float, float]:
      limits = self._limits.get(asset)
      if limits is not None:
          return limits["down"], limits["up"]
-     if self._market_data is not None:
-         return 0.0, 0.0
-     return live_quote.get_price_limits(asset)
+     return live_quote.get_price_limits(asset)

  def _get_history_bars(self, asset, count, end_date, frame_type):
-     if self._market_data is not None and hasattr(self._market_data, "get_history"):
-         return self._market_data.get_history(asset, count, end_date, frame_type)
-     if self._market_data is not None and hasattr(self._market_data, "get_bars"):
-         return self._market_data.get_bars(...)
      if getattr(daily_bars, "_store", None) is not None:
          return daily_bars.get_bars(...)
      return self._empty_history_frame()
```

```diff
# quantide/core/runtime/gateway_broker.py
  class GatewayBrokerWrapper:
-     def __init__(self, adapter, portfolio_id="gateway", history_provider=None):
+     def __init__(self, adapter, portfolio_id="gateway"):
-         self._history_provider = history_provider

      def get_history(self, ...):
-         provider = self._history_provider
-         if provider is None and getattr(daily_bars, "_store", None) is not None:
-             provider = daily_bars
+         if getattr(daily_bars, "_store", None) is None:
+             return self._empty_history_frame()
-         hist = self._provider_get_bars(provider, asset, count, end_date, frame_type)
+         hist = self._provider_get_bars(daily_bars, asset, count, end_date, frame_type)

      def _maybe_attach_forming_bar(self, ...):
-         return self._provider_get_bars(
-             self._history_provider or daily_bars, ...
-         )
+         return self._provider_get_bars(daily_bars, ...)
```

```diff
# quantide/core/runtime/modes.py:_build_market_data
- if use_gateway:
-     client = GatewayClient.from_config()
-     market_data = GatewayMarketDataAdapter(client)
-     market_data.start()
-     adapters.register("market_data", "gateway", market_data)
-     return market_data
  live_quote.start()
  market_data = LiveQuoteMarketDataAdapter(live_quote)
  adapters.register("market_data", "live_quote", market_data)
  return market_data
```

```diff
# quantide/core/runtime/gateway_market.py
- # 整个文件删除
```

```diff
# quantide/config/settings.py
- runtime_market_adapter: str
```

```diff
# quantide/core/runtime/modes.py:_register_gateway_broker_adapter
- if not use_gateway:
-     return
- client = GatewayClient.from_config()
- adapter = GatewayBrokerAdapter(client, market_data=market_data)
- legacy = GatewayBrokerWrapper(adapter)
- ...
- # 删除 use_gateway 分支，简化注册
```

---

## 8. 信号时机：`cheat_on_close`

### 8.1 当前 1d 框架的语义

`quantide/service/runner.py:271-294` 的回测主循环：

```python
for tm in frames:                            # 1d: 每个交易日 1 个 frame
    bar_tm = calendar.replace_time(tm, 9, 30)  # bar_tm 强制锁 9:30
    quote = self._get_bar_quote(...)
    await strategy.on_bar(bar_tm, quote, frame_type)
```

`_resolve_day_signal_date`（`runner.py:156-175`）：

```python
if bar_tm.time() <= 9:30:
    return yesterday        # 9:30 及之前用昨日 K 线
return current_date
```

→ **1d 回测天然是"盘后触发、9:30 开盘成交"**：触发时间 9:30、9:30 看不到当日已收盘 K 线、信号只能用昨日或更早。

### 8.2 cheat_on_close 模式（与 backtrader 对齐）

参数名 **`cheat_on_close`**（与 backtrader `cerebro.broker.set_coc(True)` / `Strategy.cheat_on_close = True` 一致，避免学习成本）。

| 策略声明 | bar_tm | execution_offset | 信号源 | 撮合 |
|---|---|---|---|---|
| `cheat_on_close = False`（默认） | 9:30 | 1（次日 9:30 open 撮合） | 昨日 K 线 | 次日 9:30 open |
| `cheat_on_close = True` | `cheat_on_close_time`（默认 14:57） | 0（当根 close 撮合） | 14:57 forming bar | 当根 close |

**不需要独立的 `execution_offset` 参数**——框架根据 `cheat_on_close` 自动推导。

### 8.3 配置位置

**类属性 + config 字典覆盖**（runner 优先取 `config["cheat_on_close"]`，回退类属性 `self.cheat_on_close`）：

```python
class MyStrategy(BaseStrategy):
    cheat_on_close: bool = False  # 默认：盘后触发、次日开盘成交
```

或 config 字典覆盖：

```python
config = {
    "symbol": "688371.SH",
    "cheat_on_close": True,  # 部署到 portfolio 时覆盖
    ...
}
```

```python
# runner.py 节选
cheat = config.get("cheat_on_close", getattr(strategy, "cheat_on_close", False))
if cheat:
    h, m = map(int, settings.cheat_on_close_time.split(":"))  # "14:57"
    bar_tm = calendar.replace_time(current_date, h, m)
    quote = _get_cheat_close_quote(broker, config, current_date)
else:
    bar_tm = calendar.replace_time(current_date, 9, 30)
    quote = self._get_bar_quote(...)
```

### 8.4 撮合价语义（14:57 集合竞价 close）

| 模式 | cheat_on_close=True 时撮合价 | 备注 |
|---|---|---|
| 回测 | daily_bars 当日 **15:00 close** | 作为 14:57 撮合价的"估算"（1d 数据无 14:57 真实价，但 14:57-15:00 集合竞价撮合价 ≈ 15:00 close，误差通常 < 1 tick） |
| paper | LiveQuote **14:57 当时累积的 close**（即 14:55-14:57 之间的最新 tick 价） | 真实集合竞价前一刻的盘中价 |
| live | LiveQuote **14:57 当时累积的 close** | 同 paper |

**bar_tm = 14:57**（不是 14:55、不是 15:00）：

```python
bar_tm = calendar.replace_time(current_date, 14, 57)
```

**回测 / 实盘偏差处理**：

- 文档需声明："cheat_on_close 模式下回测撮合价用 15:00 close 估算 14:57 集合竞价 close；paper/live 用 14:57 真实盘中价。两者误差通常 < 1 tick，极端行情下偏差可能扩大。"
- 回测报告头部显示撮合价来源（"15:00 close 估算"或"14:57 实时"），便于复盘

### 8.5 `cheat_on_close_time` 系统设置

`cheat_on_close=True` 时的 bar_tm **可在系统设置中配置**（默认 14:57），位置：系统设置（不是策略 config，所有策略共享）。

设计：
- `quantide/config/settings.py` 新增字段 `cheat_on_close_time: str = "14:57"`（HH:MM 格式）
- UI 路径：系统设置 → 策略相关 → "集合竞价撮合时间"
- `runner.py` 启动时读取并解析为 `(h, m)`，bar_tm 用配置的时间
- **警告**：用户调早到 14:50 时，回测撮合价用 daily_bars 15:00 close 估算的偏差**会扩大**（因为实盘撮合价在 14:50 远未到 close）；需在系统设置 UI 提示该偏差

### 8.6 钩子时序

`cheat_on_close=True` 时 **on_bar 在 14:57 自动触发**（取代默认的 9:30），策略**不**需要单独写 `on_close_auction` 钩子——所有逻辑写在 on_bar 里，框架**不**新增 `on_close_auction` 钩子（避免重复）。

- `cheat_on_close=True` 时 on_bar 14:57 触发，**on_day_close 仍 15:30 触发**
- 中间 33 分钟策略**不会**被框架回调；如需在集合竞价撮合期做撤销未成交单等动作，策略作者自己起 timer（超出框架范围）
- 优点：实现最简，钩子时序与 cheat_on_close=False 完全一致，**策略作者无需学新钩子**
- 缺点：策略在 14:57-15:30 期间无框架级回调。如果发现是常见需求，可以后续 issue 加 `on_close_auction` 钩子

### 8.7 回测报告标记

回测报告 metadata 区显示 `cheat_on_close: True` 字段，加 amber / 黄色 badge 提示：

> "此为作弊撮合，paper/live 实盘撮合价可能与回测不同。cheat_on_close 模式下回测撮合价用 15:00 close 估算 14:57 集合竞价 close；paper/live 用 14:57 实时盘中价。两者误差通常 < 1 tick，极端行情下可能扩大。"

撮合价来源（"15:00 close 估算" / "14:57 实时"）一并显示在回测报告头部。

### 8.8 runner.py 改造

```python
# quantide/service/runner.py:271-294 主循环
cheat = config.get("cheat_on_close", getattr(strategy, "cheat_on_close", False))
if cheat:
    h, m = map(int, settings.cheat_on_close_time.split(":"))
    bar_tm = calendar.replace_time(current_date, h, m)
    if frame_type == FrameType.DAY and is_backtest:
        # cheat-on-close: 用 daily_bars 当日已确定 close 模拟 14:57 forming
        quote = _get_cheat_close_quote(broker, config, current_date)
    else:
        # paper/live: 用 live_quote 真实 forming
        quote = _get_live_forming_quote(config)
else:
    bar_tm = calendar.replace_time(current_date, 9, 30)  # 当前实现
    quote = self._get_bar_quote(...)  # 9:30 用昨日 K 线
```

---

## 9. 推荐的策略代码范式

```python
from quantide.core.enums import FrameType
from quantide.service.livequote import live_quote


class MyStrategy(BaseStrategy):
    cheat_on_close: bool = False  # 默认：盘后触发、次日开盘成交

    async def on_bar(self, tm, quote, frame_type):
        if frame_type != FrameType.DAY:
            return

        # 1. 拿历史 — 三模式无缝
        hist = self.get_history(
            self.symbol,
            count=self.window + 5,
            end_dt=tm,
            frame_type="1d",
        )
        if len(hist) < self.window + 2:
            return

        # 2. 拿涨跌停 — paper/live 下 forming 行可能是 None，用 fallback
        last = hist.row(-1, named=True)
        up_limit = last["up_limit"]
        if up_limit is None:
            limits = live_quote.all_limits.get(self.symbol, {})
            up_limit = limits.get("up_limit", float("inf"))

        # 3. 信号逻辑
        last_close = float(last["close"])
        if last_close >= up_limit * 0.998:
            return  # 接近涨停，不开仓

        # 4. 下单 — broker 自动是 BacktestBroker / PaperBroker / GatewayBrokerWrapper
        await self.broker.buy(self.symbol, amount, last_close, tm)
```

要点：
- **不要**写 `if self.broker.__class__.__name__ == "..."` 分支
- **不要**直接读 `self.broker._clock` 或 `live_quote._daily_bars`
- 字段缺失时**显式 fallback**，不要假设 `is_st` / `up_limit` 一定非 None
- `cheat_on_close` 用类属性 + config 覆盖

---

## 10. 验证清单

| 项 | 怎么验证 |
|---|---|
| 三模式 `get_history` 签名一致 | `grep "def get_history" quantide/service/{backtest,sim}_broker.py quantide/core/runtime/gateway_broker.py quantide/core/strategy.py` |
| 12 列 schema 固定 | `grep -A 14 "_empty_history_frame" quantide/service/sim_broker.py quantide/core/runtime/gateway_broker.py` |
| `include_forming_bar` 三模式参数都有 | 同上 |
| 回测字段完整 | `python -c "import polars as pl; df=pl.read_parquet('tests/assets/2024_bars.parquet'); print(df.columns)"`（生产数据有 12 列） |
| Paper/Live forming 行 4 字段补齐（P0 实施后） | `pytest tests/service/test_forming_daily_bars.py -v` |
| UI 按钮路由 | `quantide/web/pages/strategy.py:880-955`（按钮构建）+ `1900, 1950`（POST 路由） |
| 部署到 paper/live | `quantide/service/strategy_runtime.py:227, 269` |
| LiveQuote 在 stub / 真实 live 都启动 | `modes.py:140-143`（`live_quote.start()` 永远调用） |

---

## 11. 实施路线图

| 阶段 | 内容 | 规模 |
|---|---|---|
| **P0** | forming bar 4 字段补齐 + cheat_on_close 路径测试 + 删 PaperBroker._market_data | ~50 行 + 5-6 测试 |
| **P0.5** | `cheat_on_close_time` 系统设置（settings 字段 + UI 路径） | ~30 行 + 3 测试 |
| **P0.7** | live broker 截图订单 + DeferredOrderQueue + 限价单（昨收/今开 + 滑点） | ~80 行 + 5-6 测试 |
| **P1** | cheat_on_close 双触发框架（runner.py / strategy.py / strategy_runtime.py） | ~70 行 + 6-8 测试 |
| **P1.5** | 策略 config UI（default_config + 表格 key/default/custom）+ paper/live 撮合时机明确 | ~50 行 + 4 测试 |
| **P2** | 删 GatewayBrokerWrapper._history_provider + 删 GatewayMarketDataAdapter + 删 runtime_market_adapter + 统一下单价接口 | ~80 行 + 5-6 测试 |
| **P3** | 回测报告 UI 显示 cheat_on_close amber badge + 撮合价来源 | UI 改动 + backtest_logs 字段 |
| **P4**（不在 v0.1） | 分钟级框架（1m / 5m `frame_type` 支持） | 独立 milestone |

### P0: forming bar 字段补齐 + cheat_on_close 路径测试

- `quantide/service/sim_broker.py:307-356` `_concat_with_forming`：补 `up_limit` / `down_limit` / `is_st` / `adjust` 4 字段
- `quantide/core/runtime/gateway_broker.py` `_concat_forming_with_history`：同上
- `quantide/service/sim_broker.py:73, 171-191` `_market_data` 字段删除，迁直接调 `live_quote`
- 新增测试：cheat_on_close=True 时 paper/live 路径的字段补齐

### P0.7: live broker 截图订单 + DeferredOrderQueue

- `quantide/core/ports/broker.py` `OrderRequest` **不**新增字段
- `quantide/core/runtime/gateway_broker.py` GatewayBrokerWrapper 接 buy/sell 时检查 `runtime_mode == "live" and strategy.cheat_on_close == False`：
  - 是 → 把 `(request, execution_window, slippage, scheduled_at)` 放进 `DeferredOrderQueue`
  - 否 → 立即 `submit()`
- broker 启动时起 `asyncio.create_task(self._deferred_order_loop())`：每 1 秒扫队列
- `scheduled_at` 计算：
  - `execution_window=auction` → 次日 9:25
  - `execution_window=post_auction` → 次日 9:30:00.001
- price 计算：`(昨收/今开) × (1 + slippage)`，bid_type=LIMIT
- 策略 config 新增 `live_execution_window` 和 `live_execution_slippage`（默认值见 §3.6）
- 测试：截图订单在队列里、到点发出、限价单 price 估算、废单行为
- **v0.1 不做**：DeferredOrderQueue 持久化（broker 重启丢 pending 订单）

### P0.5: `cheat_on_close_time` 系统设置

- `quantide/config/settings.py` 新增字段 `cheat_on_close_time: str = "14:57"`
- `quantide/web/pages/system/` 新增 UI：集合竞价撮合时间设置
- `quantide/service/runner.py:271-294` 主循环读 settings.cheat_on_close_time，bar_tm 用配置的时间
- 文档：用户调早到 14:50 时回测撮合价偏差扩大的警告

### P1: cheat_on_close 双触发框架

- `quantide/core/strategy.py`：`cheat_on_close: bool = False` 类属性
- `quantide/service/runner.py:271-294` 主循环按 §8.8 改造
- `quantide/service/strategy_runtime.py`：paper/live 启动时读取 cheat_on_close，决定 14:57 是否触发 on_bar
- **不新增** `on_close_auction` 钩子

### P1.5: 策略 config UI + paper/live 撮合时机

- `quantide/core/strategy.py` `BaseStrategy` 新增类方法 `default_config() -> dict`（默认 `{}`）
- 各策略覆盖 `default_config()`（如 `dual_ma.py`）
- `quantide/web/pages/strategy.py` `_paper_deploy_modal` / `_live_deploy_modal`：
  - 渲染策略 config 表格（列：key / default / custom）
  - `custom` 列默认等于 `BacktestRun.config[key]`，可编辑
  - 提交时 form 字段 `custom_*` 合并回 config dict
- `quantide/service/strategy_runtime.py` `deploy_to_paper` / `deploy_to_live` 接 `config: dict` 参数，传入 `_start_strategy_runtime`
- **paper/live 撮合时机**：明确"立即按当前价撮合"（与回测 execution_offset=1 不严格一致，但符合实时直觉）
- 测试：config 表格渲染、custom 列编辑、嵌套 dict 暂不支持的提示

### P2: 消除 `_history_provider` + 统一下单价接口 + 删除 GatewayMarketDataAdapter

- `quantide/core/runtime/gateway_broker.py:80-91` 构造函数删除 `history_provider` 参数
- `quantide/core/runtime/gateway_broker.py:114-118, 169` fallback 路径统一为 `daily_bars`
- `quantide/core/runtime/gateway_broker.py:555-562, 917, 933` `_market_data` 删除
- `quantide/core/runtime/gateway_broker.py` `_resolve_price` / `_resolve_sizing_price` 改用 `live_quote.get_quote(asset)` / `live_quote.get_price_limits(asset)`
- `quantide/service/sim_broker.py` `_get_quote` / `_get_price_limits` 改用 `live_quote.get_quote(asset)` / `live_quote.get_price_limits(asset)`
- `quantide/core/runtime/modes.py:126-143` `_build_market_data` 删除 `use_gateway` 分支，**永远**调 `live_quote.start()` + `LiveQuoteMarketDataAdapter`
- `quantide/core/runtime/gateway_market.py` GatewayMarketDataAdapter 实现**整个文件删除**
- `quantide/config/settings.py:133` 删除 `runtime_market_adapter="gateway"` 默认值
- `modes.py:189-218` `_register_gateway_broker_adapter` 简化

### P3: 回测报告 UI 显示 cheat_on_close 警告

- `quantide/web/pages/strategy.py` 回测报告 header 区：amber badge + 撮合价来源 + 偏差说明文本
- `quantide/service/backtest_logs.py` 持久化字段增加 `cheat_on_close: bool` 和 `cheat_on_close_time: str`

### P4（不在 v0.1）: 分钟级框架

- 1m / 5m `frame_type` 支持
- `cheat_on_close` 不需要（1m 已有真实盘中价）

---

## 12. 关键决策记录

| 决策 | 理由 |
|---|---|
| 策略唯一入口 `BaseStrategy.get_history` | 一行委托给 broker，策略代码 0 改动跨模式 |
| 三模式数据全部来自 `daily_bars`（tushare 落盘） | `tushare` 是唯一历史数据源；`LiveQuote` 只补 forming bar（live/paper 才有 tick 流） |
| forming bar 合并由 broker 内部完成 | 策略不感知细节，统一返 12 列 schema |
| 形成行 4 字段（up_limit / down_limit / is_st / adjust）补齐方案 | 复用 `LiveQuote._limits` 已有 9:00 cron 拉取（`livequote.py:194-202`）；`is_st` 从 daily_bars 拿昨日行；`adjust` 填 1.0（与回测语义一致） |
| 删除 `GatewayMarketDataAdapter` | 与 LiveQuote 都从同一 qmt gateway 拿 tick，差异无特别意义；统一接口让 stub / 真实 / paper / live 全部一致 |
| 删除 `runtime_market_adapter` 配置项 | 永远走 LiveQuote（已 fix §7.3 的"默认 live 下 LiveQuote 不启动"问题） |
| `cheat_on_close` 参数名 | 与 backtrader `cerebro.broker.set_coc(True)` / `Strategy.cheat_on_close = True` 对齐，避免学习成本 |
| 不需要 `execution_offset` 参数 | 默认永远是 1（次日开盘成交），开启 cheat 后变 0（当根 close 撮合） |
| `cheat_on_close_time` 在系统设置 | 所有策略共享（不是策略 config）；用户调早会扩大回测偏差，UI 需警告 |
| cheat_on_close 默认 14:57（A 股集合竞价撮合时刻） | 14:57 后进入集合竞价撮合，15:00 产生收盘价；撮合价 ≈ close，偏差最小 |
| 回测撮合价 = 15:00 close（估算 14:57 撮合） | 1d 数据无 14:57 真实价；与实盘 14:57 实时价误差通常 < 1 tick |
| cheat_on_close=True 时不新增 `on_close_auction` 钩子 | 14:57 自动触发 on_bar，策略不需要重复实现 |
| 12 列固定 schema（`date, asset, open, high, low, close, volume, amount, adjust, is_st, up_limit, down_limit`） | 跨模式一致；形成行缺字段时 fill_null(1.0) 等兜底 |
| stub 模式天然契合统一接口设计 | broker 接口、LiveQuote 累积路径、WebSocket 协议完全一致；唯一差异是数据本身（mock vs 真实） |
| paper/live 撮合时机：立即按当前价撮合 | 简化，符合 paper/live "实时"直觉；与回测 execution_offset=1 严格语义不完全一致，文档需明确 |
| paper/live 运行时段：从回测 end_date +1 起持续运行到 portfolio 手动停止 | 策略 runtime 是长生命周期 |
| 策略 config UI：表格 key/default/custom，custom 列默认等于 BacktestRun.config | 用户可直观修改 config；继承回测参数 |
| config 数据格式：当前只支持无嵌套 dict | 简化实现；嵌套支持延后到 P5+ |
| 策略类通过 `default_config() -> dict` 静态方法暴露默认值 | 统一接口；UI 模态框可遍历渲染 |
| paper / cheat_on_close=True：立即按当前价撮合 | 14:57 在合法集合竞价撮合时段内 |
| paper / cheat_on_close=False：等到次日 9:25 集合竞价结束撮合 | qmt-gateway 能拿集合竞价数据则用集合竞价 close；否则 fallback 到次日第 1 根 bar 撮合价 |
| live / cheat_on_close=True：14:57 立即发单 | 14:57-15:00 集合竞价撮合时段，发单合法 |
| live / cheat_on_close=False：broker **截图订单**（不立即送 qmt-gateway）+ 延迟到次日 9:25/9:30 + 限价单（昨收/今开 + 滑点） + 废单允许 | qmt-gateway 协议不变；复杂度留在 Millionaire broker 内部；策略 config 新增 `live_execution_window` 和 `live_execution_slippage` |
| 多策略 live 抢资金 | v0.1 不做分仓；billionaire 功能；文档明确告知 |

---

## 13. 已知未实施项（按 Aaron 决策延后）

- **daily_bars 未同步的错误处理**（§5.5）：当前不实现，以错误日志/toast 提示（P3 范围）
- **盘前 cron 入库 ST + 涨跌停价**（`is_st` / `up_limit` / `down_limit`）：当前 daily_bars 落盘数据是日级（盘后入库），不覆盖日内。LiveQuote `_start_limit_schedule`（`livequote.py:194-202`）已每天 9:00 拉 limits。`is_st` 由 `fetch_bars_ext` 一次性落盘
- **分钟级框架**（P4）：不在 v0.1 范围

## 14. 已知风险与开放问题

| # | 风险 / 问题 | 状态 | 文档位置 |
|---|---|---|---|
| R1 | cheat_on_close=False + live 模式下，15:00 立即发单是废单（9:30 之前不是合法委托时段） | **已决策**：broker 内部截图订单 + 延迟到次日 9:25/9:30 + 限价单（昨收/今开 + 滑点） | §3.6 |
| R2 | 多策略 live 抢资金（共享 gateway 账户，无分仓） | **已知风险**，文档说明；分仓是 billionaire 功能 | §3.7 |
| R3 | daily_bars 落盘数据可能未同步到最新（盘中调 `get_history` 时） | **已知风险**，当前不实现，toast 提示延后 | §5.5 |
| R4 | cheat_on_close=True 时回测撮合价用 15:00 close 估算 14:57 撮合，与实盘有偏差（< 1 tick 正常，极端扩大） | **已知**，amber badge + 撮合价来源标注 | §8.7 |
| R5 | cheat_on_close=True 模式下用户调早 `cheat_on_close_time`（如 14:50）会扩大回测撮合价偏差 | **已知**，系统设置 UI 需警告 | §8.5 |
| R6 | `cheat_on_close_time` 调早到 09:30 之前或收盘后导致触发时刻不合法 | **待校验**，需要在 settings 加范围校验（09:00-15:00） | §8.5 |
| R7 | config 嵌套 dict（v0.1 不支持） | **延后**，P5+ | §3.5 |
