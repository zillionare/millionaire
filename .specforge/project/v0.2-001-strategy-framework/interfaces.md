# Interfaces — v0.2-001-strategy-framework

- **Spec ID**: v0.2-001-strategy-framework
- **位置**: 与 [spec.md](./spec.md) (含索引)/ [acceptance.md](./acceptance.md) / [test-plan.md](./test-plan.md) 同源
- **性质**: 外部可观测契约清单 — 测试工程师据此写黑盒测试,实现层据此暴露 API/数据 schema
- **基线**: 严格对齐 [spec-strategy.md](./spec-strategy.md) 已确定部分(FR-010 ~ FR-020);NFR 引用 [spec-foundation.md NFR-050](./spec-foundation.md)
- **范围外**: FR > 020 未确定的 FR,本文件不涉及

> **本文件不是实现设计,是从 spec 推导出的"接口冻结"清单**。实现层如发现接口无法实现,需回退到 spec 修订而非本文件。

## 1. 文档约定

| 字段         | 含义                                     |
| ------------ | ---------------------------------------- |
| **Endpoint** | HTTP method + 路径;FastAPI 风格          |
| **Request**  | 请求体/参数 schema(字段名 + 类型 + 必填) |
| **Response** | 响应 schema;成功/失败各列                |
| **状态码**   | HTTP 状态码 + 业务语义                   |
| **观测点**   | 该接口数据最终落盘的位置(供测试断言)     |
| **关联 AC**  | 引用的 acceptance.md 条目                |

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

## 2. 策略框架外部契约(策略编写视角)

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

### 2.1. `Strategy`(抽象根, FR-010)

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
    def log(self, msg: str, level: str = "INFO",
            tm: datetime.datetime | None = None) -> None: ...
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

### 2.2. `BaseStrategy`(独立策略, FR-010)

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

### 2.3. `RiskStrategy`(风控策略, FR-013)

风控策略基类，`BaseStrategy` 的**兄弟**（均继承自 `Strategy`）。**不继承 BaseStrategy**，因此类层无 `buy` / `positions` / `cash`(`get_bars` 从抽象根 `Strategy` 继承,**不**算 RiskStrategy 自有)。

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
- **可回测**：❌ 否。v0.2 不支持 RiskStrategy 回测。BacktestRunner 启动时检测到 RiskStrategy 实例则拒绝(抛异常 `RiskStrategyNotBacktestable`,HTTP 错误码 `RISK_STRATEGY_NOT_BACKTESTABLE`),关联 AC-013-05

**关联 AC**: AC-013-01 ~ 05

### 2.4. 枚举契约(FR-020)

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

## 3. Web API 契约(框架 HTTP 暴露)

> **状态**: spec 未硬定 URL。本节按 FastAPI 惯例与 v0.2-002-ui 需求推断。**最终 URL 由实现层在启动时确认并冻结**,但**响应 schema 是契约,不可变**。

### 3.1. 策略枚举 API

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

| HTTP | code                 | 触发                                                              |
| ---- | -------------------- | ----------------------------------------------------------------- |
| 200  | —                    | 正常                                                              |
| 500  | `ENUMERATION_FAILED` | 枚举过程发生不可恢复错误(目前不应触发,所有失败均进入 diagnostics) |

**关联 AC**: AC-020-04, AC-020-08 ~ 12

### 3.2. 策略参数查询 API

**Endpoint**: `GET /api/strategies/{strategy_id}/config`

**Response 200**:

```json
{
  "strategy_id": "user.MyStrategy",
  "default_config": {
    "fast": { "name": "fast", "default": 5 },
    "slow": { "name": "slow", "default": 20 }
  }
}
```

`default_config` 是 `dict[str, ParamSpec]`(对齐 §1.4 ParamSpec schema 与 spec FR-020 元数据 schema)。

**关联 AC**: AC-010-03


## 4. 数据文件 / 数据库 schema

> **范围**: 本节定义所有**外部可观测**的数据契约 — 单元测试 / 集成测试均通过这些契约验证行为. **字段名、类型、必填为契约, 不可变**; 落盘位置(数据库表 vs parquet 文件) 由实现层在 PR2 决定.

