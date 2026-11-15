# 版本功能边界

源码树对应社区版（CE），分发包名为 `millionaire-ce`，运行时版本标识为
`millionaire-ce`。产品名 `millionaire` 同时覆盖 CE 与 `millionaire pro`；
专业版能力在产品文档中会明确标注。共享适配边界也可供独立维护的 millionaire pro
使用；专业版不在本包内，可通过版本门禁启用真实交易。

## CE 行为

- **实盘不可用**：实盘顶部/侧栏入口、实盘账户组件、实盘页面、gateway 设置页和
  实盘部署控制不出现在 CE 界面中。
- **直接请求被拒绝**：对实盘路由、实盘部署端点、实盘账户端点和 gateway 设置的直接
  请求返回 HTTP 503，并给出明确的 CE 不可用响应；即使旧配置数据库中保留了
  gateway 或 QMT 设置也一样。
- **初始化边界**：CE 保留共享的向导状态机，但把 gateway 设置步骤替换为仿真/纸面
  说明。提交 gateway 字段不能在 CE 中启用实盘 gateway。
- **仿真保留**：初始化和仿真/纸面账户、策略运行时仍可用。行情继续来自
  `MarketDataHub`，包括用户显式启用的行情扩展或一次固定 30 天的腾讯演示。
  腾讯默认关闭，到期后不能续期。
- **旧实盘运行时不恢复**：持久化的 `live` 运行模式不会恢复；相关策略运行时标记为
  `status=blocked`、`block_scope=edition`，gateway broker 不会启动。通用 gateway
  和实盘适配模块保留为适配边界，但 CE 不暴露也不注册它们。
- **风险程序注册表为空**：CE 不内置三重障碍、回撤卖出或成本止损程序；宿主必须显式
  注册自定义 `RiskProgramAdapter`。通用 `RISK_OVERLAY` 声明只通过该注册表解析。
- **部署调用失败**：直接调用 `deploy_to_live` 会在解析回测或接触 gateway broker 之前
  抛出 `FeatureUnavailableError("CE edition 暂不支持实盘交易")`。

版本门禁实现在 `quantide.config.features`。应用和运行时边界应使用
`supports_live_trading()` 或 `require_live_trading()`，不要删除共享 gateway 内部实现。

## 专业版合同测试

gateway 适配器和私有实盘运行时内部实现仍可在共享源码树中测试，但这些测试必须显式
启用开发版本覆盖。现有内部版本标识和测试标记是兼容契约，保留当前拼写：

```bash
QUANTIDE_ENABLE_EDITION_OVERRIDE=1 \
QUANTIDE_EDITION=zillionaire \
pytest tests/e2e -m private_only
```

普通 CE 测试排除 `private_only` 标记。CE 测试必须断言不可用异常或版本阻断，不能断言
实盘 broker 已启动。
