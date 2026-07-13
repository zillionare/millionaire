# Millionaire Coverage Recovery — Acceptance Criteria

- **Spec ID**: v0.2-004-coverage-recovery
- **创建日期**: 2026-07-13
- **对应 spec**: [spec.md](./spec.md)

编号策略：每节使用纯 `### AC-N` 标题；下一行的 `AC-FRXXXX-YY` / `AC-NFRXXXX-YY` 是唯一规范 ID。v0.2-004 使用 1001 以上的 FR/NFR 号，避免与上游 AC ID 碰撞。所有跨 spec 引用必须带 spec-id。

## 169 文件规范映射

规范路径集合 `P` 由 SHA-256 `dea992b446a352d7f48253af03cc6f472d632a661c9d68bfd771cf729a079dd4` 的 `recovery/production-file-inventory.json` 按 shard manifest SHA-256 `56ee03f245e931478fc2d6ca5f1e8e6cacdb79813a7d70ae466a01961d710616` 加载并校验全部 13 个 production-contract shards 后重建，得到 169 个唯一 path；index 单独不是合同。每条行为合同再应用 `recovery/sage-semantic-review.md` 的 160 条记录修正规则及上游优先级。对每个 `p ∈ P`，机器可验证的 outlet 为：

- manifest/classification：FR-1001 AC-1~3、FR-1101 AC-1~3；
- behavior：FR-1201 AC-1~7，加上该行 `governing_upstream_references` 指向的最高优先级上游 AC；`existing_003_spec_ac_coverage=none` 的 retained 路径还必须命中 spec.md FR-1201 的同路径文件特定条目；
- tests/remediation/closure：FR-1301 AC-1~4、FR-1401 AC-1~3、FR-1601 AC-1~4、FR-1701 AC-1~3；
- coverage/evidence：FR-1901 AC-1~3、NFR-1001 AC-1~4、NFR-1101 AC-1~3、NFR-1201 AC-1~3、NFR-1301 AC-1~2；
- `aaron_decision_candidate != null`：还必须命中 FR-1501 AC-1~3；合法 waiver（如最终存在）还必须命中 FR-1801 AC-1~4。

因此映射不是抽样：每个 inventory row 都通过 path 主键映射到本 spec 的 FR/NFR 与 AC outlet。任何路径未命中上述规则均使 FR-1001 AC-3 失败。

## FR-1001 完整生产源码清单与等式门禁

### AC-1
AC-FR1001-01

- 对同一 revision 分别枚举 `quantide/**/*.py`、inventory `inventory[*].path` 和 coverage manifest；三个规范化路径集合完全相等，且计数相同。

### AC-2
AC-FR1001-02

- 当前 production index hash 精确为 `dea992b446a352d7f48253af03cc6f472d632a661c9d68bfd771cf729a079dd4`，shard manifest hash 精确为 `56ee03f245e931478fc2d6ca5f1e8e6cacdb79813a7d70ae466a01961d710616`；13 shards 重建 169 个唯一 path。任一 hash、shard 内容或计数变化时验收失败并要求 review 新版本。

### AC-3
AC-FR1001-03

- 对 169 行逐行执行“169 文件规范映射”，输出 169 条非空 outlet 记录；0 个未映射、重复或额外路径。

### AC-4
AC-FR1001-04

- 0-statement 文件保留在 disk/inventory/manifest 等式报告中但标记 `threshold_not_applicable`；含 import/re-export statement 的文件不被当作 0-statement。

## FR-1101 逐文件分类与决定权限

### AC-1
AC-FR1101-01

- 每个 pre-v0.2 inventory row 精确含一个允许分类、git 来源、消费方/路由/registry 证据、上游引用和 classification basis；缺任一字段即失败。

### AC-2
AC-FR1101-02

- 分类汇总与逐行重算一致：35 v0.2 product、127 retained legacy、5 deprecated candidate、1 dead candidate、1 marker/schema-only，总计 169。

### AC-3
AC-FR1101-03

