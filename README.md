# TQSync NEXT

TQSync 是一个用 Python 写的异步机器人，把 Telegram 群和 QQ 群连起来，两边发的消息互相同步。TG 里的消息会转发到 QQ，QQ 里的消息也会转发到 TG，包括图片、视频、语音、贴纸这些。

> [!CAUTION]
> 本项目为开源学习交流用途，仅供技术研究与个人学习。请勿将本项目用于任何违法违规场景。
> 本程序不提供、也不包含任何代理、绕过审查等可能涉及法律风险的功能或实现。
> 使用者需自行确保群组同步内容的合法性，项目作者不对用户生成或发送的内容承担任何法律责任。
> Telegram 和 QQ 仅为即时通讯软件，与本项目无任何从属、合作或关联关系。项目均使用第三方库与软件通信，并未对软件本体进行 Hook/反编译/修改操作，如有侵权请务必告知。

## 功能

- **双向同步**：文本、图片、视频、文件、语音、贴纸、合并转发，双向转发，还能同步撤回和回复
- **用户绑定**：把自己的 TG 和 QQ 绑定起来，可以用统一昵称，同步回复和撤回时能对上号
- **管理 API + WebUI**：浏览器里查看统计、改配置、管理绑定和屏蔽词、看日志、重启
- **插件系统**：消息处理逻辑可以写成插件，按需启用，详见 `docs/plugin_development_guide.md`
- **屏蔽词**：双端都能配置，命中关键词的消息直接拦截
- **同步方向控制**：可设为双向、仅 TG→QQ 或仅 QQ→TG

## 技术栈

- **Python 3.12+**
- **Telegram**: `python-telegram-bot`（v20+）
- **QQ**: `aiohttp`，对接 NapCat 的 OneBot v11 HTTP 接口
- **Web**: `FastAPI` + `Uvicorn`，前端用 Vue 3（CDN 引入，无需构建）
- **存储**: SQLite

## 可选依赖

### FFmpeg（推荐）

FFmpeg 用于两类转换：

- WebM 动态贴纸 → GIF
- 语音消息 OGG → AMR（QQ 兼容格式）

**自动下载（推荐）：** 启动时如果检测到没装 FFmpeg，机器人会在两个群里发提示。你在任意一端回复 `/confirm`，它会自动下载并配置。不想装的话回复 `/cancel`，以后不再提示，之后再手动装也行。

**手动安装：**

- **Windows**: `winget install Gyan.FFmpeg`
- **Linux**（Debian 系）: `sudo apt install ffmpeg`
- **macOS**: `brew install ffmpeg`

装完重启 TQSync 生效。

### rlottie（推荐）

`rlottie-python` 用于把 TGS 格式动态贴纸渲染成 GIF，装好 `requirements.txt` 里的依赖就能用，不用额外配置。

验证是否装好：

```bash
python -c "from rlottie_python import LottieAnimation; print('rlottie 安装成功')"
```

没装的话，动态贴纸转不了 GIF，但静态贴纸不受影响。

## 安装

### Windows 快速安装

确认已装 Python 3.9+。

**方式一（推荐）**：双击 `install.bat`，自动建 `venv` 并装依赖。

**方式二（命令行）**：

```bat
python install.py
```

两种方式装完后，用 `venv\Scripts\python.exe main.py` 启动。

### Linux 快速安装

支持 Debian/Ubuntu、CentOS/RHEL、Arch 系。脚本会自动建 `venv`、装依赖、装 `ffmpeg`/`screen`、生成 `config.yaml`，并写好快捷命令。

```bash
bash scripts/install.sh
```

装完重开终端（或 `source ~/.bashrc`），就能用这些命令：

| 命令 | 作用 |
| --- | --- |
| `tqstart` | 在 screen 后台启动机器人 |
| `tqlog` | 回到运行日志窗口（退出按 `Ctrl+A` 再按 `D`） |
| `tqstop` | 停止机器人 |
| `tqrestart` | 重启机器人 |
| `tqstatus` | 查看运行状态 |
| `tqlogs` | 查看最近日志 |

不想用别名的话，可以直接调管理脚本：

```bash
bash scripts/tqsync.sh start      # 启动
bash scripts/tqsync.sh attach     # 回到日志窗口 (Ctrl+A D 退出)
bash scripts/tqsync.sh stop       # 停止
bash scripts/tqsync.sh status     # 状态
```

> 机器人在 `screen` 会话里后台运行，`/reboot` 和自动更新会在会话内自己重启，不用手动管。

### 手动安装（Windows / Linux / macOS）

#### 1. 装依赖

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt    # Windows
# venv/bin/pip install -r requirements.txt      # Linux / macOS
```

#### 2. 配置

```bash
cp config.yaml.example config.yaml
```

## 配置文件

改 `config.yaml`：

- `telegram.bot_token`：从 @BotFather 拿的 Token
- `telegram.group_id`：要同步的 TG 群组 ID（负数）
- `qq.napcat_api_url`：NapCat 运行地址，例如 `http://127.0.0.1:3000`
- `qq.group_id`：要同步的 QQ 群号
- `sync.direction`：同步方向，`both` / `tg_to_qq` / `qq_to_tg`

其余选项看 `config.yaml` 里的注释。

## 配置 NapCat

详细步骤见 `docs/napcat_config_guide.md`。

## 运行

```bash
venv\Scripts\python.exe main.py    # Windows
# venv/bin/python main.py          # Linux / macOS（或 tqstart 后台运行）
```

## Docker 部署

官方镜像 [`xsong1205/tqsync`](https://hub.docker.com/r/xsong1205/tqsync)，已内置 FFmpeg 和 Python 依赖。

```bash
cp config.yaml.example config.yaml
cp docker-compose.yml.example docker-compose.yml
```

填好 `config.yaml`（Token、群组 ID、NapCat 地址、QQ 群号），然后：

```bash
docker compose up -d
```

更新镜像：

```bash
docker compose pull
docker compose up -d
```

**注意事项：**

- `config.yaml` 只读挂载进容器，WebUI 里改的配置只在内存生效，不会写回宿主机
- 容器里 FFmpeg 已预装，启动时不会弹 `/confirm` 下载提示
- 持久化目录：`./db`（数据库）、`./logs`（日志）、`./plugins`（插件）、`./temp`（临时文件）
- 容器内禁用了进程内自动更新、`/checkupdate` 和 `/reboot`，升级用 `docker compose` 管理

## 使用

- **绑定**：先在 QQ 群里发 `/bind` 拿验证码，再到 TG 群里发 `/bind <验证码>` 完成绑定
- **WebUI**：默认 `http://localhost:8081/`，管理绑定、配置、屏蔽词等
- 常用命令发 `/help` 查看
