# 编写和发现策略

策略继承 `BaseStrategy`，通过 `self.broker`（或基类的买卖方法）访问账户和提交订单。
策略不需要自行连接数据库、券商 SDK 或解析行情供应商响应。

## 先复用已有示例

先创建一个可写的用户策略目录，在策略页通过“配置扫描目录”指定其**绝对路径**。
再点“复制示例策略”，成功后选“立即扫描”或“扫描策略列表”。
扫描始终包含内置示例，也会合并用户目录；文件语法、导入或配置错误会显示诊断。

把新策略放在安装目录之外，升级时保留该目录。Ubuntu 后台服务默认不能访问你的
个人主目录，建议在 `/var/lib/millionaire-ce` 下准备服务账户可读的策略目录。
复制内置示例后修改类名，避免和内置类同名；模块修改后重启服务并重新扫描。

## 一个可运行的日线配置示例

将以下内容保存为用户策略目录中的 `my_daily_ma.py`：

```python
from quantide.strategies.example.dual_ma import DualMAStrategy


class MyDailyMAStrategy(DualMAStrategy):
    """复用双均线逻辑，并公开证券、投资额和明确成交时序。"""

    BAR_INTERVAL = "1d"

    @staticmethod
    def default_config():
        return {
            "fast": 5,
            "slow": 20,
            "symbol": "000001.SZ",
            "invest": 100000,
            "fill_timing": "next_open",
            "bar_interval": "1d",
        }
```

扫描后应出现 `MyDailyMAStrategy`，回测向导能看到这些默认参数。运行时保留日线，
按[回测教程](backtesting.md)准备均线预热数据。`next_open` 表示将信号意图放到下一
可交易 bar 执行；不要把这个类运行成 30 分钟策略。

## 自己编写逻辑时

常用生命周期是 `init()`、`on_start()`、`on_bar(tm)`、`on_day_open(tm)`、
`on_day_close(tm)` 和 `on_stop()`。异步下单要 `await`，使用传入的 `tm`，
不要在回测决策里调用电脑当前日期。

历史查询可用 `self.get_bars(asset, count, tm, "1d", include_forming_bar=False)`。
先检查数据量和有效值，再计算信号；按证券分组做滚动，预热不足应明确不交易。
日志用 `self.log(...)`，研究曲线可通过 `self.record(...)` 记录。

委托数量是股，资金是元。检查总持仓和可用持仓的区别；下单结果可能没有成交，
不能在策略里自行扣现金或虚构持仓。卖出条件、选股池和成本假设应写入策略说明。
不同 Broker 的集合视图与更完整 DTO 见 `quantide/core/ports/broker.py`，
新增宿主适配器应遵守对应合同。

## 提交运行前

核对周期、数据覆盖、预热、复权、形成中 bar、交易时序、费用、重复信号与恢复行为。
先小区间回测，再比较参数及仿真。AI 编写的策略也遵循相同要求，见
[AI 辅助开发](ai-development.md)。CE 没有内置三重障碍等风险程序可供默认启用。