- 所有 inference-based deprecated/dead/duplicate 候选在 Aaron 决定前仍出现在 manifest 和 blocker matrix；没有被自动删除、跳过或自动 waiver。

### AC-4
AC-FR1101-04

- marker/schema-only 测试只断言声明的 schema/marker/re-export；若出现新 CRUD/序列化/状态机期望，必须有更高优先级合同，否则验收失败。

## FR-1201 逐文件合同推导与缺口补齐

### AC-1
AC-FR1201-01

- 每个 retained/v0.2-added path 的合同记录列出公开符号或路由、输入、输出、失败/边界和最高优先级来源；不存在只有“preserve behavior”而无这些字段的记录。

### AC-2
AC-FR1201-02

- 构造一个高优先级合同与实现冲突样本，归因为 `implementation-defect`；构造一个旧测试与合同冲突样本，归因为 `test-defect`；系统不得反向修改合同以让现状通过。

### AC-3
AC-FR1201-03

- inventory 中 104 个 full、54 个 partial、11 个 none 状态逐行均有行为出口；9 个不等待 Aaron 的 none 路径逐一命中 spec.md FR-1201 的同路径输入/输出/失败语义。

### AC-4
AC-FR1201-04

- AD-01/AD-02 的遗留注册/reset 功能在 Aaron 决定前不被测试提升为 v0.2 产品成功路径；若保留，只能按批准后的 characterization/产品决定验收。

### AC-5
AC-FR1201-05

- 对 partial 路径逐一比较公开表面与上游 AC；每个未覆盖行为产生 `spec-gap` 或明确补充合同，不得以达到 coverage 百分比代替语义闭合。

### AC-6
AC-FR1201-06

- 重建器必须读取 index 声明的全部 13 shards，逐个验证 shard hash/record count/record id/path 唯一性和 manifest hash，得到恰好 169 条；只读取 index、缺任一 shard 或产生重复/缺失 path 均失败。

### AC-7
AC-FR1201-07

- 对 169 条逐行应用 Sage 语义复核：恰好 160 条剔除非显式 re-export 的 imported dependency surface、恢复源码签名并禁止 AST 表达式发明行为，9 条无需修正；每条修正后仍含 path-specific input/boundary、observable output、failure/fallback、state/cleanup 和 precedence source。抽出任一 imported dependency 当公共 API 或任一 mangled signature 时验收失败。

## FR-1301 现有测试逐项复核与缺陷归因

### AC-1
AC-FR1301-01

- 每个 retained/v0.2-added path 都有测试复核记录，包含 test references、合同来源及 missing/conflicting/incomplete/self-fulfilling/import-only/order-dependent/failing 标记。

### AC-2
AC-FR1301-02

- 任一上述缺陷标记均对应至少一个未关闭 Devon work item；不存在以静态 `aligned` 或“issue 已做”跳过运行验证的记录。

### AC-3
AC-FR1301-03

- 自动/人工审查确认 expected value 不调用被测主体，mock 不替换被测主体，且每个 mock 边界的输入或输出被断言。

### AC-4
AC-FR1301-04

- 每条 mismatch 精确归入 `test-defect|implementation-defect|spec-gap|dead-or-marker` 并引用优先级证据；空归因或多重无结论归因阻断。

### AC-5
AC-FR1301-05

- trace 中原 179 个 `update` 函数逐条产生 open M-DEV work：85 incomplete、52 self-fulfilling、41 import-only、1 fake；work item 含 function id、质量证据、目标 AC、修复或五证据删除候选出口。任一 generic “update later” 或缺 work item 均阻断。

## FR-1401 生产修复、测试修复与重复测量

### AC-1
AC-FR1401-01

- diff 中每项生产修改可追到 implementation-defect/批准处置，每项测试修改可追到 AC/test-defect；不存在为覆盖数字新增业务语义的修改。

### AC-2
AC-FR1401-02

- 每轮修复后执行完整规范 unit invocation 与逐文件 gate，并将该 revision 的结果写回 closure matrix；只运行子集不能把条目标为 closed。

