#!/bin/bash
# 一键打包脚本 - 创建 macOS App

set -e

cd "$(dirname "$0")"

APP_NAME="瑜伽馆管理"
APP_DIR="$HOME/Desktop/${APP_NAME}.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

echo "🧘 创建 ${APP_NAME}.app ..."

# 创建目录结构
mkdir -p "$MACOS_DIR"
mkdir -p "$RESOURCES_DIR"

# 复制启动脚本
cp start.sh "$MACOS_DIR/$APP_NAME"
chmod +x "$MACOS_DIR/$APP_NAME"

# 创建 Info.plist
cat > "$CONTENTS_DIR/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>瑜伽馆管理</string>
    <key>CFBundleDisplayName</key>
    <string>瑜伽馆管理</string>
    <key>CFBundleIdentifier</key>
    <string>com.yogastudio.app</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>瑜伽馆管理</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
</dict>
</plist>
PLIST

echo "✅ App 创建完成: $APP_DIR"
echo ""
echo "📍 使用方式:"
echo "   双击打开 $APP_DIR 即可启动"
echo ""
echo "💡 提示: 首次打开可能需要在系统偏好设置 → 安全性与隐私中允许运行"
