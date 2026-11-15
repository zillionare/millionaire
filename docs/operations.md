# 启停、升级与备份恢复

后台服务运行网页、同步任务和策略。macOS 默认提供菜单栏 **M** 控件，可查看状态、
启停服务、打开网页和日志目录。退出菜单栏控件不停止服务，重新显示时打开用户
“应用程序”中的 Millionaire CE，或运行 `millionaire-ce control`。
Windows 使用系统托盘控件，右键提供同类操作，双击打开网页；退出后可从开始菜单或
桌面快捷方式重新打开。Ubuntu 桌面使用窗口式控制器。
只停止某个策略请使用“系统维护 → 运行时监控”。

## 日常启停

macOS 默认用户服务：

```bash
millionaire-ce service status
millionaire-ce service stop
millionaire-ce service start
```

Ubuntu 系统服务：

```bash
sudo millionaire-ce service status
sudo millionaire-ce service stop
sudo millionaire-ce service start
sudo journalctl -u millionaire-ce -n 100 --no-pager
```

Windows 优先使用系统托盘菜单；命令行可在管理员 PowerShell 中运行安装目录自带 Python：

```powershell
& 'C:\Program Files\MillionaireCE\runtime\python.exe' -m quantide.cli service status
& 'C:\Program Files\MillionaireCE\runtime\python.exe' -m quantide.cli service stop
& 'C:\Program Files\MillionaireCE\runtime\python.exe' -m quantide.cli service start
```

更改安装目录后对应替换路径。不要在服务已经运行时再用前台命令启动第二实例。
默认网页 `http://127.0.0.1:8130`，`/api/health` 可检查进程是否响应；健康响应不能
替代数据完整性、行情新鲜度或策略对账结果。

## 哪些目录需要保留

| 安装方式 | 配置/账户目录 | 默认行情目录 | 服务日志 |
| --- | --- | --- | --- |
| macOS 用户 | `~/.config/quantide` | `~/.quantide` | 配置目录的 `logs` |
| macOS 系统服务 | `/Library/Application Support/MillionaireCE/config` | 同级 `data` | 配置目录的 `logs` |
| Ubuntu 原生包 | `/var/lib/millionaire-ce/config` | `/var/lib/millionaire-ce/data` | systemd journal |
| Windows 原生包 | `C:\ProgramData\MillionaireCE\config` | 同级 `data` | `C:\ProgramData\MillionaireCE\logs` |

wizard 中自定义的数据目录优先；环境变量 `QUANTIDE_CONFIG_HOME` 可以指定配置目录。
配置目录中的 `quantide.db` 保存认证、配置、账户/委托/成交和跟踪事实；还应保留
模型、运行规格、日志及 `extensions`。用户策略目录可能在别处，也要单独备份。
日常日志中的目录和状态可以帮助核对服务实际使用了哪套配置。

源码前台运行时，未配置行情目录会使用系统临时目录中的
`millionaire-ce/runtime-<用户标识>/market`；已有 wizard 数据目录优先于
`QUANTIDE_DATA_HOME`。长期使用应在 wizard 中选择持久目录，临时目录可能被系统清理。
`start.sh` 的开发日志通过 `QUANTIDE_LOG_HOME` 设置，默认在上述临时根目录的 `logs`。
原生安装器会显式设置表中的持久服务目录。源码树内部路径会被拒绝；
完整解析与开发产物规则见[仓库布局](project-layout.md)。

## 一致性备份

本版没有一键备份/恢复命令。可靠的简单做法是：

1. 记录版本、数据目录和用户策略目录，使用控制器或服务命令停止后台服务。
2. 确认服务已停止且没有另一个前台实例，完整复制/归档配置目录、行情目录和用户策略目录。
3. 不遗漏 SQLite 的同目录辅助文件、JSON 备份、Parquet 分区和索引；不能只拷一张表。
4. 备份保存在独立位置并标记时间/版本，再启动服务。

离线备份应在副本上验证：数据库完整性、行情可读性、报告可重开、账户与运行规格一致。
备份含认证与 token，分享排障材料时不要直接上传整份备份。

## 恢复

停止服务，先保存当前故障目录，再在空的目标位置恢复同一时间点的完整备份。
恢复原目录关系和服务账户权限，使用兼容程序版本启动。逐项检查登录、数据范围、
账户持仓/活动委托、策略运行状态及行情源。不要混合不同时间的数据库和运行规格。
若业务状态仍不明确，先停止相应策略并核对，不以反复重启替代对账。

## 升级与卸载

升级前做一致性备份，下载并校验同平台新版本，再重复运行安装程序。
升级成功后核对服务版本、数据目录、扩展加载和关键报告。macOS 安装脚本会在
新服务检查失败时尝试恢复上一程序版本；它不代替数据迁移前的备份。

默认卸载保留持久数据及扩展。Ubuntu `apt remove` 保留，`apt purge` 删除持久目录；
Windows 卸载中的显式删除数据选项会清除，macOS 使用安装时输出的卸载脚本。
重新安装前明确是保留旧账户还是创建新实验，不要误将旧柜台数据库当作新本金。

## 服务器与重启

Ubuntu/Windows 系统服务随开机启动；macOS 默认 LaunchAgent 随用户登录启动，
无人登录服务器需另外配置系统 LaunchDaemon，见[安装](native-installation.md)。
自动进程恢复已经纳入验收，真实操作系统断电及多个完整交易日无人值守的范围见
[平台验证边界](scope.md)。
