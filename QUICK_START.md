# 🚀 快速部署指南（5 分钟搞定）

## 第一步：上传代码到 GitHub

1. 访问 https://github.com 并登录/注册
2. 点击右上角 `+` → `New repository`
3. 仓库名：`yoga-studio`
4. 选择 `Public`
5. 点击 `Create repository`
6. 点击 `Upload files`
7. 拖拽以下文件到页面：
   - `app.py`
   - `requirements.txt`
   - `render.yaml`
   - `Procfile`
   - `templates/` 文件夹
   - `static/` 文件夹
8. 点击 `Commit changes`

## 第二步：部署到 Render.com

1. 访问 https://dashboard.render.com/register
2. 选择 `Sign up with GitHub`
3. 点击 `New +` → `Web Service`
4. 选择 `Connect GitHub` → 授权
5. 选择 `yoga-studio` 仓库
6. 配置：
   - **Name**: `yoga-studio`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: `Free`
7. 点击 `Create Web Service`
8. 等待 3-5 分钟
9. 获得永久地址：`https://yoga-studio.onrender.com`

## 第三步：开始使用

1. 访问你的地址
2. 点击「立即注册」
3. 创建管理员账号
4. 开始添加教练、会员、课程

---

## ⚠️ 重要提醒

- **免费套餐会休眠**：15 分钟无访问会自动休眠，首次访问需要 30-60 秒唤醒
- **数据库会重置**：每次部署后数据库会清空，需要重新注册账号
- **解决方案**：使用 UptimeRobot 保持唤醒 + 定期导出数据

---

## 🎉 完成！

你的永久地址：`https://yoga-studio.onrender.com`

分享给其他人，他们也可以注册使用了！
