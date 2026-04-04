# TQSync - Next

TQSync 是一个简单的基于 Python 的异步机器人，用于实现 Telegram 群组与 QQ 群之间的双向消息同步。

> [!CAUTION]
> 目前已重构(Next分支)，但重构版仍在开发中，缺失功能，不便之处敬请谅解
> 请勿把您的服务器暴露在公网！API尚未做任何安全措施如密码验证等！本项目不对因此带来的安全问题负责

## 重构版功能特性

- **管理 API**：提供 FastAPI 接口，支持动态修改配置、管理绑定关系及服务重启。
- **模块化设计**：代码结构清晰，易于扩展多媒体（图片、文件等）同步功能。
- **绑定同步**：支持用户信息绑定，双向同步，配合后续同步撤回(Todo)
- **WebUI**(Todo)：可便捷地通过网页实现信息统计(Todo)、重启、配置文件、绑定用户、屏蔽词添加(Todo)等

## 技术栈

- **Python 3.9+**
- **Telegram**: `python-telegram-bot` (v20+)
- **QQ**: `aiohttp` (对接 Napcat OneBot v11 HTTP)
- **Web Framework**: `FastAPI` + `Uvicorn`
- **Database**: `SQLite` (`aiosqlite`)

## 快速安装(Windows)

执行前请确认您已安装Python。

```Command-Prompt / Powershell
python install.py
```

## 手动安装(Windows&Linux)

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置项目

复制配置模板并填入你的信息：

```bash
cp config.yaml.example config.yaml
```

在 `config.yaml` 中配置：
- `telegram.bot_token`: 从 @BotFather 获取的 Token。
- `telegram.group_id`: 需要同步的 TG 群组 ID。
- `qq.napcat_api_url`: Napcat 运行的地址（例如 `http://127.0.0.1:3000`）。
- `qq.group_id`: 需要同步的 QQ 群组号。


## 3. 配置 Napcat

在 Napcat 的配置中，启用 **HTTP POST** 模式（Webhook），并将上报地址设置为：
`http://<你的服务器IP>:8080/webhook/qq`

### 4. 运行机器人

```bash
python main.py
```

## 使用说明

- **绑定用户**：在 Telegram 群组中发送 `/bind <你的QQ号>`。
- **管理 API**：默认运行在 `http://localhost:8081/docs`，可以查看和管理绑定关系或修改配置。

## 目录结构

- `config/`: 配置加载逻辑。
- `db/`: 数据库操作与 Schema 定义。
- `handlers/`: TG 和 QQ 的消息处理入口。
- `core/`: 核心同步引擎。
- `api/`: 内部管理 API 接口。
