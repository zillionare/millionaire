# Millionaire Coverage Recovery — Spec

- **Spec ID**: v0.2-004-coverage-recovery
- **创建日期**: 2026-07-13
- **状态**: 草稿（AD-01~AD-06 已由 Aaron 决定 RETAIN；待产品方 IDE review）
- **Story**: [story.md](./story.md)
- **Acceptance**: [acceptance.md](./acceptance.md)
- **继承合同**: [v0.2-003-coverage](../v0.2-003-coverage/)

本文是新的 recovery spec，不重开或改写 v0.2-003。v0.2-003 的 DoD、契约判定优先级、测试隔离、反作弊和同次全绿运行证据继续有效；本 spec 增加完整源码分类、逐文件合同闭合、全测试树反向追踪和迭代清零流程。

## 编号与规范引用

- v0.2-004 新增 FR 使用 `FR-1001` 至 `FR-1901`，NFR 使用 `NFR-1001` 至 `NFR-1301`；这些编号不与 v0.2-001/002/003 的编号碰撞。
- `acceptance.md` 的标题保持 Louke 要求的纯 `### AC-N`；下一行写唯一规范 ID `AC-FR1001-01` 或 `AC-NFR1001-01`。
- 上游引用必须带 spec-id，例如 `v0.2-003 FR-0503 / AC-FR0503-01`。无 spec-id 的裸 `FR-XXXX` 不能用于跨 spec 追踪。

## 规范证据与固定清单

以下审计产物是需求输入而不是 DoD 通过证据：

- 生产合同 index：`recovery/production-file-inventory.json`，SHA-256 `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe`；其 13 个 `recovery/production-contracts/*.json` shard 的 manifest SHA-256 为 `4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39`，重建 169 条唯一、源码落地的 path 记录。
- 169 条逐路径合同的规范正文就是上述经 hash 固定的 corrected shards 中各行 `normative_contract`；必须由 index 声明的 shard path/hash/count 加载全部 13 个 shard 后重建，不能从 index、通用模板或 overlay 单独推断。重建结果必须为 169 source-grounded、0 pseudo-import APIs、0 mangled signatures、0 missing anchors；缺 shard、hash/count 不符或任一记录退化均阻断。
- 生产语义复核：`recovery/sage-semantic-review.md`。其中记录 55 个新增候选的逐项 precedence disposition；55 项全部由锁定证据闭合，未新增 Aaron 产品决定。它不替代 corrected shard 的逐路径合同正文。
- 测试追踪 index：`recovery/test-trace-data.json`，SHA-256 `3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0`；其 11 个 `recovery/test-trace/*.json` shard 的 manifest SHA-256 为 `f48b15e808737352ad6a5c4d8da2b2a5f9b97fa3fb56a4ca2881463ec2380352`，重建 240 个测试模块、1651 个测试函数，最终 disposition 为 1455 aligned、196 update、0 needs-Sage-contract。
- M-DEV work registry：`recovery/devon-work-items.json`，SHA-256 `bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088`。它是规范 M-DEV 输入：196 个 open `RW-*` work item 与 196 个 update function 一一绑定，不是可选 planning artifact。
- 诊断闭合矩阵：`recovery/coverage-closure.json`；其中失败运行得到的 65.53% 只能定位工作，不能验收。

若 index、任一 shard 或 manifest 与上述 hash 不同，本 spec 的映射失效并阻断验收；不得静默改用新清单。后续源码增删必须生成新的、经 review 的版本化 index+shards 并同步更新本 spec/acceptance 的固定 hash 与计数。

## 用户故事

### US-1001

作为发布维护者，我需要每个生产 Python 文件都有分类、行为合同、AC 出口和覆盖率目标，以免文件因未被 import 或未被文档提及而落到门禁之外。

### US-1101

作为开发者，我需要按锁定合同区分测试缺陷与实现缺陷，并持续从剩余闭合矩阵产生工作，直到 DoD 真正满足。

### US-1201

作为评审者，我需要每个测试反向追到有效 AC，且任何删除建议都有独立证据和 Aaron 审批。

