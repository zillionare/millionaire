# macOS 菜单栏服务控件

日期：2026-11-03。

## 交付行为

macOS 原生包增加 Cocoa 菜单栏应用，显示 M 标识，提供状态、启动/停止服务、
打开网页、打开日志和退出控件。默认用户安装后自动显示，之后随用户登录启动；
Finder 的 `~/Applications/Millionaire CE.app` 和 `millionaire-ce control` 可重新打开。
关闭控件不停止后台服务。系统 LaunchDaemon 安装只创建 `/Applications` 入口，
不为 root 注册登录 GUI；有桌面的用户手动打开后，启停系统服务通过系统管理员授权执行。

菜单进程由单独的 `<service-label>.controller` LaunchAgent 管理，不设置 KeepAlive，
以便用户退出后当前会话保持退出。服务继续由原有 LaunchAgent/LaunchDaemon 管理。
控件读取安装时保存的服务名称、域、CLI 和实际日志目录，支持自定义路径及带空格的路径；
升级重建菜单配置和快捷方式，卸载清理菜单任务与本安装拥有的快捷方式。

Swift/Cocoa 仅在 macOS 构建阶段编译，最终安装包附带二进制，用户无需安装 Xcode，
也未增加 Python GUI 依赖。原生控件最低编译目标为 macOS 13 ARM64；
本次实机验收系统为 macOS 15.6.1 ARM64，不等同于额外验收其它系统版本。
Ubuntu 继续使用现有窗口式控制器。Windows 随后的托盘实现及实体机验收见
[Windows 系统托盘记录](WINDOWS-TRAY-IMPLEMENTATION.md)。

## 验收证据

- 完整 Python 生产质量扫描通过：Ruff、认知复杂度、重复代码及文件/方法规模。
- 23 项相关测试通过，无 skip/xfail；覆盖菜单任务注册/清理/安装失败、CLI、Windows 服务管理、
  日线影子跟踪及已有 POSIX 启动器。
- 严格文档构建、wheel/sdist 内容校验、Shell 语法、目录布局和 diff 空白检查通过。
- 原生 macOS 安装验收通过：干净安装、Cocoa 菜单事件驱动的启停/网页/日志/退出操作、
  退出菜单前后后台服务 PID 不变、进程强杀恢复、同包升级、卸载保留用户数据与扩展。
  菜单验收驱动与发布应用编译相同的控件类，在独立测试服务上操作，并实际退出安装的应用。
- 首次验收发现 launchd 的运行态早于 HTTP 就绪；修正验收等待条件后重跑完整流程通过。
  最终验收既检查 HTTP 健康，也检查退出菜单不能触发后台服务重启。

生成物位于 `/tmp/millionaire-ce/menu-development/`：

- `quality.json`：最终生产质量门禁结果。
- `unit-tests.xml`：23 项定向测试。
- `acceptance-evidence/verified.json`：原生安装生命周期与菜单验收。
- `installers/millionaire-ce-0.3.0-macos-arm64.tar.gz` 及同名 `.sha256`：本地构建安装包。

安装包 SHA-256：
`41473770e90e9ae88723c6f599f2e3aea67ed72eaf117a0a6a47ee699ede8c79`。

本次未创建 Release/tag 或发布产物；CI 原生 macOS 安装任务已接入新的菜单构建与验收，
job 名称保持不变。尚未重新执行远程三平台流水线，系统级管理员授权流程未作交互实机验收。

## Shadow-Run 文案

按用户确认统一为“日线双实例对照”：仿真实例依据当前行情运行；收盘后当日历史数据
就绪，回测实例再运行。这是日线自然的对照节奏。当前 30 分钟影子生命周期待补齐，
该事实继续保留在能力边界中，不据“盘后”否定双实例设计。
