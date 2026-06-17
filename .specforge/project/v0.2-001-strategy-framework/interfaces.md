# Interfaces — v0.2-001-strategy-framework

- **Spec ID**: v0.2-001-strategy-framework
- **位置**: 与 [spec.md](./spec.md) (含索引)/ [acceptance.md](./acceptance.md) / [test-plan.md](./test-plan.md) 同源
- **性质**: 外部可观测契约清单 — 测试工程师据此写黑盒测试,实现层据此暴露 API/数据 schema
- **基线**: 严格对齐 [spec-strategy.md](./spec-strategy.md) 已确定部分(FR-010 ~ FR-020);NFR 引用 [spec-foundation.md NFR-050](./spec-foundation.md)
- **范围外**: FR > 020 未确定的 FR,本文件不涉及

> **本文件不是实现设计,是从 spec 推导出的"接口冻结"清单**。实现层如发现接口无法实现,需回退到 spec 修订而非本文件。

## 0. 文档约定

| 字段 | 含义 |
|---|---|
| **Endpoint** | HTTP method + 路径;FastAPI 风格 |
| **Request** | 请求体/参数 schema(字段名 + 类型 + 必填) |
| **Response** | 响应 schema;成功/失败各列 |
| **状态码** | HTTP 状态码 + 业务语义 |
| **观测点** | 该接口数据最终落盘的位置(供测试断言) |
| **关联 AC** | 引用的 acceptance.md 条目 |

错误响应统一约定:

```json
{
  "error": {
    "code": "STRATEGY_NOT_FOUND",
    "message": "Strategy 'my_strategy' not found in user directory or built-ins",
    "details": { "...": "..." }
  }
}
```

错误码命名:`{域}_{细分}`,全大写,下划线分隔。

## 1. 策略框架外部契约(策略编写视角)

策略**编写者**使用的接口(spec FR-010/013/020 直接约束)。用户视角只有两个可继承基类：`BaseStrategy`（独立策略）与 `RiskStrategy`（风控策略）；二者均继承自抽象根 `Strategy`（用户不直接继承）。

```
                ┌─────────────────────────────┐
                │      Strategy (抽象根)        │  ← 生命周期 + 声明 + 可观测
                │      用户不直接继承            │     （可设为 ABC）
                └────────────┬────────────────┘
            ┌────────────────┴───────────────┐
            ▼                                ▼
   ┌─────────────────────┐         ┌─────────────────────┐
   │    BaseStrategy     │         │    RiskStrategy     │
   │   独立策略基类        │         │   风控策略基类        │
   │ 账户·买卖·on_bar·数据 │         │ 宿主·卖出·on_check·数据│
   └──────────▲──────────┘         └──────────▲──────────┘
              │ 用户继承                        │ 用户继承
       class MyStrategy(...)            class MyRiskStrategy(...)
```

> `RiskStrategy` 是 `BaseStrategy` 的**兄弟**而非子类——结构性地拿不到 `buy`/`positions`/`cash`，"风控只卖不买"由继承结构保证。

### 1.1 `Strategy`(抽象根, FR-010)

抽象根，承载所有策略共享的契约。用户不直接继承此类（可设为 ABC）。`BaseStrategy` 与 `RiskStrategy` 均继承自它。

```python
class Strategy(ABC):
    def __init__(self, broker: "Broker", config: dict[str, Any]) -> None: ...
    @staticmethod
    def default_config() -> dict[str, Any]: ...  # 默认返回 {}
    async def init(self) -> None: ...
    async def on_start(self) -> None: ...
    async def on_stop(self) -> None: ...
    async def on_day_open(self, tm: datetime.datetime) -> None: ...
    async def on_day_close(self, tm: datetime.datetime) -> None: ...
    def log(self, msg: str, *, tm: datetime.datetime | None = None,
            level: str = "INFO") -> None: ...
    def record(self, key: str, value: float,
               dt: datetime.datetime | None = None,
               extra: dict | None = None) -> None: ...
    def get_bars(self, asset: str, count: int,
                 end_dt: datetime.datetime | None = None,
                 frame_type: str = "1d",  # "1d" | "30m",运行时参数非类型
                 include_forming_bar: bool = True) -> pl.DataFrame: ...
```

