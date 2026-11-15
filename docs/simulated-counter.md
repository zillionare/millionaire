# 独立模拟柜台与三模式一致性

CE 提供一个独立 HTTP 模拟柜台，用于在没有真实交易柜台时验证策略和 Broker 接口。
它不连接券商、QMT 或 qmt-gateway，也不会让 CE 的实盘 UI/API 变为可用。
Millionaire 可以复用同一策略与 Broker 抽象，另行装配自己的真实柜台适配器。

启动一个具有独立持久化数据库的柜台进程：

```bash
millionaire-ce simulated-counter --database ./demo-counter.sqlite3 --listen-port 8131
```

进程只监听本机回环地址。SDK 适配器也拒绝外部地址，并检查服务器的模拟模式标识：

```python
import asyncio
import datetime

from quantide.core.runtime.simulated_broker import SimulatedBrokerAdapter

async def demo():
    broker = SimulatedBrokerAdapter("http://127.0.0.1:8131")
    try:
        now = datetime.datetime(2024, 1, 2, 10)
        broker.on_quote(now, {"000001.SZ": {"price": 10.0}})
        await broker.buy("000001.SZ", 100, price=10.0, order_time=now)
        print(broker.query_assets())
        print(broker.query_positions())
    finally:
        broker.close()

asyncio.run(demo())
```

策略代码仍通过 `self.broker` 的买卖、资金、持仓等接口工作；数据回放和运行时装配
决定传入 BacktestBroker、PaperBroker 或 SimulatedBrokerAdapter。
独立柜台按输入行情撮合，支持 T+1、部分成交、撤单、费用和稳定 client_order_id。
订单、成交和账户快照在独立 SQLite 事务里提交，进程重启保留这些事实。

默认演示账户本金为 10000；费用可通过 Python 工厂 `create_counter_app(path, **settings)`
配置（`principal`、`commission`、`stamp_tax`）。每个数据库对应一个演示账户，
复现实验时使用新的数据库路径；不要把历史实验当成新的初始资金。

严格验收入口：

```bash
python -m pytest tests/e2e/three_mode/test_ce_parity.py --runxfail \
  --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,::1,localhost
```

同一个策略在三个 Broker 上执行预定交易，并与明确列出的人工现金、持仓和费用
基准比较；另有重复提交、部分成交、撤单和柜台进程强制退出后的恢复用例。
这些用例纳入 CE release_gate，必须非空通过且没有 skip/xfail。

该结果验证的是固定撮合假设下的核心接口和账户事实一致性。真实柜台的交易规则、
网络故障和券商回报，需要由未来的柜台扩展单独验收。
