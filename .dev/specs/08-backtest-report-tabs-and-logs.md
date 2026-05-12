# 回测报告单标签视图与回测日志中心

## 1. 文档定位

本 spec 约束两项改动：

1. 回测报告页从“锚点长页面”改为“单标签内容页”。
2. 回测日志作为独立 feature 接入回测框架、SQLite、文件持久化与 Web UI。

本 spec 受以下文档约束：

1. `.dev/specs/00-architecture.md`
2. `.dev/specs/02-layout-nav-style.md`
3. `.omx/plans/prd-backtest-report-tabs-and-logs.md`

若与旧实现或历史讨论冲突，以本 spec 为准。

## 2. 现状与根因

### 2.1 报告页过长

`quantide/web/pages/strategy.py` 的 `backtest_result()` 在一次渲染中同时输出：

1. 收益概述
2. 收益曲线
3. 交易详情
4. 每日持仓
5. 日志输出

侧边栏子菜单只是 `#overview / #trades / #positions / #logs` 锚点，点击后只会滚动页面，不会切换内容，因此会出现左侧菜单滚出视口的问题。

### 2.2 日志输出为空白

当前 `_build_log_rows()` 读取 `db.get_strategy_logs()`；但 `StrategyLog` 由 `record()` 写入，结构是 `key + value + extra` 的数值型注释，不是文本运行日志。

因此：

1. `BaseStrategy.log()` 产生的文本日志不会进入报告页。
2. `BacktestRunner` / `BacktestBroker` 的 loguru 日志也不会进入报告页。

## 3. 设计决策

### 3.1 报告页切换方式

采用 **query 参数驱动的服务端切换**，而不是前端 show/hide：

1. 路由保持 `/strategy/backtest/{portfolio_id}`。
2. 新增查询参数 `tab`，合法值：
   - `overview`
   - `trades`
   - `positions`
   - `logs`
3. 未提供或非法时回退到 `overview`。
4. 左侧子菜单 URL 统一改为 `/strategy/backtest/{portfolio_id}?tab=<tab>`。

采用该方案的原因：

1. 不需要额外前端状态管理。
2. active 高亮、刷新恢复、直接分享链接都更稳定。
3. 更容易做 HTML 级测试断言。

### 3.2 回测日志数据模型

新增独立表 `backtest_logs`，不要复用 `strategy_logs`。

建议字段：

1. `event_id`：主键，字符串 UUID
2. `portfolio_id`：组合 ID
3. `dt`：日志时间
4. `level`：日志等级（INFO/WARNING/ERROR 等）
5. `source`：来源（runner / strategy / broker）
6. `message`：文本消息
7. `extra`：JSON 字符串，可选

理由：

1. `strategy_logs` 已承担数值型注释，不应被文本日志污染。
2. 文本日志需要等级、来源、消息等字段，不适合硬塞到 `key/value` 结构。

### 3.3 文件持久化格式与路径

采用 JSONL 逐行追加写入。

路径约定：

1. 新增 `get_backtest_log_dir()` / `get_backtest_log_path(portfolio_id)`。
2. 目录位于应用配置目录下：`<app_config_dir>/backtest_logs/`。
3. 文件名：`<portfolio_id>.jsonl`。

理由：

1. 结构化文本便于反复加载。
2. 单 portfolio 单文件，路径稳定，报告页可直接反查。
3. 不需要额外保存“文件选择结果”。

## 4. 实现方案

### 4.1 SQLite 与路径层

#### 4.1.1 `quantide/data/sqlite.py`

新增：

1. `BacktestLogEntry` dataclass
2. `SQLiteDB.insert_backtest_logs()`
3. `SQLiteDB.get_backtest_logs()`

要求：

1. 返回值统一转成 `pl.DataFrame`。
2. `dt` 字段需 cast 为 `Datetime`。
3. 支持按 `portfolio_id` 查询。

#### 4.1.2 `quantide/config/paths.py`

新增：

1. `get_backtest_log_dir()`
2. `get_backtest_log_path(portfolio_id)`

### 4.2 回测日志服务

新增 `quantide/service/backtest_logs.py`（或等价模块），提供：

1. `record_backtest_log(...)`
2. `list_backtest_logs(portfolio_id, limit=...)`
3. `load_saved_backtest_logs(portfolio_id, limit=...)`
4. `saved_backtest_log_exists(portfolio_id)`
5. `saved_backtest_log_path(portfolio_id)`

行为约束：

1. 每条日志总是写入 SQLite `backtest_logs`。
2. `save_to_file=True` 时，同步追加 JSONL 文件。
3. 文件写入失败时：
   - 不能抛异常中断回测主流程；
   - 需要把失败信息再记录回 SQLite 日志（来源 `system` 或 `runner`）。

