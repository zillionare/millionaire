# 仓库布局与临时产物

本页面向开发者。源码与测试样本留在仓库；生成的安装包、报告、站点和临时运行数据
放到系统临时目录，避免污染 checkout 或混入发布包。

| 内容 | 位置 |
| --- | --- |
| Python 运行代码 | `quantide/` |
| 测试与固定行情样本 | `tests/`、`tests/assets/market_data/` |
| 构建/维护脚本与安装模板 | `scripts/`、`scripts/packaging/` |
| 用户手册 | `docs/` |
| 审查、历史证据和版本规格 | `.louke/project/reviews/`、`.louke/project/specs/` |
| 包、站点、测试/质量报告及工具缓存 | `/tmp/millionaire-ce/<工作区标识>/`；Windows 使用原生临时目录 |
| 用户持久化配置和真实行情 | 用户或服务的数据目录，见[运维](operations.md)；不放临时目录 |

安装器模板是源码，不能当临时文件删掉。原根目录的 `data` 是固定测试样本，现已迁入
测试资产。运行数据不能反过来提交成测试样本。

## 统一开发入口

在仓库根目录、已激活 Python 3.13 环境下使用模块命令：

```bash
python -m scripts.artifact_paths
python -m scripts.artifact_paths --run python -m scripts.check_quality
python -m scripts.artifact_paths --run python -m pytest tests/unit
```

第一条打印当前工作区的产物根目录；`--run` 为子进程配置报告和工具缓存路径。
可通过 `MILLIONAIRE_ARTIFACTS_DIR` 指定另一个仓库外目录，禁止指向 checkout 内部。
Windows 使用这个入口时会自动选择 `%TEMP%`，不要求存在 Unix `/tmp`。

构建源码包/文档时明确给出输出目录。POSIX 终端示例：

```bash
ce_artifacts=$(python -m scripts.artifact_paths)
python -m build --outdir "$ce_artifacts/dist"
python -m scripts.validate_release_artifacts
mkdocs build --strict --site-dir "$ce_artifacts/site"
```

PowerShell 中将第一行改为 `$ce_artifacts = python -m scripts.artifact_paths`。
原生安装器使用 `python -m scripts.build_installer --wheel <已验证wheel的路径>`，
默认将安装包放在产物根目录的 `installers`，构建 staging 在临时工作目录中自动清理。
`python -m scripts.verify_installer` 默认验收该目录，证据写入 `quality/installers`。

## 防止回归

`quality` 包含根目录布局检查；CI 在测试、安装和文档构建后再次检查，拒绝重新出现
根目录 `data`、`dist`、`packaging`、`quality-reports`、`review`、`site` 等目录。
wheel/sdist 校验还会拒绝开发管理文件和生成物，保留合法的 `quantide/data` Python 模块。

## 运行时路径

`init_data()`、`init_data(None)` 和空白路径使用同一解析流程：显式参数 → 已保存的
wizard 数据目录 → `QUANTIDE_DATA_HOME` → 系统临时目录中的
`millionaire-ce/runtime-<用户标识>/market`。默认读取配置数据库后再选择行情目录；
不再将空字符串当成当前工作目录。Windows 的临时目录取自系统 `%TEMP%`。
因子分析 CLI、ML 示例和 `daily_basic` 均复用该配置。

`start.sh` 的开发日志读取 `QUANTIDE_LOG_HOME`，未配置时写入同一临时根目录的
`logs/development.log`。构建/测试报告仍由 `MILLIONAIRE_ARTIFACTS_DIR` 单独管理。
源码启动的新实验若需要重启后长期保留行情，应在 wizard 中明确选择持久目录。

配置/认证/账户事实属于持久状态，继续使用 `QUANTIDE_CONFIG_HOME`、app factory
指定目录或系统用户配置目录；原生安装器会显式选择持久服务数据目录。
已有 wizard 数据目录不自动迁移。源码树内的行情目录、配置目录、数据库及模型
输出会在写入前拒绝，包括相对路径和符号链接别名。

pytest 在导入应用前将配置与数据目录隔离到临时测试 profile；回归测试覆盖空参数、
冷启动读取已保存配置、环境变量、临时兜底和错误路径。agent 必须遵守根目录
`AGENTS.md` 的同一产物规则，不以删除文件或添加 `.gitignore` 替代修正生成入口。

本次整理没有删除旧产物，迁移记录在
`.louke/project/reviews/2026-11-02/layout-migration.json`。其中的临时备份不作为正式发布源；
发布必须使用当前 ref 重新构建并验收的产物。
