# 🤖 Telegram Bot 申请指南

## 📋 准备工作

在开始之前，请确保你具备以下条件：
- 一个可用的 Telegram 账号
- 能够访问 Telegram 的网络环境（可能需要代理）
- 基本的计算机操作知识

## 🚀 申请步骤

### 1. 打开 BotFather
1. 在 Telegram 中搜索 `@BotFather`
2. 点击进入官方机器人账户
3. 确认头像为官方蓝色徽章标识

### 2. 创建新机器人
发送以下命令给 BotFather：
```
/newbot
```

### 3. 设置机器人名称
BotFather 会提示你输入机器人的显示名称，例如：
```
TQSync Bot
```
这个名称会显示在聊天界面中。

### 4. 设置机器人用户名
接下来需要设置机器人的唯一用户名，必须以 `bot` 结尾：
```
TQSyncBot
```
或
```
MyTQSync_Bot
```

### 5. 获取 API Token
创建成功后，BotFather 会返回类似这样的信息：
```
Congratulations! You have successfully created a new bot.

Use this token to access the HTTP API:
5234567890:AAHabcdefghijklmnopqrstuvwxyz123456789

For a description of the Bot API, see this page: https://core.telegram.org/bots/api
```

**重要**：这个 Token 就是你机器人的身份凭证，请妥善保管！

## ⚙️ 基本配置

### 1. 设置机器人描述
```
/setdescription
```
然后选择你的机器人，输入描述信息。

### 2. 设置机器人头像（可选）
```
/setuserpic
```
选择机器人后上传图片。

### 3. 设置命令列表（可选）
```
/setcommands
```
可以设置快捷命令，例如：
```
help - 显示帮助信息
start - 开始使用机器人
status - 查看机器人状态
```

## 🔧 获取 Chat ID

### 方法一：通过 @userinfobot
1. 在 Telegram 搜索 `@userinfobot`
2. 发送 `/start` 命令
3. 记录返回的 ID 信息

### 方法二：通过机器人自身
1. 启动你的机器人
2. 向机器人发送任意消息
3. 查看机器人后端日志中的 chat_id

### 方法三：群组 Chat ID
1. 将机器人添加到群组
2. 在群组中发送消息
3. 通过 API 获取群组信息

## 🔒 安全设置

### 1. 限制机器人权限
```
/setprivacy
```
选择你的机器人，设置隐私模式。

### 2. 设置域名白名单（如果需要）
```
/setdomain
```

## 🛠️ 常用命令参考

| 命令 | 功能 |
|------|------|
| `/newbot` | 创建新机器人 |
| `/mybots` | 管理现有机器人 |
| `/setname` | 修改机器人名称 |
| `/setdescription` | 设置机器人描述 |
| `/setabouttext` | 设置关于信息 |
| `/setuserpic` | 设置头像 |
| `/setcommands` | 设置命令列表 |
| `/setprivacy` | 设置隐私模式 |
| `/deletebot` | 删除机器人 |

## ⚠️ 注意事项

1. **Token 安全**：Never 将 Token 提交到公共代码仓库
2. **速率限制**：Telegram API 有调用频率限制
3. **Webhook vs Polling**：根据需求选择合适的消息接收方式
4. **代理设置**：中国大陆用户可能需要配置代理才能正常使用

## 📚 进阶配置

### Webhook 设置
如果你的机器人需要实时响应，建议配置 Webhook：
```python
import requests

TOKEN = "你的_bot_token"
WEBHOOK_URL = "https://yourdomain.com/webhook"

# 设置 webhook
response = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
    json={"url": WEBHOOK_URL}
)
```

### 获取更新
```python
# 获取最新消息
response = requests.get(
    f"https://api.telegram.org/bot{TOKEN}/getUpdates"
)
```

## 🆘 常见问题

**Q: 机器人没有响应怎么办？**
A: 检查 Token 是否正确，网络连接是否正常

**Q: 如何重置 Token？**
A: 使用 `/revoke` 命令重新生成 Token

**Q: 机器人能加入多少个群组？**
A: 默认限制为 20 个群组，可通过官方申请提高限额

**Q: 如何删除机器人？**
A: 使用 `/deletebot` 命令永久删除