**约束**:
- `get_bars(frame_type)` 支持 `"1d" | "30m"`;其他 → `ValueError`
- **可回测性是派生属性**：`frame_type="1d"` 的数据可回测；`"30m"` 等 live-only 粒度仅 paper/live 实时聚合。`BacktestRunner` 在策略调用 live-only 粒度时抛 `UnsupportedFrameTypeForBacktest`（运行时检查）
- 资金从本策略 `portfolio_id` 账户扣减;`positions` / `cash` 只反映本账户（仅 BaseStrategy 有）
- 调度路径由数据粒度决定：可回测粒度走 FR-230（回测→仿真→实盘）；live-only 粒度走 FR-240（仿真→实盘）

> **决策驱动钩子不在抽象根**：`on_bar`（时序，BaseStrategy 专有）与 `on_check`（事件，RiskStrategy 专有）语义不同，分属两个基类，不上提。

### 1.2 `BaseStrategy`(独立策略, FR-010)

独立策略基类。在 `Strategy` 之上扩展账户、交易、决策驱动三类能力。**`get_bars` 在抽象根已定义，独立策略继承即可，不再重复**。

```python
class BaseStrategy(Strategy):
    async def on_bar(self, tm: datetime.datetime) -> None: ...  # 唯一决策入口,默认 pass
    async def buy(self, asset: str, shares: int, price: float = 0,
                  order_time: datetime.datetime | None = None) -> "TradeResult": ...
    # buy_percent / buy_amount / sell / sell_percent / sell_amount 同形
    async def cancel_order(self, qt_oid: str) -> None: ...
    async def cancel_all_orders(self, side: str | None = None) -> int: ...
    async def trade_target_pct(self, asset: str, target_pct: float) -> "TradeResult": ...
    @property
    def positions(self) -> dict[str, "Position"]: ...
    @property
    def cash(self) -> float: ...
```

**约束**:
- **类层不存在** `get_ticks` / `get_prices` / `sell_host_position` / `on_check`——由继承结构保证（`BaseStrategy` 继承 `Strategy` 而非 `RiskStrategy`），非运行时检查
- 资金从本策略 `portfolio_id` 账户扣减;`positions` / `cash` 只反映本账户
- 调度路径由数据粒度决定：可回测粒度走 FR-230（回测→仿真→实盘）；live-only 粒度走 FR-240（仿真→实盘）

**关联 AC**: AC-010-01 ~ 04

### 1.3 `RiskStrategy`(风控策略, FR-013)

风控策略基类，`BaseStrategy` 的**兄弟**（均继承自 `Strategy`）。**不继承 BaseStrategy**，因此类层无 `buy` / `positions` / `cash` / `get_bars`（`get_bars` 从抽象根继承）。

```python
class RiskStrategy(Strategy):  # 兄弟类,非 BaseStrategy 子类
    # 无 buy / sell / positions / cash（继承结构保证）
    async def on_check(self, positions: dict[str, "Position"],
                       tm: datetime.datetime) -> None: ...  # tick/事件触发,默认 pass
    def get_prices(self, assets: list[str]) -> dict[str, float]: ...
    def get_ticks(self, asset: str, count: int) -> pl.DataFrame: ...
    async def sell_host_position(self, asset: str, shares: int,
                                 reason: str) -> "TradeResult": ...
```