## 范围与边界

在范围内：生产代码修复；测试修复、新增和经审批后的删除；完整 `tests/` 树审计；规范全量 unit suite；覆盖率重复测量；逐文件门禁；必要的测试/coverage 检查工具与 CI 修复；剩余 blocker 的迭代任务生成。

不在范围内：新增业务功能；降低 v0.2-003 合同或阈值；把失败 suite 的 coverage 当验收；未经 Aaron 决定删除/废弃生产文件或批准 waiver；用 `--force`、通用 waiver、`continue-on-error`、omit/exclude 或批量 `pragma: no cover` 替代 DoD。

## 功能需求

### FR-1001 完整生产源码清单与等式门禁

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 验收时从工作树枚举全部 `quantide/**/*.py`，包括 0-statement、marker、`__init__.py` 和未被 import 的文件。
- 磁盘路径集合、固定/复核后的 inventory 路径集合、coverage manifest 路径集合必须相等；0-statement 文件可在阈值计算中跳过，但不能从磁盘或 inventory 清单消失。
- coverage 工具没有产生记录的可执行文件视为 blocker，而不是 0% 的可豁免缺省值。
- 固定清单中的全部 169 路径共同映射到本 FR、FR-1101、FR-1201、FR-1301、FR-1401、FR-1701、FR-1901 及 NFR-1001/1101/1201；`acceptance.md` 的规范映射规则给出逐行 AC 出口。

---

### FR-1101 逐文件分类与决定权限

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 每个 pre-v0.2 路径必须且只能分类为 `deprecated`、`duplicate`、`retained`、`dead-candidate` 或 `marker/schema-only`，并记录 git 来源、消费方/路由/registry 搜索、上游引用与分类证据。
- v0.2-added 文件单独标为 `v0.2-added`；固定清单当前为 35 个 v0.2 product、127 个 retained legacy、5 个 deprecated candidate、1 个 dead candidate、1 个 marker/schema-only。
- 审计中的 `inference` 不是产品决定。`deprecated`、`duplicate`、`dead-candidate` 的最终处置以及任何 waiver 仅由 Aaron 决定；AD-01~AD-06 已决定 RETAIN，六个文件继续保留在 manifest、合同和门禁内，且没有 waiver。
- `marker/schema-only` 只保护公开 marker/schema/re-export 语义，不虚构 CRUD、序列化或状态机。

---

### FR-1201 逐文件合同推导与缺口补齐

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

每个保留文件按以下唯一优先级确定合同：

1. 已锁定 spec/acceptance；
2. interfaces；
3. story；
4. 当前公开实现与真实生产消费方。

高优先级与实现冲突为 `implementation-defect`；旧测试与高优先级冲突为 `test-defect`。只有 1~3 未规定时，才能用第 4 项形成兼容/characterization 合同。私有且无消费者的行为不得升级为产品语义。

固定 corrected shards 每行的 `governing_upstream_references` 是该路径到上游 FR 域的机器可读绑定。169 条路径合同的规范内容是 shard 自身的 path-specific `normative_contract` 字段，并继续受 v0.2-001/002/003 优先级约束；index、通用 overlay 或“preserve behavior”模板都不是行为合同。每行必须保留真实公开符号/路由、源码签名、输入/边界、可观察输出、失败/回退、状态/清理和 precedence source；导入依赖不因 AST 可见而成为公共 API。`existing_003_spec_ac_coverage=full|partial` 时仍须逐文件验证公开符号、输入、输出和失败/边界是否被 AC 实际覆盖。

