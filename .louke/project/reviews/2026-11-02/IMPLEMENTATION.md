# 实施记录

分支 `codex/ce-reliability-and-delivery`，基于原审查源码 `750614e`。
本文件记录修复后的状态；REPORT.md 保留原始审查结论。原有质量流程改动一并保留。

## 已实施

| 范围 | 行为与回归 |
| --- | --- |
| F01/F03 账户与委托 | SQLite 事务统一提交现金、成交、委托和完整持仓；显式空仓快照，恢复活动/部分成交委托、T+1 与费用；撤单落库失败不丢活动订单。 |
| F02 提交中断 | 持久化 intent 原子领取、稳定 client_order_id；Paper 和独立模拟柜台幂等提交，重启先对账，未知提交结果保留处理中。 |
| F04 历史数据 | 源错误、限频、空响应和缺失 session 向任务传播；分钟时间戳/价格覆盖验证后才写盘、清理对应内存区间；显式停牌证据单独持久化；检查历史内部缺口，不能只看最后日期。 |
| F05/F06 存储 | 数据库初始化错误保留原库；JSON/Parquet 原子替换、上一代 JSON 备份、分区索引重建、文件锁保护读合并写；实例运行锁替代只判断 PID。 |
| F07 生命周期 | wizard、数据页、每日维护共用持久化同步编排器；校验实际缺口，日终生成真实快照；重启标记 interrupted；关闭时取消并等待线程工作结束后关库，回测可在 replay 边界中断。 |
| F08 数据边界 | 供应商能力显式声明；BaoStock 默认沪深，显式北交所请求联网前拒绝；跨实例/进程共享串行会话和持久请求预算，冻结次数及冷却期跨重启保留。 |
| F09 一致性 | CE 独立 HTTP 模拟柜台及 SDK，无真实交易能力；同策略回测/Paper/柜台与人工核算结果比较，含非零费用、部分成交、重复提交、撤单和强制退出恢复。 |
| 腾讯政策 | 默认关闭；wizard 一次显式启用固定 30 天，到期请求层和发布循环停用，不能从 wizard 续期；独立扩展接口、明确启用/停用，升级保留用户代码。 |
| 安全与日期 | 删除未签名 remember_user 冒充路径；管理员写操作和 profile 更新真实权限/输入校验；统一交易所时区；非法方向、NaN/Infinity 下单拒绝。 |
| 结构重构 | runtime、Paper、Backtest、ML、策略/交易/wizard 页面按职责拆分；共享行情 schema、订单入口、风险控件、表格、账户选择和数据进度；保留旧位置参数及对外 DTO 的可变性契约。 |
| 安装与发布 | 自包含 Python/锁依赖；macOS ARM64 LaunchAgent/可选 LaunchDaemon、Ubuntu systemd、Windows WinSW；前台 Tk 控制器；CI 三平台单测与三个原生构建目标，tag 通过全部门禁后自动发布同批已验收产物。 |

## 当前证据

最终提交前本机证据目录为忽略提交的 `quality-reports/`，CI 将上传对应 artifacts。

- 生产质量扫描：Ruff/100 字符、CCR≤15、复制块≤5行、文件≤1000行、statements≤50、locals≤15 全通过；未放宽预算或新增历史豁免。
- 离线 unit：4606 passed、3 skipped；总覆盖率 84.85%。普通单测的三个 skip 不作为发布验收证据。
- CE release_gate：10 passed、276 deselected；JUnit 校验无 skip/xfail。
- 质量门禁反例：17 项全部通过。
- 真实 Tushare：2 项只读小样本通过；JUnit 校验无 skip，未输出或保存 token。
- actionlint 1.7.12、MkDocs strict、Poetry/uv 锁检查通过。
- wheel/sdist 成功构建并通过 CE 分发内容检查。三平台真实 CI 单测、质量、验收和 CI environment 的真实源验证已通过；原生安装构建/验收使用各次运行的 artifacts 记录结果。

## 安装与运行验证边界

