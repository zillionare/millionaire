# 30 分钟 LightGBM 示例合同

`LightGBM30mSmokeStrategy` 是受支持 30 分钟路径的生命周期冒烟示例。LightGBM 是策略的硬运行时依赖：`lightgbm` 包不可用时，策略构造会显式报错。

缺少依赖时，策略不得改用确定性分数、不得完成回测，也不得产生影子/仿真结果。运行时和回测失败会持久化，并通过运行时状态和系统风险事件界面暴露。

使用前安装可选依赖 `ml30m`：

```text
python3 scripts/install.py --ml30m
```

或使用已激活环境：

```text
python -m pip install -e ".[ml30m]"
```

该示例只消费已闭合的 30 分钟 bar，不读取形成中 bar；它用于验证初始化、历史读取、特征构造、最小模型调用和关闭流程，不代表可盈利的分钟策略。
