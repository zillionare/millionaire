# Mypy 修复审查

审查日期：2026-11-04。基准：`2cb4657`；范围：当前工作区的 mypy 修复（尚未提交）。

结论：需要修改。全量 mypy 已通过，但存在行为回归、大量未建立真实类型契约的代码，以及生产质量门禁失败。
本次仅审查并记录问题，没有修改被审查的代码。

## 发现

### R1 / P1：撤销全部订单新增运行时异常

位置：`quantide/core/strategy.py:207–208`。

`BaseStrategy.cancel_all_orders()` 将底层结果强制转换为 `int`，但
`BacktestOrders.cancel_all_orders()`、`PaperOrders.cancel_all_orders()` 和旧网关实现返回
`None`。此前该调用可正常返回，现在会在底层撤单完成后抛出 `TypeError`。

已使用实际 `BacktestOrders` 方法复现：

```python
strategy = BaseStrategy(object.__new__(BacktestOrders), {})
await strategy.cancel_all_orders()
# TypeError: int() argument must be a string, a bytes-like object
# or a real number, not 'NoneType'
```

应统一撤单计数契约或显式兼容旧返回值，并用真实 broker 方法覆盖回归。

### R2 / P1：大量 Any 声明使自身模块绕过类型检查

代表位置：`quantide/core/strategy.py:19–20`、
`quantide/strategies/example/_ml_support.py:38–40`、
`quantide/service/macos_menu.py:14`。

相对于基准，通过 AST 统计，本次净新增 724 个直接标为 `Any` 的参数声明、590 个
直接标为 `Any` 的返回声明；净新增 270 个所有非 self/cls 参数均为 `Any` 的函数。
这些范围包括训练数据处理、参数优化、策略发现和路径操作等可以明确类型的自身代码，
不能用第三方 UI 库缺少 stub 解释。

尤其是将 `Strategy.broker` 从 `BrokerPort` 改为 `Any`，再将交易结果 cast 为
`ExecutionResult`，会使策略调用的方法名、参数和返回值失去静态校验。
这不满足先前约定的“自身模块必须有真实类型声明”。应补齐适合策略使用的协议、
数据结构和函数签名；动态第三方边界的 Any 应限制在适配层。

### R3 / P2：强制转换掩盖 PaperBroker 的真实接口不兼容

位置：`quantide/service/strategy_runtime.py:344–345`；同类问题也在
`quantide/web/pages/accounts.py:691`。

注释已明确知道 `PaperBroker` 不接受 `BrokerPort` 声明的额外参数，却用
`cast(BrokerPort, port)` 消除错误。`PortBackedBroker` 仍将这些参数直接转发，
因此符合其公开签名的调用仍会失败。已通过实际包装类和实际 PaperOrders 方法复现：

```python
port = object.__new__(PaperBroker)
handle = PortBackedBroker(port, "review", BrokerKind.SIMULATION)
await handle.buy("000001.SZ", 100, fill_timing="next_open")
# TypeError: PaperOrders.buy() got an unexpected keyword argument 'fill_timing'
```

这是此前未解决、此次被 cast 隐藏的契约问题。应统一支持的参数及执行语义，
或显式划分能力接口并校验不支持的选项，不能仅依靠 cast。

### R4 / P2：MainLayout 不再支持子类覆盖 main_block

位置：`quantide/web/layouts/main.py:391`。

构造函数无条件赋值 `self.main_block = self._default_main_block`，覆盖了子类的同名方法。
原有实现明确支持子类重写，以及在实例上设置自定义内容。现在继承类即使实现了
`main_block()`，仍会显示默认占位内容。

已复现：

```python
class CustomLayout(MainLayout):
    def main_block(self):
        return "CUSTOM-CONTENT"

layout = CustomLayout(title="review")
layout._resolve_main_content()
# 返回“这是页面的主要内容区域。”，而非 CUSTOM-CONTENT
```

应保留方法覆盖机制，并为可替换的渲染回调建立类型契约。

### R5 / P2：生产质量门禁仍失败

`python -m scripts.check_quality` 返回非零，具体诊断：

- `quantide/web/pages/strategy.py:661`：16 个局部变量，预算 15。
- `quantide/web/pages/trade_main.py:301`：17 个局部变量，预算 15。
- `quantide/data/models/strategy_config.py:38` 与
  `quantide/core/strategy_metadata.py` 重复定义元数据字段，触发重复代码门禁。

最后一项来自此次将共享字段声明改为复制字段。应保留明确类型并复用公共定义；
不能提高预算或关闭检查。当前状态尚不能通过正式提交/CI 的质量门禁。

## 验证证据

- `.venv/bin/python -m mypy quantide`：324 个源文件，无诊断。
- 完整离线单元测试：4,758 passed、3 skipped；覆盖率 83.85%。
- 严格 CE release_gate：20 passed；JUnit 检查确认无 skip/xfail。
- 生产质量：Ruff/行宽通过，认知复杂度通过，重复及大小检查阶段失败，见 R5。
- 仓库布局与 `git diff --check`：通过。
- R1、R3、R4 已在隔离临时配置下执行上述实际接口复现。

原始日志留在 `/tmp/millionaire-ce/`：
`review-mypy-unit.log`、`review-mypy-quality.log`、
`review-mypy-acceptance.log`、`review-mypy-acceptance.xml`。
未验证三平台安装包和实体机部署；本审查没有部署或发布。

## 建议处理顺序

先修复 R1 和 R4 的行为回归并补充回归测试，再解决 R3 的实际接口差异。
按模块完成 R2 的真实类型声明，最后修复 R5 并重跑完整质量门禁、mypy、单元测试和验收。
现有测试通过不能替代上述已复现问题的修复。
