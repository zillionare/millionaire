# Mypy 修复第三轮审查

日期：2026-11-04。基准提交：`2cb4657`；对象：当前尚未提交的工作区。
本轮只审查并新增记录，没有修改实现或测试。

结论：上一轮前视偏差和布局兼容性问题均已修复，本轮没有发现新的运行时缺陷。
仍有一项类型清理遗留问题，见下文；属于上一轮 S2 的未完成部分。

## 唯一待处理项：S2 遗留 / P2

自身纯业务辅助函数仍存在可明确类型的 Any 声明。核心 broker、训练、优化和
初始化下载流程已建立类型，但以下遗漏不能用第三方 UI 库缺少类型声明解释：

| 文件与位置 | 函数 | 应补齐的契约 |
| --- | --- | --- |
| `quantide/web/pages/system/jobs.py:276` | `_run_snapshot` | 两个字符串参数、`Callable[[], str]` 操作回调、`None` 返回 |
| `quantide/web/apis/analysis/kline.py:25` | `bars_to_list` | 输入为 Polars DataFrame，当前为 Any |
| `quantide/web/apis/analysis/kline.py:48` | `add_ma_to_list` | 输入为 Polars DataFrame，当前为 Any |
| `quantide/web/pages/system/network.py:78` | `_is_admin` | 已直接返回 bool，声明仍为 Any |
| `quantide/web/pages/data_stocks.py:51` | `_get_active_tab` | 从 QueryParams 获取字符串，返回应为 str |
| `quantide/web/pages/data_stocks.py:55` | `_TabNav` | tab 参数应为 str；HTML 返回可单独处理 |
| `quantide/web/pages/live.py:374` | `_live_portfolios` | 注册表参数及账户列表/连接状态的返回元组 |
| `quantide/web/pages/live.py:390` | `_live_account_summary` | 账户元数据、账户 ID、所需 broker 资产能力及汇总字典 |
| `quantide/web/pages/trade_main.py:564` | `_resolve_broker_for_refresh` | 至少明确 `object | None`，与已有 `find_broker` 的契约一致 |

这些函数不是 HTML 节点构造器；保留当前声明会让相应数据处理与调用继续绕开静态校验。
应补齐后重新检查，不必因此批量限制 UI 渲染节点的动态返回类型。

本轮还对修改过的 Python 文件进行了 AST 盘点，完整原始清单在
`/tmp/millionaire-ce/review3-any-inventory.json`。清单包含现存直接 Any 参数与返回，
也包含基准版本已有声明及合理的第三方边界；不能把清单中每项都当作缺陷。
上表列出本轮确认仍需处理的、类型可以明确的业务辅助函数。

## 已解决问题复核

- **S1 前视偏差**：新增 `_execution_total_assets()`，下单按执行时的 open/close
  参考价估值，不再通过日终 `positions`/`total_assets` 读取收盘市值；日终净值仍按
  收盘价计算。`buy_percent` 和 `trade_target_pct` 均有收盘价扰动测试，结果通过。
- **S3 布局兼容性**：恢复真正的基类 `main_block()`，实例替换通过独立覆盖字段管理；
  普通覆盖、`super().main_block()`、实例回调和直接赋值的回归测试通过。
- **S2 初始化任务流程**：`start_wizard_sync`、任务进度、任务 ID、历史配置保存、
  runtime/admin/gateway 保存等流程已补齐日期、项目任务模型、AppState、Mapping、
  FT/Response 等实际类型；该部分已解决。
- 首轮撤单、PaperBroker 参数能力及生产质量门禁问题没有复发。

## 本轮重新执行的检查

- mypy：324 个源文件全部通过。
- 生产质量：Ruff/行宽、认知复杂度、重复和大小检查全部通过。
- 完整离线单元测试：4,767 passed、3 skipped，覆盖率 83.83%。
- CE 严格发布验收：20 passed，JUnit 校验无 skip/xfail。
- 仓库布局与 `git diff --check`：通过。
- 未执行三平台安装器、实体机部署或发布。

日志位于 `/tmp/millionaire-ce/`：`review3-mypy.log`、`review3-quality.log`、
`review3-unit.log`、`review3-acceptance.log`、`review3-acceptance.xml`。