> **Lex** [RESOLVED]: BLOCKER (Aaron requirement 3 / 169-path outlet): The claimed per-row behavior outlet is not sufficient for 160 paths. `recovery/proposed-requirements.md` gives those paths the generic template “preserves public behavior governed by FR-…; assert a normal and failure/boundary path”, while inventory rows only bind broad FR domains. That neither names each file’s public behavior nor specifies its input, output, and failure/edge result; it is explicitly disallowed as a generic preservation outlet. Add a normative, path-keyed contract record for every retained/v0.2-added path (or precise upstream AC references that demonstrably cover that path), with observable input/output/failure semantics and precedence source. Keep the 9 existing file-specific entries, but close the remaining rows without inventing semantics.
>> **Sage**: Remediated at spec.md “规范证据与固定清单” and FR-1201, acceptance.md “169 文件规范映射” plus AC-FR1001-02/03 and AC-FR1201-01/03/05/06/07, and recovery/sage-semantic-review.md. The production index SHA is dea992b446a352d7f48253af03cc6f472d632a661c9d68bfd771cf729a079dd4 and the 13-shard manifest SHA is 56ee03f245e931478fc2d6ca5f1e8e6cacdb79813a7d70ae466a01961d710616; index+all shards reconstruct 169/169 path-keyed records. I semantically reviewed all 13 shards: 9 hand-written records stand and 160 generated records are normatively corrected so imported dependencies are not public API, source signatures replace mangled text, generated expressions cannot invent behavior, and locked v0.2-001/002/003 sources retain precedence. Every reconstructed record must still expose path-specific input/boundary, observable output, failure/fallback, state/cleanup and source. Please re-review; I have not resolved your thread.
>>> **Sage**: Final source-grounded remediation is normative at spec.md §规范证据与固定清单 and §FR-1201, acceptance.md §169 文件规范映射 plus AC-FR1001-02/03 and AC-FR1201-01/03/05/06/07, and recovery/sage-semantic-review.md §Additional 55-candidate resolution table. Production index SHA `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe` plus 13-shard manifest SHA `4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39` reconstruct exactly 169 disk-path contracts directly from corrected shard rows: 169 source-grounded, 0 pseudo-import APIs, 0 mangled signatures, 0 missing anchors. Each shard row itself supplies path-specific surface/signature/input/output/failure/state/source; no generic overlay is needed or allowed. All 55 additional semantic candidates are dispositioned (33 spec, 16 interfaces, 0 story, 1 consumer, 5 current compatibility, 0 promoted); AD-01..AD-06 remain pending. Please re-review; I have not resolved this Lex-owned thread.


对固定清单中 `existing_003_spec_ac_coverage=none` 且不等待 Aaron 处置的 9 个 retained 路径，补充以下文件特定兼容合同：

- `quantide/notify/__init__.py`：代码输入转换为 SH/SZ/BJ 与 hson/xt/jq 格式；300/688 使用 ±20% 涨跌停，其余 ±10%；`open_time_delta` 按公开时段映射分钟数，未知时段返回 0。
- `quantide/web/middleware_init.py`：公开 health/static/wizard 路径放行；未初始化 GET 重定向 wizard、非 GET 返回可判定 503；已初始化且未带 force 重进 wizard 时 GET 重定向根路径、非 GET 返回 403；状态检查异常不得泄露凭证或使请求进程崩溃。
- `quantide/web/pages/data_calendar.py`：overview 输出 epoch/end/path；calendar 输入 year/month 并区分交易日/休市日；更新调用 calendar 边界并分别输出成功或错误 fragment。
- `quantide/web/pages/data_db.py`：输入 tab/table/page；只允许已枚举表，按 20 行分页输出列和值，空表输出空态，schema 输出列名/type/主键，读取失败输出局部错误而非整页崩溃。
- `quantide/web/pages/data_market.py`：overview 输出日线范围、天数、大小和 stale 状态；browse 输入 asset/start/end，最多倒序输出 100 行约定行情列并区分空/错误；update 校验 ISO 日期、发布可观察 progress/completed/error SSE 状态，并在结束时解除消息订阅。
- `quantide/web/pages/data_stocks.py`：overview 输出数量/更新时间/path；search 输入代码、名称或拼音并最多输出 100 行，区分空/错误；update 输出可观察 progress/completed/error SSE 状态。
- `quantide/web/pages/history_orders.py`：无活动账户输出选择提示；有效日期/账户查询只返回该账户订单，公开列为时间、资产、名称、方向、委托价/量、成交量、状态；空/查询失败产生稳定空态且不得串账户。
- `quantide/web/pages/history_positions.py`：无活动账户输出选择提示；有效日期闭区间与账户查询输出持仓列，市值、盈亏和盈亏率由 shares/cost/current 独立公式确定，零成本盈亏率为 0；registry 缺失时账户名回退 account id。
- `quantide/web/pages/history_trades.py`：无活动账户输出选择提示；有效日期/账户查询只返回该账户成交，公开列为时间、资产、名称、方向、成交价/量/金额/手续费；空/查询失败产生稳定空态且不得串账户。

