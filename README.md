# Millionaire

面向 A 股的开源量化框架：让用户专注于因子和策略研究，复用数据、回测、参数优化、
预测解释与持续仿真的完整流程。采用 MIT 许可证。

Millionaire 是社区版与专业版的合称；本仓库是社区版（CE），包名和命令均为
`millionaire`，专业版专属功能明确称为 millionaire pro。

## 为什么使用它

- **同一策略切换执行模式**：策略通过统一 Broker 接口工作，复用到回测、仿真和
  HTTP 模拟柜台。CE 不开放真实交易；millionaire pro 或用户宿主扩展可装配自己的券商适配器。
- **用户可适配自己的柜台**：HTTP 将策略与柜台进程分开。用户可以按接口契约自行
  适配券商，也可以让 AI 辅助编写，再用模拟柜台和验收用例验证适配结果。
- **统一数据格式与 adapter**：日线、30 分钟、日历、证券列表和行情扩展走统一边界，
  数据供应商差异由适配层处理。
- **策略周期固定**：日线或 30 分钟是策略本身的属性，运行时拒绝改成另一周期，
  策略作者无需处理任意周期组合。
- **明确的成交时序与交易规则**：支持 cheat-on-close、next-open 等时序；交易层处理
  T+1、可用持仓、资金与涨跌停撮合条件。具体数据前提见[执行与防呆](docs/execution.md)。
- **自带 LightGBM 研究流程**：选择已有因子，复用训练、选股、调仓、参数优化和 SHAP
  预测解释；新增因子的当前接入步骤见[因子与 LightGBM](docs/factors-and-ml.md)。
- **先检验因子，再训练模型**：[极简因子分析](docs/factor-analysis.md)提供 Rank IC、
  十分位前瞻收益和分年结果，可直接研究自定义面板中的因子列。

## 从这里开始

1. [了解本版能力和边界](docs/scope.md)。
2. [下载并安装](docs/native-installation.md)，支持 macOS ARM64、Ubuntu x86_64、Windows x64。
3. [初始化与数据准备](docs/initialization.md)，设置管理员密码和 Tushare 数据源。
4. [完成第一次回测](docs/backtesting.md)，阅读报告，再[转入仿真](docs/paper-trading.md)。

[在线文档](https://zillionare.github.io/millionaire/)随默认分支发布；
功能开发分支的文档可能尚未部署。如果站点仍显示旧版，可直接在 GitHub 仓库阅读
[`docs/`](docs/)（GitHub 会渲染 Markdown），或在源码目录运行 `mkdocs serve`
离线查看。站点不依赖第三方字体或脚本资源，代理环境不应出现渲染挂起。
安装包以 [GitHub Releases](https://github.com/zillionare/millionaire/releases)
实际列出的产物为准，旧版本的 Release 不代表已包含本分支的新安装器。

## 安装后

原生包自带 Python 和固定版本依赖。Windows 使用图形安装向导，macOS/Ubuntu 通过
命令行安装；安装后由操作系统管理后台服务。macOS 自动显示菜单栏 **M** 控件，
Windows 自动显示系统托盘控件，两者均随登录启动，可启停服务并打开浏览器。
Ubuntu 桌面提供窗口式控制器。
退出控件不会停止后台服务；退出后可以重新打开：

```bash
millionaire control
```

默认网页地址为 `http://127.0.0.1:8130`。首次启动进入 wizard，没有默认管理员密码。
Linux 系统服务的启停命令需要 sudo；Windows 会在需要时请求管理员权限。

## 实时行情和版本范围

初始化先检查所选历史数据源：Tushare 需要 token 与对应接口权限，BaoStock 日线免 token；
也可一键启用约 3.8 MB 的合成体验数据包，离线验证研究、回测和 SHAP 链路。
已有可接入的官方实时快照权限时自动选用，跳过演示配置。全部配置完成后，
单独确认并开始历史数据下载。

腾讯演示行情**默认关闭**，wizard 可显式启用一次固定 **30 天**演示。
关闭、重启、升级均不续期，到期自动关闭；后续通过自己的[行情扩展](docs/quote-extensions.md)接入。
历史数据下载与该实时行情选项相互独立。

CE 不内置三重障碍、回撤卖出、成本止损或私有风险程序，风险程序注册表默认是空的。
源码树提供 SHAP 预测解释、账户事实[收益归因](docs/prediction-explanation.md)和离线
[策略/因子审计](docs/strategy-audit.md)；它们不是收益保证，也不是对所有策略/柜台的
安全证明。30 分钟影子按闭合 bar 回放；数据源能力矩阵等后续方向见[版本状态](docs/roadmap.md)。

## 开发与贡献

包名是 `millionaire`，Python 导入名为 `quantide`。源码开发要求 Python 3.13：

```bash
python3.13 scripts/install.py --ml30m
.venv/bin/millionaire --open
```

Windows 使用 `py -3.13 scripts\install.py --ml30m`；激活虚拟环境后可直接调用命令。
完整步骤、源码专用的离线 stub、质量预算与 CI 门禁见
[源码安装](docs/installation.md)、[开发者验收](docs/developer-acceptance.md)和
[质量管理](docs/quality.md)。

仓库布局、临时构建/报告路径及推荐的模块命令见[开发目录约定](docs/project-layout.md)。
