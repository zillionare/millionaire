# {Feature 标题} — Spec

- **Spec ID**: {SPEC-ID}
- **创建日期**: {YYYY-MM-DD}
- **状态**: {草稿 / 评审中 / 已确认}

## 用户故事

### US-010
story: 作为{角色}，我想{功能}，以便{价值}
priority: P0

### US-020
story: 作为{角色}，我想{功能}，以便{价值}
priority: P0

## 用户使用场景

### scenario-010

{描述用户应该如何实用本软件}

## 功能需求

> **格式约定（必读）**: 每个 FR 单元都由三级标题+空格+FR-XXX（大写，3位零填充）+ {title} 引起，随后是需求描述和元数据，遇到以下情况时，本 FR 单元结束：
  1. 遇到一个二级标题
  2. 遇到下一个 FR 单元
  3. 文件结尾
   合格的 FR 单元必须满足以上格式要求。
> **编号约定(必读)**： FR 的编码采用3位数字，0填充，初稿时从10开始，每次增加10；以便后续可以随时在中间插入新的 FR。
> **必读**： FR-XXX 编号即该需求的 id。禁止删除已有需求 id，以避免引用混淆；如需废弃某 FR，在其元数据中, valid 改为 false，并在澄清记录中说明。

### FR-010 {title}

{需求描述}

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-020 {title}

{需求描述}

```yaml
testability: ⚠️ {原因}
resolved: ⚠️
```

## 非功能需求

> **必读**: 本节的格式、编号等要求同 FR，此处省略。

### NFR-010 {title}

{需求描述}

```yaml
testability: ✅
resolved: ✅
valid: ✅
```


