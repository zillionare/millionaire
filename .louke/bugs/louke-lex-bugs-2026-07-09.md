# Louke Lex 工具 Bug 报告 (2026-07-09)

提交者: Aaron (via Maestro 调研)
项目: millionaire v0.2-002-ui (Lex 验证报告触发)

## Bug 1: verify_issue_schema.py 用硬编码英文 label, 不支持中文 label

**文件**: `louke/_tools/verify_issue_schema.py` (line 77-79)

**问题代码**:
```python
FIELD_FR_ID = "Requirement ID"
FIELD_SPEC_URL = "Spec Link"
FIELD_AC = "Acceptance Criteria"
```

`parse_issue_form` 函数用 `^### (.+?)\s*$` 解析 GitHub form, 把 `### 需求 ID` 这种中文 heading 当 key 存 dict. 但代码用 `fields.get("Requirement ID")` 查英文 key, **永远找不到中文 label** → 阶段二全 0/90.

**复现**:
1. 项目 `feature.yml` 用中文 label (`label: 需求 ID`)
2. 创建 issue 后 body 渲染成 `### 需求 ID\nFR-0001`
3. 跑 `lk agent lex verify-issue --spec v0.2-002-ui --repo zillionare/millionaire`
4. 阶段二报 "L2 field 'Requirement ID' missing" (所有 45 个 issue)

**期望**: Lex 工具支持中英 label fallback chain, 或从 feature.yml 自动检测.

**workaround (本项目临时)**: 把 `.github/ISSUE_TEMPLATE/feature.yml` 的 label 改英文 (`Requirement ID` / `Spec Link` / `Acceptance Criteria`). 不破坏 louke, 只影响本项目新 issue 格式.

---

## Bug 2: verify-issue 不支持 --branch 参数, 默认读 main 分支

**文件**: `louke/lex.py` (line 26-31, 130-140)

**问题代码**:
```python
# verify-issue: L1-L8 schema validation (Stage 3)
p = sub.add_parser('verify-issue', help='run L1-L8 schema validation (Stage 3)')
p.add_argument('--spec', required=True)
p.add_argument('--repo', default='')
# 没有 --branch 参数 (对比 verify-acceptance 有)

def cmd_verify_issue(args):
    cmd = [sys.executable, '-m', 'louke._tools.verify_issue_schema', '--spec', args.spec]
    repo = args.repo or _read_project_info_field('Repo').replace('github.com/', '')
    if repo:
        cmd.extend(['--repo', repo])
    # 没有 --branch 传给底层, 底层默认 main → 404
```

**复现**:
1. spec 在 `releases/v0.2` 分支
2. 跑 `lk agent lex verify-issue --spec v0.2-002-ui --repo zillionare/millionaire`
3. 工具读 `releases/main` (默认) → 404 warn (但不影响 L1-L8 计数, 0/90 主因是 Bug 1)

**期望**: `verify-issue` 子命令加 `--branch` 参数, 跟 `verify-acceptance` 一致, 传给底层.

**workaround (本项目临时)**: 无 (无法不改 louke 让 verify-issue 读非 main 分支). 需 louke 修复.

---

## Bug 3: `_common.py` PROJECT_INFO_PATH 硬编码 project.toml, 不兼容 project-info.md (Markdown)

**文件**: `louke/_common.py` (line 8)

**问题代码**:
```python
PROJECT_INFO_PATH = Path('.louke/project/project.toml')  # fix-002: from project-info.md
```

**修复历史**: 评论说 "fix-002: from project-info.md" 暗示从 Markdown 改到 toml, 但**没有回退兼容**. 老项目用 `project-info.md` (Markdown, `- **Key**: value` 格式) 的, 升级到 louke 0.7+ 后找不到字段 → `verify-project` 报 "Project URL missing in project.toml".

**复现**:
1. 项目 `.louke/project/project-info.md` (Markdown) 存在, 有 `Project ID: https://github.com/users/zillionare/projects/5`
2. 没有 `.louke/project/project.toml`
3. 跑 `lk agent lex verify-project --spec v0.2-002-ui --repo zillionare/millionaire`
4. 报 "Project URL missing in project.toml"

**期望**: `_toml_load` 失败时回退到 markdown parser (读 `- **Key**: value` 行).

**workaround (本项目临时)**: 创建 `.louke/project/project.toml`, 从 project-info.md 同步关键字段. 与 project-info.md 并存.

---

## 优先级

3 个 bug 都在 M-SPEC lock 阶段阻塞 Lex 验证. 优先级:
1. **Bug 1 (高)**: 阶段二全 0/90, 阻塞 M-SPEC lock 决策
2. **Bug 2 (中)**: 仅 warn, 不影响计数, 但偏离语义 (应该读 spec 所在分支)
3. **Bug 3 (中)**: 阶段三全 FAIL, 但 45 个 issue 实际已关联 Project #5 (手动核实)

## 报告

- 项目仓库: 提 issue 给 louke 项目 (https://github.com/...)
- 或邮件: louke maintainers
- 或: 等 louke 0.7.1+ 升级, 看是否已修

## 关联

- millionaire raw session: `.louke/raw/2026-07-08/sage-v0.2-002-round-10e-lex-verify.md`
- millionaire raw session: `.louke/raw/2026-07-09/sage-v0.2-002-round-15-codex-v4-5fixes.md`
