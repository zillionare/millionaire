# AI 因子风洞工作台与发布完备性 — 测试与门禁计划（Test Plan）

- 状态：`v0.5-001-ai-factor-release` 规划测试方案，随各工作包（WP-1 ～ WP-8）同步落地。
- 关联：[主规格](spec.md)、[拟议接口](interfaces.md)、[验收标准](acceptance.md)。

## 1. 测试分层与职责

| 层次 | 测试目录与运行约束 | 覆盖目标与核心证据 |
| --- | --- | --- |
| **L1 独立手算 Oracle** | `tests/ground_truth/`，纯离线，严禁调用生产计算函数构造期望值 | 外部因子计算与复权供给、截面 Spearman 秩相关、PIT 股票池按日过滤、`excess_mean` / `cs_rank` 标签成熟边界、单票权重上限风控整手截断、30m Shadow-Run 8 槽位人工账本（对应 `AC-5004/5006/5016/5017/5018/5020`） |
| **L2 模块与安全隔离单测** | `tests/unit/`，`tmp_path` 完全隔离配置与数据库，`--disable-socket` | 向导三目录默认预填与读写探针校验、可选 AI 配置跳过与 `api_key` 全链路脱敏、Web Agent 路径沙箱防逃逸（`../`/软链/外目录拦截）、坏插件容错枚举、指纹失效、预设缺失因子阻断、Demo 数据包隔离挂载、BaoStock 日线适配器解析、五态风洞徽章视图、用户自定义附加列与自定义缓冲带策略开放性验证（对应 `AC-5001～5003/5007/5009/5010/5013/5015/5022/5025/5026/5028`） |
| **L3 跨组件流水线与 Web AI 会话闭环** | `tests/e2e/`，允许本机回环 `127.0.0.1`（含本地 Mock OpenAI 兼容服务）与子进程 worker，禁公网 | Web `/factors/studio` 自然语言会话全闭环（Mock 模型第 1 轮故意返回跨证券串算代码 → 风洞拦截 → 自动回喂 `first_difference` → 第 2 轮修复后 `PASS` → 出 IC/正交性卡片 → 一键生成预设跑消融回测 + 达到 `max_repair_rounds` 受控终止 + 中途点击停止取消）、30m Shadow-Run 跨午休/跨日/缺口补齐/子进程强杀恢复、教学风控双路径一致性（对应 `AC-5008/5018/5019/5020/5027/5028`） |
| **L4 关键变异门禁** | `quantide/audit/mutations.py` 扩展变异集 | 针对新增时间穿越点、路径沙箱与修复轮次上限植入语义变异，验证 100% 被对应目标断言杀死（对应 `AC-5005/5016/5017/5019/5024/5027/5028`） |
| **L5 Agent CLI/Skill、边界与仓库布局门禁** | `tests/quality/` + 外部构建产物验证 | `millionaire` 全套 `--json` CLI schema 与退出码校验、外部 Agent Auto-Quant 闭环回归、CE 官方不预置 pro 模块且不封堵用户扩展的双面契约检查、Demo Bundle 体积预算、`mkdocs build --strict`、`scripts/check_quality.py` 与 `--check-layout`（对应 `AC-5011/5012/5014/5021～5024`） |

## 2. 核心金标准小样本设计（L1 Oracles）

1. **外部因子与正交性 4×12 样本**：
   - 4 只股票 × 12 个交易日，包含 1 次除权因子跳变、1 只股票中途停牌 2 日、2 只股票同日因子值并列（验证平均秩）。
   - 同时放入 1 个合法外部时序因子、1 个与内置因子严格单调变换的共线因子（验证 `max_abs_rank_corr = 1.0` 触发 `HIGH_COLLINEARITY`）、1 个故意漏写 `.over("asset")` 的坏因子（验证跨证券隔离精准拦截）。
2. **PIT 股票池反幸存者偏差样本**：
   - 构造 4 只股票跨 3 个时间段的纵向历史状态：
     - 股票 A：`t1` 正常交易，`t2` 进入 `*ST`，`t3` 摘帽恢复正常；
     - 股票 B：`t1` 上市仅 15 个交易日（`< 60`），`t2` 满 60 个交易日；
     - 股票 C：`t2` 当日收盘封死一字涨停（`close == up_limit` 且 `high == low`）；
     - 股票 D：`t1` 正常交易，`t3` 退市。
   - 断言在 `t1`、`t2`、`t3` 三个截面选池时，候选集合与手工列出的当日真实可交易集合完全相等；若实现偷看 `t3` 最终状态去过滤 `t1`，断言立即报红。