**约束**:
- **类层不暴露** `buy` / `sell` / `buy_amount` / `sell_percent` / `positions` / `cash`——由继承结构保证（`RiskStrategy` 继承 `Strategy` 而非 `BaseStrategy`），非运行时检查
- **无 `portfolio_id`**;`positions` / `cash` 属性访问抛 `AttributeError`
- 不可独立运行;必须绑定一个宿主 `BaseStrategy`。绑定关系在运行配置中建立（可热调），不在策略代码中以类属性声明
- 宿主进入 paper/live 时自动激活;宿主停止时一并停止;可随时单独停止/重新启动（每次重启记一个新"开启区间"，超额收益按区间独立累计，FR-013/FR-360）
- **可回测**：⏸ 暂缓（v0.2 不强制风控可回测；是否回测由风控自身是否依赖 `get_prices` / `get_ticks` 等 live-only 数据决定；详见 FR-013 §回测状态）

**关联 AC**: AC-013-01 ~ 05

### 1.4 枚举契约(FR-020)

枚举函数(框架内部,黑盒测试通过 §2 API 触发):

```python
def enumerate_strategies(
    root: str | Path | None = None,
    include_builtin: bool = True,
) -> "EnumerationResult":
    """枚举策略类;不执行 import 之外的副作用"""
    ...

@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str                # f"{module}.{class_name}"
    name: str                       # __display_name__ or __name__
    description: str                # docstring 首行
    strategy_type: Literal["independent", "risk"]  # 由最终基类推导: BaseStrategy→independent, RiskStrategy→risk
    module: str
    is_builtin: bool
    default_config: dict[str, "ParamSpec"]
    skipped_reasons: list["SkippedReason"]  # 仅未识别类

@dataclass(frozen=True)
class ParamSpec:
    name: str
    default: Any
    type_hint: type | None = None       # v0.2 始终 None
    description: str | None = None      # v0.2 始终 None
    constraints: dict | None = None     # v0.2 始终 None

class SkippedReason(str, Enum):
    PERMISSION_DENIED = "PermissionDenied"
    SYNTAX_ERROR = "SyntaxError"
    IMPORT_ERROR = "ImportError"
    MODULE_INIT_ERROR = "ModuleInitError"
    NOT_A_STRATEGY = "NotAStrategy"
    INVALID_CONFIG = "InvalidConfig"
    BUILTIN_OVERRIDDEN = "BuiltinOverridden"

@dataclass(frozen=True)
class SkippedEntry:
    path: str
    class_name: str | None      # 文件级失败时 None
    reason: SkippedReason
    detail: str                 # 异常消息或诊断信息

@dataclass(frozen=True)
class EnumerationResult:
    strategies: list[StrategyMetadata]
    diagnostics: list[SkippedEntry]
```

**约束**:
- `root=None` → 使用框架配置的用户策略根目录;未配置时回退到内置示例目录
- 不递归子目录;只扫顶层 `.py` 文件
- `__pycache__/*.pyc` 跳过
- 单文件失败不阻塞整体
- 重复 `strategy_id` 不去重(全保留);展示层优先级见 UI spec
- 4 模式(回测/仿真/实盘/dry-run)下结果一致

**关联 AC**: AC-020-01 ~ 15

## 2. Web API 契约(框架 HTTP 暴露)

> **状态**: spec 未硬定 URL。本节按 FastAPI 惯例与 v0.2-002-ui 需求推断。**最终 URL 由实现层在启动时确认并冻结**,但**响应 schema 是契约,不可变**。

### 2.1 策略枚举 API

**Endpoint**: `GET /api/strategies`

**Request**: 无请求体。可选 query:`include_builtin=true`(默认 true)、`root=<path>`(默认 None)

**Response 200**:

```json
{
  "strategies": [
    {
      "strategy_id": "user.MyStrategy",
      "name": "My Strategy",
      "description": "An independent strategy",
      "strategy_type": "independent",
      "module": "user",
      "is_builtin": false,
      "default_config": {
        "fast": { "name": "fast", "default": 5 },
        "slow": { "name": "slow", "default": 20 }
      },
      "skipped_reasons": []
    }
  ],
  "diagnostics": [
    {
      "path": "/strategies/broken.py",
      "class_name": null,
      "reason": "SyntaxError",
      "detail": "unexpected EOF at line 42"
    }
  ]
}
```

