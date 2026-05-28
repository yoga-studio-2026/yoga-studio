#!/bin/bash
# 瑜伽馆管理系统启动脚本（含公网隧道）

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

# 启动应用（后台）
echo "启动瑜伽馆管理系统..."
python3 app.py &
FLASK_PID=$!

# 等待 Flask 启动
sleep 3

# 获取 WiFi IP
WIFI_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "未知")

# 启动 Cloudflare Tunnel（如果已安装）
CLOUDFLARED="/Users/yanqiaozhu/.local/bin/cloudflared"
if [ -f "$CLOUDFLARED" ]; then
    echo "正在启动公网隧道..."
    $CLOUDFLARED tunnel --url http://localhost:5000 > /tmp/cloudflared.log 2>&1 &
    TUNNEL_PID=$!
    
    # 等待获取公网地址
    sleep 8
    TUNNEL_URL=$(grep -o "https://.*\.trycloudflare\.com" /tmp/cloudflared.log | tail -1)
    
    echo ""
    echo "========================================"
    echo "🧘 瑜伽馆管理系统已启动！"
    echo "========================================"
    echo ""
    echo "📱 本地访问："
    echo "   http://127.0.0.1:5000"
    echo ""
    echo "📱 局域网访问（手机）："
    echo "   http://$WIFI_IP:5000"
    echo ""
    echo "🌐 公网访问（手机）："
    echo "   $TUNNEL_URL"
    echo ""
    echo "========================================"
    
    # 显示通知
    osascript -e "display notification \"公网地址: $TUNNEL_URL\" with title \"瑜伽馆管理系统已启动\""
    
    # 等待用户按 Ctrl+C 退出
    echo "按 Ctrl+C 退出..."
    wait $FLASK_PID $TUNNEL_PID
else
    echo ""
    echo "========================================"
    echo "🧘 瑜伽馆管理系统已启动！"
    echo "========================================"
    echo ""
    echo "📱 本地访问："
    echo "   http://127.0.0.1:5000"
    echo ""
    echo "📱 局域网访问（手机）："
    echo "   http://$WIFI_IP:5000"
    echo ""
    echo "⚠️  公网隧道未安装，仅限局域网访问"
    echo "========================================"
    
    osascript -e "display notification \"局域网: http://$WIFI_IP:5000\" with title \"瑜伽馆管理系统已启动\""
    
    echo "按 Ctrl+C 退出..."
    wait $FLASK_PID
fi
