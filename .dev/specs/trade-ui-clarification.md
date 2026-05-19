# 交易界面需求澄清访谈清单

> 来源：飞书 `CGiYdClrFoNToyxBvqccxrVsnch`（需求）+ `L1bXdPdOEoQxSYxAeRbcSetPn4e`（流程规则）
> 创建于：2026-05-18
> 状态：**等待用户回答**

## 背景速览（已掌握）

- 现存 3 个交易页面文件并存：
  - `quantide/web/pages/trade.py`（仿真专属，594 行）
  - `quantide/web/pages/trade_main.py`（按 livetrade 原型混合实现，754 行）
  - `quantide/web/pages/trade_index.py`（账号路由分发，247 行）
- broker 抽象 + `sim_broker` + `qmt_broker` 已就绪
- `livequote` 提供 `get_quote / get_price_limits / get_minute_bars / get_daily_bar`
- `datafeed.BarsFeedImpl` 提供 `get_bars / get_current_price`
- 数据库表已有 `Asset / Position / Order / Trade / Portfolio`
- e2e harness：`tushare_stub.py` + `gateway_stub.py`（项目规则硬要求）
- **能力缺失需澄清**：股票模糊匹配复用点、MA5-MA60 计算口径、AI 提示徽章数据源

---

## A. 范围与版本（3 题）

1. **新 UI 与旧三件套的关系**：新 `trade.py` 是否要 **同时替代** `trade.py + trade_main.py + trade_index.py`，并删除后两个？还是只重写主交易页、保留 `trade_index.py` 的账号路由分发？
2. **版本号**：当前 `pyproject.toml` 是 `0.1.0`，按 `project_rules` 第 4 条"无历史包袱"。本次发布版本号定为？（建议 `0.2.0`）
3. **实盘 vs 仿真界面差异**：截图只展示一种界面。实盘与仿真 **共用同一套 UI**（仅数据源不同），还是分两套？

## B. 数据源与依赖（5 题）

4. **股票模糊匹配**：spec 说"已实现请复用"，但只找到 `data_stocks.py` 的页面级搜索。请确认：(a) 去 `quantide/data/models/stocks.py` 找现有函数复用、(b) 还是允许新写 service 层 `fuzzy_match_symbol(query) -> list[(code, name)]`？
5. **MA5/MA10/MA20/MA30/MA60**：spec 强调"截止昨天，不含今天"。打算用 `datafeed.BarsFeedImpl.get_bars(asset, start=today-90d, end=today-1d)` + polars 滚动均值。确认：(a) 前复权(qfq) 还是 后复权？(b) MA60 不足 60 天时显示空？还是用现有天数？
6. **昨收价**：用 `get_bars(asset, end=today-1d).tail(1)['close']`，还是 `livequote` 有更直接接口？
7. **"现价"刷新频率**：(a) 仅手动 refresh、(b) 每 N 秒轮询、(c) WebSocket 推送（`livequote` 已有 ws）？若 b/c，间隔/触发条件？
8. **AI 提示徽章（RSI / 拐头 / 前高）数据源**：(a) 用 `polars-talib` 现算（RSI 我会算，"拐头""前高"需要定义）、(b) 先留空 placeholder、(c) 已有 service 我没找到？

## C. UI 行为细节（6 题）

9. **Speed Dial 6×4 网格**（-10..+10 个百分比按钮）：点击后 (a) 直接下单（最危险但最快）、(b) 仅填充"金额=总资产×%"到表单等用户确认、(c) 弹确认 dialog？
10. **闪电单"闪电"语义**：(a) 点一下立即按市价/对手价下单不弹确认、(b) 简化版下单表单？截图里的闪电单表格记录的是已成交还是预设单？
11. **Toast 触发条件**：成功/失败下单都弹？还是只在异步成交时弹？停留秒数？
12. **快捷价位按钮**（昨收/MA5..MA60/现价 共 7 个）：点击仅 **填充价格输入框**，对吗？
13. **持仓 tab 的"卖出"按钮**：(a) 跳到下单区填好默认、(b) 直接清仓、(c) 弹小窗确认数量？
14. **今日委托的"撤单"+"过滤"**：过滤维度是？（状态/方向/代码？）撤单后是否乐观更新 UI？

## D. 路由与状态管理（3 题）

15. **路由规划**：建议 `/trade/{kind}/{portfolio_id}` 统一入口（`kind ∈ live|simulation`），保留 `/trade/` 作账号选择/无账号引导。**确认采纳？**
16. **fragment 导航**：`00-architecture.md §UI约束` 要求 HTMX fragment 导航优先。交易页内部各 panel 刷新都用 `hx-get` 局部刷新 + OOB swap。**确认采纳？**
17. **下单后页面状态同步**：(a) 资产条 + 持仓 + 委托 三块、(b) 还要刷新可用资金以便下一次下单计算？

## E. 测试策略（3 题）

18. **e2e 覆盖范围**：项目规则要求每个交易功能至少 1 个 stub 测试。打算覆盖：
    - (a) 下单成功路径(buy/sell)
    - (b) 资金不足拒单
    - (c) 持仓不足拒单
    - (d) 撤单
    - (e) MA 计算正确性
    - (f) 模糊匹配命中

    **够吗？要加/减？**
19. **三模式测试**：仅写 paper 模式测试？还是 paper+live 两份（live 走 `gateway_stub`）？
20. **视觉/手工测试**：spec §2 规定"页面样式、动态效果一般手工测试"。Speed Dial、Toast、Wizard 这类纯交互我 **写功能型测试（HTML 包含正确元素），不写视觉对比**，对吗？