### 4.3 回测框架接入点

#### 4.3.1 `quantide/service/runner.py`

`BacktestRunner.run()` 增加参数：

1. `save_logs: bool = False`

在以下节点写日志：

1. 回测开始
2. 日期区间对齐结果（如需要）
3. 回测结束
4. 异常失败

#### 4.3.2 `quantide/core/strategy.py`

`BaseStrategy` 调整：

1. `self.logger` 绑定 `portfolio_id`（若 broker 可提供）。
2. `log()` 在保留现有 loguru 输出的同时，将渲染后的文本写入回测日志服务。
3. `source` 固定为 `strategy`。

#### 4.3.3 `quantide/service/backtest_broker.py`

新增/复用统一的 broker 日志辅助方法，例如：

1. `_write_backtest_log(level, message, dt=None, extra=None)`

要求：

1. 继续保留 loguru 输出。
2. 对用户可见的重要撮合日志（停牌/涨跌停/无数据/成交等）走该统一方法。
3. `source` 固定为 `broker`。

### 4.4 回测启动 UI

#### 4.4.1 `quantide/web/pages/strategy.py` 的回测弹窗

表单新增：

1. `save_logs` checkbox
2. 辅助说明文案：开启后将写入本地回测日志目录

交互补齐：

1. 开始运行按钮提交后需禁用，避免重复点击。
2. 提交中的文案可切换为“启动中...”或至少禁用按钮。

#### 4.4.2 `run_backtest()`

1. 解析 `save_logs`。
2. 传入 `BacktestRunner.run(save_logs=...)`。
3. `strategy_runtime_manager.create_backtest_runtime(...)` 需要记录 `save_logs`，以便报告页读取当前运行配置。

### 4.5 回测报告 UI

#### 4.5.1 标签解析

新增 helper：

1. `_normalize_backtest_tab(value)`
2. `_build_backtest_sidebar_menu(portfolio_id, active_tab)`

`backtest_result()` 只渲染当前 tab 对应内容：

1. `overview`：指标 + 曲线 + 状态区 + 投放区
2. `trades`：交易详情表
3. `positions`：每日持仓表
4. `logs`：日志面板

#### 4.5.2 日志面板

日志面板需包含：

1. 实时状态提示（运行中 / 已完成 / 失败）
2. 保存状态提示（未保存 / 已保存到文件）
3. 文件路径摘要
4. “加载已保存日志”按钮（仅文件存在时可用）
5. 日志空态
6. 错误态容器

#### 4.5.3 WebSocket 负载

保留现有 `/strategy/backtest/{portfolio_id}/ws`，但：

1. `logs` 字段改为来自 `backtest_logs`。
2. 负载增加 `log_meta`：
   - `saved`
   - `saved_path`
   - `save_requested`
3. 页面脚本更新日志面板状态文案。

#### 4.5.4 保存文件加载接口

新增路由，例如：

1. `GET /strategy/backtest/{portfolio_id}/logs/saved`

返回日志面板局部内容，供 `hx-get` 局部刷新或等价方式使用。

要求：

1. 多次点击幂等。
2. 文件不存在时返回错误提示块，而不是 500。

## 5. 向后兼容与边界

1. 旧的 `strategy_logs` 保持不变，继续服务于数值记录与分析场景。
2. 没有保存文件的历史回测报告仍可打开；日志面板显示“未保存日志”，但不报错。
3. 历史回测若无 `backtest_logs` 数据，则日志面板显示空态。

## 6. 测试要求

### 6.1 单元测试

新增或补充：

1. `tests/core/test_strategy_runner.py`
   - `BaseStrategy.log()` 能写入回测日志
   - `BacktestRunner.run(save_logs=True)` 会创建日志文件
2. `tests/service/...`（如需要）
   - 回测日志服务写 DB / 写文件 / 文件失败回退

### 6.2 Web 测试

补充 `tests/web/test_strategy.py`：

1. 默认 tab 为 `overview`
2. `?tab=logs` 时不再渲染交易详情/每日持仓区
3. 日志面板显示空态
4. 有保存文件时显示加载入口
5. 无保存文件时不显示可点击加载入口或按钮为禁用态

### 6.3 验证重点

1. 报告页不会再把四个区块一起渲染。
2. 运行中 websocket 能读到追加日志。
3. 文件保存与加载链路完整。
4. 文件写失败不会使回测失败。

## 7. 验收标准

1. 回测报告页任一时刻只展示一个主内容标签。
2. 日志输出不再依赖 `strategy_logs` 的 `key/value` 结构。
3. 策略、runner、broker 产生的文本日志能进入 UI。
4. 勾选保存后能生成 JSONL 文件并在报告页重复加载。
5. 相关测试通过，现有回测报告能力不回退。
