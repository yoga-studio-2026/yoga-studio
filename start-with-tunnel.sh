#!/bin/bash
# 瑜伽馆管理系统 - 一键启动（服务器 + 公网隧道 + 手机入口）

cd "$(dirname "$0")"

echo "🧘 正在启动瑜伽馆管理系统..."

# 1. 检查并启动 Flask
if lsof -i :5000 -sTCP:LISTEN &>/dev/null; then
    echo "✅ 服务器已在运行"
else
    echo "🚀 启动服务器..."
    python3 app.py &
    FLASK_PID=$!
    sleep 3
    echo "✅ 服务器已启动 (PID: $FLASK_PID)"
fi

# 2. 检查并启动 Cloudflare Tunnel
if ps aux | grep -v grep | grep "cloudflared tunnel" &>/dev/null; then
    echo "✅ 公网隧道已在运行"
else
    echo "🌐 启动公网隧道..."
    /Users/yanqiaozhu/.local/bin/cloudflared tunnel --url http://localhost:5000 > /tmp/cloudflared.log 2>&1 &
    TUNNEL_PID=$!
    sleep 8
    echo "✅ 公网隧道已启动 (PID: $TUNNEL_PID)"
fi

# 3. 获取地址
WIFI_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "未知")
TUNNEL_URL=$(grep -o "https://.*\.trycloudflare\.com" /tmp/cloudflared.log | tail -1)

echo ""
echo "========================================"
echo "🧘 瑜伽馆管理系统已启动！"
echo "========================================"
echo ""
echo "📱 手机入口（推荐）："
echo "   $TUNNEL_URL/mobile"
echo ""
echo "💻 本地访问："
echo "   http://127.0.0.1:5000"
echo ""
echo "📱 局域网（同一 WiFi）："
echo "   http://$WIFI_IP:5000"
echo ""
echo "========================================"

# 4. 打开浏览器到手机入口页
open "http://127.0.0.1:5000/mobile"

# 5. 发送通知
osascript -e "display notification \"手机入口: $TUNNEL_URL/mobile\" with title \"瑜伽馆已启动\" sound name \"default\""
