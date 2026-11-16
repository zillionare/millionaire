# 初始化数据源流程与权限检测

日期：2026-11-03。针对用户安装验收反馈的实施记录，不是正式 Release 声明。

## 用户流程

保持六步：欢迎 → 运行环境 → 管理员密码 → 数据源配置/权限检测 →
实时行情配置（条件跳过）→ 数据准备与完成。

- 第 4 步“检测并继续”只读少量样本，不启动批量历史下载。
- 第 5 步使用“实时行情”，不向用户介绍 MarketDataHub 等内部组件。
- CE 检测到可接入的 Tushare `rt_k` 时自动选用，并跳过第 5 步；返回时直接回第 4 步。
- 无可用实时源可选择一次 30 天腾讯演示、已有行情扩展，或暂不启用，仅研究回测。
- 第 6 步显示摘要，用户明确点击“开始下载历史数据”；失败关闭进度弹窗后仍保留重试入口。
- 新安装在历史同步成功前不能通过完成接口跳过数据准备。开发 stub 使用内置样本路径。
- 已运行服务更换实时源需重启；本版未实现热切换。

## 权限与实时合同

必需检查为 trade_cal、stock_basic、daily、adj_factor、stk_limit、stock_st、daily_basic、
index_daily、index_weight。不静默省略 ST 和历史涨跌停。实际接口明确拒绝授权时提示
到 Tushare 权限中心升级积分或开通对应权限；不硬编码付费金额或账号级别。
网络错误、限频、密钥无效、空样本、字段缺失单独报告，空样本不能推断必须付费。

探测最多 11 个小样本请求，单次 SDK timeout 5 秒、并发最多 3；报告绑定 token 摘要、
历史源及首次下载起点，缓存 15 分钟。手动再次点击检测会强制刷新，同一 token 升级后可重检。
探测使用显式 SDK token，不调用 set_token，不回显原始异常或密钥。原有历史抓取器的
SDK token 持久化行为未在本次重构，不能据此声称整个历史导入没有 SDK token 文件写入。

新增官方 `rt_k` 股票快照发布者，每 60 秒读取订阅；交易日和时段外不轮询，无订阅不请求。
要求同日实际限价、完整源时间戳和有效价格/昨收，拒绝超过 150 秒或未来超过 5 秒报价。
股/元转换为标准的手/千元。停止期间到达的请求结果不再发布，次日不复用昨日限价。
初始化样本检查只确认权限、字段和价格样本，持续时效与完整覆盖不在该结论范围内。

rt_k 与 rt_min 是独立权限；本版对 rt_min 只检测，不自动装配分钟 adapter。
只有分钟权限的用户可使用扩展，不要求为框架额外购买快照权限。指数实时尚未接入。
pre_close 必须结合历史原始收盘与历史因子，不能独自代替完整复权因子。

官方合同参考：

- https://tushare.pro/document/2?doc_id=372 （rt_k）
- https://tushare.pro/document/2?doc_id=374 （rt_min）
- https://tushare.pro/document/2?doc_id=183 （stk_limit）
- https://tushare.pro/document/2?doc_id=397 （stock_st）
- https://tushare.pro/document/2?doc_id=28 （adj_factor）

多源组合、能力矩阵、分钟/指数适配和安全热切换已规划到
`.louke/project/specs/v0.4-002-data-sources/story.md`。

## 验证与边界

产物位于 `/tmp/millionaire-ce/wizard-data-source/`：

- `regression.xml`：249 项现有向导回归通过。
- `related.xml`：109 项实时发布、数据权限、扩展与 Runtime 等关联测试通过。
- `final-wizard.xml`：41 项最终向导、页面及离线完整导入测试通过。
- `unit.xml` / `coverage.xml`：4,691 项通过，3 项既有 skip，覆盖率 84.13%，80% 门禁通过。
- `acceptance.xml`：16 项 CE 发布验收，全通过，无 skip/xfail，JUnit 校验通过。
- `quality.json`：全生产代码 lint、认知复杂度、重复和规模预算全部通过。
- `site/`：严格 MkDocs 构建通过；wheel/sdist 通过 CE 内容校验。
- `live-access.json`：环境 token 的真实小样本。首次 daily 连接异常，重试后九个必需
  历史接口全部通过；rt_k 明确权限不足，rt_min 权限通过。未抓全市场、未下单。

全量回归额外发现旧页面测试启动真实补数；已将该页面测试的维护函数隔离，
不靠外网请求或延长测试超时放行。已有单测的 private skip 不属于 release_gate 验收。

## 最终本地 macOS 验收包

`/tmp/millionaire-ce/wizard-data-source/installers/millionaire-ce-0.3.0-macos-arm64.tar.gz`

SHA-256：`e0a68f10a17a3f13166a6a13afda54553fc84fe6fa250ed25852c6008be39025`。

最终 wheel 与当前 Python/静态资源逐字节一致；已重新打包并对该 hash 的安装包执行
完整原生验收。`native-acceptance/verified.json` 验证 macOS 菜单、启停、退出控件后服务
PID 保持不变、服务重启、异常退出恢复、升级、卸载保留数据及用户扩展。
验收临时服务已卸载。本次没有重新跑 Windows/Ubuntu 实机安装，不借用前序证据
宣称其当前包已更新；本次未推送、创建 tag 或发布。
