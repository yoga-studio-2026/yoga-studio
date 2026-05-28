# ✅ 部署检查清单

## 部署前检查

- [ ] 代码已提交到本地 Git
- [ ] `requirements.txt` 包含所有依赖
- [ ] `render.yaml` 配置文件已创建
- [ ] `Procfile` 已创建
- [ ] 所有模板文件已创建（`templates/` 文件夹）
- [ ] 所有静态文件已创建（`static/` 文件夹）
- [ ] `app.py` 支持环境变量 `PORT`
- [ ] 数据库初始化逻辑正常

## GitHub 上传检查

- [ ] 已创建 GitHub 账号
- [ ] 已验证邮箱
- [ ] 已创建新仓库 `yoga-studio`
- [ ] 已上传以下文件：
  - [ ] `app.py`
  - [ ] `requirements.txt`
  - [ ] `render.yaml`
  - [ ] `Procfile`
  - [ ] `templates/` 文件夹（包含所有 .html 文件）
  - [ ] `static/` 文件夹（包含所有 CSS、JS、图标文件）
- [ ] 提交信息清晰（`Initial commit`）

## Render.com 部署检查

- [ ] 已注册 Render.com 账号
- [ ] 已连接 GitHub 账号
- [ ] 已创建 Web Service
- [ ] 已选择 `yoga-studio` 仓库
- [ ] 配置正确：
  - [ ] **Name**: `yoga-studio`
  - [ ] **Environment**: `Python 3`
  - [ ] **Build Command**: `pip install -r requirements.txt`
  - [ ] **Start Command**: `python app.py`
  - [ ] **Plan**: `Free`
- [ ] 部署成功（显示 `Build in progress` → `Live`）
- [ ] 获得永久地址（例如：`https://yoga-studio.onrender.com`）

## 系统功能检查

- [ ] 可以访问登录页面
- [ ] 可以注册新账号
- [ ] 可以登录系统
- [ ] 仪表盘正常显示
- [ ] 可以添加教练
- [ ] 可以添加会员
- [ ] 可以记录课程
- [ ] 可以查看财务报表
- [ ] 手机端可以正常访问
- [ ] PWA 可以安装到桌面

## 性能优化（可选）

- [ ] 设置 UptimeRobot 定时 ping（防止休眠）
- [ ] 定期导出数据库备份
- [ ] 考虑升级到付费套餐（持久化存储）

---

## 🎉 部署完成！

**你的永久地址**：_________________________________

（填写你的 Render.com 地址）

**分享给其他人**：任何人都可以注册使用了！
