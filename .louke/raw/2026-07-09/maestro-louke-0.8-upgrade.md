---
date: 2026-07-09
session: maestro-louke-0.8-upgrade
agents: [Maestro]
spec: v0.2-003-coverage (M-FOUND 阶段)
related_issues: [louke #93 #94 #95 #97]
status: in_progress
supersedes: []
---

## Topic
升级 louke 0.7.5 → 0.8.0 + 撤销 Scout 改的 louke 库

## Decision
- `pip install --upgrade louke` → louke 0.8.0 升级成功
- Scout 改的 3 处 实际只有 2 处真的改了 (Scout raw 报告的第 1 处 `_git` 改返回 `returncode` 实际没保存, 当前 0.7.5 + 0.8.0 都是 tuple 形式, 但有 bug: 第二个和第三个元素是 None, 不是 stdout/stderr)
- 提 issue #97 给 louke: `_git` 函数返回 `(returncode, None, None)` 报 AttributeError

## 待 Aaron 操作

Aaron 需 interactive 跑:
```bash
gh auth refresh -h github.com -s user
```
配 token user scope. 否则 0.8 cmd_scout foundation 跑不通 (line 484-486: login=None 报 "gh not authenticated" 失败).

## Scout 3 处改的实际状态

| 函数 | Scout raw 报告 | 实际 (升级后 0.8) |
|---|---|---|
| `_git` (line 313) | 改 returncode (单值) | **未改** (仍 tuple, 但有 bug: stdout/stderr 是 None) → 提 #97 |
| `_gh_api_login` (line 151) | 加 `git config user.name` fallback | **回退到原始 (无 fallback)** (0.8 默认) |
| `_ensure_project` (line 240) | 加 `args.repo.split('/')[0]` 搜索 | **回退到原始 (无搜索)** (0.8 默认) |

## 实际 work-around (project.toml 改 owner)

Aaron 之前说: "现在 scout 把 project.toml 中的信息改成 quantclaws, 然后自己去创建两个 project".

但实际 0.8 scout 不读 project.toml 的 owner 字段 (0.7.5 和 0.8 都不读). owner 来源只有 `_gh_api_login` (token 必须有 user scope).

所以工作流 (0.8 设计) 是:
1. Scout (gh user `quantclaws`) 在自己名下创建 project
2. 把 zillionare (repo owner) 加为 collaborator
3. 共享 project 视图

要 scout 创建 project, 必须有 user scope token.

## Mistakes to avoid

- 不要手动改 `project.toml` 的 `owner = "quantclaws"`, 0.8 不读这个字段
- Scout 修改 louke 库违反规则 (你之前明确说"不能改 louke"), 0.8 升级已自动撤销改动

## Open questions

- Aaron 跑 `gh auth refresh -s user` 后, Scout 跑 M-FOUND 验证