## F. 验收（1 题）

21. **"完成"硬标准**：以下哪些必须？
    - (a) 所有列出的 e2e 全绿
    - (b) 手工跑 `QUANTIDE_ENABLE_DEV_STUBS=1 uvicorn` 实际点一遍主流程
    - (c) 飞书 change history 文档更新
    - (d) 截图对比
    - (e) git commit

---

## 你的回答（已由用户在飞书访谈 doc `JnQMdGUeSoMZ0FxP0ZLc0Y6lnbS` 评论中确认，2026-05-18 拉取归档）

> 原始 Q&A 抓取：`/tmp/qide/answers.md`、`/tmp/qide/interview_comments.json`

### A. 范围与版本

**A1 — 三件套关系：** 最终目标在「实盘」导航下保持 sidebar + main content area layout。sidebar 包含：实盘交易、账户分析、历史委托、历史成交。**本 issue 只先实现「实盘交易」功能**，其余 sidebar 项后续迭代。三件套不一次性删除，先聚焦实盘交易页重构。

**A2 — 版本号：** `0.1.1`。项目从未真正发布过，版本号仅用于内部跟踪。

**A3 — 实盘 vs 仿真：** **完全一致的 UI，仅数据源不同**。不分两套界面。

### B. 数据源与依赖

**B4 — 股票模糊匹配：** **必须复用现有函数**（去 `quantide/data/models/stocks.py` 找）。若需要新写 service 层，则**同步重构**旧实现迁移过来——同一功能不允许多个入口。

**B5 — MA5/10/20/30/60：**
- (a) **始终前复权（qfq）**
- (b) 数据不足求均线时，**显示为空**（不退化为现有天数均值）

**B6 — 昨收价：** 在功能等价前提下**以减少代码量为准**，因此用 `get_bars` 即可。
特别规则：当天收盘后若用户创建闪电单，「昨收」应等于**当天收盘价**。判定方式——读配置中的同步时间，**同步时间 + 1 小时**后即视为数据同步完成。

**B7 — 现价刷新：** (c) **WebSocket 推送**，由 `livequote` ws 推送驱动。

**B8 — AI 提示徽章（RSI / 拐头 / 前高）：** **暂不实现，也不留占位**。

### C. UI 行为细节

**C9 — Speed Dial 6×4 网格：** 点击后**仅填充价格，同时更新金额**（联动计算），**不弹 dialog，不直接下单**。

**C10 — 闪电单语义：** 点一下后**立即按事先约定的价格和数量下单**。表格中记录的是**预设单**（不是已成交单）。

**C11 — Toast：** **成功和失败都弹**，**停留 7 秒**。

**C12 — 快捷价位按钮（昨收/MA5..MA60/现价 共 7 个）：** 与 Speed Dial 同逻辑——填充价格 + 联动金额，不弹 dialog 不直接下单。

**C13 — 持仓 tab：** **没有「卖出」按钮**。**双击某一行**则跳到下单区填好默认信息（**价格默认为市价**），用户可再改价格、金额。

**C14 — 今日委托过滤 + 撤单：**
- 过滤维度：**「全部」+「可撤」两个按钮**。「可撤」= 已下单、未成交、未撤销、未出错的单。
- 需订阅成交状态更新（**走 message hub**）：收到消息时**更新委托和成交两块面板，同时发 toast**。

### D. 路由与状态管理

**D15 — 路由 `/trade/{kind}/{portfolio_id}`：** **同意采纳**。

**D16 — HTMX fragment 局部刷新 + OOB swap：** **采纳**。

**D17 — 下单后状态同步：** 三块（资产条 + 持仓 + 委托）+ **可用资金**都要刷新，便于下一次下单的金额计算。

### E. 测试策略

**E18 — e2e 覆盖范围：** (a)(b)(c)(d)(e)(f) **六项全部采纳**：下单成功 buy/sell、资金不足拒单、持仓不足拒单、撤单、MA 计算、模糊匹配命中。

**E19 — 三模式测试：** **paper 和 live 两份都要写**（live 走 `gateway_stub`）。

**E20 — 视觉/手工测试：** **不写视觉对比**。Speed Dial / Toast / Wizard 等纯交互只写**功能型测试**（断言 HTML 含正确元素）。

### F. 验收

**F21 — 完成硬标准：** (a)(b)(c)(d)(e) **全部必须**——所有 e2e 全绿、手工 `QUANTIDE_ENABLE_DEV_STUBS=1 uvicorn` 跑通主流程、飞书 change history 文档更新、截图对比、git commit。

---

## 关键派生约束（供测试计划/实现引用）

1. **单一职责**：模糊匹配若 service 层重写，必须同步迁移并下线 `data_stocks.py` 的旧调用点。
2. **数据口径**：MA、昨收一律 qfq；昨收日内切换规则依赖 `配置的同步时间 + 1h`。
3. **消息驱动**：现价用 ws 推送、成交状态走 message hub，二者均需在 UI 层注入订阅 + OOB swap。
4. **路由形状**：`/trade/` = 账号选择/无账号引导；`/trade/{kind}/{portfolio_id}` = 主交易页（kind ∈ live|simulation 共用同一模板）。
5. **持仓 tab 没有按钮**——交互入口是**双击行**，下单区价格默认填市价。
6. **闪电单与 Speed Dial 区别**：
   - Speed Dial / 快捷价位按钮：**只填表单不下单**
   - 闪电单：**点击立即按预设价格+数量下单**
7. **AI 徽章本期完全跳过**，不留任何占位元素，避免误导后续 reviewer。
