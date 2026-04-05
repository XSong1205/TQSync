# TQSync NEXT

TQSync 是一个简单的基于 Python 的异步机器人，用于实现 Telegram 群组与 QQ 群之间的双向消息同步。

> [!TIP]
> Next 分支功能已经足够强大，且兼容性、速度大幅提升，新用户建议使用 Next 版。目前重构版仍处于早期阶段，如有 Bug 敬请谅解！

## 重构版功能特性

- **管理 API**：提供 FastAPI 接口，支持动态修改配置、管理绑定关系及服务重启。
- **模块化设计**：代码结构清晰，易于后续扩展多媒体（图片、文件等）同步功能。
- **绑定同步**：支持用户信息绑定，双向同步，配合同步撤回、同步回复
- **WebUI**(目前可用，待完善)：可便捷地通过网页实现信息统计查看、重启、配置文件、绑定用户、屏蔽词添加(Todo)等

## 技术栈

- **Python 3.9+**
- **Telegram**: `python-telegram-bot` (v20+)
- **QQ**: `aiohttp` (对接 Napcat OneBot v11 HTTP)
- **Web Framework**: `FastAPI` + `Uvicorn` + `Vue`
- **Database**: `SQLite`

## 安装

### 快速安装(Windows)

执行前请确认您已安装Python。

```Command-Prompt / Powershell
python install.py
```

### 手动安装(Windows&Linux)

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置项目

复制配置模板并填入你的信息：

```bash
cp config.yaml.example config.yaml
```

## 配置文件

在 `config.yaml` 中配置：
- `telegram.bot_token`: 从 @BotFather 获取的 Token。
- `telegram.group_id`: 需要同步的 TG 群组 ID。
- `qq.napcat_api_url`: Napcat 运行的地址（例如 `http://127.0.0.1:3000`）。
- `qq.group_id`: 需要同步的 QQ 群组号。
- 其他配置项说明请查看 `config.yaml` 中的注释。


## 配置 Napcat

请前往项目目录/docs/napcat_config_guide获取详细信息

## 运行机器人

```Shell
python main.py
```

## 使用说明

- **绑定用户**：在 Telegram 群组中发送 `/bind <你的QQ号>`。
- **WebUI**：默认运行在 `http://localhost:8081/`，可以查看和管理绑定关系或修改配置。

