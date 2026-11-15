# 月线均线策略

`MonthlyMAStrategy` 是真正的月线示例，不是日线策略里的“月末 if”。它固定声明：

```python
BAR_INTERVAL = "1M"
short_window = 3
long_window = 12
```

运行参数不能把周期改成 `1d`、`30m` 或小写 `1m`；`1M` 表示月线，`1m` 表示分钟线，二者不能混用。
3 月/12 月均线比较至少需要 13 根闭合月线，预热不足时不交易。

## 聚合口径

`quantide.service.monthly_bars.aggregate_monthly` 从日线和权威交易日历生成：

- 实际月末交易日和该 bar 的可用时间；
- 首日开盘、区间最高/最低、末日收盘、成交量/额求和；
- 已闭合、形成中、缺月末三类状态；
- 缺月不补造价格；停牌导致月末缺失时标记不完整，不进入信号。

只有闭合月线进入 3/12 均线。形成中月份单独保留，不参与已完结信号或训练。

## 执行与恢复

信号记录信号月、方向和下月首个实际交易日开盘执行时间。月末回调只持久化意图，不改变
账户；`BacktestRunner` 在下一交易日 9:30 运行执行事件，Paper/柜台在目标日期行情到达后
才撮合并提交。目标日期前不会产生未来成交，重启后未完成意图在下一个可用执行事件补交。
`MonthlyIntentStore` 以“资产+信号日+方向”为幂等键去重；回测、Paper 和 HTTP 模拟柜台
共用 `execute_intent` 提交路径，同一幂等键同时作为柜台订单身份，已提交或已完成的意图
不会重复下单。`tests/e2e/three_mode/test_ce_parity.py` 在信号月末、次日开盘等边界对拍
三条路径的订单、现金和持仓结果。

## 最小示例

```python
from quantide.service.monthly_bars import aggregate_monthly, monthly_ma_signals

series = aggregate_monthly(daily_panel, trading_days, as_of=date.today())[asset]
signals = monthly_ma_signals(series, trading_days)
for signal in signals:
    print(signal.signal_date, signal.execute_date, signal.direction)
```

优化与报告必须保留 `1M` 周期，不得统一转小写或把一个月折算成 20/30 个交易日。