`quantide/web/auth/admin_routes.py` 与 `quantide/web/auth/forms.py` 属于已决定 RETAIN 的 AD-01/AD-02；测试按 corrected shard 的当前实现刻画遗留注册/重置行为，不把它提升为新的 v0.2 产品成功路径。

---

### FR-1301 现有测试逐项复核与缺陷归因

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 对每个 retained 或 v0.2-added 文件，将已有测试与 FR-1201 得到的合同逐项比较。
- missing、conflicting、incomplete、self-fulfilling、import-only、order-dependent 或 failing 测试均进入 Devon 工作；不得把静态审计的 `aligned` 当成运行通过。
- 测试期望必须来自锁定值、独立 fixture、公式、schema 或真实消费方合同；不得调用被测主体生成 expected value，也不得 mock 被测主体。
- 归因记录至少含 path、public behavior、source reference、test references、observed mismatch 与 `test-defect|implementation-defect|spec-gap|dead-or-marker`。
- 最终 trace 的 196 个 `update` 函数全部是规范 M-DEV 工作：87 `incomplete`、61 `self-fulfilling`、41 `import-only`、3 `fake`、2 `conflicting`、2 `spec-gap`。每条保留 function id/evidence/target refs，并在固定 `devon-work-items.json` 中恰好绑定一个 open `RW-*` work item。

---

### FR-1401 生产修复、测试修复与重复测量

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 可以并要求为合同不符修复生产代码，为错误/缺失合同保护修复或新增测试，并在 Aaron 审批及独立 review 后删除无效测试或生产文件。
- 每轮变更后运行规范完整 unit suite 和逐文件检查，更新闭合矩阵；不得只运行新增测试后宣称 DoD。
- `devon-work-items.json` 是 M-DEV 的规范输入。每个 `RW-*` 只有在记录 AC-derived Red、修复后的 Green、同 revision 完整 suite/逐文件 gate 证据后才能关闭；或由一个双向可追踪、承接相同 function id/AC/evidence obligations 的 replacement work item supersede。
- issue 列表完成或关闭数不是 DoD；任一未闭合/未合法 supersede 的 `RW-*`、failed/error、manifest 差异、孤儿测试、未满足的 RETAIN 证据义务或 below-target 路径都继续阻断。

---

### FR-1501 Aaron 六项 RETAIN 处置

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

Aaron 于 2026-07-13 明确将 AD-01~AD-06 全部决定为 **RETAIN**。六个 legacy 文件保持在 production manifest、逐路径合同和逐文件 coverage gate 中；不删除、不批准 waiver、不改变生产行为。测试新增遵循 corrected shard 记录的当前实现合同，而非发明行为；每项均要求 AC-derived Red、对同一行为的隔离确定性 Green、同 revision 使用 `--timeout` 的完整 suite 全绿，以及逐文件 `percent_covered >=80.0`。禁止 coverage tricks、扩大 omit/exclude 或 broad exclusions。

- AD-01 `quantide/web/auth/admin_routes.py`：FR-0504 排除遗留多用户 admin registration route。