**错误码**:

| HTTP | code | 触发 |
|---|---|---|
| 200 | — | 正常 |
| 500 | `ENUMERATION_FAILED` | 枚举过程发生不可恢复错误(目前不应触发,所有失败均进入 diagnostics) |

**关联 AC**: AC-020-04, AC-020-08 ~ 12

### 2.2 策略参数查询 API

**Endpoint**: `GET /api/strategies/{strategy_id}/config`

**Response 200**:

```json
{
  "strategy_id": "user.MyStrategy",
  "default_config": { "fast": 5, "slow": 20 }
}
```

**关联 AC**: AC-010-03

### 2.3 交易日历 API(FR-014)

#### 2.3.1 `is_trade_day`

**Endpoint**: `GET /api/calendar/is_trade_day?date=YYYY-MM-DD`

**Response 200**:

```json
{ "date": "2024-09-30", "is_trade_day": true }
```

#### 2.3.2 `day_shift`

**Endpoint**: `GET /api/calendar/day_shift?date=YYYY-MM-DD&offset=N`

**Response 200**:

```json
{ "input_date": "2024-09-30", "offset": 1, "result_date": "2024-10-08" }
```

`offset=0` → 返回最近已结束的交易日(根据 test 数据 2025-12-31 计算)

#### 2.3.3 `count_trading_days`

**Endpoint**: `GET /api/calendar/count?start=YYYY-MM-DD&end=YYYY-MM-DD`

**Response 200**:

```json
{ "start": "2024-09-30", "end": "2024-10-11", "count": 8 }
```

`start > end` → 400 + `code="INVALID_RANGE"`

#### 2.3.4 `get_trade_dates`

**Endpoint**: `GET /api/calendar/dates?start=YYYY-MM-DD&end=YYYY-MM-DD`

**Response 200**:

```json
{
  "start": "2024-09-30",
  "end": "2024-10-11",
  "dates": ["2024-09-30", "2024-10-08", "2024-10-09", "2024-10-10", "2024-10-11"]
}
```

#### 2.3.5 `last_trade_date`

**Endpoint**: `GET /api/calendar/last_trade_date`

**Response 200**:

```json
{ "date": "2024-12-31" }
```

`last_trade_date()` 返回"最近一个已结束的交易日",与 `day_shift(<any>, 0)` 语义一致。回测模式下基于仿真时间;paper/live 基于真实时间。早于数据范围时抛 `RangeExhausted`(关联 AC-014-05)。

按日期升序,不含周末与节假日。

**关联 AC**: AC-014-01 ~ 04

### 2.4 证券列表 API(FR-015)

#### 2.4.1 `stocks_listed`

**Endpoint**: `GET /api/securities/listed?date=YYYY-MM-DD&exclude_st=true`

**Response 200**:

```json
{ "date": "2024-09-30", "exclude_st": true, "stocks": ["000001.SZ", "000002.SZ", "..."] }
```

#### 2.4.2 `is_st`

**Endpoint**: `GET /api/securities/is_st?asset=000001.SZ&date=YYYY-MM-DD`

**Response 200**:

```json
{ "asset": "000001.SZ", "date": "2024-09-30", "is_st": false }
```

#### 2.4.3 `days_since_ipo`

**Endpoint**: `GET /api/securities/days_since_ipo?asset=000001.SZ&date=YYYY-MM-DD`

**Response 200**:

```json
{ "asset": "000001.SZ", "date": "2024-09-30", "days": 1234 }
```

`date < ipo_date` → 0

#### 2.4.4 `get_name`

**Endpoint**: `GET /api/securities/name?asset=000001.SZ`

**Response 200**:

```json
{ "asset": "000001.SZ", "name": "平安银行" }
```

