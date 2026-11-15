# 原生安装与后台服务

发布流水线构建包含 Python 3.13 和固定版本依赖的安装包，无需用户自行安装 Python。
发布前对同一次构建执行安装、启停、崩溃恢复、升级和卸载保留数据验收。
只有质量、测试、真实源检查和安装验收全部通过，tag 流水线才发布 GitHub Release。

| 平台 | 产物 | 默认服务 |
| --- | --- | --- |
| macOS Apple Silicon（ARM64） | `.tar.gz`，解压后运行 `sh install.sh` | 当前用户的后台服务与菜单栏控件，登录后启动 |
| Ubuntu x86_64 | `.deb`，`sudo apt install ./millionaire-ce-…deb` | systemd 系统服务，开机启动 |
| Windows x64 | `.exe` 图形安装向导，需要管理员权限 | WinSW 系统服务开机启动；系统托盘控件随登录启动 |

macOS 官方支持范围仅包含 Apple Silicon（M 系列芯片）；不提供 Intel（x86_64）安装包或验收支持。

平台验证边界见[本版能力](scope.md)。macOS 包目前没有 Developer ID 签名或 Apple 公证；
内置动态库使用 ad-hoc 签名。Windows 没有配置发行者代码签名证书。
WinSW 和 OpenMP 的版权许可声明随相应安装包提供。

## 下载与校验

打开 [GitHub Releases](https://github.com/zillionare/millionaire-ce/releases)，选择明确包含
本手册对应原生包的版本，同时下载安装包和同名 `.sha256` 文件。以下以 `0.3.1` 为例；
只有 Release 实际列出这些文件时才使用，不要拿旧版本或其他架构的包代替。

| 平台 | 文件名 |
| --- | --- |
| macOS ARM64 | `millionaire-ce-0.3.1-macos-arm64.tar.gz` |
| Ubuntu x86_64 | `millionaire-ce-0.3.1-ubuntu-amd64.deb` |
| Windows x64 | `millionaire-ce-0.3.1-windows-x64.exe` |

## macOS 安装

在存放这两个下载文件的目录打开终端：

```bash
uname -m
shasum -a 256 -c millionaire-ce-0.3.1-macos-arm64.tar.gz.sha256
tar -xzf millionaire-ce-0.3.1-macos-arm64.tar.gz
cd millionaire-ce-0.3.1-macos-arm64
sh install.sh
```

`uname -m` 应是 `arm64`，校验应显示 `OK`。后续版本相应替换文件名中的版本号。
安装成功后，菜单栏会自动出现 **M** 图标，提供以下菜单：

- 查看服务状态、启动或停止服务。
- 打开网页界面、打开服务日志目录。
- 退出菜单栏控件；后台服务继续运行。

控件随用户登录启动，不占用 Dock。退出后，可在 Finder 的用户“应用程序”目录
（`~/Applications`）打开 **Millionaire CE**，或运行以下命令重新显示菜单栏图标：

```bash
~/.local/bin/millionaire-ce control
```

如系统提示来源无法验证，先确认下载来源及校验值，再使用 macOS 对该文件提供的
安全确认流程；安装不要求全局关闭 Gatekeeper。

## Ubuntu 安装

```bash
sha256sum -c millionaire-ce-0.3.1-ubuntu-amd64.deb.sha256
sudo apt install ./millionaire-ce-0.3.1-ubuntu-amd64.deb
sudo millionaire-ce service status
```

有桌面的机器可从应用菜单打开控制器，或运行 `millionaire-ce control`。
无桌面服务器用命令管理服务。默认仅监听本机；从另一台电脑访问时，可建立 SSH 隧道：

```bash
ssh -L 18130:127.0.0.1:8130 your-user@your-server
```

保持该连接，在本机浏览器打开 `http://127.0.0.1:18130`。

## Windows 安装

在 PowerShell 中进入下载目录，核对校验值：

```powershell
$package = 'millionaire-ce-0.3.1-windows-x64.exe'
$expected = ((Get-Content "$package.sha256" -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash $package -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'SHA256 校验失败，请重新下载' }
```

校验成功后双击 `.exe`，确认 UAC 管理员提示并完成安装。安装后系统托盘会自动显示
Millionaire CE 图标，之后每次登录自动启动。若图标被 Windows 收纳，点击通知区域的
“显示隐藏的图标”（上箭头）查看，也可在系统的任务栏设置中选择始终显示。

右键图标可查看服务状态、启停服务、打开网页和日志目录；双击图标打开网页。
退出托盘控件后，服务继续运行。需要重新显示时，从开始菜单或桌面快捷方式打开
Millionaire CE。查看状态和打开网页不要求管理员权限，启停系统服务时按需请求 UAC 授权。

目前安装包可能显示“未知发行者”或 SmartScreen 提示；核实文件来源和 SHA-256 后，
使用针对该文件的继续安装选项，无需全局关闭 Windows 安全功能。

## 打开服务网页

macOS 默认安装后直接使用菜单栏 **M** 图标；`millionaire-ce control` 可以重新打开控件。
Windows 默认使用系统托盘，快捷方式与 `millionaire-ce control` 可重新打开；
Ubuntu 桌面可从应用菜单打开窗口式控制器。关闭窗口或退出常驻控件不影响后台服务。
默认浏览器地址为 `http://127.0.0.1:8130`。

```bash
millionaire-ce service status
millionaire-ce service stop
millionaire-ce service start
```

macOS 默认安装到 `~/.local/share/millionaire-ce`，CLI 链接在 `~/.local/bin`。
若终端找不到命令，将该目录加入 PATH。升级时运行新版安装脚本；服务检查失败时
恢复上一版本。卸载默认保留配置、扩展和数据，可执行安装时输出的路径：

```bash
sh "$HOME/.local/share/millionaire-ce/uninstall.sh"
```

新版解压目录中的 `sh uninstall.sh` 也会找到默认用户安装；系统安装使用
`sudo sh uninstall.sh --system`。自定义位置设置 `MILLIONAIRE_INSTALL_ROOT`。
脚本会核对安装标记及服务信息，只删除识别出的安装目录。

macOS 服务器可安装为无需登录的系统 LaunchDaemon，并指定运行账户：

```bash
sudo sh install.sh --system --user quantide
sudo millionaire-ce service status --system
sudo millionaire-ce service stop --system
sudo millionaire-ce service start --system
```

该账户必须预先存在且不能是 root。系统安装默认代码在 `/usr/local/share/millionaire-ce`，
CLI 在 `/usr/local/bin`；配置、扩展和数据在 `/Library/Application Support/MillionaireCE`。
服务器安装不会为 root 创建登录菜单任务；有桌面时，可从 `/Applications/Millionaire CE.app`
打开菜单栏控件，启停系统服务会请求管理员授权。

Ubuntu 默认代码位于 `/opt/millionaire-ce`，运行用户为 `millionaire-ce`，持久数据在
`/var/lib/millionaire-ce`。使用 `sudo apt remove millionaire-ce` 卸载程序时保留数据；
显式执行 `apt purge` 会删除该目录。系统服务管理命令需要 sudo。

Windows 默认程序目录为 `C:\Program Files\MillionaireCE`，持久数据位于
`C:\ProgramData\MillionaireCE`。升级再次运行新版安装器。卸载默认保留数据；交互卸载
会另行提供删除数据选项，默认回答否。非管理员启动/停止系统服务时控制器会请求 UAC。

打开网页后继续[初始化](initialization.md)。日常升级、备份与恢复见[运维](operations.md)。
源码安装方式见[开发者安装](installation.md)，实时行情配置见[行情扩展](quote-extensions.md)。