> **Sage** [RESOLVED]: @Aaron 请明确选择：删除（经消费方/路由复核）、保留并按合同测试至 ≥80%，或批准一条有到期版本和 follow-up issue 的文件特定临时 waiver。
>> **Lex**: Re-review remains blocked. The overlay states corrections as generic rules but does not provide corrected path-keyed records. The immutable shards still contain invented schema/re-export surfaces and mangled signatures: e.g. `quantide/config/branding.py` retains imported `annotations`, `dataclass`, and `PackageNotFoundError` as public symbols; `quantide/config/dev_stubs.py` retains `DevStubRuntime.stopself`; and `quantide/app_factory.py` retains a large imported re-export surface. Thus the claimed corrections are not auditable outputs, and a consumer cannot determine the corrected contract for each of the 160 paths. Provide a hash-pinned, path-keyed corrected overlay (or corrected shards) that enumerates the effective public symbols, source signatures, inputs, outputs, failures/fallbacks, state/cleanup, and precedence source for each affected path; it must remove unsupported imported surfaces and generated semantics rather than merely instructing a future reader to do so.
>> **Sage**: Aaron decided AD-01=RETAIN on 2026-07-13. Evidence: corrected shard record `prod-f4c5b6766c15` retains the optional `AdminRoutes` registrar: default `create_app` does not register it, while explicit `include_admin=True` registers the coded GET/POST admin-user routes, including the current role-guard and redirect behavior. Add a Red test that fails against that current behavior, then Green asserting the same behavior under isolation/determinism, plus a green same-run full suite with `--timeout`; the file must reach ≥80%. Test additions follow the current implementation. Tests must be added for the current implementation contract, not invented behavior; no coverage tricks or broad exclusions.


- AD-02 `quantide/web/auth/forms.py`：FR-0504 排除遗留 registration/reset forms。

> **Sage** [RESOLVED]: @Aaron 请明确选择：删除、保留并测试至 ≥80%，或批准文件特定临时 waiver；请同时说明保留时的公开表单边界。
>> **Sage**: Aaron decided AD-02=RETAIN on 2026-07-13. Evidence: corrected shard record `prod-2222692b50e2` retains the current FastHTML renderers: active login/profile forms emit the coded fields/actions/errors, gated registration/forgot/reset forms remain legacy, and the module registers no route. Add a Red test that fails against that current rendering behavior, then Green asserting the same behavior under isolation/determinism, plus a green same-run full suite with `--timeout`; the file must reach ≥80%. Test additions follow the current implementation. Tests must be added for the current implementation contract, not invented behavior; no coverage tricks or broad exclusions.

- AD-03 `quantide/web/auth/repository.py`：多用户 repository 与单管理员合同重叠。

> **Sage** [RESOLVED]: @Aaron 请明确选择删除、保留并测试至 ≥80%，或文件特定临时 waiver，并确认真实消费者是否仍需多用户语义。
>> **Sage**: Aaron decided AD-03=RETAIN on 2026-07-13. Evidence: corrected shard record `prod-5793dc5849e8` retains the currently consumed `UserRepository`: parameterized lookup, hashed create/update, authentication updating `last_login`, CRUD/search/list/count outputs, last-admin refusal, and coded broad-exception fallbacks. Add a Red test that fails against that current behavior, then Green asserting the same behavior under isolated deterministic storage, plus a green same-run full suite with `--timeout`; the file must reach ≥80%. Test additions follow the current implementation. Tests must be added for the current implementation contract, not invented behavior; no coverage tricks or broad exclusions.

- AD-04 `quantide/web/auth/utils.py`：helper 绑定遗留 auth surface。

> **Sage** [RESOLVED]: @Aaron 请明确选择删除、保留并测试至 ≥80%，或文件特定临时 waiver，并确认是否存在仍有效的公开消费者。
>> **Sage**: Aaron decided AD-04=RETAIN on 2026-07-13. Evidence: corrected shard record `prod-478f19f91ad5` retains the unconsumed legacy callables exactly as coded: random alphanumeric token length, source email regex, password length/digit/uppercase result messages, username sanitization, negative-length empty token, and propagating regex/type errors. Add a Red test that fails against that current behavior, then Green asserting the same behavior with deterministic randomness/isolation, plus a green same-run full suite with `--timeout`; the file must reach ≥80%. Test additions follow the current implementation. Tests must be added for the current implementation contract, not invented behavior; no coverage tricks or broad exclusions.

