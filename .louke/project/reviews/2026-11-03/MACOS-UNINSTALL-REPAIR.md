# macOS 解压目录卸载入口修复与 mini-two 安装

日期：2026-11-03。用户授权排查旧版卸载失败、修复并在 mini-two 安装最新版。

## 原因

安装包同时带有 `uninstall.sh`，但旧脚本始终把脚本所在目录当成安装目录。
用户在解压目录执行它时，没有找到只存在于正式安装根目录的所有权标记，因此拒绝删除。
检查确认 mini-two 正式安装的 marker、current、CLI 链接及服务元数据完整；并非安装损坏。
原服务仍在运行，安装内容尚未包含本次初始化向导的数据源权限检测。

## 修复

- 同一卸载脚本支持从解压目录和正式安装目录调用。解压目录默认定位当前用户的正式安装。
- 自定义目录使用 `MILLIONAIRE_INSTALL_ROOT`，系统安装使用 `--system`。
- 核对 marker 的内容、有效 scope、CLI 目录及可执行入口后才停止服务、删除程序；
  未识别的目标、缺元数据、scope 冲突、根目录或 HOME 均拒绝删除。
- 不删除配置、账户、扩展或市场数据。错误提示给出目标目录与正确调用方式。
- 脚本分发为可执行文件，安装/升级后也显式设置安装副本为 755。
- 原生安装验收改为从解压目录执行卸载，覆盖用户此次实际操作。
- 用户安装文档补充正确命令和两种入口。

## 验证

产物位于 `/tmp/millionaire-ce/mini-two-uninstall/`。

- `uninstall.xml`：8 项通过，覆盖两入口、路径空格、系统 scope、无安装、损坏 marker、
  缺入口及 scope 冲突；所有拒绝路径均确认没有停止服务或删除目标。
- `quality.json`：生产代码的 lint、认知复杂度、重复和规模门禁通过。
- `site/`：严格 MkDocs 构建通过，wheel/sdist 通过 CE 内容校验，shell 语法通过。
- `native-acceptance/verified.json`：最终包在本机完成安装、菜单操作、启停、异常退出
  恢复、升级及从解压目录卸载；数据/用户扩展保留。
- `verified-mini-two.json`：mini-two 安装后健康检查通过，菜单登录任务处于 running；
  安装内 333 个源码/静态文件与最终 wheel 逐一校验一致，安装卸载脚本可执行。

本次仅改变 POSIX 安装/卸载与其验收、文档；没有改动应用 Python 运行逻辑，未重跑
全部应用单元测试或 Windows/Ubuntu 实机安装。新增 shell 测试在 Windows 单元任务中
明确跳过，由 macOS 原生安装任务实际执行。

## mini-two 操作与保留

先在私有临时目录保存配置、SQLite 在线备份、市场数据和原程序可恢复副本。
校验包 SHA-256 后，从新解压目录运行卸载脚本，成功移除旧程序，再安装最终包。
卸载后及安装后分别比较市场文件内容和配置/用户/账户表内容摘要，均保持不变。
用户 token、密码和配置值未输出到报告或日志。

远程备份：`/tmp/millionaire-ce/mini-two-uninstall-yWnyf56t/backup/`。
远程操作日志及校验记录位于同一父目录；临时备份不是长期备份。
默认服务与菜单均恢复运行，配置和数据继续使用原来的持久位置。

最终本地安装包：
`/tmp/millionaire-ce/mini-two-uninstall/installers/millionaire-ce-0.3.0-macos-arm64.tar.gz`

SHA-256：`89725d377158c6357dbc71cca6af12e7c31479104dbb9cae28eee811ef2c0a6e`。

本次未推送、创建 tag 或发布 GitHub Release；用户授权的 mini-two 实际安装已完成。
