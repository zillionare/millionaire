# Millionaire UI — Interface Contracts

- **Spec ID**: v0.2-002-ui
- **阶段**: M-ARCH
- **范围**: FastHTML HTTP route / HTML form / JSON schema / SSE event / v0.2-001 API usage
- **原则**: 本文件只定义外部可观察契约; 内部模块、类层次、数据库实现见 `architecture.md`

---

## 1. 通用约定

### 1.1 ErrorEnvelope

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ok` | boolean | 是 | 固定 `false` |
| `code` | string | 是 | 业务错误码 |
| `message` | string | 是 | 用户可见中文消息 |
| `details` | object | 否 | 字段错误/诊断信息, 不含 token/password |
| `retry_after_seconds` | integer | 否 | 自动重试倒计时 |
| `request_id` | string | 否 | 排查用请求 ID |

### 1.2 业务错误码

| code | HTTP | 触发场景 | 用户表现 |
| --- | --- | --- | --- |
| `AUTH_REQUIRED` | 401/303 | 未登录访问受保护页面 | 跳 `/login?next=...` |
| `NOT_INITIALIZED` | 303 | wizard 未完成 | 跳 `/wizard` |
| `VALIDATION_ERROR` | 400 | 表单字段非法 | 字段错误提示 |
| `GATEWAY_NOT_CONFIGURED` | 503 | A 类降级 | 503 提示页/入口 disabled |
| `GATEWAY_OFFLINE` | 503 | B 类降级或下单时断线 | 黄色 banner / error toast |
| `BROKER_RUNTIME_ERROR` | 502 | qmt-gateway reject/timeout | error toast, 表单保留 |
| `DATA_SOURCE_UNAVAILABLE` | 503 | Tushare/行情数据源不可用 | 表格错误占位 + retry |
| `TASK_RUNNING` | 409 | 重复启动长任务 | 保持当前进度 |
| `NOT_FOUND` | 404 | 资源不存在 | 404 页面或 fragment |
| `INTERNAL_ERROR` | 500 | 未预期错误 | 通用错误提示 |

---

## 2. HTTP 路由契约

### 2.1 系统壳层与认证

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/` | session | 未初始化→`303 /wizard`; 已初始化未登录→`303 /login`; 已登录→dashboard Page | `NOT_INITIALIZED` redirect | FR-0110, FR-0460 |
| GET | `/login` | `next?` | 登录 Page | 已登录可 redirect `next` | FR-0120, FR-0140 |
| POST | `/login` | `username`, `password`, `next?` | `303 /dashboard` 或 `next` | `VALIDATION_ERROR` | FR-0120, FR-0140 |
| POST | `/logout` | session | `303 /login` | — | FR-0130 |
| GET | `/profile/password` | session | 改密 Page | `AUTH_REQUIRED` | FR-0130 |
| POST | `/profile/password` | `old_password`, `new_password`, `confirm_password` | success Fragment/Redirect | `VALIDATION_ERROR` | FR-0130 |
| GET | `/notify` | `status?`, `level?`, `source?`, `range?`, `page?` | 告警中心 Page | `AUTH_REQUIRED` | FR-0160 |
| POST | `/notify/{alert_id}/read` | path `alert_id` | AlertActionResult JSON/Fragment | `NOT_FOUND` | FR-0160, FR-0203 |
| POST | `/notify/bulk-confirm` | `alert_ids[]` | AlertActionResult JSON/Fragment | `VALIDATION_ERROR` | FR-0160 |

