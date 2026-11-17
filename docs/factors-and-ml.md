# 因子与 LightGBM 策略

`MLMomentumReversalStrategy` 是日线截面选股示例。它把数据准备、因子计算、标准化、LightGBM 训练/排序、选股和调仓串起来，适合作为研究因子的起点。原生包包含 ML 依赖；源码安装需 `ml30m` extra，见[源码安装](installation.md)。

研究新因子时可先使用[极简因子分析](factor-analysis.md)，独立查看 Rank IC、分层前瞻收益和年度稳定性，再放进 ML 流程。自定义面板列无需先登记到 ML catalog 即可检验。

## 先运行原版

准备足够的历史日线、复权、证券池和辅助字段，扫描后选择该策略。第一次使用较短区间和较小证券池，保持其他参数不变，确认能完成训练、回测并重开报告。固定数据、源码、因子集和参数作为基准，再逐项比较改动。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `top_k` | `5` | 持有的排序前列证券数 |
| `universe_size` | `2000` | 证券池规模上限，不是训练样本总数 |
| `train_window` | `45` | 训练历史窗口；需另外留出因子预热与标签成熟时间 |
| `future_return_horizon` | `3` | 训练标签的未来交易日跨度；不是固定持有期 |
| `retrain_days` | `5` | 按交易日计算的重训间隔 |
| `fill_timing` | `auction_close` | 收盘集合竞价建模路径 |
| `features` | 已登记因子 | 不提供或空列表表示全部；不能用空列表表示完全不使用因子 |

示例按当前 `top_k` 调整组合：保留仍入选的持仓，卖出不再入选的可用持仓，买入新入选证券。它没有固定持有天数、三重障碍或内置私有风险程序。30 分钟的 `LightGBM30mSmokeStrategy` 是另一个策略，不能把本日线策略改周期运行。

## 不写代码也能研究已有因子

回测向导的因子步骤按组展示已登记因子，选择一个固定子集并运行。例如比较均线/偏离因子与量价因子，再用[参数优化](optimization.md)研究窗口与选股数量。在[预测解释](prediction-explanation.md)中查看某次决策的因子取值和贡献。

注意，截面标准化依赖同日证券池：同一股票在不同证券池中的标准化值可能不同。改变证券池和因子集是两个不同实验，不应混在一次归因结论里。

## 添加一个自己的因子

外部因子以单文件插件方式接入 `factor_dir`：文件导出 `FACTOR_PLUGIN`，声明因子 ID、周期、预热、必需列和计算函数，即可出现在因子选择和预设中。Web `/factors/studio` 可以按自然语言生成插件，`millionaire factor check` 和因子详情页会运行风洞；只有当前源码指纹为 `PASS` 的因子能进入预设和统计结论。插件文件失败不会影响内置因子加载，外部目录也不受内置字段黑名单限制。

如需把因子并入内置 ML 特征集并随源码发行，仍需在源码工作区修改因子模块并重新构建；策略训练、选股和下单流程可继续复用。原生包用户可以优先使用 `factor_dir` 插件；直接修改安装器管理的文件会在升级时丢失。

以下函数计算每只证券的三交易日动量，接收原始价格与累计复权因子：

```python
import polars as pl


def add_momentum_3d(bars: pl.DataFrame) -> pl.DataFrame:
    ordered = bars.sort(["asset", "date"])
    adjusted_close = pl.col("close") * pl.col("adjust")
    previous = adjusted_close.shift(3).over("asset")
    return ordered.with_columns(
        pl.when(previous > 0)
        .then(adjusted_close / previous - 1.0)
        .otherwise(None)
        .alias("custom_momentum_3d")
    )
```

每只股票头三行应为空；若四个交易日的调整后收盘价为 `10, 11, 12, 13`，第四行应为 `0.3`。两只股票价格量级不同也不能互相借用前三行。不要用负向 shift、未来回填或全区间拟合来消除预热空值。

把因子接入源码内置 ML 特征集的步骤：

1. 在源码 `quantide/factors/alpha.py` 的 `compute_alpha_features` 最终 `return out` 前增加 `custom_momentum_3d` 计算。这里的 `out.close` **已完成后复权转换**，应直接用 `pl.col("close")`，不能再次乘 `adjust`。
2. 将名称加入 `FEATURE_GROUPS`，并在 `FEATURE_DOCS` 写公式、预热、单位、可得时间和缺失值含义；`FEATURE_COLS` 从分组派生，无需再维护另一份独立列表。
3. 使用标准化函数生成对应 `_z` 列；当前训练和解释流程按同一个选中因子集取列。
4. 对小样本核对结果，重启服务、扫描并在回测因子列表中确认新名称。
5. 比较只增加该因子的回测与基准，进入参数优化和单次预测解释，确认该列确实参与。

例如，在已调整的 `out` 上使用这段表达式：

```python
previous = pl.col("close").shift(3).over("asset")
out = out.with_columns(
    pl.when(previous > 0)
    .then(pl.col("close") / previous - 1.0)
    .otherwise(None)
    .alias("custom_momentum_3d")
)
```

源码变更会改变因子版本，但旧回测不会变成新实验；重新生成报告并保留版本。自定义外部公式也要纳入版本记录，不能只改一个外部文件后继续引用旧缓存证据。

## 训练与解释的边界

标签是未来 N 个**权威交易日**的收盘收益，只用于已经成熟的训练样本；当前决策不能读取自身未来标签。退出日按交易日历精确推进，若该证券在退出日没有价格，标签保持缺失，不能顺延到下一个存在的行，也不能用停牌前旧价冒充退出价。`raw_return` 是未来收盘价相对信号日收盘价的原始收益；`excess_mean` 与 `cs_rank` 只在同一历史信号日的合格截面内计算，任一成员未成熟时该日整日不进入训练。历史训练截面还要按当日已知的 ST、上市天数、停牌和涨跌停资格判断，不能把后来 ST/退市的静态事实倒灌到过去。基金/自定义固定资产训练篮子必须声明其范围，并在篮子内逐日执行资格过滤。

研究/回测/解释实例生成的模型产物写入不可变实验引用，不推进 Paper 正在使用的 `latest` 指针；研究完成不会改变运行中仿真下一次决策加载的模型。信号用当时可见数据，收益标签与卖出规则分别处理。SHAP 解释模型分数，不证明因子具有因果作用，也不解释完整交易收益。源码树提供未来扰动、随机对照与关键变异的离线审计入口，但它不会自动覆盖任意自定义策略；见[策略与因子审计](strategy-audit.md)。运行成功或回测赚钱都不能冒充完整审计。
