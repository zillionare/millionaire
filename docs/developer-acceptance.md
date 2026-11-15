# 开发者使用与基础验收指南

本文档面向仓库开发者，而不是最终用户。

代码质量预算、三平台安装/测试、离线测试隔离及发布硬门禁见
[代码质量与发布门禁](quality.md)。发布 CI 使用 `--runxfail` 并拒绝跳过，
不能用下列普通 pytest 命令中的 xfail/skip 作为发布通过证据。

目标只有两个：

1. 说明本地如何启动和使用当前系统。
2. 说明在提交前，开发者至少应该完成哪些基础验收。

## 1. 适用范围

本文档覆盖当前仓库里最常见的两类开发动作：

1. 修改策略、交易链路或页面后，先在本地验证核心流程没有断。
2. 需要在不连接真实 Tushare、真实 qmt-gateway/QMT 的情况下，使用 stub 走通
   开发态纸面/仿真验证。

本文档不替代仓库中的测试用例和 CI 发布门禁；后者仍然是工程约束和发布态验收基线。

## 2. 环境准备

本项目使用标准 Python 虚拟环境（**不再使用 conda**）。

首次准备环境：

```bash
# 1. 创建虚拟环境（仅首次需要）
python3.13 -m venv .venv --prompt=millionaire-py3.13

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 安装 Poetry（如果尚未安装）
pip install poetry

# 4. 通过 Poetry 安装项目依赖
poetry install
```

如果当前 shell 没有激活环境，则在命令前用 `.venv/bin/` 前缀直接调用：

```bash
.venv/bin/python -m pytest ...
.venv/bin/uvicorn quantide.app:app --reload
```

或者重新激活：

```bash
source .venv/bin/activate
```

开始验证前，默认你已经完成一次初始化，至少具备：

1. 可用的 `app_home`。
2. 已完成基础登录/初始化状态；管理员密码由初始化向导设置，系统不提供默认密码。
3. 仓库测试资产和本地 SQLite 可正常访问。

## 3. 本地启动方式

### 常规启动

```bash
uvicorn quantide.app:app --reload
```

或者使用仓库自带的启动脚本：

```bash
./start.sh
```

### 开发态 Stub 启动

```bash
QUANTIDE_ENABLE_DEV_STUBS=1 uvicorn quantide.app:app --reload
```

或：

```bash
./start.sh --stub
```

启用 `QUANTIDE_ENABLE_DEV_STUBS=1` 后，当前进程会：

1. 启动本地 gateway stub，并把 effective gateway 配置指向它。
2. 用 fixture-backed 数据替代默认 Tushare fetcher。
3. 在已完成初始化的前提下，开放开发态的 simulation/paper 链路；CE
   不开放 live 链路。

注意：

1. 这个开关只覆盖当前进程的 effective settings，不会改写数据库里持久化的 gateway 配置。
2. 系统维护页的"连接测试通过"只能说明表单里的地址可连通，不等于当前 runtime 已经切换到那套配置。
3. 如果你看到旧的 dev server 日志，不足以说明当前 stub 模式失败；应以本次实际启动命令对应的日志为准。

## 4. 提交前最小自动化验收

### 全量 release gate

```bash
.venv/bin/python -m pytest -m "e2e and release_gate" tests/e2e -q
```

用途：确认已经纳入发布态证据的 E2E 主链路没有回归。

### 三模式一致性定向核查

```bash
.venv/bin/python -m pytest tests/e2e/three_mode/test_ce_parity.py -q
```

用途：对同一个策略分别运行回测、Paper 和独立 HTTP 模拟柜台，比较订单、成交、
持仓、现金和每日权益。柜台使用独立数据库，不依赖 QMT 或真实交易接口。
用例包含零费用和非零费用的人工核算基准，以及重复提交、部分成交、撤单、
柜台进程强制退出后恢复。详见[模拟柜台与一致性](simulated-counter.md)。

### 开发态 stub UI 流程核查

```bash
.venv/bin/python -m pytest tests/e2e/web/test_dev_stub_mode.py -q
```

用途：确认开发态 stub 不是"只能启动"，而是真能支撑策略页、回测报告、转仿真
和纸面交易入口路径。

## 5. 提交前最小手工验收

当改动涉及策略页、交易页、runtime 装配、gateway/tushare stub 或导航时，至少手工检查下面几项：

1. 使用 `QUANTIDE_ENABLE_DEV_STUBS=1` 启动后，日志能确认本地 stub 已启动；
   CE 不要求配置真实 live gateway。
2. 策略页能正常打开，已有回测报告时，"转仿真"不会被错误禁用；"转实盘"
   在 CE 中应保持隐藏或不可用。
3. `/trade/simulation` 可访问。
4. `/trade/live` 在 CE 中返回明确的不可用响应（当前为 HTTP 503）。
5. 旧入口 `/strategy/live` 不得绕过 CE 的 live feature gate。
6. 如果本次改动涉及交易逻辑，至少再跑一次 backtest/paper parity 定向用例。

millionaire pro 专属的 gateway/live UI 合同用例使用 `private_only` marker，不能作为
CE 验收证据。需要验证这些共享内部实现时，必须显式启用
`QUANTIDE_ENABLE_EDITION_OVERRIDE=1 QUANTIDE_EDITION=zillionaire`；普通 CE
运行不应启动 live broker，也不应恢复持久化的 live runtime。

## 6. 如何理解"验收通过"

开发中最容易误读的是下面两件事：

1. `release_gate accuracy passing` 不等于"整个版本已经发布就绪"。它只说明当前已纳入 gate 的准确性链路通过。
2. `dev-stub manual flow passing` 不等于"真实生产 gateway 已完全验证"。它只说明 controlled stub 场景下的开发流程是通的。

因此，开发者应该同时关注三类证据：

1. release gate 是否通过。
2. backtest/paper parity 是否通过。
3. 本次改动影响到的手工 UI 流程是否可走通。

## 7. 结果去哪里看

1. 自动化结果首先看终端里的 pytest 输出。
2. CE parity 的人工现金与持仓基准在测试中明确列出，不从被测实现生成。
3. 三模式 parity 的测试入口在 `tests/e2e/three_mode/test_ce_parity.py`。
4. 发布态验收缺口与放行判断以 release gate 和 CI 结果为准。

如果你只想回答一个最小问题："我这次改动有没有把三模式主链路弄坏？"

优先顺序是：

1. 跑三模式 parity。
2. 跑受影响的 release gate 切片。
3. 用 dev-stub 手工走一遍受影响页面。
