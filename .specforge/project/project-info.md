# Project Info

- **Version**: v0.2
- **Repo**: github.com/zillionare/millionaire
- **Project**: specforge-v0.2 (#4, PVT_kwHOED0Dk84BZfh0)
- **Spec ID**: v0.2-001-strategy-framework
- **Release Branch**: `releases/v0.2`（Scout 产生的全部上游产物都在该分支上；上游固定为 `main`）
- **Test Issue**: #53 (closed) — Good First Issue: millionaire-v0.2
- **Test PR**: #54 (closed) — Good First PR: millionaire-v0.2
- **Story Source**: `.specforge/project/v0.2-001-strategy-framework/story.md`（351 行原文）
- **Spec 编号决策**: `.specforge/project/` 目录为空 → 自动分配 `001`；keyword 从 story §1「策略框架」提取为 `strategy-framework`
- **Repo 状态**: 已存在
- **Project 状态**: 已存在并复用（`specforge-v0.2` #4）
- **gh 权限**: 通过（issue create + close 验证）
- **Created**: 2026-06-15

## 备注
- **故事单源**：`.specforge/project/v0.2-001-strategy-framework/story.md`（351 行）；`.dev/specs/story.md` 是指向它的软链，供习惯从 `.dev/specs/` 读 story 的下游 Agent 沿用旧路径。
- **specforge 是本仓库的内部代号**（不是 OMC 协议本身），与项目内 `.specforge/agents/*.md` 角色契约是一体的。
- **当前 working tree 起始点**：v0.2 已含 main 的 `adopt specforge` 同步（merge commit `6ce2a8f`），与 Scout "上游固定为 main" 的契约一致。
- **Keyword 选取修正**：原 commit 误用 `specforge` 作 keyword；按 Scout 规则应从 story 内容提取，现改为 `strategy-framework`（对应 story §1 标题）。通过 `git commit --amend` 一次性修正，无新 commit 污染历史。
- **F11 身份不一致说明**：specforge F11 期望 `git remote owner` 与 `gh user` 一致。当前状态是 git remote = `zillionare`、gh user = `quantclaws`（同一用户的两个 GitHub 身份）。按 Aaron 判断：**身份不一致在本工作流中不算阻断**，因此 Warden 走 [通过+警告] 而非 [拒绝]。F11 不退回 Scout。
