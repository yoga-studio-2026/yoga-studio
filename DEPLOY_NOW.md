# 🚀 Render.com 一键部署步骤（只需3步）

## 前置条件
- GitHub 已登录（代码已经推送到：https://github.com/yoga-studio-2026/yoga-studio）
- 浏览器打开 https://dashboard.render.com

---

## 第1步：注册/登录 Render

1. 打开 https://dashboard.render.com
2. 点击 **"Sign in with GitHub"**（用 GitHub 账号登录）
3. 授权 Render 访问你的 GitHub 仓库

---

## 第2步：创建 Web 服务

1. 点击右上角 **"New +"** → 选择 **"Web Service"**
2. 连接 GitHub 仓库：选择 `yoga-studio-2026/yoga-studio`
3. Render 会自动读取 `render.yaml` 配置，**直接点击 "Apply"** 即可

---

## 第3步：等待部署完成（约3-5分钟）

1. 在 Dashboard 中看到 `yoga-studio` 的状态变为 **"Live"**
2. 点击服务名称，顶部就是你的公网地址：`https://yoga-studio.onrender.com`
3. 打开这个地址，用现有账号登录即可使用

---

## ⚠️ 注意事项

- 首次部署后，数据库是空的，需要先注册账号
- 公网地址固定不变，可以收藏到手机桌面
- Render 免费套餐每月 750 小时，足够日常使用
- 如果 15 分钟没人访问会自动休眠，再次访问时会自动唤醒（稍等几秒）

## 📱 手机使用

打开地址后，点击浏览器菜单 → **"添加到主屏幕"**，就像用 APP 一样方便！
