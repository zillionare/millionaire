---
date: 2026-07-08
session: maestro-v0.2-002-record-lock-state
agents: [Maestro, Aaron]
spec: v0.2-002-ui
related_issues: [louke #93 #94 #95, project #132-#177]
status: open
---

## Topic
M-SPEC record-lock 尝试: Stage 1 PASS, Stage 2 45 PASS / 45 FAIL (v0.2-001 老 issue), Stage 3 gh project item-list failed (louke 0.7+ tomli 依赖 + #94 bug).

## 决定

- Stage 1 verify-acceptance: 5/5 PASS (215 ACs)
- Stage 2 verify-issue: 45/45 v0.2-002 PASS, 45/45 v0.2-001 老 issue FAIL (title 不符合 `[FR-XXXX]`, body 无 requirement ID 字段)
- Stage 3 verify-project: `gh project item-list failed` (louke 0.7+ 内部用 subprocess 跑 gh, 失败原因: 缺 tomli 库解析 project.toml? 或 louke gh 调用 API 限制?)
- record-lock 拒绝: 三信号不全 PASS

## 阻塞

1. **v0.2-001 45 老 issue** (45 个老 issue title 形如 `feature: xxx` 不带 `[FR-XXXX]`, body 无三字段)
2. **louke #94 --branch 缺失** (阶段 2 不知道读哪个分支, 走 main 404)
3. **louke #95 已 wont-fix** (用 project.toml workaround)
4. **tomli 缺失** (我已装, 但 lk 仍报空错误)

## Open questions

- Aaron 是否要修 v0.2-001 老 issue (45 个, 不在本 spec 范围但 record-lock 阻塞)
- 等 louke 0.7.1+ 修 #94 再 record-lock?
- 修 v0.2-001 老 issue (大改动, 超 v0.2-002 范围)
- 用 --branch 之外的方法 (如 fix-002 doc 提到 schema-vol path)

## Mistakes to avoid

- 不要在 record-lock 失败时强行覆盖状态 (louke 不支持)
- 不要在 v0.2-002 spec 范围外修 v0.2-001 issue (范围控制)
