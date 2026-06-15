# {Feature 标题} — Task Execution Log

- **Spec ID**: {SPEC-ID}
- **Task ID**: {T-XXX}

## Phase 1: Red

- **测试文件**: ...
- **测试用例编号**: ...
- **CI 状态**: Red ✅
- **失败原因**: 指向待实现功能（非测试本身 Bug）
- **Commit**: `test: red – {编号} {描述}`

## Phase 2: Green

- **实现文件**: ...
- **实现策略**: ...
- **测试结果**: 全部通过 ✅
- **Commit**: `feat: green – {编号} {描述}`

## Phase 3: Refactor

- **重构内容**: ...
- **测试结果**: 仍全部通过 ✅
- **Lint/类型检查**: 无错误 ✅
- **Commit**: `refactor: {描述}`

## Keeper 门禁

- [ ] Red 阶段完成（测试先失败）
- [ ] Green 阶段完成（关联测试通过）
- [ ] Refactor 阶段完成（无 lint/类型错误）
- [ ] 代码已提交
