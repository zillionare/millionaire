# Mypy 修复第二轮审查

日期：2026-11-04。提交基准仍为 `2cb4657`，审查对象是当前尚未提交的工作区。
本次只新增审查记录，没有修改实现或测试。

结论：需要修改。上一轮 R1、R3 和 R5 已解决；R2 与 R4 尚未完全解决，
并在新增的 ShadowBroker 方法中发现一处前视偏差。

## 需要处理的问题

### S1 / P1：next-open 百分比下单使用了尚未发生的收盘价

位置：`quantide/service/shadow_broker.py:389`，同类调用在第 422 行。

新增的 `buy_percent()` 和 `trade_target_pct()` 使用 `self.total_assets` 计算目标金额，
而该属性经过 `positions`，以回放日的 **close** 更新全部持仓市值。
`StrategyTaskManager._process_shadow_intents()` 会在 `next_open` 回放中调用这些方法，
订单时间是当天 09:25，成交价格取 open。因此订单数量依赖当天下午才会出现的收盘价。
这会破坏仿真/回测对照，也构成前视偏差。

已执行未来扰动复现，直接使用实际 ShadowBroker 和成交实现：

- 现金 10,000；已持 A 股票 1,000 股；A、B 的开盘价均为 10。
- 模式 `next_open`；佣金、最低佣金、税费、滑点均设为 0。
- 调用 `buy_percent(B, 0.1, order_time=当天09:25)`。
- A 当日收盘价为 10 时，B 买入 200 股。
- 只把 A 的当日收盘价扰动为 20，B 买入 300 股。

复现通过给 `_price_cache` 和 `_open_cache` 注入已知数据，不访问外网，也不修改行情文件。
价格扰动是审计手段；开盘时已知的所有输入完全相同，订单结果应当不变。

应区分执行时估值与日终估值：next-open 下单只能使用当时可用的价格；
日终净值仍应按收盘价估值。新增覆盖 `buy_percent` 与 `trade_target_pct` 的未来扰动测试。

### S2 / P1（上一轮 R2 遗留）：自身业务流程仍用 Any 代替实际类型

代表位置：`quantide/web/pages/wizard_sync.py:21`、第 49、59 行，
`quantide/web/pages/init_wizard.py:433`。

核心训练、优化和 broker 类型已显著改善；但自身初始化和任务流程仍存在整段 Any 声明：

```python
def start_wizard_sync(start_date: Any) -> Any: ...
def _apply_task_progress(task: Any) -> Any: ...
async def _wait_for_pipeline(task_id: Any) -> Any: ...
async def _save_history_step(form_dict: Any, step: Any) -> Any: ...
```

这些函数的参数实际分别是日期、项目任务模型、任务 ID、表单及步骤编号，
并非缺少 stub 的第三方 UI 对象；前三者等函数还可明确声明 `None` 返回。
因此“自身模块具备真实类型声明”的要求尚未完成。

AST 统计相对基准仍净新增 102 个直接 Any 参数、398 个直接 Any 返回。
这个数量不能全部当成错误：动态 UI 渲染边界允许有针对性的 Any；
应重点清理以上自身逻辑，以及同类可确定类型的流程，不能只依据 mypy 变绿认定完成。

### S3 / P2（上一轮 R4 遗留）：布局的 super().main_block() 扩展方式仍然失效

位置：`quantide/web/layouts/main.py:510`，以及第 391–395 行的实例绑定逻辑。

普通子类覆盖与实例回调已恢复，但原有基类 `main_block()` 被重命名成
`_default_main_block()`，没有保留原名称。因此原本合法的组合扩展会报错：

```python
class ComposedLayout(MainLayout):
    def main_block(self):
        return super().main_block()

ComposedLayout(title="review")._resolve_main_content()
# AttributeError: 'super' object has no attribute 'main_block'
```

以上已实际执行复现。应保留基类原有可调用的 `main_block` 扩展入口，
同时支持实例替换；测试需覆盖子类扩展父类内容的情况。

## 上一轮各项状态

| 项目 | 本轮结果 |
| --- | --- |
| R1：撤单返回 None 导致 TypeError | 已修复；有回归测试 |
| R2：大量 Any 掩盖自身接口 | 部分修复，见 S2 |
| R3：PaperBroker 强制转换掩盖参数差异 | 已移除 cast；显式校验不支持的选项，并提示使用 next-open proxy |
| R4：布局子类覆盖失效 | 普通覆盖已修复，父类组合仍失败，见 S3 |
| R5：局部变量及重复代码门禁失败 | 已修复，生产质量扫描通过 |

## 重新验证

- mypy：324 个源文件全部通过。
- 完整离线单元测试：4,762 passed，3 skipped；覆盖率 83.78%。
- 严格 CE release_gate：20 passed；JUnit 验证无 skip/xfail。
- 生产质量：Ruff/行宽、认知复杂度、重复和大小检查均通过。
- 仓库布局及 `git diff --check`：通过。
- S1 和 S3 在临时配置下实际执行复现；不是推测性诊断。
- 未进行三平台安装包或实体机部署验收。

原始输出位于 `/tmp/millionaire-ce/`：`review2-mypy.log`、`review2-quality.log`、
`review2-unit.log`、`review2-acceptance.log`、`review2-acceptance.xml`。