### 2.2 概览

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/dashboard` | session | Dashboard Page: alerts/accounts/tasks | 局部 `DATA_SOURCE_UNAVAILABLE` | FR-0201~0203 |
| GET | `/dashboard/alerts` | `group?` | 告警分类 Fragment | degraded Fragment | FR-0203 |
| GET | `/dashboard/accounts` | none | 账户总览 Fragment | degraded Fragment | FR-0201 |
| GET | `/dashboard/tasks` | none | 任务状态 Fragment | degraded Fragment | FR-0202 |
| POST | `/dashboard/tasks/{task_id}/run` | path `task_id` | TaskActionResult | `TASK_RUNNING`, `NOT_FOUND` | FR-0202, FR-0310 |

### 2.3 策略

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/strategy` | `q?`, `strategy_type[]?`, `source?`, `show_hidden?`, `show_overridden?` | 策略管理 Page | `DATA_SOURCE_UNAVAILABLE` | FR-0010 |
| POST | `/strategy/scan` | none | ScanResult JSON/Fragment | `BROKER_RUNTIME_ERROR`/`INTERNAL_ERROR` | FR-0011 |
| POST | `/strategy/{strategy_id}/hide` | `confirm_name?` | StrategyActionResult | `VALIDATION_ERROR` | FR-0012 |
| POST | `/strategy/{strategy_id}/unhide` | none | StrategyActionResult | `NOT_FOUND` | FR-0012 |
| POST | `/strategy/{strategy_id}/delete` | `confirm_name` | StrategyActionResult | `VALIDATION_ERROR`, `TASK_RUNNING` | FR-0013 |
| GET | `/strategy/{strategy_id}/run/backtest` | path | Backtest form Page/Fragment | `NOT_FOUND` | FR-0020, FR-0040 |
| POST | `/strategy/{strategy_id}/backtests` | RuntimeParams + StrategyParams + `start_date`, `end_date` | `303 /strategy/backtests/{run_id}` | `VALIDATION_ERROR` | FR-0040, FR-0080 |
| GET | `/strategy/backtests/{run_id}` | path `run_id`, `tab?` | 回测进度/报告 Page | `NOT_FOUND` | FR-0080, FR-0380 |
| GET | `/strategy/backtests/{run_id}/export/trades.csv` | path | CSV download | `NOT_FOUND` | FR-0080 |
| POST | `/strategy/backtests/{run_id}/delete` | `confirm_name` | BacktestActionResult | `VALIDATION_ERROR` | FR-0092 |
| POST | `/strategy/{strategy_id}/backtests/delete-all` | `confirm_strategy_name` | BacktestActionResult | `VALIDATION_ERROR` | FR-0093 |
| POST | `/strategy/backtests/{run_id}/logs/clear` | `confirm_run_name` | BacktestActionResult | `VALIDATION_ERROR` | FR-0093 |
| POST | `/strategy/backtests/{run_id}/promote` | RuntimeParams + `mode=paper|live`, `account_name`, `principal` | RuntimeInstanceResult | `GATEWAY_NOT_CONFIGURED`, `VALIDATION_ERROR` | FR-0040, FR-0260 |
| POST | `/strategy/runtime/{instance_id}/stop` | path | RuntimeInstanceResult | `NOT_FOUND` | FR-0040, FR-0060 |
| POST | `/strategy/runtime/{instance_id}/dry-run` | `enabled=true|false`, `confirm=true` | RuntimeInstanceResult | `GATEWAY_OFFLINE` | FR-0060 |
| GET | `/strategy/risk-events` | `strategy_id?`, `reason?`, `from?`, `to?` | 风控事件 Page | degraded Fragment | FR-0070 |

