# 拟议接口、插件协议、CLI/JSON 与存储契约

- 状态：`v0.5-001-ai-factor-release` 规划接口草案，供实施与评审对齐；落地实现前不得写入当前版本对外操作手册。
- 关联：[主规格](spec.md)、[用户故事](story.md)、[验收标准](acceptance.md)、[测试计划](test-plan.md)。

## 1. 外部因子插件契约（对应 FR-5001、FR-5013）

### 1.1 目录解析

- 统一配置项：`factor_dir` 与 `strategy_dir` 与 `data_home` 一并在初始化向导“运行环境”步骤及系统设置中持久化（见第 9 节），未显式修改时分别默认为 `ensure_app_config_dir() / "factors"` 与 `ensure_app_config_dir() / "strategies"`。
- 路径安全边界：所有工作目录必须通过 `external_runtime_path` 等价校验，拒绝指向源码仓库根及其子路径（含符号链接解析后路径），并在保存时执行服务进程读写探针校验。

### 1.2 单文件插件协议

每个 `.py` 插件文件至少导出一个 `FACTOR_PLUGIN`（或 `FactorPlugin` 实例），结构如下：

```python
from dataclasses import dataclass, field
from typing import Literal, Protocol
import polars as pl


class FactorComputeFn(Protocol):
    def __call__(self, panel: pl.DataFrame) -> pl.Series | pl.DataFrame: ...


@dataclass(frozen=True)
class GoldenCase:
    """可选的独立手算小样本自检用例。"""

    name: str
    bars: list[dict[str, object]]
    expected: list[float | None]
    atol: float = 1e-9


@dataclass(frozen=True)
class FactorPlugin:
    factor_id: str  # 匹配 ^[a-z][a-z0-9_]{2,63}$，禁止与内置 FEATURE_COLS 重名
    display_name: str
    group: str = "自定义因子"
    bar_interval: Literal["1d", "30m", "1M"] = "1d"
    scope: Literal["time_series", "cross_sectional"] = "time_series"
    price_adjustment: Literal["hfq", "raw"] = "hfq"
    required_columns: tuple[str, ...] = ("open", "high", "low", "close", "volume", "amount")
    warmup_bars: int = 1
    availability: Literal["bar_close", "next_open"] = "bar_close"
    direction: Literal["positive", "negative", "nonlinear"] = "positive"
    principle: str = ""
    formula: str = ""
    example: str = ""
    caveats: str = ""
    compute: FactorComputeFn = ...  # type: ignore[assignment]
    golden_cases: tuple[GoldenCase, ...] = field(default_factory=tuple)
```

- **输入约定**：当 `price_adjustment="hfq"`（默认）时，框架传入的 `open/high/low/close` 已统一完成后复权转换，插件不得再次乘 `adjust`；`adjust` 是 hfq 输入中的框架保留列，若插件在 `required_columns` 中再次声明它，契约检查以结构化 `PluginContractError` 拒绝，而不是静默删除或二次复权。当 `price_adjustment="raw"` 时传入原始价与 `adjust` 列；用户自定义扩展列不设列名黑名单，满足 `required_columns` 即原样放行。面板保证按 `["asset", "date"]`（或 `["asset", "dt"]`）严格排序且无重复键。
- **输出约定**：返回与输入等长的 `pl.Series`，或含 `["asset", "date", factor_id]` 的 `pl.DataFrame`；缺失/预热期统一用 Polars `null` 表示，禁止返回残留 `NaN` 或 `±Inf`。
- **跳过诊断枚举 `SkippedFactorReason`**：`SyntaxError`、`ImportError`、`MissingPluginDeclaration`、`InvalidMetadata`、`BuiltinIdConflict`、`DuplicatePluginId`、`SourceCheckoutRejected`。

## 2. 正交性与风洞徽章数据结构（对应 FR-5002、FR-5003、FR-5007）

### 2.1 正交性摘要 `FactorOrthogonalitySummary`

```python
@dataclass(frozen=True)
class FactorCorrelationPeer:
    peer_factor_id: str
    peer_group: str
    mean_rank_corr: float
    abs_mean_rank_corr: float
    n_common_days: int


@dataclass(frozen=True)
class FactorOrthogonalitySummary:
    factor_id: str
    threshold: float  # 默认 0.85，纳入统计配置版本
    max_abs_rank_corr: float | None
    nearest_peer_id: str | None
    high_collinearity: bool
    top_peers: tuple[FactorCorrelationPeer, ...]
```

### 2.2 风洞体检徽章视图 `WindTunnelBadgeView`