资产不存在 → 404 + `code="ASSET_NOT_FOUND"`

**关联 AC**: AC-015-01 ~ 04

## 3. 数据文件 / 数据库 schema

> 实施时落盘位置由实现层确定;**字段名、类型、必填为契约,不可变**。

### 3.1 回测结果 JSON(回测完成后落盘)

```json
{
  "run_id": "uuid",
  "strategy_id": "user.MyStrategy",
  "strategy_type": "independent",
  "interval": { "start": "2024-01-01", "end": "2024-12-31" },
  "initial_capital": 1000000.0,
  "final_value": 1150000.0,
  "returns": 0.15,
  "metrics": {
    "annual_return": 0.15,
    "max_drawdown": -0.08,
    "sharpe_ratio": 1.2,
    "sortino_ratio": 1.5,
    "calmar_ratio": 1.875,
    "win_rate": 0.55,
    "profit_loss_ratio": 1.8,
    "trade_count": 24
  },
  "nav_curve": [
    { "date": "2024-01-02", "nav": 1.0 },
    { "date": "2024-01-03", "nav": 1.005 }
  ],
  "trades": [
    {
      "trade_id": "uuid",
      "asset": "000001.SZ",
      "side": "buy",
      "shares": 100,
      "price": 10.5,
      "amount": 1050.0,
      "commission": 5.0,
      "timestamp": "2024-03-15T09:35:00",
      "order_id": "qt_xxx"
    }
  ],
  "skipped_days": ["2024-04-19"],   // 停牌/数据缺失
  "completed_at": "2024-04-20T16:30:00"
}
```

### 3.2 委托表(orders)

| 列 | 类型 | 说明 |
|---|---|---|
| `order_id` | str (PK) | 框架生成,`qt_` 前缀 |
| `strategy_id` | str | 归属策略 |
| `asset` | str | 标的代码 |
| `side` | str | `buy` / `sell` |
| `shares` | int | 委托数量 |
| `price` | float | 限价(`0` 表示市价) |
| `status` | str | `pending` / `filled` / `rejected` / `cancelled` |
| `created_at` | datetime | 委托时间(仿真时间) |
| `filled_at` | datetime \| null | 成交时间 |
| `filled_price` | float \| null | 成交价 |
| `reject_reason` | str \| null | 拒绝原因 |

### 3.3 成交表(fills)

| 列 | 类型 | 说明 |
|---|---|---|
| `fill_id` | str (PK) | |
| `order_id` | str (FK) | 关联委托 |
| `strategy_id` | str | |
| `asset` | str | |
| `side` | str | |
| `shares` | int | 成交数量 |
| `price` | float | 成交价 |
| `commission` | float | 佣金 |
| `tax` | float | 印花税 |
| `timestamp` | datetime | 成交时间 |

### 3.4 虚拟账本快照(accounts)

| 列 | 类型 | 说明 |
|---|---|---|
| `strategy_id` | str (PK) | |
| `cash` | float | 可用资金 |
| `total_value` | float | 总资产(含持仓市值) |
| `as_of` | datetime | 快照时间 |

### 3.5 持仓表(positions)

| 列 | 类型 | 说明 |
|---|---|---|
| `strategy_id` | str (PK part) | |
| `asset` | str (PK part) | |
| `shares` | int | 总持仓 |
| `sellable_shares` | int | 可卖持仓(T+1 约束) |
| `cost_basis` | float | 加权均价 |
| `as_of` | datetime | 快照时间 |

### 3.6 风控触发事件(risk_events)

| 列 | 类型 | 说明 |
|---|---|---|
| `event_id` | str (PK) | |
| `risk_strategy_id` | str | 风控策略 |
| `host_strategy_id` | str | 宿主策略 |
| `asset` | str | |
| `trigger_price` | float | 触发价 |
| `cost_basis` | float | 成本价 |
| `reason` | str | `cost_stop` / `drawback` / ... |
| `timestamp` | datetime | |