- 本机 macOS 15.6.1 ARM64，当前量化源码原生包通过干净安装、启停、SIGKILL 自动恢复、覆盖升级、默认卸载保留数据和扩展；安装器命令链接也纳入实际启停验收。
- Windows 实机 192.168.0.103 是 Windows 10 build 19045 AMD64。自包含安装器已在实机多次通过上述安装/恢复/升级流程；每次验收与安装产物 SHA-256 绑定。
- 原生验收实际创建控制器并操作启停按钮，检查网页目标地址和关闭窗口后服务仍运行。控制器服务操作串行执行，避免停止尚未完成时启动。
- Windows 最新 CI runner 实际是 Windows Server 2025 build 26100，不能将其称为 Windows 11 桌面实机。
- CI 编译器固定为上游 Inno Setup 6.4.3，下载前后核对 SHA-256；不依赖 Chocolatey 是否收录该补丁版本。
- Ubuntu、Intel Mac 和 Windows runner 的安装结果以 PR 的真实 CI artifacts 为准，不从本机结果推断。
- macOS 系统 LaunchDaemon 尚未实测；本机没有免密 sudo。默认用户 LaunchAgent 在登录后启动，服务器无人登录场景需要系统服务。
- 尚无 Apple Developer ID/公证和 Windows 发行者签名证书。
- 多交易日无人值守、操作系统重启/断电不是进程强杀测试的同义词，尚未取得现场证据。
- mini-two 现有部署尚未替换；没有改动其当前服务和用户数据。
- GitHub 当前权限为 WRITE；维护者已建立 Active 的 `protect-main` 规则，要求 quality、三平台 tests、acceptance 和三个安装验收共八项通过，且分支与默认分支保持最新。禁止强推和删除，合并需经过 PR。

## 使用入口

- 最终用户：[原生安装](../../../../docs/native-installation.md)、[行情扩展](../../../../docs/quote-extensions.md)。
- Millionaire/开发者：[模拟柜台与 SDK](../../../../docs/simulated-counter.md)。
- 固定门禁和发布流程：[quality.md](../../../../docs/quality.md)。

现有 MyPy pre-commit 钩子在全仓检查时被命名空间目录的同名模块冲突阻断，
尚未形成可用的全仓类型检查证据。它不是本次约定的六项结构预算或发布门禁，
未通过修改类型规则来掩盖；生产质量扫描仍必须全通过。

补充资源清理：主 SQLite 库在工作线程停止后关闭全部连接；认证库在重绑定和应用退出时关闭，支持重新打开；TrackingStore 每次读写同时结束事务和连接，异常退出也会回滚并关库。新增 Windows 可重命名/删除数据库文件的回归。

PR：https://github.com/zillionare/millionaire-ce/pull/1 。发布 workflow 支持手工完整预检；手工运行不发布，匹配包版本的 v* tag 才会自动创建 GitHub Release。当前尚未创建发布 tag，mini-two 的部署保持原状。

最终本机回归为 4606 passed / 3 skipped、覆盖率 84.85%；严格 release_gate 10 passed 无 skip/xfail，质量反例 17 项通过。关闭流程先暂停调度，再取消并等待运行中的维护/策略/优化任务，最后关闭存储；系统服务超时强制退出仍由操作系统监督，原子事务用于异常退出后的恢复。

## 支持范围与文档后续约定

维护者决定 macOS 仅支持 Apple Silicon（ARM64）。安装 matrix 已移除 `macos-x86_64`，
发布流水线复用该 matrix，因此本次变更后的版本不再构建、验收或发布 Intel 安装包。
此前 Intel 安装验收属于历史证据，不作为继续支持的声明；原生安装和质量文档已同步。

最终用户手册尚未达到正式发布标准，具体内容规划、功能表述边界与验收要求见
[文档规划](DOCUMENTATION-PLAN.md)。该规划不代表相应用户手册已经完成。

后续已编写中文用户手册首稿与下一版审计/收益归因规格，并修复 Windows 服务停止
未完成即启动的竞态。本轮验证与尚未完成的文档发布验收见[文档实施记录](DOCUMENTATION.md)。
前文的 4606 单测数是此前实施证据；本轮为 4615 passed / 3 skipped、覆盖率 84.51%。