```python
@dataclass(frozen=True)
class WindTunnelBadgeView:
    target_kind: Literal["factor", "backtest"]
    target_id: str
    badge_status: Literal["PASS", "FAIL", "INCONCLUSIVE", "STALE", "UNVERIFIED"]
    run_id: str | None
    checked_at: str | None
    source_hash: str
    recorded_source_hash: str | None
    data_hash: str
    config_hash: str
    check_items: tuple[dict[str, object], ...]  # 未来扰动、跨证券隔离、统计对照、账户守恒
    first_difference_summary: str | None
```

- 判定规则：无记录为 `UNVERIFIED`；有记录但任一当前指纹（`source_hash`、`config_hash`、`data_hash`）与记录不一致时强制降级为 `STALE`，不得继续返回 `PASS`。

## 3. 因子组合预设与消融对比契约（对应 FR-5004、FR-5010）

### 3.1 `FactorPreset`

持久化于 `<app_config_dir>/presets/<preset_id>.json`（原子写入）或应用 SQLite 表 `factor_presets`：

| 字段 | 类型与约束 |
| --- | --- |
| `preset_id` | 唯一标识 `^[a-z0-9][a-z0-9_-]{1,63}$` |
| `name`, `description` | 人类可读名称与备注 |
| `strategy_id`, `bar_interval` | 绑定策略类与固有周期（如 `MLMomentumReversalStrategy` + `"1d"`） |
| `features` | 非空有序因子 ID 列表；加载时逐个校验存在性与风洞准入状态 |
| `label_kind` | `"raw_return"` \| `"excess_mean"` \| `"cs_rank"` |
| `strategy_params` | `top_k`、`train_window`、`future_return_horizon`、`retrain_days`、`fill_timing`、`universe_filter` 等 |
| `preset_hash`, `updated_at` | 参数规范化 SHA-256 指纹与带时区时间戳 |

### 3.2 `AblationStudySpec` 与对比输出

- 输入：`baseline_preset_id`、`variant_preset_ids: list[str]`（1～5 个）、共享固定的 `start_date`、`end_date`、`principal`、`commission`、`stamp_tax`、`seed`、`universe_filter`。
- 输出：每个预设对应的 `backtest_id`、净值序列、核心指标（总收益、年化收益、相对 Baseline 年化超额、最大回撤、Sharpe、Calmar、双边年化换手率、累计费用）以及新增/差异特征的平均绝对 SHAP 权重占比表。

## 4. 免 Token 离线体验数据包契约（对应 FR-5005）

- 内置只读资源路径：`quantide/assets/demo_bundle/`（含 `manifest.json`、`calendar.parquet`、`stocks.parquet`、`daily_bars.parquet`、`limit_prices.parquet`、`daily_basic.parquet`、`stock_status_pit.parquet`）。
- `manifest.json` 包含：`bundle_version`、`start_date`、`end_date`、`asset_count`、各文件 SHA-256 与字段单位说明。
- 激活时挂载路径：`ensure_app_config_dir() / "demo_market"`（或只读指向经校验的外部缓存副本），通过配置项 `data_source_mode = "demo_bundle" | "standard"` 切换，严禁改动用户已保存的正式 `data_home` 路径。

## 5. AI Agent CLI 与 JSON 输出契约（对应 FR-5006）

所有新增 CLI 子命令挂载于 `millionaire` 主入口：

```text
millionaire data status [--json]
millionaire factor list [--json]
millionaire factor init <factor_id> [--group <name>] [--dir <path>] [--json]
millionaire factor check <path_or_factor_id> [--cutoff YYYY-MM-DD] [--json]
millionaire factor study <factor_id> --start YYYY-MM-DD --end YYYY-MM-DD [--holdings 1,3,5] [--price open|close] [--json]
millionaire preset list [--json]
millionaire preset save --id <id> --name <name> --features f1,f2,... [--label-kind raw_return|excess_mean|cs_rank] [--params JSON] [--json]
millionaire backtest run --strategy <id> [--preset <id> | --params JSON] --start YYYY-MM-DD --end YYYY-MM-DD [--ablation-vs <baseline_id>] [--json]
millionaire risk-extension <enable|disable|status> [--copy-example] [--json]
```

JSON 顶层统一信封：