### 2.4 账户

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/accounts` | `strategy_type?`, `mode?`, `strategy_id?`, `display_hidden_accounts?` | AccountOverview Page | `DATA_SOURCE_UNAVAILABLE` | FR-0390, FR-0411 |
| GET | `/accounts/{account_id}` | `range?`, `top_loss_n?`, `top_profit_m?` | AccountDetail Page | `NOT_FOUND` | FR-0410 |
| POST | `/accounts/{account_id}/hide` | `confirm_name` | AccountActionResult | `VALIDATION_ERROR` | FR-0411 |
| POST | `/accounts/{account_id}/unhide` | none | AccountActionResult | `NOT_FOUND` | FR-0411 |
| POST | `/accounts/live-principal` | `principal` | AccountActionResult | `VALIDATION_ERROR` | FR-0040, FR-0420 |

### 2.5 交易

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/trade/live` | `strategy_id?` | 实盘交易 Page | `GATEWAY_NOT_CONFIGURED` 503 | FR-0420, FR-0180 |
| GET | `/trade/paper` | `strategy_id?` | 仿真交易 Page | `GATEWAY_NOT_CONFIGURED` 503 | FR-0430, FR-0180 |
| POST | `/trade/live/orders` | OrderRequest | OrderResponse JSON/Fragment | `GATEWAY_OFFLINE`, `BROKER_RUNTIME_ERROR`, `VALIDATION_ERROR` | FR-0420 |
| POST | `/trade/paper/orders` | OrderRequest | OrderResponse JSON/Fragment | `BROKER_RUNTIME_ERROR`, `VALIDATION_ERROR` | FR-0430 |
| POST | `/trade/orders/{order_id}/cancel` | path `order_id`, `mode=paper|live` | OrderResponse | `GATEWAY_OFFLINE`, `NOT_FOUND` | FR-0420 |
| GET | `/trade/orders` | `mode`, `strategy_id?`, `symbol?`, `from?`, `to?` | 委托记录 Page/Fragment | degraded Fragment | FR-0400 |
| GET | `/trade/trades` | `mode`, `strategy_id?`, `symbol?`, `from?`, `to?` | 成交记录 Page/Fragment | degraded Fragment | FR-0400 |