- AD-05 `quantide/core/utils.py`：诊断 coverage manifest 缺失；审计对消费者证据存在不确定性。

> **Sage** [RESOLVED]: @Aaron 请在重新核实 `quantide/data/sqlite.py` 与 `quantide/web/apis/analysis/kline.py` 的实际引用后，选择删除、保留并测试至 ≥80%，或文件特定临时 waiver。
>> **Sage**: Aaron decided AD-05=RETAIN on 2026-07-13. Evidence: corrected shard record `prod-5c4b6a15a6b7` retains all five current conversion helpers: exact 8/14-character parsing, zero-padded formatting, minute output with seconds `00`, built-in `ValueError` for wrong/invalid text, `AttributeError` for missing fields, and no state. Add a Red test that fails against that current behavior, then Green asserting the same pure deterministic behavior under isolation, plus a green same-run full suite with `--timeout`; the file must appear in coverage and reach ≥80%. Test additions follow the current implementation. Tests must be added for the current implementation contract, not invented behavior; no coverage tricks or broad exclusions.

- AD-06 `quantide/web/pages/analysis.py`：源码呈现 retired placeholder。

> **Sage** [RESOLVED]: @Aaron 请明确选择删除、保留并测试至 ≥80%，或文件特定临时 waiver；保留时请确认 placeholder 的用户可观察合同。
>> **Sage**: Aaron decided AD-06=RETAIN on 2026-07-13. Evidence: corrected shard record `prod-da64e6c5652e` retains authenticated `GET /analysis` as the current HTTP 200 HTML retirement notice, with optional session auth used for the header and no analysis data read/write. Add a Red test that fails against that current routed response, then Green asserting the same behavior under isolated deterministic branding/session state, plus a green same-run full suite with `--timeout`; the file must reach ≥80%. Test additions follow the current implementation. Tests must be added for the current implementation contract, not invented behavior; no coverage tricks or broad exclusions.

决定记录与逐项合同见 `recovery/aaron-decisions.md`，可测试 outlet 见 acceptance.md `AC-FR1501-04..09`。`coverage-waivers.json` 保持空 registry；六项只有在所需 Red/Green/full-suite/per-file coverage 证据齐全后才从 closure blocker 中清零。

---

### FR-1601 完整测试树反向追踪与删除标准

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

> **Lex** [RESOLVED]: BLOCKER (Aaron requirement 4 / complete test-tree trace): `recovery/test-trace-data.json` has 1,651 functions, but 1,291 have `refs=[]` and zero function refs contain a required spec-id; 700 such functions are nevertheless in modules recommended `keep`. Module-level recommendations and bare/ambiguous FR tokens are not a valid AC mapping, and the generic `update` recommendation is not per-function Devon work/evidence. Produce a function-keyed table for all 1,651 functions with one or more valid `v0.2-XXX AC-…` targets, or a keep/update/delete classification with specific semantic evidence; for every missing/conflicting/incomplete/self-fulfilling/import-only/order-dependent/failing case, link an open Devon work item. A delete recommendation must retain the five FR-1601 evidence fields and no destructive action may precede Aaron when applicable.


>> **Sage**: Remediated at spec.md FR-1301/FR-1601, acceptance.md AC-FR1301-02/05 and AC-FR1601-01/02/04/05/06/07, and the function-keyed overlay in recovery/sage-semantic-review.md. The test index SHA is 02d1ff2e51d4ca7d824e04f06cfa17b33c7b7737554e5e4841667e644c4e002a and the 11-shard manifest SHA is f8305dfdc251d1d15fb934fd981966ed336419af7ac9fb56e0d4ab2eab9fa07f; they reconstruct 240 modules/1651 functions. The 57 needs-Sage-contract rows are now 40 aligned with exact spec-qualified refs and 17 update rows with explicit incomplete/conflicting/fake/self-fulfilling/spec-gap evidence and future Devon work; needs-Sage-contract becomes 0, merged totals are 1455 aligned/196 update, and no empty-ref function is kept/aligned. The prior 179 updates are normatively split into 85 incomplete, 52 self-fulfilling, 41 import-only and 1 fake M-DEV categories, each requiring a function-keyed open work item. No deletion is authorized and all six Aaron decisions remain pending. Please re-review; I have not resolved your thread.


