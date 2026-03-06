# TQSync 配置指南

本文档详细说明如何配置 TQSync (Telegram-QQ Bot) 的各项参数。

## 📋 目录

- [快速开始](#快速开始)
- [配置方式对比](#配置方式对比)
- [.env 配置详解](#env-配置详解)
- [config.yaml 配置详解](#configyaml-配置详解)
- [常见问题](#常见问题)

---

## 🚀 快速开始

### 方法一：使用安装脚本（推荐）

运行安装脚本会自动创建配置文件：

```bash
python install.py
```

脚本会自动：
1. 复制 `.env.example` → `.env`
2. 复制 `config.yaml.example` → `config.yaml`
3. 创建必要的目录（logs, data, temp）

### 方法二：手动创建

```bash
# 复制环境文件
cp .env.example .env

# 复制 yaml 配置文件
cp config.yaml.example config.yaml
```

然后编辑这两个文件，填入你的实际配置。

---

## 🔧 配置方式对比

### .env 文件（推荐）

**优点**：
- ✅ 简洁明了，只包含必要参数
- ✅ 适合快速部署和测试
- ✅ 支持环境变量覆盖
- ✅ 易于在服务器间迁移

**缺点**：
- ❌ 不支持复杂配置
- ❌ 缺少详细注释

**适用场景**：
- 快速测试
- 简单部署
- CI/CD 自动化

### config.yaml 文件

**优点**：
- ✅ 支持完整配置项
- ✅ 详细的中文注释
- ✅ 支持嵌套结构
- ✅ 易于理解和修改

**缺点**：
- ❌ 文件较长
- ❌ 需要 YAML 语法知识

**适用场景**：
- 生产环境
- 需要自定义高级选项
- 团队协作

---

## 📝 .env 配置详解

### 必要配置

```bash
# ===========================================
# Telegram Bot 配置
# ===========================================

# Telegram Bot Token
# 从 @BotFather 获取
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Telegram 聊天 ID
# 可以是群组、频道或私聊的 ID
TELEGRAM_CHAT_ID=-1001234567890

# ===========================================
# QQ Bot 配置 (NapCat)
# ===========================================

# NapCat WebSocket URL
# NapCat 反向 WebSocket 连接地址
NAPCAT_WS_URL=ws://127.0.0.1:8080/ws

# NapCat HTTP API URL
# NapCat HTTP 接口地址
NAPCAT_HTTP_URL=http://127.0.0.1:5700

# QQ 群号
# 机器人所在的 QQ 群号码
QQ_GROUP_ID=123456789
```

### 可选配置

```bash
# ===========================================
# 日志配置
# ===========================================

# 日志级别
# 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# ===========================================
# Telegram 代理设置（中国大陆用户需要）
# ===========================================

# 代理配置（JSON 格式）
TELEGRAM_PROXY={"scheme": "http", "hostname": "127.0.0.1", "port": 7890}
```

---

## 📄 config.yaml 配置详解

### Telegram 配置

```yaml
telegram:
  # Bot Token (必填)
  token: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
  
  # 聊天 ID (必填)
  chat_id: "-1001234567890"
  
  # 代理配置（可选）
  proxy:
    enable: true           # 是否启用代理
    scheme: "http"         # 代理类型：http, https, socks5
    hostname: "127.0.0.1"  # 代理地址
    port: 7890             # 代理端口
    username: ""           # 用户名（可选）
    password: ""           # 密码（可选）
```

### QQ 配置

```yaml
qq:
  # WebSocket URL (必填)
  ws_url: "ws://127.0.0.1:8080/ws"
  
  # HTTP API URL (必填)
  http_url: "http://127.0.0.1:5700"
  
  # 群号 (必填)
  group_id: "123456789"
```

### 同步配置

```yaml
sync:
  # 双向同步（默认开启）
  bidirectional: true
  
  # 过滤关键词
  filter_keywords:
    - "#skip"
    - "!skip"
  
  # 最大消息长度
  max_message_length: 4096
  
  # 发送冷却时间（秒）
  cooldown_time: 1
  
  # 媒体文件配置
  media:
    enable: true
    supported_types:
      - photo      # 照片
      - video      # 视频
      - audio      # 音频
      - voice      # 语音
      - document   # 文档
      - sticker    # 贴纸
      - animation  # GIF
    max_file_size: 50        # MB
    temp_file_retention: 24  # 小时
  
  # 回复功能
  reply:
    enable: true
    format: "[{replier} 回复 {replied}] 原始消息：『{original_message}』，新回复：『{reply_message}』"
    simple_format: "[回复 @{username}] {message}"
  
  # 命令前缀
  filter_prefix: "!"
```

### 日志配置

```yaml
logging:
  # 日志级别
  level: "INFO"
  
  # 日志文件路径
  file: "logs/bot.log"
  
  # 输出到控制台
  console: true
  
  # 日志格式
  format: "{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function}:{line} - {message}"
```

### 数据库配置

```yaml
database:
  # 数据库文件路径
  path: "data/tqsync.db"
  
  # 自动备份
  auto_backup: true
  
  # 备份间隔（小时）
  backup_interval: 24
```

### 高级配置

```yaml
advanced:
  # 重试配置
  retry:
    max_retries: 3    # 最大重试次数
    delay: 2          # 重试间隔（秒）
  
  # 用户绑定
  binding:
    code_length: 6    # 验证码长度
    timeout: 300      # 超时时间（秒）
  
  # 消息 ID 映射
  message_mapping:
    ttl: 86400              # 存活时间（秒）
    cleanup_interval: 3600  # 清理间隔（秒）
```

---

## 🔍 获取配置信息的教程

### 获取 Telegram Bot Token

1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot` 创建新机器人
3. 按提示设置机器人名称
4. 获得 Token，格式类似：`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### 获取 Telegram Chat ID

**方法一：使用 @userinfobot**
1. 在 Telegram 搜索 `@userinfobot`
2. 发送任意消息
3. 它会返回你的 User ID

**方法二：通过网页**
1. 打开：https://www.idbot.com/
2. 发送消息给机器人
3. 查看返回的 ID

**方法三：手动计算**
- 群组 ID 通常在前面加 `-100`
- 例如：群组链接 `t.me/groupname` 对应的 ID 可能是 `-1001234567890`

### 配置 NapCat

1. **安装 NapCat**
   ```bash
   # Linux
   curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
   sudo bash napcat.sh --docker n --cli y
   
   # Windows
   # 下载一键包解压即可
   ```

2. **获取配置信息**
   - 打开 NapCat WebUI（通常 http://127.0.0.1:6099）
   - 登录后进入「配置」页面
   - 找到 WebSocket 和 HTTP 地址

3. **常用端口**
   - WebSocket: `ws://127.0.0.1:8080/ws`
   - HTTP API: `http://127.0.0.1:5700`

### 获取 QQ 群号

1. 打开 QQ 群聊天窗口
2. 点击群右上角的菜单
3. 查看群资料
4. 群号就是显示的一串数字

---

## ⚠️ 常见问题

### Q1: 配置文件在哪里？

A: 运行 `python install.py` 后，会在项目根目录生成：
- `.env`
- `config.yaml`

如果没有，可以手动复制模板文件。

### Q2: .env 和 config.yaml 哪个优先级高？

A: `.env` 文件的优先级更高。如果两个文件都配置了相同的参数，以 `.env` 为准。

### Q3: 修改配置后需要重启吗？

A: 是的，需要重启机器人才能生效。

```bash
# 停止机器人
Ctrl + C

# 重新启动
python main.py
```

### Q4: 配置不生效怎么办？

A: 检查清单：
1. ✅ 配置文件是否存在
2. ✅ YAML 语法是否正确
3. ✅ 键名是否拼写错误
4. ✅ 值是否正确（如 Token、ID 等）
5. ✅ 重启机器人

### Q5: 如何使用代理？

A: 两种方法：

**方法一：在 config.yaml 中配置**
```yaml
telegram:
  proxy:
    enable: true
    scheme: "http"
    hostname: "127.0.0.1"
    port: 7890
```

**方法二：使用系统代理**
```bash
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
python main.py
```

### Q6: 日志级别应该设为什么？

A: 
- **DEBUG**: 开发调试时使用，输出所有信息
- **INFO**: 日常使用，输出重要信息
- **WARNING**: 仅警告和错误
- **ERROR**: 仅错误信息
- **CRITICAL**: 仅严重错误

推荐：`INFO`

---

## 📚 相关文档

- [README.md](README.md) - 快速开始
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) - 项目概览
- [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) - 安全配置清单
- [USAGE.md](USAGE.md) - 使用说明

---

*更新日期：2026-02-25*
*TQSync 项目文档*
