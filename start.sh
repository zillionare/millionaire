#!/bin/bash
# 启动 Millionaire 应用。

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv"
LOG_FILE="/tmp/quantide.log"

# 解析参数
STUB_MODE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --stub)
            STUB_MODE=1
            shift
            ;;
        *)
            echo "未知参数: $1"
            echo "用法: $0 [--stub]"
            exit 1
            ;;
    esac
done

# 检查虚拟环境
if [ ! -d "$VENV" ]; then
    echo "虚拟环境不存在: $VENV"
    exit 1
fi

# 激活虚拟环境
source "$VENV/bin/activate"

# 设置 stub 环境变量
if [ -n "$STUB_MODE" ]; then
    export QUANTIDE_ENABLE_DEV_STUBS=1
fi

# 进入项目目录
cd "$PROJECT_DIR"

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 写入启动标记
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动 Millionaire..." >> "$LOG_FILE"
if [ -n "$STUB_MODE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] stub 模式已启用" >> "$LOG_FILE"
fi

# 同时输出到控制台和日志文件
exec > >(tee -a "$LOG_FILE")
exec 2>&1

# 启动应用（监听所有接口）
uvicorn quantide.app:app --host 0.0.0.0 --port 8000
