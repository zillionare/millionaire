# Test Plan — v0.2-001-strategy-framework

- **Spec ID**: v0.2-001-strategy-framework
- **位置**: 与 [acceptance.md](./acceptance.md) 并列,与 [spec.md](./spec.md) 同源

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

#### 1.3.1. 防护机制

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

4. **paper/live E2E 的 marker 管控**（详见 §6.5）
   - paper/live 相关 E2E 测试**必须**标注 §6.5.1 定义的三类 marker（`e2e_paper` / `e2e_gateway` / `e2e_live_smoke`）之一，无 marker 的 paper/live 测试阻塞 merge。
   - `e2e_live_smoke`（L3）默认 deselect；其"默认不运行"**只能**通过 marker deselect 实现，**禁止**用 `pytest.skip()` 实现（违反第 2 条断言禁忌）。


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
- 跨场景的共享工具放 `tests/assets/*/conftest.py` 或 `tests/assets/*/utils/`，'*' 的取值为`unit|e2e`.

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


### 2.5. tick 与 30m 合成数据规范 (FR-270-A 联动)

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

> **范围声明**: 本节是 FR-270 的**回放 fixture 专用扩展**, 仅约束 `tests/assets/**/fixtures/data/` 下的合成 parquet 文件, **不**约束生产数据。生产 tick / 30m 数据通过 qmt-gateway 实时获得 (FR-300), 无 fixture 要求。
> **关联 spec**: spec-trading.md FR-270 (本节是其回放 fixture 扩展, 不进 FR-270-A 子节, 避免与产品数据规范混在一起)

#### 2.5.1. 数据范围

- 标的范围: 与 §2.4.2 的 universe 一致 (105 个标的)
- 时间范围: **仅 2022 年最后 2 个交易日** (test-plan §2.4.1 声明)
- 频率:
  - **tick**: 任意时刻, 每日数千至数万笔 (按合成算法决定)
  - **30m**: 每日 8 根 (9:30~11:30 / 13:00~15:00, A 股交易时段)

#### 2.5.2. tick 字段契约

| 字段     | 类型             | 说明                                                  |
| -------- | ---------------- | ----------------------------------------------------- |
| `asset`  | `str`            | 标的代码, 与日线 `asset` 同 schema                    |
| `date`   | `str` (YYYYMMDD) | 交易日, 与日线 `date` 同 schema                       |
| `time`   | `str` (HHMMSS)   | tick 时刻, 精确到秒 (范围 09:30:00 ~ 15:00:00)       |
| `price`  | `float64`        | tick 价                                              |
| `volume` | `float64`        | 累计成交量 (自开盘起); 单笔增量 = 当前 - 前一 tick    |
| `amount` | `float64`        | 累计成交额 (自开盘起); 单笔增量 = 当前 - 前一 tick    |

> 累计 volume/amount 模式 (而非单笔模式) — 简化 R0 一致性约束 (日终值直接等于日线).

#### 2.5.3. 30m 字段契约 (从 tick 聚合)

| 字段     | 类型             | 说明                                                                |
| -------- | ---------------- | ------------------------------------------------------------------- |
| `asset`  | `str`            | 标的代码, 与日线 `asset` 同 schema                                  |
| `date`   | `str` (YYYYMMDD) | 交易日, 与日线 `date` 同 schema                                     |
| `time`   | `str` (HHMM)     | 30m bar 起始时刻 (0930, 1000, 1030, 1100, 1130, 1300, 1400, 1500)   |
| `open`   | `float64`        | bar 内第一笔 tick 的 price                                          |
| `high`   | `float64`        | bar 内所有 tick 的 max(price)                                       |
| `low`    | `float64`        | bar 内所有 tick 的 min(price)                                       |
| `close`  | `float64`        | bar 内最后一笔 tick 的 price                                        |
| `volume` | `float64`        | bar 内 tick 累计 volume 的增量                                      |
| `amount` | `float64`        | bar 内 tick 累计 amount 的增量                                      |

> **30m 不是独立合成的** — 是 `聚合(ticks)`. 任何 tick 合成的修改, 自动反映到 30m. 二者天然一致 (R1 自动满足).

#### 2.5.4. 一致性约束 (硬规则, 合成算法必须满足)