### 2.6 系统管理

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/system/tasks` | none | 任务调度 Page | `AUTH_REQUIRED` | FR-0310 |
| POST | `/system/tasks/{task_id}/run` | path | TaskActionResult | `TASK_RUNNING` | FR-0310 |
| POST | `/system/tasks/{task_id}/enabled` | `enabled` | TaskActionResult | `NOT_FOUND` | FR-0310 |
| POST | `/system/tasks/{task_id}/cron` | `cron` | TaskActionResult | `VALIDATION_ERROR` | FR-0310 |
| GET | `/system/integrity` | none | IntegrityReport Page | `DATA_SOURCE_UNAVAILABLE` | FR-0320 |
| GET | `/system/stocks` | `q` | StockSearch Page/Fragment | `VALIDATION_ERROR` | FR-0330 |
| GET | `/system/stocks/{symbol}/kline` | `from?`, `to?`, `frame=1d` | KlineData JSON/Fragment | `NOT_FOUND` | FR-0330 |
| GET | `/system/gateway` | none | GatewayConfig Page | `AUTH_REQUIRED` | FR-0340 |
| POST | `/system/gateway/test` | GatewayConfig | GatewayTestResult | `VALIDATION_ERROR`, `GATEWAY_OFFLINE` | FR-0340 |
| POST | `/system/gateway` | GatewayConfig | GatewayConfigResult | `VALIDATION_ERROR`, `GATEWAY_OFFLINE` | FR-0340, FR-0180 |

### 2.7 事件通知与系统配置

| Method | Path | 入参 | 出参 | 错误响应 | 关联 FR |
| --- | --- | --- | --- | --- | --- |
| GET | `/setting` | none | 系统设置 Page | `AUTH_REQUIRED` | FR-0460 |
| GET | `/setting/notifications` | none | 通知配置 Page | `AUTH_REQUIRED` | FR-0450 |
| POST | `/setting/notifications/wechat/enable` | none | QRCodeBinding JSON/Fragment | `INTERNAL_ERROR` | FR-0450 |
| POST | `/setting/notifications/subscriptions` | NotificationSubscription | NotificationConfigResult | `VALIDATION_ERROR` | FR-0450 |
| GET | `/wizard` | `force?` | Wizard Page | 已完成且非 force→`303 /dashboard` | FR-0460 |
| POST | `/wizard/step/{step_id}` | step-specific form | WizardStepResult | `VALIDATION_ERROR` | FR-0460 |
| POST | `/wizard/step/{step_id}/skip` | `reason?` | WizardStepResult | `VALIDATION_ERROR` for required parent step | FR-0460 |
| GET | `/wizard/progress` | none | Progress Page/Fragment | `NOT_FOUND` | FR-0460, NFR-0060 |
| POST | `/wizard/pending-banner/dismiss` | none | `{ok:true}` | — | FR-0460 |

---

## 3. v0.2-001 API 调用契约

| 001-FR | 用途 | 同步/异步 | UI 失败行为 | 覆盖 UI FR |
| --- | --- | --- | --- | --- |
| FR-020 | 策略自动发现与元数据列表 | 同步/短任务 | 扫描失败 toast, 列表保留 | FR-0010/0011/0012/0013 |
| FR-040 | 一份策略跨回测/仿真/实盘运行 | 同步提交, 后台运行 | 表单错误或 runtime error | FR-0040/0260 |
| FR-200 | 运行时参数定义 | 同步校验 | `VALIDATION_ERROR` | FR-0020/0040 |
| FR-210 | 虚拟账本、委托、成交、持仓 | 同步查询 + 推送刷新 | stale/degraded fragment | FR-0201/0390/0410/0400/0420/0430 |
| FR-220 | 手工交易/补单/风控卖出归属 | 同步下单 | `BROKER_RUNTIME_ERROR` toast | FR-0420/0430 |
| FR-230 | 日线策略回测→仿真/实盘启动 | 异步长任务 | task_progress + retry | FR-0040/0080/0380 |
| FR-240 | live-only 策略无回测启动 | 同步提交, 后台运行 | 表单错误/入口不可见 | FR-0040 |
| FR-250 | 风控策略调度 | 同步配置 | 表单校验失败 | FR-0070 |
| FR-300 | 数据源/Tushare 数据同步 | 异步任务 | 表格失败占位 + retry | FR-0310/0320/0330 |
| FR-310 | 回测报告/评估数据 | 同步查询 | 报告页 degraded | FR-0080/0091/0370 |
| FR-360/380 | 风控评估与回测进度 | 异步/同步查询 | 进度中断提示 | FR-0070/0380 |
| FR-440 | dry-run 模式 | 同步状态切换 | `GATEWAY_OFFLINE`/toast | FR-0060 |
| FR-450 | 事件定义/通知 | 异步事件 | 告警记录仍保留 | FR-0160/0170/0450 |

---

## 4. 数据 schema

### 4.1 RuntimeParams

| 字段 | 类型 | 约束 | 默认 | FR |
| --- | --- | --- | --- | --- |
| `principal` | number | `>0` | 上一次值 | FR-0020 |
| `slippage_rate` | number | `0<=x<=0.1` | `0` | FR-0020 |
| `stamp_tax_rate` | number | `0<=x<=0.01` | `0.001` | FR-0020 |
| `commission_rate` | number | `0<=x<=0.01` | `0.0001` | FR-0020 |
| `min_commission` | number | `>=0` | `5` | FR-0020 |

### 4.2 AccountSummary

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account_id` | string | 账户 ID |
| `account_name` | string | 展示名称 |
| `mode` | enum | `total_live` / `paper` / `live` |
| `strategy_id` | string/null | 总账户为空 |
| `total_assets` | number | 总资产 |
| `available_cash` | number | 可用现金 |
| `market_value` | number | 持仓市值 |
| `account_pnl` | number | 账户盈亏 |
| `daily_pnl` | number | 当日盈亏 |
| `hidden` | boolean | 服务端隐藏事实 |
| `status` | enum | `idle` / `running` / `offline` / `fault` / `stopped` |

### 4.3 OrderRequest / OrderResponse

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `mode` | enum | 是 | `paper` / `live` |
| `strategy_id` | string | 是 | 风控策略不可作为目标 |
| `account_id` | string | 是 | 归属账户 |
| `symbol` | string | 是 | 证券代码 |
| `side` | enum | 是 | `buy` / `sell` |
| `quantity` | integer | 是 | 100 股整数倍 |
| `price` | number/null | 否 | 委托价; 市价可空 |
| `price_source` | enum | 否 | `prev_close` / `realtime` / `ma5` / `ma10` / `limit_up` / `limit_down` / `manual` |
| `order_type` | enum | 是 | `limit` / `market` |

| 响应字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean | 成功为 true |
| `order_id` | string | 订单号 |
| `status` | enum | `submitted` / `rejected` / `cancelled` / `filled` |
| `message` | string | toast 文案 |
| `created_at` | string | ISO datetime |