### 4.1. 回测结果 JSON(回测完成后落盘)

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
  "skipped_days": ["2024-04-19"],
  "completed_at": "2024-04-20T16:30:00"
}
```


### 4.2. 委托表 (`orders`)

| 列             | 类型                                 | 说明                                                           |
| -------------- | ------------------------------------ | -------------------------------------------------------------- |
| `qtoid`        | str (PK)                             | 框架生成, UUID                                                 |
| `portfolio_id` | str (FK → `portfolios.portfolio_id`) | 归属策略 / 组合                                                |
| `asset`        | str                                  | 标的代码                                                       |
| `side`         | str (`OrderSide` enum)               | `buy` / `sell`                                                 |
| `shares`       | float                                | 委托数量 (调用者需保证符合交易要求)                            |
| `price`        | float                                | 限价 (`0` 表示市价)                                            |
| `bid_type`     | str (`BidType` enum)                 | 委托类型 (限价 / 市价)                                         |
| `tm`           | datetime                             | 委托时间 (仿真时间)                                            |
| `filled`       | float                                | 已成交量 (默认 `0`)                                            |
| `foid`         | str \| null                          | 外部订单 id (QMT 等) — 透传, 用于排错                          |
| `cid`          | str \| null                          | 券商柜台合约 id                                                |
| `status`       | str (`OrderStatus` enum)             | `unreported` / `pending` / `filled` / `rejected` / `cancelled` |
| `status_msg`   | str                                  | 委托状态描述 (如废单原因)                                      |
| `error`        | str                                  | 报单错误 (错误码:错误信息, `:` 分隔)                           |
| `extra`        | str (JSON)                           | 额外信息                                                       |

**索引**:
- 唯一索引: (`qtoid`, `tm`)

**关联 AC**: AC-010-01 ~ 04, AC-013-*

### 4.3. 成交表 (`trades`)

| 列             | 类型                                 | 说明                                               |
| -------------- | ------------------------------------ | -------------------------------------------------- |
| `tid`          | str (PK)                             | 成交 id; 可使用代理 (QMT) 返回值                   |
| `qtoid`        | str (FK → `orders.qtoid`)            | 委托 id (quantide 内部 id)                         |
| `portfolio_id` | str (FK → `portfolios.portfolio_id`) | 归属策略                                           |
| `foid`         | str                                  | 外部订单 id (QMT 等)                               |
| `asset`        | str                                  | 标的代码                                           |
| `shares`       | float                                | 成交数量                                           |
| `price`        | float                                | 成交价                                             |
| `amount`       | float                                | 成交金额 = 成交数量 × 成交价                       |
| `tm`           | datetime                             | 成交时间 (仿真时间)                                |
| `side`         | str (`OrderSide` enum)               | 成交方向                                           |
| `cid`          | str                                  | 柜台合同编号 (应与同 `qtoid` 的 `orders.cid` 一致) |
| `fee`          | float                                | 本笔交易手续费 (默认 `0`)                          |

**索引**:
- 唯一索引: (`tid`, `tm`)

**外键**:
- `qtoid` → `orders.qtoid`
- `portfolio_id` → `portfolios.portfolio_id`

**关联 AC**: AC-010-01 ~ 04, AC-360-*

### 4.4. 持仓表 (`positions`)

| 列             | 类型                                          | 说明                                                 |
| -------------- | --------------------------------------------- | ---------------------------------------------------- |
| `portfolio_id` | str (PK part, FK → `portfolios.portfolio_id`) |                                                      |
| `dt`           | date (PK part)                                | 持仓快照日期                                         |
| `asset`        | str (PK part)                                 | 标的代码                                             |
| `shares`       | float                                         | 总持仓                                               |
| `avail`        | float                                         | 可卖持仓 (T+1 约束) — 原 spec 名为 `sellable_shares` |
| `price`        | float                                         | 持仓成本 (加权均价) — 原 spec 名为 `cost_basis`      |
| `profit`       | float                                         | 盈亏 — 实盘快速查询用, 回测/仿真不写                 |
| `mv`           | float                                         | 市值                                                 |

**索引**:
- 非唯一索引: (`portfolio_id`, `asset`, `dt`)

**关联 AC**: AC-010-01 ~ 04, AC-160-*

### 4.5. 资产表 (`assets`)

> **修订说明**: 原 spec 误为 `accounts` 表, PK 是 `strategy_id` 单列, 字段是 `cash` / `total_value` / `as_of`. 实际表名是 `assets`, PK 是 `(portfolio_id, dt)`, 字段是 `principal` / `cash` / `frozen_cash` / `market_value` / `total`, `total = cash + market_value`.

| 列             | 类型                                          | 说明                           |
| -------------- | --------------------------------------------- | ------------------------------ |
| `portfolio_id` | str (PK part, FK → `portfolios.portfolio_id`) |                                |
| `dt`           | date (PK part)                                | 资产快照日期                   |
| `principal`    | float                                         | 初始本金 (必填)                |
| `cash`         | float                                         | 可用资金                       |
| `frozen_cash`  | float                                         | 冻结资金 (委托占用等)          |
| `market_value` | float                                         | 持仓市值                       |
| `total`        | float                                         | 总资产 = `cash + market_value` |

**索引**:
- 唯一索引: (`portfolio_id`, `dt`)

### 4.6. 组合表 (`portfolios`)

| 列             | 类型                    | 说明                              |
| -------------- | ----------------------- | --------------------------------- |
| `portfolio_id` | str (PK)                | 组合 id (= strategy_id 的实例)    |
| `kind`         | str (`BrokerKind` enum) | backtest / paper / live / dry-run |
| `start`        | date                    | 启动日期                          |
| `name`         | str                     | 显示名 (默认 `""`)                |
| `info`         | str                     | 描述信息 (默认 `""`)              |
| `end`          | date \| null            | 结束日期                          |
| `status`       | bool                    | 启用状态 (默认 `true`)            |

**索引**:
- 唯一索引: (`portfolio_id`)

**关联 AC**: AC-010-01 ~ 04

### 4.7. 策略日志 (`strategy_logs`)

| 列             | 类型                                          | 说明                                        |
| -------------- | --------------------------------------------- | ------------------------------------------- |
| `portfolio_id` | str (PK part, FK → `portfolios.portfolio_id`) |                                             |
| `dt`           | datetime (PK part)                            |                                             |
| `key`          | str (PK part)                                 | 日志键 (策略 `record(key, value)` 的 `key`) |
| `value`        | float                                         |                                             |
| `extra`        | str (JSON)                                    | 额外字段                                    |

**索引**:
- 唯一索引: (`portfolio_id`, `dt`, `key`)

### 4.8. 回测文本日志 (`backtest_logs`)

> **新增 (2026-06-21)**: 原 spec §4 缺此表, 实际 `quantide/data/sqlite.py` 有 `BacktestLogEntry` dataclass.

| 列             | 类型                                 | 说明                                        |
| -------------- | ------------------------------------ | ------------------------------------------- |
| `event_id`     | str (PK)                             |                                             |
| `portfolio_id` | str (FK → `portfolios.portfolio_id`) |                                             |
| `dt`           | datetime                             |                                             |
| `level`        | str                                  | INFO / WARNING / ERROR                      |
| `source`       | str                                  | 源码位置 (如 `quantide.service.sim_broker`) |
| `message`      | str                                  | 日志消息                                    |
| `extra`        | str (JSON)                           | 额外字段                                    |

**索引**:
- 非唯一索引: (`portfolio_id`, `dt`)

### 4.9. 风控触发事件 (`risk_events`) — spec 保留, 实现待定

| 列                 | 类型     | 说明                                 |
| ------------------ | -------- | ------------------------------------ |
| `event_id`         | str (PK) |                                      |
| `activation_id`    | str      | 所属开启区间 (详见 FR-360 AC-360-02) |
| `risk_strategy_id` | str      | 风控策略                             |
| `host_strategy_id` | str      | 宿主策略                             |
| `asset`            | str      |                                      |
| `trigger_price`    | float    | 触发价                               |
| `cost_basis`       | float    | 成本价                               |
| `reason`           | str      | `cost_stop` / `drawback` / ...       |
| `trigger_ts`       | datetime | 触发时间戳                           |

### 4.10. 超额收益事件 (`excess_returns`) — spec 保留, 实现待定

> **状态**: 同 §4.9, FR-360 实现 PR 时落库. 期间通过 `risk.excess_return.finalized` 日志条目记录 (见 §6).

| 列                 | 类型                                    | 说明                                                                                                                                                                                                                                     |
| ------------------ | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `event_id`         | str (PK)                                | 与 `risk_events.event_id` 对应                                                                                                                                                                                                           |
| `activation_id`    | str                                     | 所属开启区间 (详见 FR-360 AC-360-02)                                                                                                                                                                                                     |
| `risk_strategy_id` | str                                     |                                                                                                                                                                                                                                          |
| `host_strategy_id` | str                                     |                                                                                                                                                                                                                                          |
| `asset`            | str                                     |                                                                                                                                                                                                                                          |
| `sell_price`       | float                                   | 卖出价 `P_sell`                                                                                                                                                                                                                          |
| `up_threshold`     | float                                   | 上阈值 (百分点, 如 5.0 表示 5%)                                                                                                                                                                                                          |
| `down_threshold`   | float                                   | 下阈值 (百分点, 如 0.5 表示 0.5%)                                                                                                                                                                                                        |
| `barrier_hit`      | `Literal["up", "down", "expire", null]` | 触发的屏障, 数据不足时 `null`                                                                                                                                                                                                            |
| `close_price_n`    | float \| null                           | N 日后收盘价 (N=0 即当日); 未触发屏障时使用                                                                                                                                                                                              |
| `n_window`         | int                                     | 窗口 (默认 0, 来自风控策略 `default_config()`)                                                                                                                                                                                           |
| `excess_return`    | float \| null                           | Triple Barrier 公式 (详见 [spec-trading.md F-TB-1 / F-TB-2 / F-TB-3](./spec-trading.md)):<br>• `barrier_hit="up"` → 应用 F-TB-1<br>• `barrier_hit="down"` → 应用 F-TB-2<br>• `barrier_hit="expire"` → 应用 F-TB-3<br>• 数据不足 → `null` |
| `is_final`         | bool                                    | false=待回填, true=终值                                                                                                                                                                                                                  |
| `created_at`       | datetime                                |                                                                                                                                                                                                                                          |
| `finalized_at`     | datetime \| null                        | N=0 时 = `created_at`; N>0 时 = `trigger_ts + n_window` 日                                                                                                                                                                               |

### 4.11. 枚举缓存 JSON (枚举结果持久化)

```json
{
  "version": "1",
  "generated_at": "2026-06-17T10:00:00",
  "strategies": [/* StrategyMetadata 数组 */],
  "diagnostics": [/* SkippedEntry 数组 */]
}
```

### 4.12. 交易日历 Parquet (`calendar.parquet`)

> **修订说明 (2026-06-21)**: 原 spec 写的是 `(date, is_trade_day, exchange)`, 但 `tests/assets/unit/scripts/build_env.py` 实际生成的是 `(exchange, date, is_open, pretrade_date)`. 字段名 `is_trade_day` → `is_open`, 多了 `pretrade_date` 字段. **完全照现有实现**.

| 列              | 类型               | 说明                                         |
| --------------- | ------------------ | -------------------------------------------- |
| `exchange`      | str                | 交易所代码 (SSE / SZSE / BSE)                |
| `date`          | str (YYYYMMDD, PK) |                                              |
| `is_open`       | int (0/1)          | 是否交易日                                   |
| `pretrade_date` | str (YYYYMMDD)     | 前一交易日 (用于回测时 `day_shift(-1)` 查询) |

### 4.13. 证券列表 (`universe.json`)

| 列            | 类型           | 说明                                                                               |
| ------------- | -------------- | ---------------------------------------------------------------------------------- |
| `asset`       | str            | 标的代码 (如 `000001.SZ`)                                                          |
| `name`        | str            | 中文名 (如 `平安银行`)                                                             |
| `category`    | str            | 类别 (ordinary / st / ipo / delisted / chinext_star / suspended / dividend_adjust) |
| `list_date`   | int (YYYYMMDD) | 上市日期                                                                           |
| `delist_date` | int \| null    | 退市日期 (未退市为 null)                                                           |
| `exchange`    | str            | 交易所                                                                             |

### 4.14. 日线行情 Parquet (`daily_bars.parquet`)

> **新增 (2026-06-21)**: 原 spec §4 缺日线行情 parquet 规范. 按 `build_env.py` 实际补齐.

| 列       | 类型           | 说明        |
| -------- | -------------- | ----------- |
| `asset`  | str            | 标的代码    |
| `date`   | str (YYYYMMDD) | 交易日      |
| `open`   | float          | 开盘价      |
| `high`   | float          | 最高价      |
| `low`    | float          | 最低价      |
| `close`  | float          | 收盘价      |
| `volume` | float          | 成交量 (手) |
| `amount` | float          | 成交额 (元) |

### 4.15. 复权因子 Parquet (`adj_factor.parquet`)

> **新增 (2026-06-21)**: 同 §4.14.

| 列           | 类型           | 说明     |
| ------------ | -------------- | -------- |
| `asset`      | str            | 标的代码 |
| `date`       | str (YYYYMMDD) | 交易日   |
| `adj_factor` | float          | 复权因子 |

### 4.16. ST 标记 Parquet (`st_info.parquet`)

> **新增 (2026-06-21)**: 同 §4.14.

| 列      | 类型           | 说明             |
| ------- | -------------- | ---------------- |
| `asset` | str            | 标的代码         |
| `date`  | str (YYYYMMDD) | 交易日           |
| `is_st` | int (0/1)      | 是否 ST (含 *ST) |

### 4.17. 涨跌停价 Parquet (`limit_price.parquet`)

> **新增 (2026-06-21)**: 同 §4.14.

| 列           | 类型           | 说明     |
| ------------ | -------------- | -------- |
| `asset`      | str            | 标的代码 |
| `date`       | str (YYYYMMDD) | 交易日   |
| `up_limit`   | float          | 涨停价   |
| `down_limit` | float          | 跌停价   |

## 5. 异常 / 错误码表

| code                                  | HTTP    | 触发场景                                                   | 关联 AC   |
| ------------------------------------- | ------- | ---------------------------------------------------------- | --------- |
| `STRATEGY_NOT_FOUND`                  | 404     | API 查询不存在 strategy_id                                 | —         |
| `INVALID_FRAME_TYPE`                  | 400     | `get_bars(frame_type)` 取值不在 `{"1d", "30m"}` 之内       | AC-010-03 |
| `UNSUPPORTED_FRAME_TYPE_FOR_BACKTEST` | 400/409 | 回测模式下 `get_bars(frame_type != "1d")` 抛（运行时检查） | AC-010-03 |
| `INVALID_RANGE`                       | 400     | 交易日历 `start > end`                                     | AC-014-03 |
| `ASSET_NOT_FOUND`                     | 404     | `get_name` 资产代码不存在                                  | —         |
| `RISK_NO_ACCOUNT`                     | 400/422 | RiskStrategy 访问 `positions` / `cash`                     | AC-013-01 |
| `RISK_NOT_BOUND`                      | 422     | RiskStrategy 启动时未绑定宿主                              | AC-013-05 |
| `RISK_NO_BUY_API`                     | 400/422 | RiskStrategy 调用 buy 类方法                               | AC-013-02 |
| `RISK_STRATEGY_NOT_BACKTESTABLE`      | 422     | RiskStrategy 提交给 BacktestRunner                         | AC-013-05 |
| `ENUMERATION_FAILED`                  | 500     | 不可恢复的枚举错误                                         | AC-020-12 |

> 注:`UNSUPPORTED_FRAME_TYPE_FOR_BACKTEST` 是 `RuntimeError` 子类，仅在 BacktestRunner 上下文抛出；paper/live 不受影响。

## 6. 日志条目类型(从 test-plan §3.1.3 细化)

| event                          | 字段                                                                         | level   | 关联 FR    |
| ------------------------------ | ---------------------------------------------------------------------------- | ------- | ---------- |
| `strategy.enumerated`          | `strategy_id, is_builtin, default_config_size`                               | INFO    | FR-020     |
| `strategy.skipped`             | `path, class_name, reason, detail`                                           | WARNING | FR-020     |
| `strategy.lifecycle`           | `strategy_id, hook, tm`                                                      | DEBUG   | FR-010     |
| `order.submitted`              | `strategy_id, asset, side, shares, price`                                    | INFO    | FR-010     |
| `order.filled`                 | `strategy_id, asset, filled_qty, fill_price, ts`                             | INFO    | FR-010/013 |
| `order.cancelled`              | `strategy_id, order_id, reason`                                              | INFO    | FR-013     |
| `risk.triggered`               | `risk_strategy_id, host_strategy_id, asset, trigger_price, cost, reason, ts` | INFO    | FR-013/125 |
| `risk.excess_return.finalized` | `event_id, excess_return`                                                    | INFO    | FR-013/360 |
| `backtest.started`             | `strategy_id, params, interval`                                              | INFO    | FR-010     |
| `backtest.progress`            | `strategy_id, current_day, total_days, pct`                                  | INFO    | FR-010     |
| `backtest.completed`           | `strategy_id, metrics`                                                       | INFO    | FR-010     |

## 7. 运行时装配契约 (NFR-060 联动)

> **范围**: 本节声明 NFR-060 涉及的 3 个装配点的可观测出口, 仅供测试侧在不依赖实现细节的前提下验证装配是否生效。
> **关联 spec**: [spec-foundation.md NFR-060](./spec-foundation.md)
> **关联 test-plan**: [test-plan.md §5.4](./test-plan.md) — L1/L2 E2E 测试的前置
> **关联 acceptance**: [acceptance.md AC-CLOCK-INJ-01 ~ 06](./acceptance.md)

#### 7.0.1. 装配点 1: 虚拟时钟 (ClockPort)

**协议定义** (`quantide/core/ports/clock.py`):

- `ClockPort.now() -> datetime` — 框架读"当前时刻"用
- `ClockPort.set_now(tm: datetime) -> None` — 测试侧快进用
- `ClockPort.iter_frames(start, end, frame_type) -> Iterable` — 回测遍历

**可观测出口**:

- 任意策略钩子 (`on_day_open` / `on_bar` / `on_day_close`) 收到的 `tm` 参数 == `context.clock.now()` 调用结果
- 行情事件的 `timestamp` 字段 == 推送时刻的 `context.clock.now()`
- 日志条目 (`order.submitted` / `order.filled` / `risk.triggered`) 的 `ts` 字段 == 事件发生时刻的 `context.clock.now()`

#### 7.0.2. 装配点 2: 实时行情源 (MarketDataPort)

**协议定义** (`quantide/core/ports/market_data.py`):

- `MarketDataPort.snapshot(symbols) -> dict[str, QuoteSnapshot]`
- `MarketDataPort.subscribe / unsubscribe / start / stop / stream`

**可观测出口**:

- 撮合结果 (orders / fills 表) 的成交价 == 撮合时刻的 `market_data.snapshot([asset])[asset].price`
- 委托回报的 `filled_at` 字段 == 撮合时刻的 `context.clock.now()`

#### 7.0.3. 装配点 3: 网关地址

**配置路径**: `Settings.gateway_url` (已存在, 由 PR2 验证暴露)

**可观测出口**:

- 框架启动时, 解析 `Settings.gateway_url` 失败 → 启动失败并报错 (无静默回退)
- 框架运行中, 网关断开 → [test-plan.md §5.4.4](./test-plan.md) 假网关 / 真网关断开 → 触发 FR-450 #5 通知事件

## 8. 变更记录

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
- **2026-06-17 (本轮 3)**: 用户决定 RiskStrategy 不可回测,落地到 interfaces
  - §1.3 RiskStrategy '可回测: ⏸ 暂缓' -> '❌ 否. BacktestRunner 启动拒绝'
  - §4 异常表加 `RISK_STRATEGY_NOT_BACKTESTABLE` (RiskStrategy 提交给 BacktestRunner)
  - §4 '⏸ 暂缓: 风控回测语义' 段删除
  - §6 C10: '⏸ 暂缓' -> 'v0.2 不支持 RiskStrategy 回测 (用户决定)'
- **2026-06-17 (本轮 4)**: GLM 评审 8 处遗漏 / 矛盾全部修复
  - §3.6 risk_events 加 `activation_id` 字段;`timestamp` -> `trigger_ts`(对齐 FR-360)
  - §3.7 excess_returns 加 `activation_id` / `up_threshold` / `down_threshold` / `barrier_hit`;公式从旧版 `(sell_price - close_price_n)/sell_price` 改为 Triple Barrier 三种退出条件
  - §1.3 / §6 C10 错误码命名一致:异常类名 `RiskStrategyNotBacktestable`,HTTP 错误码 `RISK_STRATEGY_NOT_BACKTESTABLE`
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