**R0 — tick 与日线一致性** (用户决策原文: "无论是 ticks 还是 30m, 都要与真实获得的日线数据不抵触"):

```
∀ asset, day ∈ last_2_trading_days:
    tick[asset, day, FIRST].price  == day_open(asset, day)
    tick[asset, day, LAST].price   == day_close(asset, day)
    min(tick[asset, day, *].price) == day_low(asset, day)
    max(tick[asset, day, *].price) == day_high(asset, day)
    tick[asset, day, LAST].volume  == day_volume(asset, day)   # 允许 ±0.5% 误差
    tick[asset, day, LAST].amount  == day_amount(asset, day)   # 允许 ±0.5% 误差
```

**R1 — 30m 与 tick 聚合一致性** (R0 的推论, 不引入新约束):

```
∀ asset, day, t (30m bar 起始时刻):
    30m(asset, day, t).open   == tick[asset, day, FIRST in 30m_window].price
    30m(asset, day, t).high   == max(tick[asset, day, t_window].price)
    30m(asset, day, t).low    == min(tick[asset, day, t_window].price)
    30m(asset, day, t).close  == tick[asset, day, LAST in 30m_window].price
    30m(asset, day, t).volume == tick[asset, day, END_WINDOW].volume
                              - tick[asset, day, START_WINDOW_PREV].volume
    30m(asset, day, t).amount == tick[asset, day, END_WINDOW].amount
                              - tick[asset, day, START_WINDOW_PREV].amount
```

> R1 由"30m 严格聚合 tick"决定, 只要 tick 合成满足 R0, R1 自动满足. validate_env.py 仍要校验 R1 (防止聚合函数 bug).

**R2 — 涨跌停约束** (与 R0 配套):

```
∀ tick (因此 ∀ 30m bar):
    tick[asset, day, *].price >= day_down_limit(asset, day)
    tick[asset, day, *].price <= day_up_limit(asset, day)
    # is_st 标的放宽到 ±5% (按 FR-140)
```

**R3 — 时间窗口约束** (原 R4 重新编号):

```
∀ tick:
    tick[asset, day, *].time ∈ [09:30:00, 11:30:00] ∪ [13:00:00, 15:00:00]
∀ 30m bar:
    bar.time ∈ {0930, 1000, 1030, 1100, 1130, 1300, 1400, 1500}
    1100→1300 间隔 2 小时 (午休), 其它间隔 30 分钟
```

> **R3 (原"内在波动合理性") 已删除** — ticks 是源, 30m 是聚合, "单根 30m 波动合理性" 不是合成层约束, 而由 tick 序列自然决定. A 股真实市场偶尔单边 (涨跌停 / 消息面) 不应被"≤5 根同向"等规则过拟合. 3 个具体阈值 (3% / 5 根 / 1 根反向) 也没有 spec 来源, 属于凭直觉拍的规则.

#### 2.5.5. 合成算法契约 (实现层必须遵循, 不规定实现细节)

满足 R0+R2+R3 的合成算法由实现层自行决定。算法输出**确定性**: 同一 universe + 同一日线数据 → 同一 tick 数据 (无随机种子依赖, 或使用固定种子)。

**推荐路径** (非强制):

1. **先合成 ticks** (核心步骤):
   - 以日线 open/close 为锚, 在 [open, close] 区间内用**泊松到达过程 + 几何布朗运动**生成 tick 序列
   - tick.price 用 1 分钟级粒度 (避免 R0 high/low/open/close 失真)
   - tick.volume 按"日内成交量均匀分布" + 局部扰动 (±10% 局部噪声), 末笔累计值 = day_volume
   - 在 day_high / day_low 附近安排"接近触及涨跌停"的事件 (满足 R2)
2. **再聚合 30m** (确定性函数, 不需算法选择):
   - 严格按 §2.5.3 字段定义, 从 tick 序列聚合
   - 30m 是 tick 数据的"副产物", **不独立合成**, 也不需要单独的算法契约
3. **整体确定性**: 同一 universe + 同一日线 → 同一 tick; tick → 30m (聚合函数无随机性); 整体可重现

#### 2.5.6. 验证脚本

`tests/assets/*/scripts/validate_env.py` 必须新增 tick + 30m 校验逻辑:

- 加载 `ticks.parquet` (若存在) + `30m_bars.parquet` (若存在) + 对应日线
- 验证 R0 全部 6 个等式 (允许 volume/amount ±0.5%)
- 验证 R1 全部 6 个等式 (聚合一致性, 即使理论上由 R0 推论, 仍要校验以防聚合函数 bug)
- 验证 R2 涨跌停约束
- 验证 R3 时间窗口与 30m 边界
- **校验完成后, 计算所有 fixture parquet 的 SHA-256, 写入 `env_manifest.json` 的 `data_checksum` 字段** (详见 §2.6.3)

校验失败 → CI 红, 阻塞 PR 合并。

### 2.6. 环境构建

#### 2.6.1. 拉取脚本

位置:`tests/assets/*/scripts/build_env.py`

功能:
- 调用 tushare API 拉取上述数据
- 调用 qmt 临时抓取/数据合成 30m + tick(2 天)
- 写入本地 parquet / 数据库
- 输出 `env_manifest.json` 记录:数据范围、标的清单、生成时间(用于追溯)

#### 2.6.2. 校验脚本

位置:`tests/assets/*/scripts/validate_env.py`

校验内容:
- 完整性:每个标的的日线条数应 ≈ 实际交易日数(±5 容忍因停牌)
- 一致性:OHLCV 字段无空值;ST 标记与涨跌停价一致
- 范围:数据起止日期在预期范围内
- 抽样:对随机 5 个标的随机抽 5 天,人工核对(tushare 网页版/行情软件)

#### 2.6.3. 快照与版本

- 数据存储在 `tests/assets/*/fixtures/data/`
- `env_manifest.json` 记录版本,CI 中校验 "测试数据版本 = 预期版本"
- 数据不可变;更新数据需新版本号 + 重新走 §2.5 环境构建流程

##### 2.6.3.1. 基准数据完整性校验 (data_checksum 字段)

**目的**: 在 `env_manifest.json` 生成后, 任何对 fixture parquet 的"手改"或"中途损坏"必须被 `env` fixture (即 `tests/unit/conftest.py` 的 `TestEnv` session fixture) 在加载时立即 fail, 不让"看似通过"的数据进入测试。

**`env_manifest.json` 新增字段**:

```json
{
  "version": 1,
  "data_source": "...",
  "date_range": [...],
  "row_counts": {...},
  "data_checksum": {
    "algorithm": "sha256",
    "computed_at": "2026-06-21T12:00:00Z",
    "files": {
      "daily_bars.parquet":  "abc123...def",  // hex SHA-256
      "calendar.parquet":    "012abc...789",
      "adj_factor.parquet":  "...",
      "st_info.parquet":     "...",
      "limit_price.parquet": "...",
      "30m_bars.parquet":    "...",   // 若存在
      "ticks.parquet":       "..."    // 若存在
    }
  }
}
```

**写入时机** (在 `build_env.py` 完成 §2.6.1 数据落盘后):

1. 遍历 `fixtures/data/` 全部 `.parquet` 文件
2. 用 `hashlib.sha256()` 计算每个文件的 hex digest
3. 加上 `computed_at` 时间戳和 `algorithm: "sha256"` 标记
4. 序列化到 `env_manifest.json` 的 `data_checksum` 字段

**校验时机** (在 `tests/unit/conftest.py` 的 `env` fixture 加载时):

1. 读 `env_manifest.json` 的 `data_checksum.files`
2. 对每个声明的文件, **重新计算** SHA-256
3. 与 manifest 记录对比:
   - 全部一致 → 通过
   - 任一不一致 → **fail-fast**, 报 `DataCorrupted: file X has sha256=Y, manifest says Z`
4. 报错信息明确指出"该问题不是测试 bug, 而是 fixture 损坏, 请重新跑 build_env.py"

**对 `validate_env.py` 的衔接**: §2.5.6 校验脚本运行完成且无错后, 才计算并写入 `data_checksum`. 也就是说 `data_checksum` 标记的是"通过 §2.5.6 R0~R3 校验的"数据集.

##### 2.6.3.2. 与 `env` fixture 的协作

```python
# tests/unit/conftest.py (伪代码, 仅描述契约)
@pytest.fixture(scope="session")
def env() -> TestEnv:
    manifest = _load_manifest()
    _verify_data_checksum(manifest)  # ← 新增: 失败则 fail-fast
    return TestEnv(...)
```