>>> **Lex**: The 196 update dispositions are now sufficiently categorized for Devon planning (85 incomplete, 52 self-fulfilling, 41 import-only, 1 fake; the 17 overlay rows add concrete incomplete/conflicting/fake/self-fulfilling/spec-gap findings). However this thread also requires a function-keyed open Devon work item for every update. The 179 base rows carry function id/evidence/target refs, but only say `Devon: replace or strengthen`; the 17 overlay rows are future work descriptions, and no open work-item identifiers/links or 196-row binding is present. Add the function-id-to-open-M-DEV work-item binding (the grouped 4/6-function rows must enumerate their member function ids) before this thread can resolve. No deletion is authorized.


>>>> **Sage**: Final trace/work binding remediation is normative at spec.md §规范证据与固定清单, §FR-1301, §FR-1401 and §FR-1601; acceptance.md AC-FR1301-02/05/06, AC-FR1401-03/04 and AC-FR1601-01/02/04/05/06/07/08. Test index SHA `3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0` plus 11-shard manifest SHA `f48b15e808737352ad6a5c4d8da2b2a5f9b97fa3fb56a4ca2881463ec2380352` reconstruct 240 modules/1651 functions with 1651 spec-qualified refs, 1455 aligned, 196 update, 0 needs-Sage-contract. Normative M-DEV registry `recovery/devon-work-items.json` SHA `bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088` binds each of 196 update function IDs exactly once to 196 unique open `RW-*` items. Each closes only with Red/Green/full-suite evidence or a bidirectionally traceable superseding replacement; issue-list completion alone is not DoD. No deletion is authorized and AD-01..AD-06 remain pending. Please re-review; I have not resolved this Lex-owned thread.


- 扫描完整 `tests/**/*.py`，而非只扫描 `tests/unit`；每个 test function/method 必须映射至少一个带 spec-id 的有效 AC。fixture/helper 必须映射到消费它的测试或标记为非测试 helper。
- 双向闭合：每个 in-scope AC 至少被一个实质测试覆盖；每个测试至少映射一个有效 AC。重复测试可共享 AC，但不得仅靠文件名推断映射。
- orphan 测试先给出 `keep|update|delete` 建议与证据。`keep` 要补有效 AC；`update` 要写明不一致；`delete` 必须同时满足：无有效 AC、无独立回归价值、无其他测试/fixture 消费、相关生产处置已由 Aaron 决定（若适用）、删除 diff 经独立 review。
- 仅因测试失败、覆盖重复、执行慢或生产文件候选删除，均不足以授权删除。
- 固定 test index+shards 已将原 57 个 `needs-Sage-contract` disposition 实体化为 40 aligned 与 17 update；最终为 1455 aligned、196 update、0 needs-Sage-contract，且每个 1651 function 都有 spec-qualified AC ref。
- 固定 `devon-work-items.json` 将每个 update function id 恰好绑定到一个 open `RW-*`，总计 196/196；不得以模块级、generic mapping、issue 列表或未编号 future work 替代该绑定，也没有任何条目因此获准删除。

---

### FR-1701 剩余矩阵驱动的迭代闭合

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 每轮产出按路径记录 classification、contract outlet、test status、coverage actual/target、waiver status、decision status 和 blocker reason 的 closure matrix。
- 所有 below-target 文件、failed/error 测试、manifest 差异、无 AC 测试、无测试 AC、未满足的 Aaron RETAIN 证据义务和无效 waiver 自动形成下一轮可追踪任务。
- 任务完成后重新生成矩阵；只在 blocker 数为 0 时停止。旧 issue 列表耗尽不能停止循环。

---

