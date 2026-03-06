# TQSync Web Dashboard

安全的 Web 管理面板，用于配置和管理 TQSync 机器人。

## 🚀 快速开始

### 首次启动

```bash
# 1. 进入目录
cd web_dashboard

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置管理员密码（首次启动）
python set_admin_password.py

# 4. 启动面板
python main.py
```

访问：http://localhost:8000

## 🔒 安全特性

- Argon2 密码哈希加密
- JWT Token 身份验证
- HTTPS 支持
- CSRF 保护
- 会话超时机制

## 📖 详细文档

参见 [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md)
