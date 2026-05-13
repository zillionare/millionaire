1. 在 pyproject.toml 中指定的第三方库可用时，就不要再使用其它类似的库。比如，指定了 loguru，就不要使用内置的logging。
2. 运行命令时，始终使用 conda 创建的、与项目同名（小写）的虚拟环境名。
3. 如果发现有需要的依赖没有安装，先通过 poetry添加依赖，再执行安装。
4. 当项目版本是0.1.0时，意味着从来没有发布过，不需要考虑任何以前版本的兼容性和移植。不要在项目中留任何冗余代码。
5. 凡是交易相关的 feature 或 fix，必须同时补充至少一条由 `tests/e2e/support/tushare_stub.py` 或 `tests/e2e/support/gateway_stub.py` 支撑的测试用例；如果变更同时涉及行情下载与交易链路，则两类 stub 测试都要覆盖。