### 3.7 超额收益事件(excess_returns)

| 列 | 类型 | 说明 |
|---|---|---|
| `event_id` | str (PK) | 与 risk_events.event_id 对应 |
| `risk_strategy_id` | str | |
| `host_strategy_id` | str | |
| `asset` | str | |
| `sell_price` | float | |
| `close_price_n` | float \| null | N 日后收盘价(N=0 即当日) |
| `n_window` | int | 窗口(默认 0) |
| `excess_return` | float \| null | `(sell_price - close_price_n) / sell_price`;数据不足时 null |
| `is_final` | bool | false=待回填,true=终值 |
| `created_at` | datetime | |
| `finalized_at` | datetime \| null | |

### 3.8 枚举缓存 JSON(枚举结果持久化)

```json
{
  "version": "1",
  "generated_at": "2026-06-17T10:00:00",
  "strategies": [/* StrategyMetadata 数组 */],
  "diagnostics": [/* SkippedEntry 数组 */]
}
```

### 3.9 交易日历 Parquet(test-plan §1.1.1)

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | date (PK) | |
| `is_trade_day` | bool | |
| `exchange` | str | 交易所代码(预留,统一 SSE/SZSE 时为 `ALL`) |

### 3.10 证券列表 Parquet

| 列 | 类型 | 说明 |
|---|---|---|
| `asset` | str (PK) | |
| `name` | str | |
| `pinyin` | str | |
| `list_date` | date | |
| `delist_date` | date \| null | |
| `exchange` | str | |

## 4. 异常 / 错误码表

| code | HTTP | 触发场景 | 关联 AC |
|---|---|---|---|
| `STRATEGY_NOT_FOUND` | 404 | API 查询不存在 strategy_id | — |
| `INVALID_FRAME_TYPE` | 400 | `get_bars(frame_type)` 取值不在 `{"1d", "30m"}` 之内 | AC-010-XX |
| `UNSUPPORTED_FRAME_TYPE_FOR_BACKTEST` | 400/409 | 回测模式下 `get_bars(frame_type != "1d")` 抛（运行时检查） | AC-010-XX |
| `INVALID_RANGE` | 400 | 交易日历 `start > end` | AC-014-03 |
| `ASSET_NOT_FOUND` | 404 | `get_name` 资产代码不存在 | — |
| `RISK_NO_ACCOUNT` | 400/422 | RiskStrategy 访问 `positions` / `cash` | AC-013-01 |
| `RISK_NOT_BOUND` | 422 | RiskStrategy 启动时未绑定宿主 | AC-013-05 |
| `RISK_NO_BUY_API` | 400/422 | RiskStrategy 调用 buy 类方法 | AC-013-02 |
| `ENUMERATION_FAILED` | 500 | 不可恢复的枚举错误 | AC-020-12 |

> 注:`UNSUPPORTED_FRAME_TYPE_FOR_BACKTEST` 是 `RuntimeError` 子类，仅在 BacktestRunner 上下文抛出；paper/live 不受影响。

> **⏸ 暂缓**：风控策略回测语义未固化前，`get_prices` / `get_ticks` 在回测下的行为不写进错误码表（不抛错还是返回模拟值由实现层决定）。

## 5. 日志条目类型(从 test-plan §3.1.3 细化)

