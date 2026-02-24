# Telegram 代理配置指南

## 🌐 为什么需要代理？

由于网络环境限制，中国大陆用户访问Telegram API需要通过代理服务器。

## 🛠️ 支持的代理类型

### 1. SOCKS5 代理（推荐）
- 最稳定的选择
- 支持用户名密码认证
- 适合大多数科学上网工具

### 2. HTTP 代理
- 配置简单
- 兼容性好
- 部分场景下可能不稳定

## ⚙️ 配置方法

### 方法一：通过环境变量配置（推荐）

编辑 `.env` 文件：

```env
# Telegram 代理配置
TELEGRAM_PROXY_ENABLE=true
TELEGRAM_PROXY_TYPE=socks5
TELEGRAM_PROXY_HOST=127.0.0.1
TELEGRAM_PROXY_PORT=1080
TELEGRAM_PROXY_USERNAME=your_username  # 可选
TELEGRAM_PROXY_PASSWORD=your_password  # 可选
```

### 方法二：通过配置文件配置

编辑 `config.yaml` 文件：

```yaml
telegram:
  token: "YOUR_TELEGRAM_BOT_TOKEN"
  chat_id: "YOUR_TELEGRAM_CHAT_ID"
  proxy:
    enable: true
    type: "socks5"  # 或 "http"
    host: "127.0.0.1"
    port: 1080
    username: ""  # 可选
    password: ""  # 可选
```

## 🔧 常见代理软件配置

### Clash 配置
```
代理类型: socks5
地址: 127.0.0.1
端口: 7890  # 或其他端口
```

### V2Ray 配置
```
代理类型: socks5
地址: 127.0.0.1
端口: 1080  # 默认端口
```

### Shadowsocks 配置
```
代理类型: socks5
地址: 127.0.0.1
端口: 1080  # 默认端口
```

### Trojan 配置
```
代理类型: socks5
地址: 127.0.0.1
端口: 1080  # 或其他端口
```

## 🧪 测试代理配置

### 1. 启用代理后测试连接
```bash
python test.py
```

### 2. 查看日志确认代理状态
```
INFO | Telegram机器人已配置代理
INFO | Telegram代理已配置: socks5://127.0.0.1:1080
```

## 🔍 故障排除

### 常见问题

**Q: 代理配置后仍然无法连接**
A: 
1. 检查代理软件是否正常运行
2. 确认代理端口是否正确
3. 测试代理是否能正常访问Telegram

**Q: 出现认证错误**
A:
1. 检查用户名密码是否正确
2. 确认代理服务器是否支持认证
3. 尝试不使用认证的代理

**Q: 连接超时**
A:
1. 检查网络连接
2. 确认代理服务器可用性
3. 尝试更换代理服务器

### 调试方法

在 `config.yaml` 中设置更详细的日志级别：
```yaml
logging:
  level: "DEBUG"
```

## 🛡️ 安全建议

1. **使用本地代理**：尽量使用本地回环地址(127.0.0.1)
2. **保护凭证**：不要在代码中硬编码代理用户名密码
3. **定期更换**：定期更换代理配置和凭证
4. **最小权限**：只为必需的服务配置代理

## 📱 移动端配置

如果在移动设备上部署：

### Termux (Android)
```bash
# 安装代理工具
pkg install shadowsocks-libev

# 配置环境变量
export ALL_PROXY=socks5://127.0.0.1:1080
```

### iOS (通过SSH隧道)
```bash
# 本地端口转发
ssh -D 1080 user@server
```

## 🔄 代理切换策略

项目支持动态代理切换，可以通过修改配置文件实现：

```yaml
# 无代理模式
proxy:
  enable: false

# SOCKS5代理模式
proxy:
  enable: true
  type: "socks5"
  host: "127.0.0.1"
  port: 1080

# HTTP代理模式
proxy:
  enable: true
  type: "http"
  host: "127.0.0.1"
  port: 8080
```

## 🎯 最佳实践

1. **开发环境**：使用稳定的SOCKS5代理
2. **生产环境**：考虑使用负载均衡的代理集群
3. **备份方案**：准备多个代理备选方案
4. **监控告警**：监控代理连接状态，及时发现问题

通过以上配置，你的Telegram-QQ同步机器人就能在中国大陆网络环境下正常使用了！