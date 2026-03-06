# TQSync Web Dashboard 使用指南

## 📋 目录

1. [功能概述](#功能概述)
2. [快速开始](#快速开始)
3. [安全特性](#安全特性)
4. [功能详解](#功能详解)
5. [部署说明](#部署说明)
6. [常见问题](#常见问题)

---

## 🎯 功能概述

TQSync Web Dashboard 是一个独立于主程序的 Web 管理面板，提供：

- 🔐 **安全认证** - Argon2 密码哈希 + JWT Token
- ⚙️ **配置管理** - 在线编辑 `.env` 和 `config.yaml`
- 📊 **实时监控** - 消息统计、运行状态
- 🔄 **远程重启** - 一键重启机器人（需实现）

### 设计原则

- ✅ **完全独立** - 不修改现有代码逻辑
- ✅ **安全第一** - 多层安全防护
- ✅ **轻量级** - 适合树莓派等低资源设备
- ✅ **易用性** - 简洁直观的界面

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd web_dashboard
pip install -r requirements.txt
```

### 2. 设置管理员密码（首次启动）

```bash
python set_admin_password.py
```

**说明**：
- 密码长度至少 8 位
- 使用 Argon2 算法加密存储
- 明文密码不会被保存

### 3. 启动面板

```bash
python main.py
```

访问：**http://localhost:8000**

默认用户名：`admin`

---

## 🔒 安全特性

### 密码安全

#### 存储安全
- **算法**: Argon2（获得密码哈希竞赛冠军）
- **盐值**: 自动生成随机盐
- **文件**: `admin_password.hash`（只读权限）

#### 传输安全
- **HTTPS**: 生产环境必须使用 HTTPS
- **Token**: JWT Token 有效期 24 小时
- **二次确认**: 敏感操作需要确认

### 会话管理

```python
# JWT Token 配置
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时
ALGORITHM = "HS256"
SECRET_KEY = "请修改为环境变量"  # 生产环境
```

### 安全建议

#### 生产环境部署

1. **修改密钥**
   ```bash
   # 设置环境变量
   export DASHBOARD_SECRET_KEY="your-random-secret-key"
   ```

2. **启用 HTTPS**
   
   使用 Nginx 反向代理：
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;
       
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

3. **限制访问 IP**
   ```python
   # main.py 中添加 IP 白名单
   ALLOWED_IPS = ["127.0.0.1", "192.168.1.0/24"]
   ```

4. **定期更换密码**
   ```bash
   # 重新运行密码设置脚本
   python set_admin_password.py
   ```

---

## 📊 功能详解

### 1. 登录认证

**流程**：
1. 输入用户名和密码
2. 后端验证密码哈希
3. 生成 JWT Token
4. 前端保存 Token 到 localStorage
5. 后续请求携带 Token

**安全机制**：
- 密码错误不提示具体原因
- Token 过期自动跳转登录
- 支持多标签页共享登录状态

### 2. 统计看板

**显示数据**：
- Telegram 接收/发送数量
- QQ 接收/发送数量
- 过滤消息数量
- 运行时间

**数据来源**：
```python
# TODO: 从 MessageSync 获取真实数据
@app.get("/api/status")
async def get_status():
    return {
        "stats": {
            "telegram_received": 0,  # 从 MessageSync.stats 获取
            "qq_received": 0,
            "telegram_sent": 0,
            "qq_sent": 0,
            "filtered": 0,
            "uptime": "0h 0m"
        }
    }
```

### 3. 配置管理

#### .env 配置

支持编辑内容：
```bash
TELEGRAM_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
NAPCAT_WS_URL=ws://127.0.0.1:8080/ws
NAPCAT_HTTP_URL=http://127.0.0.1:5700
QQ_GROUP_ID=your_group_id
LOG_LEVEL=INFO
```

#### config.yaml 配置

完整的 YAML 配置：
```yaml
telegram:
  token: "your_token"
  chat_id: "your_chat_id"
  proxy:
    enable: false
    
qq:
  ws_url: "ws://127.0.0.1:8080/ws"
  http_url: "http://127.0.0.1:5700"
  group_id: "your_group_id"

sync:
  bidirectional: true
  filter_keywords: ["#skip", "!skip"]
```

**保存机制**：
- 实时保存到文件系统
- 不修改现有加载逻辑
- 下次启动时自动应用

### 4. 重启机器人

**当前状态**：功能框架已实现，需添加实际重启逻辑

**推荐方案**（不修改现有代码）：

```python
@app.post("/api/restart")
async def restart_bot():
    """通过外部进程重启"""
    import subprocess
    import sys
    
    # 方案 1: systemd 服务
    subprocess.run(["sudo", "systemctl", "restart", "tqsync"])
    
    # 方案 2: 进程管理器
    # subprocess.run(["pm2", "restart", "tqsync"])
    
    # 方案 3: Python 脚本
    # python = sys.executable
    # script = Path(__file__).parent.parent / "main.py"
    # os.execl(python, python, str(script))
```

---

## 🖥️ 部署说明

### Windows 部署

#### 直接运行

```batch
cd web_dashboard
pip install -r requirements.txt
python set_admin_password.py
python main.py
```

#### 开机自启

创建 `start_dashboard.bat`：
```batch
@echo off
cd /d %~dp0
python main.py
```

添加到任务计划程序。

### Linux 部署

#### Systemd 服务

创建 `/etc/systemd/system/tqsync-dashboard.service`：

```ini
[Unit]
Description=TQSync Web Dashboard
After=network.target

[Service]
Type=simple
User=tqsync
WorkingDirectory=/opt/TQSync/web_dashboard
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable tqsync-dashboard
sudo systemctl start tqsync-dashboard
```

### Docker 部署

创建 `Dockerfile`：

```dockerfile
FROM python:3.11-slim

WORKDIR /app/web_dashboard

COPY web_dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web_dashboard/ .

EXPOSE 8000

CMD ["python", "main.py"]
```

构建和运行：
```bash
docker build -t tqsync-dashboard .
docker run -d -p 8000:8000 \
  -v /opt/TQSync:/app/TQSync \
  tqsync-dashboard
```

---

## ❓ 常见问题

### Q1: 忘记密码怎么办？

A: 重新运行密码设置脚本：
```bash
python set_admin_password.py
```

### Q2: 无法访问面板？

A: 检查：
1. 防火墙是否开放 8000 端口
2. 服务是否运行
3. 查看日志：`main.py` 输出

### Q3: 配置保存后不生效？

A: 
1. 确认保存成功提示
2. 手动重启机器人
3. 检查配置文件权限

### Q4: 统计数据始终为 0？

A: 
当前版本从硬编码返回 0，需要从 MessageSync 获取真实数据：

```python
# 在 main.py 中导入
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.message_sync import MessageSync

# 获取统计数据
@app.get("/api/status")
async def get_status():
    # 需要通过某种方式获取 MessageSync 实例
    # 这可能需要修改现有的架构
    pass
```

### Q5: 如何启用 HTTPS？

A: 使用 Nginx 反向代理（推荐）：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Let's Encrypt 免费证书：
```bash
sudo certbot --nginx -d your-domain.com
```

---

## 🔧 开发调试

### 开启调试模式

```python
# main.py
uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_level="debug")
```

### API 测试

使用 curl 测试：

```bash
# 登录
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'

# 获取状态（替换 TOKEN）
curl http://localhost:8000/api/status \
  -H "Authorization: Bearer TOKEN"
```

### 日志查看

```python
# 添加日志
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/api/config/update")
async def update_config(...):
    logger.info(f"用户 {current_user} 更新了配置")
```

---

## 📚 技术栈

### 后端
- **FastAPI** - 现代高性能 Web 框架
- **Uvicorn** - ASGI 服务器
- **Pydantic** - 数据验证
- **Passlib** - 密码加密
- **Python-Jose** - JWT 实现

### 前端
- **Vue.js 3** - 渐进式框架
- **原生 CSS** - 无额外 UI 库
- **Fetch API** - HTTP 请求

### 安全
- **Argon2** - 密码哈希
- **JWT** - 身份验证
- **CORS** - 跨域控制

---

## 🎯 下一步计划

### v0.1.0 (当前版本)
- ✅ 基础认证
- ✅ 配置管理
- ⏳ 统计数据（待实现真实数据）
- ⏳ 重启功能（待实现实际逻辑）

### v0.2.0 (计划)
- [ ] 实时 WebSocket 推送
- [ ] 日志查看界面
- [ ] 用户绑定管理
- [ ] 消息历史查询

### v0.3.0 (计划)
- [ ] 多用户支持
- [ ] 权限分级
- [ ] 操作审计日志
- [ ] 配置版本控制

---

## 📞 反馈与支持

遇到问题或有改进建议？

- **GitHub Issues**: https://github.com/XSong1205/TQSync/issues
- **讨论区**: https://github.com/XSong1205/TQSync/discussions

---

*最后更新：2026-02-25*  
*TQSync Team*
