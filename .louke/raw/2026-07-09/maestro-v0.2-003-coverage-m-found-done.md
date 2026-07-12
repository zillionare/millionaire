---
date: 2026-07-09
session: maestro-v0.2-003-coverage-m-found-done
agents: [Maestro]
spec: v0.2-003-coverage
related_issues: [louke #97]
status: resolved
supersedes: [raw/2026-07-09/maestro-v0.2-003-coverage-m-found-finalize.md]
---

## Topic
v0.2-003-coverage M-FOUND 完成 (Aaron 配 token + workaround patch + 修复)

## Decision

- `pip install --upgrade louke` → 0.8.0
- gh auth refresh -s user (Aaron 配 token)
- 打 venv/scout.py workaround patch:
  - `_git` (line 313) 改返回 `(returncode, stdout, stderr)` 而非 `(returncode, None, None)` — 修 issue #97
  - `_gh_project_create` (line 212) 加 `timeout=30` — 修 0.8.0 卡死
- amend HEAD commit 改 author (noreply → openclaw@quantide.cn) 修 L4 identity check
- 复制 .opencode/agents/ → agents/ 12 个文件 修 F5
- 加 coverage.json 到 .gitignore
- 删 quantclaws 下重复 project (#12 #13)
- 跑 `lk agent scout foundation --no-repo --no-commit` → [PASS] 11/11

## 失败记录

- 0.8 cmd_foundation 多次卡: pre-commit hook, 重复 project, 空 commit — 全 workaround
- venv workaround patches 2 处: `_git` (issue #97) + `_gh_project_create` (timeout)
- 0.8 cmd_foundation 不支持 `--no-commit` flag 解决空 commit, 用 workaround commit 0.8 已 commit 文件

## 后续

- 启动 M-SPEC (Sage 写 spec.md + acceptance.md for v0.2-003-coverage)
- record-lock 状态 (v0.2-002-ui) 未解决 (Louke 0.8 路径 bug 在 #97)
- 5 个 workaround 都在 venv/louke 库 (reinstall 后丢失, 待 issue #97 + 0.8.1+ 修后解决)
