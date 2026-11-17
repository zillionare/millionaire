# 风险程序扩展边界

CE 保留通用 `RiskStrategy` 契约和 Broker 级回测风险叠加生命周期。它不内置三重障碍、回撤卖出或成本止损程序，默认注册表为空。内置三重障碍程序属于 millionaire pro；宿主维护的学习型程序不在 CE 源码树内，也不会进入 CE 的自动发现、运行器回退或选择界面。

回测配置保存有序的 `risk_programs` 数组。每一项包含显式注册的适配器 ID、规范化参数和确定性的优先级。空数组是合法值，也是宿主未安装适配器时的正常结果。`allow_same_bar_repurchase` 与它一起保存，并透传给通用叠加/组合边界；Broker 仍会执行 A 股 T+1 可用性检查。

宿主包通过 `quantide.service.risk_programs.register_risk_program`（或导出的 `risk_program_registry`）注册 `RiskProgramAdapter`。适配器提供兼容性检查、默认参数、回测叠加工厂和/或实盘 `RiskStrategy` 工厂。CE 运行时不会按 ID 导入私有类，也不会把发现的 `RiskStrategy` 在没有适配器的情况下当作可回测策略。

已注册的叠加层按规范化优先级通过 `CompositeRiskOverlay` 执行。Paper/实盘构造使用同一组选中 ID 和参数。旧配置中已不存在于注册表的 ID 会显示为不可用/阻断，并使启动校验失败关闭；不会静默替换为另一个程序。