### AC-3
AC-FR1401-03

- 当 issue 列表为空但矩阵仍含任一 blocker 时，stage 保持 FAIL 并生成后续任务。

## FR-1501 Aaron 六项待决处置

### AC-1
AC-FR1501-01

- AD-01~AD-06 每项均有 Aaron 的显式 disposition、日期、证据和适用合同/后续 issue；缺一项即 closure blocker 非零。

### AC-2
AC-FR1501-02

- 选择 delete 时附消费者/路由复核与独立删除 review；选择 retain 时有文件特定合同并达到 80%；选择 waiver 时通过 FR-1801 全部校验。

### AC-3
AC-FR1501-03

- 在 Aaron 显式决定前，六项均保持 pending，未被 acceptance、inventory 或 waiver 文件解释成已接受 disposition。

## FR-1601 完整测试树反向追踪与删除标准

### AC-1
AC-FR1601-01

- 扫描完整 `tests/**/*.py` 得到与复核 revision 一致的模块/函数清单；当前 test index SHA-256 为 `02d1ff2e51d4ca7d824e04f06cfa17b33c7b7737554e5e4841667e644c4e002a`、11-shard manifest SHA-256 为 `f8305dfdc251d1d15fb934fd981966ed336419af7ac9fb56e0d4ab2eab9fa07f`，重建 240 模块、1651 test functions；只读 index、缺 shard 或任何未解释变化均失败。

### AC-2
AC-FR1601-02

- 每个 test function/method 至少有一个带 spec-id 的有效 AC，且每个 in-scope AC 至少有一个实质测试；双向 orphan 数均为 0。

### AC-3
AC-FR1601-03

- fixture/helper 映射到至少一个消费测试或明确标记 non-test helper；文件名、目录名或 import 本身不能充当 AC 映射。

### AC-4
AC-FR1601-04

- 每个 delete 建议同时具备无有效 AC、无独立回归价值、无消费者、必要的 Aaron 生产处置和独立 review 五项证据；任一缺失则只能 keep/update。

### AC-5
AC-FR1601-05

- 对原 57 个 `needs-Sage-contract` function id 应用 Sage 覆盖层后，结果精确为 40 `aligned`（每条至少一个 spec-qualified ref）和 17 `update`（每条有具体 mismatch、目标 AC 或 spec-gap、未来 Devon 工作）；剩余 `needs-Sage-contract=0`，不得以模块级或 generic mapping 替代。

### AC-6
AC-FR1601-06

- 合并 Sage disposition 后，trace 为 1455 aligned、196 update、0 needs-Sage-contract；196 update 全部绑定 open M-DEV work，且零 empty-ref function 被计为 aligned/keep。17 个新增 update 与原 179 个 update 都不授权删除。

### AC-7
AC-FR1601-07

- 六项 Aaron decision 仍为 pending；任何 trace overlay、update/delete candidate 或生产合同语义复核均不得把 AD-01~AD-06 解释为 delete/retain/waiver 决定。

## FR-1701 剩余矩阵驱动的迭代闭合

### AC-1
AC-FR1701-01

- closure matrix 每行含 path、classification、contract outlet、test status、coverage actual/target、waiver、decision 和 blocker reason；169 个生产 path 全部出现。

### AC-2
AC-FR1701-02

- 每轮将 below-target、failed/error、manifest mismatch、双向 orphan、未决 Aaron、无效 waiver 的并集生成下一轮任务，且每个 blocker 至少映射一项任务。

### AC-3
AC-FR1701-03

- 最终矩阵重算后上述 blocker 各类别均为 0；任一非零时不得报告 closure。

## FR-1801 文件特定临时 waiver 机制

### AC-1
AC-FR1801-01

- 初始 `coverage-waivers.json` 通过版本化 schema 校验且 `waivers=[]`；不存在隐式、通用或预批准 waiver。

### AC-2
AC-FR1801-02

