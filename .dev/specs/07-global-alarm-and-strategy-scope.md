# 全局告警入口与策略页边界收敛

## 1. 文档定位

本 spec 约束以下功能调整：

1. header 中的 alarm / bell 图标必须成为风险事件中心与运行时监控的全局入口。
2. `/strategy` 页面只能保留与策略发现、策略管理、回测相关的内容。
3. 风险事件中心与运行时监控从 `/strategy` 移出，迁入 `系统维护` 模块下的独立页面。

本 spec 受 `.dev/specs/00-architecture.md`、`.dev/specs/02-layout-nav-style.md`、`.dev/specs/05-release-readiness.md` 约束；若与较旧草案冲突，以这些高优先级文档和本 spec 为准。

## 2. 背景与问题

当前实现中，`/strategy` 首页除了策略列表与回测报告外，还直接渲染了：

1. 风险事件中心
2. 运行时监控

这样做虽然复用了已有运行时数据，但会带来以下问题：

1. 信息架构混乱。`/strategy` 在导航层面属于“策略管理”，而不是系统运行维护中心。
2. 页面职责不清。用户进入策略页，本应关注策略发现、配置、回测与结果，而不是账户封控、运行时阻断、系统级告警。
3. 全局入口缺失。header 中的 alarm 图标目前只有视觉占位，没有承载真实业务入口。
4. 与发布约束不符。`.dev/specs/05-release-readiness.md` 已要求“系统必须提供独立的风险事件中心，而不是仅依赖消息中心”。

## 3. 设计决策

### 3.1 总体决议

采用以下信息架构：

1. `/strategy` 仅保留“策略”和“回测”相关内容。
2. 风险事件中心与运行时监控迁入 `系统维护`，作为独立页面存在。
3. header 中的 bell 图标升级为“告警中心”入口：
   - 负责展示当前风险告警摘要；
   - 提供进入“风险事件中心”和“运行时监控”的快捷入口；
   - 不在弹层中直接承载完整运维操作。

### 3.2 导航归属

`系统维护` 侧边栏新增一个分组：

```md
- 运行保障:
    - 风险事件中心
    - 运行时监控
```

原因：

1. 风险事件与运行时实例都属于系统级、跨模式的运维对象；
2. 它们既不只属于策略，也不只属于实盘或仿真；
3. 放到 `系统维护` 可与网关、任务、数据源等“系统运行支持能力”保持一致。

### 3.3 bell 图标的产品语义

bell 不是通用“消息中心”，而是当前阶段的“告警中心”入口。

本阶段其 badge 含义定义为：

1. badge 数字 = 当前未关闭风险事件数（`open_events`）；
2. 没有未关闭风险事件时，不显示 badge；
3. bell 点击后打开告警弹层；
4. 告警弹层内同时展示：
   - 风险事件摘要与最近事件；
   - 运行时概览；
   - 两个独立页面的跳转入口。

注意：运行时监控是告警中心的关联入口，而不是 bell 的主语义。

## 4. 页面与路由调整

### 4.1 `/strategy`

`/strategy` 首页只允许保留以下内容：

1. 策略列表
2. 策略扫描 / 复制示例 / 目录配置等与策略发现直接相关的工具
3. 回测报告列表
4. 策略详情、回测报告详情对应的既有跳转

`/strategy` 首页不得再包含：

1. 风险事件中心
2. 运行时监控
3. 账户级/系统级告警摘要
4. 与 live/paper/backtest 运行时生命周期管理直接相关的大表或操作按钮

### 4.2 新增页面

新增两个系统维护页面：

1. `/system/risk-events`
   - 页面标题：`风险事件中心`
   - 显示风险事件摘要、风险事件列表、空态说明
   - 当前阶段允许先复用现有 risk center card 的渲染逻辑

2. `/system/runtime-monitor`
   - 页面标题：`运行时监控`
   - 显示运行时列表与既有启动 / 停止 / 封锁 / 解除封锁操作
   - 当前阶段允许先复用现有 runtime table 的渲染逻辑

### 4.3 告警中心弹层

header bell 点击后打开一个轻量告警弹层（popover / dropdown 风格即可，不要求首版就做复杂 drawer）。

弹层结构：

1. 标题：`告警中心`
2. 风险摘要区：
   - 账户封控数
   - 策略封控数
   - 活动告警数
3. 最近风险事件（最多 5 条）
4. 运行时摘要：
   - running / blocked / failed 等简要计数
   - 或等价的概览信息
5. 页底快捷操作：
   - `查看风险事件中心`
   - `查看运行时监控`

弹层中不放以下操作：

1. 启动/停止运行时
2. 解除封锁
3. 封锁账户/策略

这些重操作只保留在对应完整页面中。

