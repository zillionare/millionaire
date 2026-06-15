# BUG-{编号} — Bug Report & Fix

- **Bug ID**: BUG-{编号}
- **发现日期**: {YYYY-MM-DD}
- **严重程度**: {P0 阻塞 / P1 严重 / P2 一般 / P3 轻微}

## 复现步骤

1. ...
2. ...
3. 观察到的行为: ...
4. 期望的行为: ...

## Root Cause

<!-- Hunter 定位到的根因 -->

## 修复方案

<!-- 修复策略 -->

## Phase 1: Red（Bug 复现测试）

- **测试文件**: ...
- **CI 状态**: Red ✅（确认 Bug 可被测试捕获）
- **Commit**: `test: red – BUG-{编号} {描述}`

## Phase 2: Green（修复）

- **修复文件**: ...
- **测试结果**: 通过 ✅
- **Commit**: `fix: green – BUG-{编号} {描述}`

## Phase 3: Refactor

- **重构内容**: ...
- **Commit**: `refactor: BUG-{编号} {描述}`

## Shield 回归检查

- [ ] 全量测试通过
- [ ] 无新 Bug 引入
- [ ] 原始 Bug 已确认修复