### 4.4 AlertEvent

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `alert_id` | string | 告警 ID |
| `created_at` | string | ISO datetime |
| `source` | enum/string | `strategy` / `system` / `gateway` / `scheduler` |
| `category` | enum | `strategy` / `system` |
| `level` | enum | `error` / `warning` / `info` |
| `summary` | string | 列表摘要 |
| `detail_url` | string | 点击跳转 URL |
| `read` | boolean | 是否已读 |
| `confirmed` | boolean | 是否确认 |

### 4.5 PushEvent

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_id` | string | 单调/唯一, 用于断线续传 |
| `type` | enum | `alert` / `order` / `portfolio` / `task_progress` / `gateway_status` |
| `created_at` | string | ISO datetime |
| `payload` | object | 按事件类型变化 |

| type | payload 必备字段 |
| --- | --- |
| `alert` | `AlertEvent`, `unread_count` |
| `order` | `order_id`, `strategy_id`, `status`, `message` |
| `portfolio` | `account_id`, `total_assets`, `available_cash`, `market_value`, `daily_pnl` |
| `task_progress` | `task_id`, `task_name`, `percent`, `stage`, `status`, `message` |
| `gateway_status` | `status=online|offline|not_configured`, `degrade_class=A|B|null`, `message` |

### 4.6 GatewayConfig

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `server` | string | 非空 host/IP |
| `port` | integer | `1..65535` |
| `url_prefix` | string | 以 `/` 开头 |
| `api_key` | string | 服务端保存, 不写 localStorage |
| `timeout_seconds` | integer | `>=1` |

### 4.7 NotificationSubscription

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `channel` | enum | `wechat` / `im` / `email` |
| `enabled` | boolean | 是否启用 |
| `receiver` | string/null | IM/email 接收方 |
| `event_types` | array | `order` / `trade` / `failure` / `gateway_offline` |

---

## 5. 推送接口

| Method | Path | 鉴权 | 入参 | 出参 | 关联 FR/NFR |
| --- | --- | --- | --- | --- | --- |
| GET | `/events/stream` | session cookie | `last_event_id?` query 或 `Last-Event-ID` header | `text/event-stream` | FR-0160, FR-0420, FR-0460, NFR-0060 |

断线规则:

| 场景 | 契约 |
| --- | --- |
| 浏览器断线 | UI 显示“重连中”, 已加载内容保持 |
| 重连成功 | client 携带 `Last-Event-ID`, 服务端补发可用事件或发送 snapshot |
| 服务端无历史事件 | 发送各区域最新 snapshot: unread_count / task status / gateway_status |

---

## 6. localStorage key 契约

| key | 类型 | 默认 | 敏感 | FR/NFR |
| --- | --- | --- | --- | --- |
| `quantide.sidebar.collapsed` | boolean | `false` | 否 | FR-0150, NFR-0070 |
| `quantide.accounts.display_hidden` | boolean | `false` | 否 | FR-0411 |
| `quantide.runtime_params.last` | RuntimeParams | spec 默认 | 否 | FR-0020, NFR-0070 |
| `quantide.filters.strategy` | object | `{}` | 否 | NFR-0070 |
| `quantide.wizard.pending_banner.dismissed_at` | string/null | null | 否 | FR-0460 |

禁止 key: password, session token, Tushare token, qmt-gateway api_key。

---

## 7. AC → 接口出口闭环

所有 AC 均通过本文件出口观察: FR-0110~0180 走认证/告警/SSE/ErrorEnvelope; FR-0201~0203 走 `/dashboard*`; FR-0010~0380 走 `/strategy*` 与 RuntimeParams/PushEvent; FR-0390~0411 走 `/accounts*`; FR-0400~0430 走 `/trade*` 与 OrderRequest/Response; FR-0310~0340 走 `/system*`; FR-0450 走 `/setting/notifications*`; FR-0460 走 `/wizard*`; NFR 走 SSE、degraded fragments、localStorage 与可访问 DOM 属性。