- synthetic pre-v0.2 waiver 只有在 module/current_coverage/reason/evidence/approved_by/approved_at/expires_at/followup_issue 完整、approved_by 为 Aaron、未过期且 path 唯一存在时才有效。

### AC-3
AC-FR1801-03

- 缺字段、过期、未知/重复 path、无 follow-up issue 或非 Aaron 批准均使 gate FAIL 并输出具体 module/reason。

### AC-4
AC-FR1801-04

- 任一 v0.2-added path 的 waiver 记录均被拒绝；`--force` 或 generic waiver 参数不存在可将其放行的执行路径。

## FR-1901 二进制退出证据

### AC-1
AC-FR1901-01

- 单一 stage verdict 仅在 pytest exit 0、0 failed/errors、overall >95、manifest equality、所有逐文件 target、waiver validation、双向 trace、六项 Aaron 决定及 blockers=0 同时成立时为 PASS。

### AC-2
AC-FR1901-02

- 注入任一失败信号后 verdict 为 FAIL，并列出对应信号；没有 `--force`、generic waiver 或 closed-issue count 覆盖结果。

### AC-3
AC-FR1901-03

- failing pytest invocation 产生的 coverage artifact 标为 diagnostic 且不参与 overall/per-file acceptance，即使其中百分比超过阈值。

## NFR-1001 覆盖率阈值不可降级

### AC-1
AC-NFR1001-01

- 同一全绿 unit invocation 的 coverage JSON 显示 `totals.percent_covered > 95.0`；等于 95.0 不满足“>95%”。

### AC-2
AC-NFR1001-02

- 35 个 v0.2-added path 中每个 `num_statements>0` 文件均 `percent_covered >=95.0`，无 waiver；当前诊断中的 4 个 below-95 路径必须清零。

### AC-3
AC-NFR1001-03

- 每个 retained pre-v0.2 且 `num_statements>0` 路径均 `percent_covered >=80.0`，或命中唯一合法未过期 Aaron waiver；无记录路径不得跳过。

### AC-4
AC-NFR1001-04

- 0-statement 路径只跳过百分比比较，仍通过 FR-1001 manifest equality、FR-1101 分类与 FR-1201 合同 outlet。

## NFR-1101 有意义测试与反作弊

### AC-1
AC-NFR1101-01

- 每个恢复覆盖的 path 至少有正常路径和适用失败/边界路径，且断言输出、状态、持久化、异常或边界调用之一。

### AC-2
AC-NFR1101-02

- 静态与 diff 审查均未发现 `assert True`、空 `pass` 测试、import-only 冒充行为覆盖、self-fulfilling expected、mock 被测主体或无断言 mock。

### AC-3
AC-NFR1101-03

- 与基线比较未扩大生产 omit/exclude、未批量新增 `pragma: no cover`、未降低阈值、未无依据删除有效生产逻辑。

## NFR-1201 全绿、隔离、确定性与资源清理

### AC-1
AC-NFR1201-01

- 完整 unit suite 在隔离临时 HOME/config/data 且禁止真实网络、网关、SMTP、Tushare 的环境中 exit 0、0 failed、0 errors。

### AC-2
AC-NFR1201-02

- 完整 suite 连续运行及变序运行的 pass/fail/skip、statements/covered totals 一致；代表性测试单独运行结果一致。

### AC-3
AC-NFR1201-03

- suite 后无 pending task、存活 worker/scheduler、未关闭 client/websocket/database 或仓库测试残留文件。

## NFR-1301 证据可重放与不可替代性

### AC-1
AC-NFR1301-01

- exit evidence 包含 commit SHA、命令、环境/Python、pytest summary、coverage JSON/hash、manifest/hash、逐文件报告、waiver validation、trace matrix/hash 和 closure summary，字段均非空且 revision 一致。

### AC-2
AC-NFR1301-02

- 从记录 revision 和规范命令可独立重放得到相同二进制 verdict；删除任一必需信号时验证器返回 FAIL。

## No Acceptance

- US-1001、US-1101、US-1201 由上述 FR/NFR 验收，不设独立 AC 节。