## 5. 交互要求

### 5.1 bell 图标

1. bell 必须可点击，不允许成为无功能装饰。
2. `aria-label` 应从“消息中心”调整为更准确的“告警中心”。
3. 点击 bell 后：
   - 打开告警弹层；
   - 再次点击或点击外部区域关闭；
   - 按 `Escape` 关闭。

### 5.2 空态

当没有未关闭风险事件时：

1. bell 不显示 badge；
2. 告警弹层显示“当前没有待处理风险事件”；
3. 仍保留进入完整页的入口，便于查看历史或运行时状态。

### 5.3 页面边界

1. `/strategy` 不负责系统级运维告警承载；
2. `系统维护/风险事件中心` 是风险事件的权威列表页；
3. `系统维护/运行时监控` 是运行时控制与观测的权威列表页；
4. bell 是全局入口，不替代完整页。

## 6. 实施建议

### 6.1 代码组织

建议新增或调整：

1. `quantide/web/pages/system/risk_events.py`
2. `quantide/web/pages/system/runtime_monitor.py`
3. `quantide/web/components/header.py`
4. `quantide/web/layouts/main.py`
5. `quantide/web/pages/strategy.py`
6. 视需要在 `quantide/service/strategy_runtime.py` 增加告警摘要辅助方法

### 6.2 复用策略

首版优先复用现有逻辑，避免重复开发：

1. 风险事件中心页面可复用 `_risk_event_center_content()`
2. 运行时监控页面可复用 `_runtime_table_content()` 或其拆分后的公共函数
3. bell 告警弹层可复用 `risk_summary()`、`list_risk_events()`、`list_runtime_rows()`

但应避免把整个 `_runtime_ops_panel()` 继续原样嵌入 `/strategy`。

## 7. 非目标

本阶段不要求完成以下能力：

1. 风险事件高级筛选（账户/策略/时间/事件类型）的完整 UI
2. 历史已关闭风险事件的完整详情页
3. 顶部实时流式推送或 websocket 告警
4. 通用消息中心与风险中心合并
5. 新增一级导航“运维”

这些可在后续迭代中扩展。

## 8. 验收标准

### 8.1 策略页边界

1. 访问 `/strategy` 时，只看到策略与回测相关内容。
2. 页面 HTML 中不再出现“风险事件中心”“运行时监控”两个区块。

### 8.2 系统维护页面

1. `系统维护` 侧边栏出现“运行保障”分组。
2. 分组下包含：
   - 风险事件中心
   - 运行时监控
3. 访问 `/system/risk-events` 可查看风险事件中心内容。
4. 访问 `/system/runtime-monitor` 可查看运行时监控内容。

### 8.3 bell 入口

1. bell 点击后有可见反馈。
2. bell 弹层展示当前风险摘要。
3. bell badge 能正确反映未关闭风险事件数。
4. bell 弹层能跳转到：
   - 风险事件中心
   - 运行时监控

### 8.4 行为一致性

1. 原有风险事件和运行时操作能力不丢失。
2. 风险事件中心和运行时监控迁出 `/strategy` 后，页面行为保持一致。
3. `/strategy` 不再承担系统运维职责。

## 9. 验证建议

至少补充以下测试：

1. `/strategy` 页面不再包含风险中心 / 运行时监控区块。
2. `/system/risk-events` 页面渲染风险事件中心。
3. `/system/runtime-monitor` 页面渲染运行时监控。
4. header bell 在有/无风险事件时，badge 与弹层内容正确。
5. `系统维护` 侧边栏含新的“运行保障”菜单项。

## 10. GitHub Issue 草案

### Title

`feature: make header alarm the global alert entry and remove non-strategy ops from /strategy`

### Labels

- `feature`

### Body

#### Summary

Move risk event center and runtime monitor out of `/strategy`, make `/strategy` strategy-only, and turn the header alarm icon into the global alert entry.

#### Why

- `/strategy` currently mixes strategy/backtest content with system-wide operational content.
- The header alarm icon is currently non-functional.
- Release-readiness spec requires an independent risk event center.

#### Scope

- Remove risk event center and runtime monitor blocks from `/strategy`
- Add `/system/risk-events`
- Add `/system/runtime-monitor`
- Add a new `运行保障` group under `系统维护`
- Make the header alarm icon open an alert popover with risk summary and shortcuts

#### Acceptance Criteria

- `/strategy` shows only strategy/backtest-related content
- `系统维护` exposes dedicated entry points for risk events and runtime monitor
- Header alarm is clickable and shows alert summary
- Alarm badge reflects current open risk events count
- Existing runtime/risk actions remain available in their new pages

#### Validation

- Add/update targeted web tests for `/strategy`, system pages, header alarm, and sidebar structure