| event | 字段 | level | 关联 FR |
|---|---|---|---|
| `strategy.enumerated` | `strategy_id, is_builtin, default_config_size` | INFO | FR-020 |
| `strategy.skipped` | `path, class_name, reason, detail` | WARNING | FR-020 |
| `strategy.lifecycle` | `strategy_id, hook, tm` | DEBUG | FR-010 |
| `order.submitted` | `strategy_id, asset, side, shares, price` | INFO | FR-010 |
| `order.filled` | `strategy_id, asset, filled_qty, fill_price, ts` | INFO | FR-010/013 |
| `order.cancelled` | `strategy_id, order_id, reason` | INFO | FR-013 |
| `risk.triggered` | `risk_strategy_id, host_strategy_id, asset, trigger_price, cost, reason, ts` | INFO | FR-013/125 |
| `risk.excess_return.finalized` | `event_id, excess_return` | INFO | FR-013/360 |
| `backtest.started` | `strategy_id, params, interval` | INFO | FR-010 |
| `backtest.progress` | `strategy_id, current_day, total_days, pct` | INFO | FR-010 |
| `backtest.completed` | `strategy_id, metrics` | INFO | FR-010 |

## 6. 与现有实现的冲突与处理

### 6.1 现状摘要

实现层 `quantide/core/strategy.py` 当前**只含 `BaseStrategy` 一个空壳类**(157 行):
- 有: `__init__`, `init`, `on_start`, `on_stop`, `on_day_open`, `on_day_close`, `default_config`, `get_history`, `log`, `record`
- 缺: `Strategy` 抽象根, `RiskStrategy`, `on_bar`, `on_check`, `get_bars`(叫 `get_history`), `get_prices`, `get_ticks`, 账户接口(`buy`/`sell`/`positions`/`cash`/`sell_host_position`)
- 缺: 回测端点(`backtest.started` 等日志触发点)
- 缺: 风控触发 / 超额收益日志触发点

> 之前记录的"DayStrategy / LiveStrategy 子类已存在"是**误判** — 实际不存在。本节冲突表按实际空壳重写。

### 6.2 已识别冲突(基于实际代码核对)

| # | 冲突点 | spec 决定 | 现有实现 | 处理 |
|---|---|---|---|---|
| C1 | `on_bar` 缺失 | `BaseStrategy` 子类专有, 签名 `on_bar(tm)` | 缺 | **新增** `on_bar(tm)` 到 BaseStrategy(默认 pass) |
| C2 | `on_check` 缺失 | `RiskStrategy` 专有, 签名 `on_check(positions, tm)` | 缺; RiskStrategy 整个缺 | **新增** `RiskStrategy` 类 + `on_check` 默认实现 |
| C3 | 数据方法名 | `get_bars(asset, count, end_dt=None, frame_type="1d", include_forming_bar=True) → pl.DataFrame` 在 `Strategy` 抽象根 | 现有 `get_history(asset, count, end_dt=None, frame_type="1d", include_forming_bar=True) → pl.DataFrame` in BaseStrategy | **重命名** `get_history` → `get_bars`;**上移**到新 `Strategy` 抽象根 |
| C4 | 策略类分层 | 三层: `Strategy`(抽象根) / `BaseStrategy`(独立) / `RiskStrategy`(风控);`BaseStrategy` 与 `RiskStrategy` **兄弟**,均继承 `Strategy` | 仅 `BaseStrategy` | **新增** `Strategy` 抽象根 + `RiskStrategy`(兄弟类,非 BaseStrategy 子类);`BaseStrategy(Strategy)` |
| C5 | 账户接口 | `BaseStrategy` 子类有 `buy` / `sell` / `positions` / `cash`;`RiskStrategy` 有 `sell_host_position`,**类层无** `buy` / `positions` / `cash` | 全部缺 | **新增** 全部账户接口;`RiskStrategy` 继承 `Strategy` 而非 `BaseStrategy` 保证拿不到 buy/positions/cash(类层缺失) |
| C6 | `default_config` UI 展示字段 | spec 要求元数据 schema | 现有仅返回原始 dict | **增强**:在枚举时把 dict 转 `dict[str, ParamSpec]` |
| C7 | 策略目录默认 | spec 不硬定路径 | `~/.millionaire/strategies/` | 现有实现保留可配置;spec 兼容(只要默认指向内置示例即满足 AC-020-01) |
| C8 | SDK 元数据(FR-014/015) | spec 接口 | 已在 `data/models/` 实现 | **对齐**:验证签名/返回类型与 spec 一致 |
| C9 | `get_prices` / `get_ticks` 归属 | 仅 `RiskStrategy` | 缺 | **新建**于 `RiskStrategy` 专有;**类层不存在**于 `BaseStrategy`(继承结构保证) |
| C10 | 风控回测语义 | ⏸ 暂缓(FR-013 §回测状态) | 缺 | **不固化**到 spec;实现层决定 |
| C11 | `UnsupportedFrameTypeForBacktest` 抛出位置 | BacktestRunner 上下文: `get_bars(frame_type != "1d")` 抛 | 缺 | **新增** 该异常类;BacktestRunner 拦截 |
| C12 | 测试数据 | spec 要 2023-2025, 105 标的 | 已有(已扩展) | **保留**: `tests/assets/real/` 105 资产 + 69,551 日线 + 3 年真实 tushare 数据 |