测试代码无需感知 checksum 校验, 失败时直接得到清晰报错.

### 2.7. 环境使用接口

#### 2.7.1. 测试代码加载环境

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

#### 2.7.2. 环境生命周期

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

#### 3.1.1. Ground Truth 隔离（强制规则）

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

## 4. 测试范围

本测试计划对应同级目录下 spec.md 文档、以及它导入的其它同级 spec 文档中，所有『有效需求』、『可测试性』和『是否已决定』均为绿灯的需求。

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

---

## 5. 验收标准

1. 单元测试覆盖率95%以上
2. Story和 Spec 中的用户场景全覆盖并且通过。
3. §6.3 定义的 paper/live E2E 三层结构中:L1(`e2e_paper`)与 L2(`e2e_gateway`)在默认 CI 中可重复通过;L3(`e2e_live_smoke`)在 nightly/手动环境可运行,默认 deselect 不得以无 issue 的 `skip` 实现(见 §6.5.3)。


---


## 6. Paper / Live 端到端测试策略

> **范围说明**: §2 定义了"离线、确定、可重现"的数据环境,解决了**回测**的可测性。但 spec/story 中存在大量**仅在 paper/live 下生效**的需求,它们在 §2 环境下无法直接运行。本节专门解决这类需求的端到端测试问题。
>
> **方法论声明**: 本节是**规范的一部分**,依据 spec / story / acceptance / interfaces 编写,描述测试**要观测什么外部行为**,不描述框架**内部如何实现**。框架内部的时间推进机制、撮合触发方式、类层次等均不属于本节范围——它们由实现层自行决定,测试只通过 [interfaces.md](./interfaces.md) 定义的外部可观测契约(数据库表 schema、结构化日志、Web API、回测/运行结果文件)来断言。若某条 AC 因实现层缺少公开装配点而无法测试,按 §6.4.6 的可测试性回退流程处理。

### 6.1. 问题由来 — 为何 paper/live E2E 是一个难题

#### 6.1.1. paper/live 的运行时定义

依据 [story §1.5 / §2 调度总览](./story.md)、[spec-trading.md FR-190 / FR-300](./spec-trading.md) 与 [架构文档 §2.1 / §4.1](../../specs/00-architecture.md):

| 模式      | 时间推进         | 行情来源                 | 成交执行               |
| --------- | ---------------- | ------------------------ | ---------------------- |
| backtest  | 历史数据回放     | 历史日线(tushare)        | 本地仿真撮合           |
| **paper** | **真实交易日历** | **qmt-gateway 实时行情** | **本地仿真撮合**       |
| **live**  | **真实交易日历** | **qmt-gateway 实时行情** | **qmt-gateway 真柜台** |

即:**paper/live 在定义上同时依赖 qmt-gateway 进程和真实交易日历推进**。

#### 6.1.2. 三个不可回避的约束

| #   | 约束                           | 根因(规范依据)                                                                            | 后果                                                |
| --- | ------------------------------ | ----------------------------------------------------------------------------------------- | --------------------------------------------------- |
| C1  | **测试环境不能连 qmt-gateway** | 架构文档 §2.1:qmt-gateway 只能装在带 QMT+xtquant 的 **Windows** 机器上,且涉及**真实账户** | CI / linux / mac 开发机无法运行任何 paper/live 路径 |
| C2  | **不能等真实时间**             | story §1.12 T+1 跨日;FR-360 风控 N 日窗口;FR-125 `on_check` 为 tick 级监控                | 一个完整策略周期要跑真实日历数日至数周,测试不可承受 |
| C3  | **不能 mock 框架内部**         | 本文件 §2.1:E2E 不允许 mock 框架实现;§1.3 作伪模式 #5 "mock 过度"                         | 不能靠替换/打补丁框架内部撮合、调度来绕过           |

#### 6.1.3. 矛盾点

paper/live 的可测性需求,与 C1/C2/C3 在三个维度上正面冲突:

- **外部进程依赖**(C1):qmt-gateway 是 quantide 的外部依赖进程,生产中二者**只共享协议、不共享实现**(架构文档 §2.1 第 4 条)。
- **时间不可压缩**(C2):T+1、风控窗口、策略生命周期都绑定真实交易日历推进。
- **真实度要求**(C3):被测的策略生命周期、交易规则、虚拟账本必须原样运行,否则违反黑盒立场(§1.1)。

