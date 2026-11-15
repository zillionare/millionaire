# 源码安装与开发启动

最终用户请使用[原生安装器与后台服务](native-installation.md)。本页面向贡献者，
说明如何从源码 checkout 创建环境、启动服务和运行发布检查。

## 环境要求

- Python 3.13（开发与 CI 的受支持版本）。
- 本地 Python 虚拟环境。
- 能访问 Python 依赖源的网络。

`pyproject.toml` 中的分发包名是 `millionaire`，运行时版本标识默认为
`millionaire`。

## 跨平台本地安装

仓库自带安装脚本，在 Windows、macOS 和 Linux 上创建 `.venv` 并以可编辑模式
安装当前 checkout：

```bash
python3 scripts/install.py
```

Windows 如果通过 Python Launcher 安装 Python 3.13，可使用：

```powershell
py -3.13 scripts\install.py
```

30 分钟 LightGBM 示例依赖默认不安装，需要时显式启用：

```bash
python3 scripts/install.py --ml30m
```

对应的包 extra 是 `ml30m`（`lightgbm` 与 `scikit-learn`）。如果已有激活的环境，
等价的包安装方式是：

```bash
python -m pip install -e ".[ml30m]"
```

文档、测试和质量工具是依赖组，不是运行时 extra：

```bash
python -m pip install --group doc --group test --group quality
```

Poetry 用户也可以使用 `poetry install --with doc,test,quality`。

## 启动研究/仿真模式

安装后运行：

```bash
.venv/bin/millionaire --open
```

命令行接受 `--host`、`--port`、`--reload`、`--stub`、`--open` 和
`--no-browser`。源码树也可以直接运行：

```bash
.venv/bin/python scripts/serve.py --open
```

Windows 使用 `.venv\Scripts\millionaire.exe --open` 或
`.venv\Scripts\python.exe scripts\serve.py --open`。`--open` 在 Uvicorn
启动后打开本机地址；环境变量 `QUANTIDE_OPEN_BROWSER=1` 有同样效果，
`--no-browser` 可覆盖它。

源码 checkout 在没有真实行情或 gateway 时可以使用开发 stub；它依赖仓库测试
fixture，不随安装 wheel 提供：

```bash
.venv/bin/python scripts/serve.py --stub --open
```

已有的 Unix 辅助脚本也可用：

```bash
./start.sh --stub
```

它要求 `.venv` 已存在，不会自动安装依赖。

## 首次启动的安全默认值

首次启动处于未初始化状态，会打开初始化向导。CE 不会在启动时创建管理员账户或
默认密码；向导中的管理员密码步骤负责创建或更新 `admin` 账户。在该步骤完成前
无法登录，系统不会生成 `admin`/`admin123` 之类的默认账户。

监听地址默认是 `127.0.0.1:8130`。向导保存的地址和端口在服务重启后生效；
管理员之后可在“系统维护 → 系统设置 → 服务访问”修改。显式 `--host`、`--port`
或 `QUANTIDE_HOST`、`QUANTIDE_PORT` 会覆盖已保存值。

## 后台服务

原生安装使用 launchd、systemd 或 Windows 服务，并提供独立的前台控制器。
安装、升级、数据目录和服务命令见[原生安装与后台服务](native-installation.md)。
源码 checkout 的开发运行留在前台，不注册系统服务。

## 发布产物检查

发布前构建并检查 wheel 与 sdist：

```bash
ce_artifacts=$(python -m scripts.artifact_paths)
python -m build --outdir "$ce_artifacts/dist"
python -m scripts.validate_release_artifacts
```

校验会拒绝 wheel 和 sdist 中的私有风险源文件名（包括三重障碍、回撤卖出和成本止损
模块）及已知私有风险 ID 标记。仓库专用测试和说明不会进入 CE sdist，但仍保留在
checkout 中供开发使用。CE 产物只包含通用风险程序框架；实盘交易保持隐藏且不可用。