```json
{
  "schema_version": "1.0",
  "command": "factor.check",
  "ok": false,
  "status": "FAIL",
  "exit_code": 3,
  "fingerprints": {
    "source_hash": "...",
    "data_hash": "...",
    "config_hash": "..."
  },
  "data": {},
  "diagnostics": [
    {
      "code": "FUTURE_PERTURBATION_MISMATCH",
      "message": "Output at or before cutoff changed when future bars were perturbed",
      "first_difference": {
        "date": "2024-05-15",
        "asset": "000001.SZ",
        "expected": 0.0312,
        "actual": 0.0489
      }
    }
  ]
}
```

## 6. PIT 股票池与免积分日线能力契约（对应 FR-5009）

### 6.1 `UniverseFilterConfig`

```python
@dataclass(frozen=True)
class UniverseFilterConfig:
    exclude_st: bool = True  # 仅使用信号日 t0 已知的历史 ST/退市整理状态
    min_listing_days: int = 60  # 按 list_date 与权威交易日历计算的已上市交易日数
    exclude_suspended: bool = True  # 剔除 t0 停牌或零成交量标的
    exclude_limit_locked_on_close: bool = True  # auction_close 时序下剔除 t0 收盘封死一字/涨跌停不可买标的
    max_universe_size: int | None = 2000  # 若存在 PIT 市值则按市值排序截断；免积分源无市值时按近 20 日成交额均值截断并显式标注
```

- **严格防穿越条款**：当底层数据源没有提供 `stock_status_pit`（历史日级或区间级 ST/名称变更表）而只有当前静态股票列表时，若 `exclude_st=True`，系统不得用静态当前名称过滤历史日期，必须在结果诊断中记录 `pit_warnings=["st_history_unavailable"]`。
- **CE 边界与开放扩展约定**：CE 官方内置 `DailyBasic` 采集维持 `date, asset, total_mv, circ_mv`（不内置换手率、PE、PB 或行业分类落库）；但若用户通过自定义数据源或研究面板自行附加扩展列（如自定义换手率、估值或行业列），面板传递与 `FactorPlugin.required_columns` 校验必须原样放行，不做列名封堵。

## 7. CE 教学风控扩展契约（对应 FR-5011）

- 默认行为：未执行启用命令前，`risk_program_registry.list()` 为空列表 `[]`。
- 扩展位置：`<app_config_dir>/extensions/risk_extensions.py` 与状态文件 `<app_config_dir>/extensions/risk-extensions.json`（`{"enabled": true}`）。
- 入口约定：用户扩展文件导出 `register_extensions(registry: RiskProgramRegistry) -> None`。
- 附带只读教学模板：`quantide/assets/examples/risk_single_asset_cap.py`，注册 ID 为 `example.single_asset_weight_cap`，默认参数 `{"max_weight": 0.25}`：
  - 回测叠加层与仿真 `RiskStrategy` 均检查单笔买入委托金额加当前持仓市值是否超过 `max_weight * total_equity`，超出时按整手（100 股整数倍）下调可买股数或拦截开仓，不涉及止盈止损价格线或三重障碍逻辑。

## 8. 30 分钟 Shadow-Run 逐 bar 跟踪契约（对应 FR-5012）

- `TrackingStore` 时间槽标识规范化为 `bar_slot: str`：
  - 日线策略保持 `"YYYY-MM-DD"`（向后兼容现有 `strategy_tracking_daily` 记录或通过无损迁移增加 `bar_slot` / `bar_interval` 列）；
  - 30 分钟策略使用交易所时区闭合时刻 `"YYYY-MM-DDTHH:MM:00+08:00"`（每日 8 个闭合槽位）。
- `strategy_tracking_runs` 新增或扩展字段：`bar_interval`（`"1d"` \| `"30m"`）、`last_tracking_slot`、`gap_slots`（JSON 数组）。
- 幂等推进约束：仅当 `minute_bars` 存储对目标 `bar_slot` 的覆盖检查通过且 `bar_slot > last_tracking_slot` 时，在单事务中推进影子回放、落库快照并更新 `last_tracking_slot`。

## 9. 初始化三目录、AI 助手配置与 Web「AI 因子工坊」契约（对应 FR-5013、FR-5014、NFR-5007）

### 9.1 工作目录与 AI 助手配置结构

```python
@dataclass(frozen=True)
class WorkspaceDirectories:
    data_home: str
    factor_dir: str  # 默认 str(ensure_app_config_dir() / "factors")
    strategy_dir: str  # 默认 str(ensure_app_config_dir() / "strategies")


@dataclass(frozen=True)
class AIAssistantPublicView:
    """前端与日志可见的脱敏视图，严禁包含明文 api_key。"""

    configured: bool
    provider_preset: Literal["deepseek", "dashscope", "openai", "ollama", "custom"]
    base_url: str
    model: str
    api_key_masked: str  # 例如 "sk-****9a1f" 或 ""（本地免密模型如 Ollama）
    timeout_seconds: int = 60
    max_repair_rounds: int = 3
    max_tool_steps: int = 12
```