### 6.3 未识别冲突(实施时跟踪)

实现层 PR review 时需对照 spec 逐项核对,标记以下信息:

- [ ] FR-010 钩子默认值(`pass`)
- [ ] FR-010 不可知运行模式(无 `get_mode` / `is_backtest`)
- [ ] FR-013 风控策略的 `__init__` 强制绑定宿主参数
- [ ] FR-020 模式无关性(枚举结果在 4 模式下一致)
- [ ] FR-115 钩子调用顺序(已写进 AC-010-02)

## 7. 变更记录

- **2026-06-17 初稿**:
  - §1 策略框架契约(从 spec FR-010/011/012/013/020 推导)
  - §2 Web API(基于 FastAPI 惯例推断,需实现层确认 URL)
  - §3 数据 schema(从 acceptance 推断)
  - §4 异常表(集中 spec 散落的错误场景)
  - §5 日志条目(细化 test-plan §3.1.3)
  - §6 冲突清单(基线 8 项)
- **2026-06-17 (本轮 1)**: 对齐 spec.md 的"数据方法上提 / 下移"决策
  - §1.1 `Strategy` 加 `get_bars` 签名
  - §1.2 `BaseStrategy` 移除 `get_bars`(已上提);类别从"四类"改为"三类"
  - §1.3 `RiskStrategy` 保留 `get_prices` / `get_ticks`(已明确归属)
  - §4 异常表加 `UNSUPPORTED_FRAME_TYPE_FOR_BACKTEST`;移除 `LIVE_NOT_BACKTESTABLE` 与 `RISK_NO_BUY_API`(因 FR-011/012 删除);`INVALID_FRAME_TYPE` 关联 AC 改 AC-010-XX
  - §6 加 C9(数据方法归属)/ C10(风控回测 暂缓);更新 C1/C2/C3/C4 措辞以反映新分层
  - §4 注:`get_prices` / `get_ticks` 在回测下的行为 ⏸ 暂缓,不进错误码表
- **2026-06-17 (本轮 2)**: 重新核对实现层实际状态后重写 §6
  - 纠正:实现层仅含 `BaseStrategy` 空壳(157 行);"DayStrategy / LiveStrategy 子类"系误判,实际不存在
  - §6.1 现状摘要:列出 BaseStrategy 有/缺什么
  - §6.2 冲突表按实际重写(11 条):
    - 删除原 C1/C2(基于错误假设的"on_bar 已存在")
    - 新增 C1/C2/C5(基于实际"缺什么")
    - C3 措辞调整(原"重命名"改为对上移到 Strategy 根)
    - C4 措辞调整(明确"兄弟类")
    - 新增 C11(`UnsupportedFrameTypeForBacktest` 抛出位置)
    - C12 取代原 C8(测试数据已扩展完成,标"保留"而非"扩展中")
  - §5 日志条目 FR 引用: FR-011/012 → FR-010(因 FR-011/012 已删除)
  - §6.3 待跟踪清单补 FR-115 钩子顺序
