# TQSync

TQSync 是一个简单的基于 Python 的机器人，用于实现 Telegram 与 QQ 之间的双向群组消息同步。


> [!CAUTION]
> 本项目为开源学习交流用途，仅供技术研究与个人学习。请勿将本项目用于任何违法违规场景。
> 使用者需自行确保群组同步内容的合法性.

## 同步功能支持情况

| 功能 | 是否支持 |
| :--- | :---: |
| 文本消息同步 | ✅ |
| 图片视频同步 | ✅ |
| 语音消息同步 | ✅ |
| 文件消息同步 | ✅ |
| Stickers 同步 | ✅ |
| QQ 表情同步 | ❓ |
| 合并转发同步 | ✅ |
| 引用回复同步 | ✅ |
| 消息撤回同步 | ✅ |
| @ 提及同步 | ✅ |
| 置顶消息 - 群公告同步 | ✅ |
| 小表情转换 | ❌ |
| 戳一戳同步 | ❌ |
| 表情回应同步 | ❌ |




## 技术栈

- **Python 3.12+**
- **Telegram**: `python-telegram-bot` (v20+)
- **QQ**: `aiohttp` (对接 Napcat OneBot v11 HTTP)
- **Web Framework**: `FastAPI` + `Uvicorn` + `Vue`
- **Database**: `SQLite`


## 安装

### 快速安装(Windows)

执行前请确认您已安装Python 3.12+。

**方式一 (推荐，自动创建虚拟环境):** 双击运行 `install.bat`

**方式二 (命令行):**
```Command-Prompt / Powershell
python install.py
```

两种方式都会自动创建 `venv` 虚拟环境并安装依赖，完成后使用 `venv\Scripts\python.exe main.py` 启动。

### 快速安装(Linux)

支持 Debian/Ubuntu、CentOS/RHEL、Arch 系发行版。脚本会自动：创建 `venv` 虚拟环境、安装依赖、安装 `ffmpeg`/`tmux`（并保留 `screen` 作为回退）、生成 `config.yaml`，并写入快捷命令。

```bash
bash scripts/install.sh
```

安装完成后，重启终端或执行 `source ~/.bashrc`，即可使用快捷命令：

| 命令 | 说明 |
| --- | --- |
| `tqstart` | 在 tmux 后台启动机器人 |
| `tqlog` | 进入日志窗口，**鼠标滚轮可翻历史** |
| `tqshell` | 切到命令窗口，实时执行 `tqstop`/`tqrestart` 等命令 |
| `tqstop` | 停止机器人 |
| `tqrestart` | 重启机器人 |
| `tqstatus` | 查看运行状态（含窗口列表） |
| `tqlogs` | 查看最近日志（自动解析 JSON 行） |

不想用别名时，也可直接调用管理脚本：

```bash
bash scripts/tqsync.sh start      # 启动
bash scripts/tqsync.sh attach     # 进入日志窗口（滚轮翻历史）
bash scripts/tqsync.sh shell      # 切换到命令窗口
bash scripts/tqsync.sh stop       # 停止
bash scripts/tqsync.sh status     # 状态
bash scripts/tqsync.sh logs 100   # 最近 100 行（已格式化）
```

> **说明:** 机器人在 tmux 会话 `tqsync` 中后台运行，分为 `logs`（实时日志）和 `shell`（命令窗口）两个窗口：
> - `Ctrl+b` 然后按 `0` / `1` 切换窗口，`Ctrl+b` 然后按 `d` 退出（进程继续后台运行）；
> - 日志窗口内直接滚动鼠标滚轮即可回看历史（默认保留 10 万行），按 `q` 退出翻页；
> - 未安装 `tmux` 时自动回退到 `screen`（翻页用 `Ctrl+A [`），`/reboot` 与自动更新在两种会话下都能自动重启。

### 手动安装(Windows/Linux/macOS)

#### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt    # Windows
# venv/bin/pip install -r requirements.txt      # Linux / macOS
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

请前往项目目录 `/docs/napcat_config_guide.md` 获取详细信息

## 运行机器人

```Shell
venv\Scripts\python.exe main.py    # Windows
# tqstart                          # Linux / macOS (或使用 venv/bin/python main.py 运行)
```

## Docker 部署

TQSync 提供官方 Docker 镜像 [`xsong1205/tqsync`](https://hub.docker.com/r/xsong1205/tqsync)，支持 `amd64` 与 `arm64` 架构，镜像内置 FFmpeg、证书套件与 Python 运行环境。

### 1. 准备配置

```bash
# 复制配置文件模板（重要：必须在启动前创建此文件，避免被 Docker 误识别为目录）
cp config.yaml.example config.yaml
```

编辑 `config.yaml` 填入 Telegram Bot Token、目标群组 ID 等配置。

> **提示（NapCat 通信地址）**：
> - 若 NapCat 部署在同一台宿主机上，可将 `config.yaml` 中的 `qq.napcat_api_url` 填写为 `http://host.docker.internal:3000`；
> - NapCat 的 HTTP Webhook 地址请填写为 `http://<宿主机IP或局域网IP>:8080/webhook/qq`。

### 2. 启动服务

```bash
# 复制 compose 模板
cp docker-compose.yml.example docker-compose.yml

# 启动容器
docker compose up -d
```

### 3. 查看日志与状态

```bash
# 查看实时日志
docker compose logs -f

# 检查健康检查状态
docker compose ps
```

### 4. 更新镜像

```bash
docker compose pull
docker compose up -d
```

### Docker 运行特性与说明

- **非 root 降权运行**：容器内置 `gosu` 权限管理，挂载目录会自动处理权限，杜绝 Linux 宿主机常见的 SQLite 数据库与日志写入 `Permission Denied` 异常。
- **健康检查**：内置高效的轻量级 HTTP 健康探测，随时反映服务就绪状态。
- **持久化目录**：
  - `./db`：SQLite 数据库持久化存储；
  - `./logs`：日志文件目录（Compose 已配置日志轮转，防止打满磁盘）；
  - `./plugins`：自定义插件目录；
  - `./temp`：临时转换媒体缓存。
- **配置只读保护**：`config.yaml` 默认以只读挂载，防止容器进程意外覆盖宿主机配置文件。

## 使用说明

- **绑定用户**：在 Telegram 群组中发送 `/bind <你的QQ号>`。
- **WebUI**：默认运行在 `http://localhost:8081/`，可以查看和管理绑定关系或修改配置。

