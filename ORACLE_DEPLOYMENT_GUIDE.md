# Oracle Cloud Always Free 部署指南

## 优势
- ✅ **完全免费**，永不收费
- ✅ **永不休眠**，24/7 在线
- ✅ **固定公网 IP** + 固定域名
- ✅ **2个 VM** 免费额度
- ✅ 支持 **随时随地多人访问**

## 准备工作
1. 有效邮箱（接收验证邮件）
2. 信用卡（仅验证，不扣费）
3. 手机号码（接收短信验证）

---

## Step 1: 注册 Oracle Cloud（你来做，5-10分钟）

### 1.1 访问注册页面
```
https://www.oracle.com/cloud/free/
```

### 1.2 填写注册信息
- **Country:** China
- **Name:** 你的姓名
- **Email:** 你的邮箱
- **Password:** 设置密码

### 1.3 验证邮箱
- 查收 Oracle 验证邮件
- 点击验证链接

### 1.4 填写个人信息
- **地址：** 中国地址
- **电话：** 手机号
- **信用卡：** 绑定（仅验证，不扣费）

### 1.5 完成注册
- 等待账户审批（通常几分钟）
- 收到 "Welcome to Oracle Cloud" 邮件

---

## Step 2: 创建 Always Free VM（我来做，10-15分钟）

### 2.1 登录 Oracle Cloud Console
```
https://cloud.oracle.com/
```

### 2.2 创建计算实例
1. 点击 **"Create a VM instance"**
2. **Name:** `yoga-studio-vm`
3. **Shape:** 选择 **VM.Standard.E2.1.Micro** (Always Free)
4. **Image:** Ubuntu 22.04 LTS
5. **Network:** 默认 VCN
6. **Add SSH keys:** 选择 "Generate a key pair for me"
   - 下载私钥 `opc-key.pem`
7. 点击 **"Create"**

### 2.3 记录公网 IP
- 等待 VM 创建完成（2-3分钟）
- 记录 **Public IP Address**（例如：`140.xxx.xxx.xxx`）

---

## Step 3: 部署瑜伽馆管理系统（我来做）

### 3.1 SSH 连接到 VM
```bash
chmod 400 opc-key.pem
ssh -i opc-key.pem ubuntu@<公网IP>
```

### 3.2 安装依赖
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python3 和 pip
sudo apt install -y python3 python3-pip python3-venv

# 安装 Nginx
sudo apt install -y nginx

# 安装 Git
sudo apt install -y git
```

### 3.3 上传项目文件
```bash
# 方法1: 使用 SCP（在你本地电脑执行）
scp -i opc-key.pem -r ~/Desktop/yoga-studio ubuntu@<公网IP>:~/

# 方法2: 使用 Git（如果项目在 GitHub）
git clone https://github.com/yoga-studio-2026/yoga-studio.git
```

### 3.4 配置 Python 虚拟环境
```bash
cd ~/yoga-studio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3.5 配置 Systemd 服务
创建 `/etc/systemd/system/yoga-studio.service`：

```ini
[Unit]
Description=Yoga Studio Management System
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/yoga-studio
Environment="PATH=/home/ubuntu/yoga-studio/venv/bin"
ExecStart=/home/ubuntu/yoga-studio/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable yoga-studio
sudo systemctl start yoga-studio
sudo systemctl status yoga-studio
```

### 3.6 配置 Nginx 反向代理
创建 `/etc/nginx/sites-available/yoga-studio`：

```nginx
server {
    listen 80;
    server_name <公网IP>;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/yoga-studio /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3.7 配置防火墙
```bash
sudo ufw allow 80/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

---

## Step 4: 测试访问

### 4.1 本地测试
```bash
curl http://localhost:5000
```

### 4.2 公网测试
在浏览器访问：
```
http://<公网IP>
```

---

## Step 5: 绑定域名（可选）

### 5.1 购买域名（可选）
- 阿里云、腾讯云、GoDaddy 等

### 5.2 配置 DNS
- A 记录：`@` → `<公网IP>`
- A 记录：`www` → `<公网IP>`

### 5.3 访问
```
http://yourdomain.com
```

---

## 常见问题

### Q1: Oracle Cloud 注册失败？
- 确保信用卡支持国际支付
- 确保手机号能接收短信
- 尝试使用企业邮箱

### Q2: VM 创建失败？
- 检查是否选择了 **Always Free** shape
- 检查区域是否支持 Always Free

### Q3: 无法访问？
- 检查 VM 安全列表（Security List）
- 添加入站规则：允许 TCP 端口 80、5000

### Q4: 服务无法启动？
- 检查日志：`sudo journalctl -u yoga-studio -f`
- 检查端口占用：`sudo netstat -tulpn | grep 5000`

---

## 完成！🎉

你现在有：
- ✅ 永久免费云服务
- ✅ 随时随地访问
- ✅ 多人同时使用
- ✅ 永不休眠

访问地址：
```
http://<公网IP>
```

（或者你绑定的域名）
