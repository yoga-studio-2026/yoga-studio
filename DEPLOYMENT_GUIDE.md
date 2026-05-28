# 瑜伽馆管理系统 - Render.com 部署指南

## 📦 部署包内容

这个部署包包含了部署到 Render.com 所需的所有文件：

- `app.py` - 后端主程序（已适配云端环境）
- `requirements.txt` - Python 依赖列表
- `render.yaml` - Render.com 配置文件
- `Procfile` - 备用启动文件
- `templates/` - 前端模板文件
- `static/` - 静态资源文件（CSS、JS、PWA 支持）
- `yoga.db` - 数据库文件（可选，部署后会创建新的）

---

## 🚀 部署步骤（总计 10 分钟）

### 第一步：创建 GitHub 仓库（3 分钟）

1. **注册/登录 GitHub**
   - 访问：https://github.com/signup
   - 填写用户名、邮箱、密码
   - 验证邮箱（检查垃圾邮件夹）

2. **创建新仓库**
   - 点击右上角 `+` → `New repository`
   - Repository name: `yoga-studio`（或任何你喜欢的名字）
   - 选择 `Public`（免费用户只能部署公开仓库）
   - ✅ 勾选 `Add a README file`
   - 点击 `Create repository`

3. **上传代码**
   - 在仓库页面点击 `Add file` → `Upload files`
   - 拖拽以下文件和文件夹到页面：
     - `app.py`
     - `requirements.txt`
     - `render.yaml`
     - `Procfile`
     - `templates/` 文件夹（包含所有 .html 文件）
     - `static/` 文件夹（包含所有 CSS、JS、图标文件）
   - Commit message: `Initial commit`
   - 点击 `Commit changes`

---

### 第二步：部署到 Render.com（5 分钟）

1. **注册/登录 Render.com**
   - 访问：https://dashboard.render.com/register
   - 选择 `Sign up with GitHub`（推荐，自动关联）

2. **创建 Web Service**
   - 登录后点击 `New +` → `Web Service`
   - 选择 `Build and deploy from a Git repository`
   - 点击 `Connect GitHub` → 授权 Render 访问你的 GitHub 账号
   - 选择刚才创建的 `yoga-studio` 仓库

3. **配置部署选项**
   - **Name**: `yoga-studio`（或任何你喜欢的名字）
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: 选择 `Free`（免费套餐）

4. **高级设置（可选）**
   - 展开 `Advanced` 选项卡
   - 添加环境变量（如果需要）：
     - `FLASK_ENV`: `production`

5. **开始部署**
   - 点击 `Create Web Service`
   - 等待 3-5 分钟，Render 会自动：
     - 下载代码
     - 安装依赖
     - 启动服务器

6. **获取访问地址**
   - 部署完成后，Render 会显示一个永久地址：
     - 例如：`https://yoga-studio.onrender.com`
   - 点击这个地址即可访问你的瑜伽馆管理系统

---

### 第三步：初始化数据库（2 分钟）

1. **访问系统**
   - 打开你的 Render 地址（例如：`https://yoga-studio.onrender.com`）
   - 系统会自动创建数据库表

2. **注册管理员账号**
   - 点击「立即注册」
   - 用户名：`admin`（或任何你喜欢的）
   - 密码：设置一个安全的密码
   - 邮箱：你的邮箱

3. **开始使用**
   - 登录后进入仪表盘
   - 添加教练、会员、课程等信息

---

## ⚠️ 重要注意事项

### 1. 免费套餐限制

Render 免费套餐有以下限制：

- **休眠机制**：15 分钟无访问会自动休眠
  - 解决：使用 [UptimeRobot](https://uptimerobot.com/) 定时 ping 你的地址
- **启动延迟**：休眠后首次访问需要 30-60 秒唤醒
- **每月 750 小时**：足够一个服务 24/7 运行

### 2. 数据库持久化

- Render 免费套餐**不提供持久化存储**
- 每次部署或休眠后，数据库会**重置**
- **解决方案**：
  - 方案 A：定期导出数据（设置 → 导出数据库）
  - 方案 B：升级到付费套餐（$7/月，支持持久化）
  - 方案 C：使用外部数据库（如 Supabase，免费）

### 3. 自定义域名（可选）

如果你有自己的域名：

1. 在 Render 服务页面点击 `Settings` → `Custom Domain`
2. 输入你的域名（例如：`yoga.yourdomain.com`）
3. 按照提示在域名服务商添加 CNAME 记录

---

## 🔧 故障排查

### 部署失败

1. **查看日志**
   - 在 Render 服务页面点击 `Logs` 选项卡
   - 检查错误信息

2. **常见错误**
   - `Module not found`: 检查 `requirements.txt` 是否完整
   - `Port already in use`: 确保 `app.py` 使用环境变量 `PORT`
   - `Database error`: 检查数据库文件权限

### 无法访问

1. **检查服务状态**
   - 在 Render 服务页面查看服务是否正在运行
   - 如果显示 `Build in progress`，等待部署完成

2. **手动重启**
   - 在 Render 服务页面点击 `Manual Deploy` → `Deploy latest commit`

---

## 📱 手机访问

部署成功后，你可以在任何设备上访问：

1. **手机浏览器**
   - 输入你的 Render 地址（例如：`https://yoga-studio.onrender.com`）
   - 系统会自动适配手机屏幕

2. **安装到桌面（PWA）**
   - 在手机浏览器中打开
   - iOS Safari：点击「分享」→「添加到主屏幕」
   - Android Chrome：点击「菜单」→「安装应用」

---

## 🎉 完成！

现在你的瑜伽馆管理系统已经部署到云端，任何人都可以访问了！

**你的永久地址**：`https://yoga-studio.onrender.com`（替换为你的实际地址）

---

## 📞 需要帮助？

如果遇到问题，可以：

1. 查看 [Render 文档](https://render.com/docs)
2. 联系 Render 支持：support@render.com
3. 在 GitHub 仓库提 Issue

---

**祝你的瑜伽馆生意兴隆！🧘‍♀️**
