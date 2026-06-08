# millionaire ↔ qmt-gateway 通讯契约

> 与 issue #32 配套；定位"哪些调用是被允许的，哪些不是"。

## 1. 文档定位

- 本文件约束 `quantide/` 中所有到 qmt-gateway 的 HTTP 调用。
- 优先级：低于 `00-architecture.md`、与 `01-e2e-accuracy-contract.md` 平行。
- 适用范围：所有 quantide runtime、dev-stub、e2e 测试。

## 2. 核心约定

| 调用类型 | 协议 | 允许 | 鉴权 |
|---|---|---|---|
| 业务数据（positions / orders / asset / trades） | JSON | 必 | `X-API-Key` 或 session cookie |
| 交易动作（buy / sell / cancel） | JSON（POST form-encoded） | 必 | session cookie（来自 `/auth/login`） |
| 健康检查（ping、connection-status） | 纯文本或 JSON | 必 | 通常无 |
| htmx 视图（`?view=table` / `?view=card` / HTML 片段） | text/html | **禁** | — |

**禁止**：
- 任何 quantide 代码不得以 `Accept: text/html` 或 `?view=*` 参数请求 gateway。
- 任何 quantide 代码不得对 `text/html` 响应调用 `json.loads` 或按 HTML 解析。
- 任何 quantide 代码不得**依赖** gateway 的 htmx 端点布局（标签、class、id）来提取数据。

**允许例外**：
- qmt-gateway 自己的 Web UI 仍返回 htmx 页面，**但这是给浏览器用的**，不是给 quantide。

## 3. 协议清单

### 3.1 业务数据（GET，JSON）

| Endpoint | 返回 | 调用方 |
|---|---|---|
| `GET /api/ping` | 200/401/403 | init_wizard, system/gateway |
| `GET /api/asset` | `{total, cash, frozen_cash, market_value, pnl, pnl_pct}` | `GatewayBrokerWrapper` |
| `GET /api/trade/positions` | `[{asset, shares, avail, price, profit, mv, ...}]` | `GatewayBrokerWrapper`, `trade_main._fetch_positions_orders_via_gateway` |
| `GET /api/trade/orders?portfolio_id=...&date=...` | `[{qtoid, asset, side, shares, price, status, ...}]` | `GatewayBrokerWrapper`, `trade_main._fetch_positions_orders_via_gateway` |
| `GET /api/trade/trades` | `[{...}]` | `GatewayBrokerWrapper` |

### 3.2 交易动作（POST，form-encoded，JSON 响应）

| Endpoint | Body | 返回 |
|---|---|---|
| `POST /auth/login` | `username, password, auto_login=false` | 200/4xx |
| `POST /api/trade/buy` | `portfolio_id, asset, shares, price, ...` | `{qtoid, status, ...}` |
| `POST /api/trade/sell` | 同上 | 同上 |
| `POST /api/trade/cancel` | `qtoid=...` | `{status, ...}` |

### 3.3 健康检查

| Endpoint | 返回 | 调用方 |
|---|---|---|
| `GET /api/ping` | 200/4xx（text 或 json） | init_wizard, system/gateway |

## 4. 鉴权两种形式

quantide 端对 gateway 有两种合法鉴权：

1. **Session cookie**：通过 `/auth/login` 拿 cookie，后续走 cookie。`GatewayClient` 用了这个。
2. **`X-API-Key` header**：用于 stateless 调用（不需要完整登录）。`trade_main._fetch_positions_orders_via_gateway` 用了这个。

**混用**：同一请求不应同时带 cookie 和 `X-API-Key`；后端按优先级选择。

## 5. 防御性约束

`quantide.core.runtime.gateway_client.GatewayClient` 与 `_fetch_positions_orders_via_gateway` 在解析响应前必须做：

1. 检查 `Content-Type` 头：
   - 期望为 `application/json` 才继续 `json.loads`
   - 期望为 `text/plain`（仅 ping）才接受文本
   - **收到 `text/html` 必须抛 `RuntimeError`，并在日志 warning 中记录 URL、status、content-length**
2. 检查 HTTP status code：4xx/5xx 必须抛异常（不要静默返回 None）
3. 检查响应体非空：空 body 视为网络异常

实现位置：
- `GatewayClient.get_json` / `GatewayClient.post_form` 已有 `json.loads`；**需加 Content-Type 校验**
- `_fetch_positions_orders_via_gateway` 走 `urllib.request`，**目前没 Content-Type 校验**（直接 json.loads 失败时回退到 empty）；需在解析前先 assert response Content-Type

## 6. 测试约束

新增 `tests/core/test_gateway_protocol_contract.py`，覆盖：

1. GatewayClient 收到 `Content-Type: text/html` 时抛 `RuntimeError`
2. `_fetch_positions_orders_via_gateway` 收到 `Content-Type: text/html` 时回退到 empty 并 log warning
3. GatewayClient 4xx 状态码抛异常
4. 端到端：所有在 `quantide/` 中以 HTTP 调用 gateway 的位置（grep audit）有覆盖

## 7. No-do

- 不修改 `GatewayClient.ensure_login` 的协议（`/auth/login` POST form）
- 不为兼容 htmx 端点保留 `?view=table` 调用
- 不在 quantide 端写 HTML 解析器

## 8. 决策记录

- 用户拍板（#32）："只能请求基于 json 的接口，少量允许基于 text response 的接口（比如 ping?），但绝对不能请求返回 htmx 的请求"
- 用户拍板（#54 反馈）：qmt-gateway 端日志级别已下调
- 决定：防御性 Content-Type 校验放在 `GatewayClient` 与 `_fetch_positions_orders_via_gateway` 两处
- 决定：本 spec 与后续 e2e 测试一起作为 release gate

## 9. 验收

1. `grep -rn "?view=table\|?view=html\|?view=card" quantide/` 无结果
2. `grep -rn "Accept: text/html" quantide/` 无结果（除测试 stub）
3. `tests/core/test_gateway_protocol_contract.py` 全 pass
4. 整体 web + service 套件不新增 fail
