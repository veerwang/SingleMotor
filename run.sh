#!/bin/bash
# NiMotion 步进电机调试工具启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# 检查虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "虚拟环境不存在，正在创建..."
    uv venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    uv pip install -e "$SCRIPT_DIR"
else
    source "$VENV_DIR/bin/activate"
fi

python -m nimotion.main "$@"