3. **截面训练标签成熟样本**：
   - 3 只股票 × 10 个交易日，`horizon = 3`。手算每日原始未来 3 日收益、每日截面均值相减后的 `excess_mean`（每日截面和严格为 `0`）、以及含并列值的 `cs_rank`。
   - 推进决策日 `t0`，断言凡退出日 `t(h+1)` 晚于 `t0` 的信号日整日被排除，绝不出现部分股票提前进入截面排名。
4. **30 分钟 Shadow-Run 跨日人工账本样本**：
   - 2 个交易日 × 每日 8 根 30m 闭合 bar + 1 根盘中未闭合 forming bar，包含第 1 日 `14:30` 触发 `next_open` 买入（应于 `15:00` 或次日 `10:00` 依时序契约执行）、第 1 日买入仓位在第 2 日 `10:00` 解锁 T+1、以及第 2 日 `11:00` 历史分钟 bar 延迟到达产生 `gap_slots` 后在 `13:30` 补齐按序回放。

## 3. 新增关键变异清单（L4 Mutations）

在 `quantide.audit.mutations` 中新增以下必需杀死的非等价语义变异：

- `MUT-5001（外部因子跨证券串算）`：移除外部参考因子中的 `.over("asset")` 分组，必须被 `FR-5002` 跨证券隔离检查杀死。
- `MUT-5002（PIT 静态最新名称穿越）`：将 PIT ST 过滤改为读取最新静态 `stock_list` 名称前缀，必须被 `AC-5016` 反幸存者偏差测试杀死。
- `MUT-5003（截面秩跨日池化泄露）`：将 `cs_rank` 的 `.over("date")` 改为全训练窗口池化排名（混入跨日分布或未成熟边界），必须被 `AC-5017` 手算对拍与未来扰动检查杀死。
- `MUT-5004（风洞徽章忽略源码指纹变更）`：在 `WindTunnelBadgeView` 计算中跳过 `source_hash` 相等性校验，必须被 `AC-5013` 篡改源码降级 `STALE` 测试杀死。
- `MUT-5005（30m 影子提前消费 forming bar）`：关闭 30m Shadow-Run 对 `is_closed` 的过滤，使未闭合分钟桶进入影子回放，必须被 `AC-5019` 杀死。
- `MUT-5006（预设静默忽略缺失因子）`：当 `FactorPreset` 中某个因子不存在时静默过滤而非抛错阻断，必须被 `AC-5007` 杀死。
- `MUT-5007（Web Agent 沙箱路径逃逸或绕过风洞直接出检验卡片）`：移除 `write_factor_plugin` 对 `factor_dir` 直接父目录的 `resolve()` 限制，或允许风洞 `FAIL` 的因子直接通过 `run_factor_ic_study` 返回有效结论卡片，必须分别被 `AC-5028` 与 `AC-5027` 杀死。

## 4. 版本边界与仓库洁净度验证命令

所有验证均须通过 `scripts.artifact_paths` 将缓存、覆盖率、JUnit XML 与文档站点输出至源码树外部目录：

```bash
PY=.venv/bin/python
ART=$($PY -m scripts.artifact_paths)

# 1. 离线单元、金标准与验收测试
$PY -m scripts.artifact_paths --run $PY -m pytest \
  tests/ground_truth tests/unit tests/quality \
  --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,::1,localhost \
  --junitxml="$ART/junit-unit.xml"

# 2. 代码质量门禁（复杂度、重复代码、行宽、文件规模）
$PY -m scripts.artifact_paths --run $PY scripts/check_quality.py

# 3. 严格文档构建验证
$PY -m scripts.artifact_paths --run .venv/bin/mkdocs build --strict --site-dir "$ART/site"

# 4. 源码仓库零污染检查
$PY -m scripts.artifact_paths --check-layout
git --no-pager status --short
```

## 5. 2026-11-18 补充反例

- 缺失退出交易日：A 在信号日后第 1 个权威交易日无行情时，`raw_return` 必须为 `null`；`cs_rank` 该信号日整日不进入训练，不能顺延使用下一存在行。
- 研究模型隔离：Paper 先加载 active 模型，研究实例保存同 key 的历史模型后，Paper 再刷新仍必须加载 active latest；实验 `model_ref` 仍可独立回放。
- 轮次身份：旧轮次风洞 PASS 后自动 IC 阻塞，新轮次完成并清理 `_ACTIVE`，释放旧 IC 后最终状态、卡片和 active factor 仍属于新轮次。
- Session 队列：`last_bar` 等于当前闭合 bar 时，下一 tick 仍调用一次 `process_next_open_30m_intents`，但不重复策略回调。
- 30m 数据修订：只修改分钟文件、不修改日线文件时，依赖身份必须变化，旧徽章不得继续命中旧 `data_hash`。
