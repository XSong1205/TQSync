# TQSync NEXT

TQSync 是一个简单的基于 Python 的异步机器人，用于实现 Telegram 群组与 QQ 群之间的双向消息同步。


> [!CAUTION]
> 本项目为开源学习交流用途，仅供技术研究与个人学习。请勿将本项目用于任何违法违规场景。
> 本程序不提供、也不包含任何代理、绕过审查等可能涉及法律风险的功能或实现。
> 使用者需自行确保群组同步内容的合法性，项目作者不对用户生成或发送的内容承担任何法律责任。
> Telegram 和 QQ 仅为即时通讯软件，与本项目无任何从属、合作或关联关系。项目均使用第三方库与软件通信，并未对软件本体进行Hook/反编译/修改操作，如有侵权请务必告知。

## 重构版功能特性

- **管理 API**：提供 FastAPI 接口，支持动态修改配置、管理绑定关系及服务重启。
- **模块化设计**：每个功能都是模块化设计，后续可在WebUI中自由开关。
- **绑定同步**：支持用户信息绑定，双向同步，配合同步撤回、同步回复
- **WebUI**：可便捷地通过网页实现信息统计查看、重启、配置文件、绑定用户、屏蔽词添加(Todo)等

## 技术栈

- **Python 3.12+**
- **Telegram**: `python-telegram-bot` (v20+)
- **QQ**: `aiohttp` (对接 Napcat OneBot v11 HTTP)
- **Web Framework**: `FastAPI` + `Uvicorn` + `Vue`
- **Database**: `SQLite`

## 可选依赖

### FFmpeg (推荐安装)
FFmpeg 用于以下功能：
- WebM 格式动态贴纸转换 (WebM -> GIF)
- 语音消息转码 (OGG -> AMR)

**自动下载（推荐）：**
启动机器人时，如果检测到未安装 FFmpeg，机器人会在 QQ 和 Telegram 群内发送提示。您只需在任意一端回复 `/confirm`，机器人将自动下载并配置适合当前系统的 FFmpeg。
如您不想安装且不想再被提示，请输入 `/cancel`，然后程序将记录此选择，下次不再提示，此后您可手动安装。

**手动安装方法：**
如果您希望手动安装或自动下载失败，请参考以下命令：
- **Windows**: `winget install Gyan.FFmpeg`
- **Linux**(Debian系): `sudo apt install ffmpeg`
- **macOS**: `brew install ffmpeg`

安装完成后，请重启 TQSync 以生效。

### rlottie (推荐安装)

`rlottie-python` 用于将 TGS 格式动态贴纸渲染为 GIF。安装 `requirements.txt` 中的依赖后即可使用，无需额外配置。

**验证安装:**
```bash
python -c "from rlottie_python import LottieAnimation; print('rlottie 安装成功')"
```

**注意:** 如果未安装 `rlottie-python`，动态贴纸将无法转换为 GIF，但仍可正常同步静态贴纸。

## 安装

### 快速安装(Windows)

执行前请确认您已安装Python。

```Command-Prompt / Powershell
python install.py
```

### 手动安装(Windows/Linux/macOS)

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

## Docker 部署

TQSync 提供官方 Docker 镜像 [`xsong1205/tqsync`](https://hub.docker.com/r/xsong1205/tqsync)，镜像内已内置 FFmpeg 与 Python 依赖。

### 1. 准备配置文件

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml` 填入 Telegram Token、群组 ID、Napcat 地址与 QQ 群号。

### 2. 启动

```bash
cp docker-compose.yml.example docker-compose.yml
docker compose up -d
```

### 3. 更新镜像

容器内禁用进程内自动更新，更新请使用：

```bash
docker compose pull
docker compose up -d
```

### Docker 注意事项

- `config.yaml` 以只读方式挂载进容器，通过 WebUI 修改的配置仅在内存中生效，不会写回宿主机文件。
- 容器内 FFmpeg 已预装，启动时不会触发 `/confirm` 下载提示。
- 数据持久化目录：`./db`（数据库）、`./logs`（日志）、`./plugins`（插件）、`./temp`（临时文件）。
- 自动更新检查与 `/checkupdate`、`/reboot` 在容器内被禁用，请改用 `docker compose` 管理。

## 使用说明

- **绑定用户**：在 Telegram 群组中发送 `/bind <你的QQ号>`。
- **WebUI**：默认运行在 `http://localhost:8081/`，可以查看和管理绑定关系或修改配置。