> 仅靠 §2 的离线数据环境,无法让 paper/live 跑起来——本节即为此而设。

### 6.2. 核心解法 — 替换外部依赖,不碰框架内部

#### 6.2.1. 立场:可控化 vs mock

paper/live 运行所依赖的三个外部源——**真实墙钟**、**qmt-gateway 行情**、**qmt-gateway 真柜台**——都是 quantide 的**外部依赖**,不是 quantide 自身的实现。本节的解法是:**为这三个外部依赖各提供一个确定性的测试侧替身,框架自身的策略生命周期、交易规则实施、虚拟账本一律原样运行**。

> **关键立场判定**(为何不违反 §2.1 与 §1.3 作伪模式 #5):
> - 被替换的是 quantide 的**外部依赖**(墙钟、外部网关进程),而非框架**内部实现**(撮合、调度、账本);
> - qmt-gateway 在生产里本就是与 quantide 只共享协议的独立进程(架构文档 §2.1),用一个遵守同一协议的替身替换它,等价于用一个 stub 替换外部 HTTP 服务;
> - 被测对象(策略生命周期、交易规则、虚拟账本归因)的代码路径与生产完全一致。

> **边界铁律**: 任何情况下,**不得**为"让测试通过"而替换或绕过框架自身的撮合、调度、T+1/涨跌停/资金等交易规则实施。这些是**被测对象**。若测试发现必须绕过它们才能跑通,说明 AC 的可观测性设计有误(参见 §6.4.6),应回退修订 acceptance / interfaces,而非在测试侧打补丁。

#### 6.2.2. 三类外部依赖的测试侧替身

| 外部依赖           | 生产形态          | 测试侧替身(本节定义职责)   | 替身的可观测边界                   |
| ------------------ | ----------------- | -------------------------- | ---------------------------------- |
| 真实墙钟           | 系统墙钟          | 可快进的虚拟时钟           | 对外表现为"当前交易日/时刻"        |
| qmt-gateway 行情   | gateway 实时推送  | 回放 §2.4 固化行情的回放源 | 对外表现为 paper/live 下的行情序列 |
| qmt-gateway 真柜台 | gateway 下单/回报 | 遵守 gateway 协议的假网关  | 对外表现为订单的接收/回报/查询     |

> 三类替身替换的是**外部源**;框架的**仿真撮合**在 paper 下属于被测对象,**不替换**(live 下成交走假网关,属替身范畴)。

### 6.3. 三层测试金字塔

按真实度/代价/速度,分三层。各层覆盖的 AC 互不重叠,由 test marker 严格区分运行时机(见 §6.5)。

| 层     | 名称         | 时间     | 行情         | 成交执行           | 速度        | 覆盖范围                         | 默认运行          |
| ------ | ------------ | -------- | ------------ | ------------------ | ----------- | -------------------------------- | ----------------- |
| **L1** | 确定性仿真   | 虚拟时钟 | 回放(固化)   | 框架仿真撮合(被测) | **秒级**    | paper 下绝大部分 AC              | ✅ CI 默认         |
| **L2** | 网关契约仿真 | 虚拟时钟 | 回放         | 假网关(L2 替身)    | 秒级        | gateway 协议 / qtoid / 通知类 AC | ✅ CI 默认         |
| **L3** | 实盘路径冒烟 | 真实日历 | 真实 gateway | 真柜台             | 真实(≤1 笔) | 跨模式运行 / dry-run 冒烟        | ❌ 仅 nightly/手动 |

#### 6.3.1. L1 — 确定性仿真(Deterministic Paper)

**原理**:paper 模式的成交由框架自身仿真撮合(story §1.5),本就是被测对象;只需把"时间推进"和"行情来源"两个外部源换成确定性版本,即可在秒级跑完原本需数日的策略周期。

**覆盖的 AC**(以 acceptance 编号为准):
- FR-013 / FR-125 / FR-360(风控策略:**spec 明确 paper-only**,不可回测,只能落在 L1)
- AC-014-04 / AC-015-04 / AC-020-07(模式无关性:同一代码 paper 下行为与其它模式一致)
- FR-160 T+1、FR-140 涨跌停、FR-150 数量取整、FR-180 资金校验(仿真撮合侧的外部可观测结果)
- FR-210 / FR-220 虚拟账本归属(通过 [interfaces.md §4.2~§4.5](./interfaces.md) 的 orders / trades / assets / positions 表断言)

**不覆盖**(交给 L2):任何依赖 qmt-gateway 协议本身的行为(下单参数透传、网关推送、网关断开通知 FR-450 #5)。

#### 6.3.2. L2 — 网关契约仿真(Gateway-Contract Paper)

**原理**:qmt-gateway 在生产中是独立进程,只与 quantide 共享协议(架构文档 §2.1)。测试起一个**遵守同一协议的假网关**,框架的网关客户端指向它;假网关用 L1 的虚拟时钟+回放行情驱动推送与回报。

**覆盖的 AC**:
- FR-300 实时行情接入、FR-410~430 paper/live 账户与交易界面背后的网关交互
- FR-450 #5 实盘交易网关断开通知
- qtoid 全链路贯通(下单→假网关收件→回报→落库,断言见 [interfaces.md §4.2/§4.3](./interfaces.md))
- live 模式下委托/撤单/成交回报的解析

**不覆盖**(交给 L3):真柜台的真实成交规则差异(成交量随机、滑点等)。

#### 6.3.3. L3 — 实盘路径冒烟(Live Smoke)

**原理**:证明"无替身路径真的通"。**不做完整策略周期真测**(C2 不允许),只做**单次往返冒烟**。

**覆盖**(最小集):
- AC-010-04 跨模式运行中 live 这一格(策略能以 live 模式装配启动)
- US-070 回测参数带入实盘
- FR-190 实盘预校验、FR-440 dry-run 切换后订单不再发出

**约束**:用 1 只低价股 100 股的最小代价,一次冒烟 < 1 分钟,资金当日内可冲销(买入→卖出回款,不跨日 T+1)。**仅在有 Windows+QMT 真机的环境运行**,默认 deselect,见 §6.5。

### 6.4. 测试基础设施的职责契约

> 本节定义 L1/L2 测试基础设施中各组件的**职责与外部可观测边界**,供测试工程师实现。**不规定内部实现细节**(具体类名、方法签名、数据结构由实现层自行决定),只规定"它必须对外提供什么、受什么约束"。所有组件置于 `tests/e2e/support/`(见 §6.7)。

#### 6.4.1. 虚拟时钟(替换"真实墙钟")

**职责**: 在测试中扮演"当前交易日历时刻",使被测框架读到的时间可被测试任意快进,从而把数日的策略周期压缩到秒级。

**外部可观测要求**:
- 任意时刻能给出一个确定的"当前时刻"(供框架读"今日"、判断 T+1、判断交易时段)。
- 能从时刻 A 快进到时刻 B;**快进跨越日界时,框架应在 B 时刻表现出与真实跨日一致的外部可观测结果**(例如 T+1 后持仓变为可卖——至于框架内部在何时、以何种机制完成结算,不在本节范围)。

**约束**:
- 不得通过全进程 mock 系统时间(如 freezegun)实现——会污染框架内 asyncio / 数据库客户端等所有时间依赖,引入非被测行为的异常。必须走框架对外暴露的"当前时间"装配点(见 §6.4.6)。

#### 6.4.2. 回放行情源(替换"qmt-gateway 实时行情")

**职责**: 在测试中扮演 paper/live 下的行情来源,从 §2.4 + §2.5 固化的 parquet 中按虚拟时钟的推进喂出行情,使被测框架的撮合/风控监控有真实可回放的数据驱动。

**外部可观测要求**:
- 行情**只来自 §2.4 + §2.5 固化的数据**(§2.4 = 日线/复权/ST/涨跌停/日历, §2.5 = 合成的 ticks + 30m),零网络、可重现。
- 必须能驱动框架的撮合与 tick 级监控(FR-125 `on_check`):即虚拟时钟推进时,框架应能观测到对应时刻的行情并据此产生成交/风控事件(具体驱动机制由实现层决定,测试只断言**外部结果**)。
- 必须支持 spec 要求的数据粒度:`frame_type="1d"`(日线)与 `"30m"`(日内策略,见 story §1.8、US-050)。

#### 6.4.3. 订单观察器(可选,非撮合替身)

**职责**: 仅在需要独立核对订单/成交流的场景使用(如验证风控 `sell_host_position` 是否按 spec 发出卖出、归属是否正确)。它是**只读观察者**,读取 [interfaces.md §4.2/§4.3](./interfaces.md) 的 orders / trades 表与结构化日志,**不接管撮合**。

**约束**(与 §3 ground truth 隔离一致):
- 禁止 import 框架撮合/调度实现;只读外部可观测出口(数据库表、日志)。
- 规则正确性的期望值由 §3 手算脚本提供,不由观察器提供(避免 §1.3 作伪模式 #6 "ground truth 用 impl")。

#### 6.4.4. 假网关(替换"qmt-gateway 真柜台",L2 用)

**职责**: 作为独立进程,实现 quantide↔gateway 的协议(架构文档 §2.1 第 3 条:实时行情推送 / 下单 / 撤单 / 资产·持仓·订单·成交查询),供框架的网关客户端连接。内部用虚拟时钟+回放行情产生推送与回报。

**外部可观测要求**:
- 框架发出的订单应**原样到达**假网关(可断言收到的订单字段与框架提交一致)。
- 假网关的回报应使框架落库的 orders / trades 记录满足 [interfaces.md §4.2/§4.3](./interfaces.md) 的 schema。
- 行为边界 = gateway 协议文档;**不**模拟真柜台成交随机性(那是 L3 范畴)。

#### 6.4.5. 测试编排器(assembly)

**职责**: 把虚拟时钟 + 回放行情源(+ 假网关)与被测框架组装成一个可驱动的测试运行上下文,并对外暴露"推进时间 / 触发一个交易日生命周期"的操作。

**约束**(防走样):
- 组装**只走框架对外公开的装配点**,不 `mock.patch` 任何内部符号,不依赖 `quantide/` 包私有 API(符合 §2.1)。
- 编排器只负责"提供外部源 + 推进时间",**不**代框架执行撮合、结算、调度——这些都是被测对象的行为。

#### 6.4.6. 可测试性回退流程(当实现层缺少公开装配点时)

本节所有替身都假设框架对外暴露了"可注入时间源 / 行情源 / 网关地址"的公开装配点。若实现层当前**未提供**这样的公开点,导致某条 paper/live AC 无法在不碰内部实现的前提下测试,则:

1. **不得**在测试侧用 `mock.patch` 内部符号强行打通(违反 §6.2.1 边界铁律)。
2. 应作为**框架侧的可测试性需求**登记(类比 [spec-foundation.md NFR-050](./spec-foundation.md) 可观测契约的思路:实现层必须为可测试性提供公开出口),由实现层补公开装配点后,测试再据此实现。
3. 该缺口在补齐前,对应 AC 标记为"受阻于可测试性缺口",并在 §1.3 防护机制下挂 issue 跟踪。

### 6.5. Test Marker 与运行控制

三层结构必须用 pytest marker 严格区分,**禁止**默认运行 L3。

#### 6.5.1. Marker 定义

| Marker           | 层  | 默认选中? | 运行条件                    | 说明                          |
| ---------------- | --- | --------- | --------------------------- | ----------------------------- |
| `e2e_paper`      | L1  | ✅         | 无外部依赖                  | 确定性仿真,CI 每次 push 必跑  |
| `e2e_gateway`    | L2  | ✅         | 需可起 localhost 假网关进程 | 网关契约,CI 每次 push 必跑    |
| `e2e_live_smoke` | L3  | ❌         | 需 Windows+QMT+真实账户     | 默认 deselect;仅 nightly/手动 |

#### 6.5.2. CI 选择策略

- **默认 CI**(`pytest`):选中 `e2e_paper` + `e2e_gateway`,deselect `e2e_live_smoke`。
- **Nightly / 手动**:在带 QMT 的 Windows runner 上 `pytest -m e2e_live_smoke`。

#### 6.5.3. 与 §1.3 断言禁忌的衔接

L3 的"默认不运行"必须以**合法方式**实现,不得违反 §1.3 第 2 条"禁止无 issue 的 skip":

- L3 测试**不使用** `pytest.skip()`(那会被 §1.3 CI 拦截)。
- L3 测试用 **marker deselect** 实现默认不运行(marker 本身即"合法的选择性运行机制",且本节即为该 marker 的依据文档)。
- 一旦 marker 失效或被误删导致 L3 永远不跑,按 §1.3 防护机制处理(等同 `skip` 但不带 issue)。

> 建议:为 `e2e_live_smoke` 建立一个长期 GitHub issue 跟踪其运行环境(nightly runner 配置),满足 §1.3 的可追溯要求。

### 6.6. 断言依据 — 外部可观测契约清单

L1/L2 测试的断言**只能**落在 [interfaces.md](./interfaces.md) 已定义的外部可观测出口上,不得依赖框架内部状态。各层典型断言依据:

| 被测行为                    | 断言依据(interfaces 章节)                                                                             | 关联 AC                  |
| --------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------ |
| 委托/成交的产生与字段       | [§4.2](./interfaces.md) orders 表 / [§4.3](./interfaces.md) trades 表                                 | FR-010 / FR-150 / FR-160 |
| 虚拟账本资金/持仓/可卖持仓  | [§4.5](./interfaces.md) assets 表 / [§4.4](./interfaces.md) positions 表 (`avail` 验 T+1)          | FR-160 / FR-210 / FR-220 |
| 风控触发与超额收益          | **v0.2**: [§6](./interfaces.md) 日志事件 `risk.triggered` / `risk.excess_return.finalized` (event payload 字段见 [interfaces.md §4.9 / §4.10](./interfaces.md) 表 schema); **PR3** (FR-360 阶段): 升级为 [§4.9](./interfaces.md) risk_events 表 / [§4.10](./interfaces.md) excess_returns 表 | FR-013 / FR-125 / FR-360 |
| 策略生命周期与订单事件      | [§6](./interfaces.md) 日志条目类型(`order.submitted` / `order.filled` / `risk.triggered` / `risk.excess_return.finalized`) | FR-010 / FR-013          |
| 回测/运行结果               | [§4.1](./interfaces.md) 回测结果 JSON                                                                 | FR-340 / FR-350          |
| 日历/证券元数据(模式无关性) | SDK `Calendar` / `StockList` 直接调用(按 §1.3 白盒单元测试, 对账 env fixture 加载的 parquet)         | AC-014-04 / AC-015-04    |
| qtoid 贯通(L2)              | [§4.2](./interfaces.md) orders.`qtoid` 与 [§4.3](./interfaces.md) trades.`qtoid` 外键一致            | FR-300 / FR-410          |

> 若某条 AC 需要的状态在 interfaces.md 中**没有**对应可观测出口,这是可观测性缺口(违反 NFR-050),应回退修订 interfaces/acceptance 补齐出口,而非在测试中窥探内部状态。

### 6.7. 测试基础设施目录

```
tests/e2e/support/      # paper/live E2E 测试基础设施(L1/L2 替身 + 编排器)
├── virtual_clock.py        # §6.4.1 替换真实墙钟
├── replay_market_data.py   # §6.4.2 替换 gateway 实时行情
├── order_observer.py       # §6.4.3 只读订单观察者(可选)
├── fake_gateway.py         # §6.4.4 替换 gateway 真柜台(L2)
└── runtime_factory.py      # §6.4.5 编排器(组装 + 时间推进)
```

> 隔离规则:该目录下所有模块属于**测试基础设施**,治理标准与 `tests/ground_truth/`(§3.1)一致——禁止为绕过被测行为而 import 框架的撮合/调度/规则实现;只允许经由框架**对外公开**的装配点与契约(interfaces.md 定义的数据 schema、公开 API)与之交互。

### 6.8. 落地优先级

1. **Phase 1(L1)**:虚拟时钟 + 回放行情源 + 编排器 → 跑通双均线 paper 全生命周期,与 §3 ground truth 对账。优先级最高,因风控类 AC(FR-013/125/360)spec 明确 paper-only,**只能**落在 L1。
2. **Phase 2(L2)**:假网关 → 覆盖网关协议 / qtoid / 通知类 AC。
3. **Phase 3(L3)**:`e2e_live_smoke` 用例 + nightly Windows runner。

---


## 7. 附录 — 相关文档

- [spec.md](./spec.md) — 策略框架 spec
- [acceptance.md](./acceptance.md) — 验收标准
- [../v0.2-002-ui/spec.md](../v0.2-002-ui/spec.md) — UI spec
- empyrical — 第三方评估指标库(https://github.com/quantopian/empyrical)
