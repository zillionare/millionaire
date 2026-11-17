# 用户风控扩展（可选）

CE 启动时的 `risk_program_registry` 默认是空列表 `[]`，不内置三重障碍、移动回撤卖出、成本止损或历史私有风险程序。用户可以在服务外编写自己的风控适配器，并通过显式启用的扩展通道加载；未启用时，服务不会导入或执行用户风控代码。

## 启用与查看

扩展文件放在配置目录下的固定位置：

```text
<app_config_dir>/extensions/risk_extensions.py
<app_config_dir>/extensions/risk-extensions.json   # {"enabled": true|false}
```

使用 CLI：

```bash
millionaire risk-extension status
millionaire risk-extension enable --copy-example
millionaire risk-extension disable
millionaire risk-extension status --json
```

`enable --copy-example` 在扩展文件不存在时，把只读教学模板复制到用户扩展目录；已有文件不会被覆盖。`enable` 只保存启用状态，不会在 CLI 进程中导入用户代码。状态变更在服务重启后装配生效。系统维护 → 数据源页面也提供“复制模板并启用”“启用”和“停用”入口，并显示当前进程已加载的程序 ID。

启用但文件缺失、JSON 状态字段不是布尔值、扩展文件导入失败或注册冲突时，服务启动会明确报错，不会静默回退到其它风险程序。

## 扩展入口

用户文件必须导出：

```python
from quantide.service.risk_programs import RiskProgramAdapter, RiskProgramRegistry


def register_extensions(registry: RiskProgramRegistry) -> None:
    registry.register(
        RiskProgramAdapter(
            id="my.example.risk",
            default_params={},
            overlay_factory=MyBacktestOverlay,
            live_strategy_factory=MyLiveRiskStrategy,
        )
    )
```

- `overlay_factory(params)`：返回回测 Broker 级叠加层，至少实现 `check_open`、`check_intraday`、`sync_positions`。用于处理已有持仓的退出策略或在宿主下单前安装通用买入约束。
- `live_strategy_factory(broker, params)`：返回 `RiskStrategy` 实例；Paper/实盘会话在每个 tick 的宿主信号前调用 `on_check`。
- 回测叠加层和仿真风控可以共享纯函数与参数，但两者都必须显式提供；只提供一侧时，另一模式会明确拒绝。

Broker 提供通用的 `set_buy_guard(key, guard)`、`clear_buy_guard(key)` 与风险计算辅助方法。买入 guard 在 `buy`、`buy_amount`、`buy_percent` 和 `trade_target_pct` 的最终下单前按注册顺序执行，返回整手股数或 `0` 拦截。该接口只约束买入，不改写已成交持仓，也不包含私有止盈止损价格线。

## 教学模板

源码附带 [`quantide/assets/examples/risk_single_asset_cap.py`](https://github.com/zillionare/millionaire/blob/main/quantide/assets/examples/risk_single_asset_cap.py)，注册 ID 为 `example.single_asset_weight_cap`，默认参数为 `{"max_weight": 0.25}`。它按账户总权益限制单标的买入后的目标市值：

```text
当前持仓市值 + 本次买入金额 <= max_weight * 总权益
```

超出预算时按 100 股整手向下截断；预算不足以买入一手时返回 `0` 拦截开仓。它同时提供回测 `overlay_factory` 和 Paper `live_strategy_factory`，不包含止盈、止损或三重障碍逻辑。模板是可读、可复制的教学起点，生产使用前应自行审查参数与风控假设。

启用模板后，在回测或 Paper 配置中选择 `example.single_asset_weight_cap`，并设置 `max_weight`。若未选择该风险程序，即使扩展已加载也不会生效。
