#!/bin/bash
# 瑜伽馆管理系统启动脚本

cd "$(dirname "$0")"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    osascript -e 'display dialog "未找到 Python3，请先安装 Python3" buttons {"确定"} default button 1'
    exit 1
fi

# 检查依赖
if ! python3 -c "import flask" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install flask -q
fi

# 检查数据库
if [ ! -f "yoga.db" ]; then
    echo "数据库不存在，将自动创建..."
fi

# 启动应用
echo "启动瑜伽馆管理系统..."
python3 app.py
