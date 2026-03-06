# TQSync 配置快速指南

## 🚀 快速开始

### 1. 运行安装脚本

```bash
python install.py
```

安装脚本会自动：
- ✅ 创建 `.env` 配置文件
- ✅ 创建 `config.yaml` 配置文件  
- ✅ 创建必要的目录（logs, data, temp）

### 2. 编辑配置文件

#### 方式一：使用 .env（推荐）

编辑 `.env` 文件，填写以下**必要参数**：

```bash
# Telegram Bot Token（从 @BotFather 获取）
TELEGRAM_TOKEN=your_bot_token_here

# Telegram 聊天 ID
TELEGRAM_CHAT_ID=your_chat_id_here

# NapCat WebSocket 地址
NAPCAT_WS_URL=ws://127.0.0.1:8080/ws

# NapCat HTTP API 地址
NAPCAT_HTTP_URL=http://127.0.0.1:5700

# QQ 群号
QQ_GROUP_ID=your_group_id_here
```

#### 方式二：使用 config.yaml

编辑 `config.yaml` 文件，填写完整配置：

```yaml
telegram:
  token: "your_bot_token_here"
  chat_id: "your_chat_id_here"

qq:
  ws_url: "ws://127.0.0.1:8080/ws"
  http_url: "http://127.0.0.1:5700"
  group_id: "your_group_id_here"
```

### 3. 启动机器人

```bash
python main.py
```

---

## 📋 配置文件说明

### .env.example → .env

简洁的环境配置文件，包含必要参数。

**优点**：
- ✅ 简单明了
- ✅ 快速部署
- ✅ 支持环境变量覆盖

**适用场景**：快速测试、简单部署

### config.yaml.example → config.yaml

完整的 YAML 配置文件，包含所有选项和详细注释。

**优点**：
- ✅ 完整配置项
- ✅ 详细中文注释
- ✅ 支持高级选项

**适用场景**：生产环境、自定义配置

---

## 🔍 获取配置信息

### Telegram Bot Token
1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot` 创建机器人
3. 按提示设置名称
4. 获得 Token（格式：`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`）

### Telegram Chat ID
- 使用 `@userinfobot` 查询
- 或访问：https://www.idbot.com/

### NapCat 配置
1. 安装 NapCat
2. 打开 WebUI（通常 http://127.0.0.1:6099）
3. 查看 WebSocket 和 HTTP 地址
4. 常用配置：
   - WebSocket: `ws://127.0.0.1:8080/ws`
   - HTTP API: `http://127.0.0.1:5700`

### QQ 群号
1. 打开 QQ 群聊天窗口
2. 点击右上角菜单
3. 查看群资料
4. 群号即为所求

---

## ⚙️ 配置优先级

如果同时配置了 `.env` 和 `config.yaml`：

1. **环境变量优先级最高**（`.env` 中的配置）
2. `config.yaml` 次之
3. 默认值最低

---

## 📚 详细文档

更详细的配置说明请查看：
- [CONFIG_GUIDE.md](CONFIG_GUIDE.md) - 完整配置指南
- [README.md](README.md) - 项目说明
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) - 项目概览

---

*更新日期：2026-02-25*