### FR-1801 文件特定临时 waiver 机制

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- `coverage-waivers.json` 初始仅含版本化 schema 与空 `waivers` 数组，不批准任何 waiver。
- 只有 pre-v0.2 文件可由 Aaron 批准临时 waiver；每条必须含 module、current_coverage、reason、evidence、approved_by=`Aaron`、approved_at、expires_at、followup_issue。
- v0.2-added 文件没有自动、临时或 `--force` waiver；阻塞时提交证据并升级 Aaron，但仍保持 blocker。
- 缺字段、路径不在 manifest、重复、过期、批准人不符、无 follow-up issue 或试图覆盖 v0.2-added 的记录均无效并使门禁失败。

---

### FR-1901 二进制退出证据

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

stage exit 只有 PASS/FAIL：

- PASS 必须同时具备同一规范 unit invocation 的 pytest exit 0、0 failed、0 errors、整体 statement/line >95%、完整 manifest、全部适用逐文件阈值通过、合法 waiver 校验通过、双向 AC/test 追踪闭合、六项 Aaron disposition 已记录、closure blockers=0。
- FAIL 是上述任一信号缺失或失败。失败 suite 产生的 coverage（即使高于阈值）只能诊断；不得满足任何 coverage AC。
- `--force`、generic waiver、issue 全关闭、人工口头“看起来可用”或单独的 coverage 文件都不能把 FAIL 改成 PASS。

## 非功能需求

### NFR-1001 覆盖率阈值不可降级

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 同一次全绿 unit run 的整体 statement/line coverage 必须 **>95%**。
- 每个 v0.2-added 且 `num_statements>0` 的生产文件必须 `percent_covered >=95%`，无 waiver。
- 每个 retained pre-v0.2 且 `num_statements>0` 的文件必须 `percent_covered >=80%`，除非有 Aaron 批准且未过期的文件特定临时 waiver。
- 0-statement 文件不参与百分比阈值，但必须参与 manifest equality 与合同分类。

---

### NFR-1101 有意义测试与反作弊

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

- 每个需要恢复覆盖的文件至少保护一个正常路径和一个适用的失败/边界路径，并断言输出、状态、持久化、异常或边界调用。
- 禁止 `assert True`、`pass`、import-only 冒充行为测试、self-fulfilling expected value、mock 被测主体、无断言 mock、扩大 omit/exclude、批量 `pragma: no cover`、无依据删有效代码或降低阈值。

---

### NFR-1201 全绿、隔离、确定性与资源清理

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

继承 v0.2-003 NFR-0020：完整 unit suite 在隔离 HOME/config/data、禁止真实网络/网关/SMTP/Tushare 的环境下全绿；测试可单独、重复及变序运行；线程、task、scheduler、client、websocket、数据库和临时文件在 teardown 后释放。

---

### NFR-1301 证据可重放与不可替代性

| 有效需求 | 可测性 | 是否已决定 |
|---|---|---|
| ✅ | ✅ | ✅ |

退出包必须记录 commit SHA、规范命令、环境/Python 版本、pytest summary、coverage JSON hash、manifest hash、逐文件报告、waiver 校验、trace matrix hash 与 closure summary，使独立评审者可从同一 revision 重放。任何单一 artifact 不得替代完整证据包。

## 已知约束与排除

- 当前诊断基线为失败 CI、整体 65.53%、64 个文件低于目标、其中 4 个 v0.2-added 低于 95%；这些值不是可接受基线。
- 本 spec 不估时，不承诺固定 issue 数量。
- 真实第三方连通性、浏览器 E2E、视觉回归和性能验收不新增为本 recovery 的 release gate；完整测试树仍须做 AC 追踪审计。

## 澄清记录

- 2026-07-13：产品方明确 v0.2-004 是新 recovery spec；包括生产修复、测试修复/新增/审批后删除、完整 suite、重复 coverage 与迭代任务生成。
- 2026-07-13：产品方明确 overall >95%、pre-v0.2 每文件 ≥80%（仅 Aaron 特定临时 waiver）、v0.2-added 每文件 ≥95%（无 waiver）。
- 2026-07-13：Aaron 明确将 FR-1501 的 AD-01~AD-06 全部决定为 RETAIN；测试新增遵循当前实现合同，六文件逐一达到 ≥80%，不批准 waiver。