- 初始化向导步骤约定：
  - “运行环境”步（`REQUIRED`）统一接收并校验 `data_home`、`factor_dir`、`strategy_dir`；
  - “AI 助手配置”步（`OPTIONAL`，`is_step_skippable(...) == True`）支持保存连接配置、运行 `POST /wizard/ai/test` 连通性探测，或直接跳过进入系统。

### 9.2 Web 内置 Agent 受控白名单工具签名

Web Agent 循环通过标准 OpenAI Chat Completions `tools` 协议仅注册以下 6 个工具，底层直接调用与第 5 节 CLI 共享的 Python 服务函数：

| 工具名 | 输入参数摘要 | 安全约束与返回结构 |
| --- | --- | --- |
| `inspect_market_schema` | `{}` | 只读返回激活数据模式（正式/体验）、可用表与列名、复权约定、起止日期 |
| `search_registered_factors` | `{"query": str, "group": str \| None}` | 只读返回匹配因子的 `factor_id`、名称、分组、公式与预热期摘要 |
| `write_factor_plugin` | `{"factor_id": str, "code": str}` | 校验 `factor_id` 合法且非内置名，解析目标路径 ` (Path(factor_dir).resolve() / f"{factor_id}.py").resolve()` 严格位于 `Path(factor_dir).resolve()` 直接子级，原子写入并返回 `source_hash` |
| `run_factor_wind_tunnel` | `{"factor_id": str, "cutoff": str \| None}` | 在超时受限子进程执行 `FR-5002` 风洞校验与 `FR-5003` 正交性检查，返回 `PASS/FAIL/INCONCLUSIVE`、`first_difference` 及最高相关现有因子摘要 |
| `run_factor_ic_study` | `{"factor_id": str, "lookback": "1y" \| "3y", "holdings": list[int]}` | 要求该因子最近一次当前指纹风洞状态为 `PASS`，返回 RankIC、ICIR、十分位收益与 `as_of_date` |
| `save_preset_and_run_ablation` | `{"preset_id": str, "name": str, "baseline_preset_id": str \| None, "add_factor_id": str, "label_kind": str}` | 保存含新因子的 `FactorPreset`，可选触发与基准预设的固定条件消融回测并返回任务/报告标识 |

### 9.3 Web「AI 因子工坊」会话存储与路由

- 应用 SQLite 新增持久化表：
  - `ai_studio_sessions(session_id PRIMARY KEY, title, active_factor_id, status, created_at, updated_at)`
  - `ai_studio_messages(message_id PRIMARY KEY, session_id, role, content, step_cards_json, run_id, created_at)`
- 主要 Web 路由（均受管理员登录鉴权保护）：
  - `GET /factors/studio`：工坊主界面（左侧历史会话与已产出因子，右侧对话流、可视化阶段卡片与快捷操作按钮）；
  - `POST /factors/studio/sessions`：新建会话；
  - `POST /factors/studio/sessions/{session_id}/messages`：提交用户自然语言需求并启动异步受控 Agent 轮次；
  - `GET /factors/studio/sessions/{session_id}/stream`（或状态片段轮询端点）：增量渲染“生成草稿 → 风洞自检/自动修复（`1..max_repair_rounds`）→ IC 与查重结论卡片”；
  - `POST /factors/studio/sessions/{session_id}/cancel`：中断正在运行的模型请求与子进程风洞/检验任务。

## 2026-11-18 接口补充

- `ModelStore.save_version(key, model, metadata)` 只发布不可变 `key/artifact_hash`，不写 `latest.pkl`/`latest.json`。研究/回测/解释路径使用该入口；Paper 启动与决策前刷新仍解析正式 `latest` 或显式 `model_ref`。
- `StrategySession` 的 durable `last_signal_slot` 与 actual bar 存在性共同阻止同一闭合槽位重复回调；`process_next_open_30m_intents` 在 completed/last_bar 早退之前每 tick 独立推进。
- `AiRound` generation 在所有状态、消息和卡片提交前校验，而不是仅依赖当前 `_ACTIVE` 事件是否存在。
- `compute_future_close_return_labels` 使用权威交易日历的精确退出日；退出日无该证券行情返回 `null`。`_training_feature_panel` 只在完整成熟且符合历史资格的截面上训练。
