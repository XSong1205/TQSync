# TQSync

TQSync 是一个简单的基于 Python 的机器人，用于实现 Telegram 与 QQ 之间的双向群组消息同步。


> [!CAUTION]
> 本项目为开源学习交流用途，仅供技术研究与个人学习。请勿将本项目用于任何违法违规场景。
> 使用者需自行确保群组同步内容的合法性.

## 项目初衷与理念

TQSync 的核心初衷是**专注于 Telegram 与 QQ 之间纯粹、可靠、高质量的双向群组消息与媒体同步**。

我们致力于让跨平台的群组成员拥有无缝的交流体验，抹平不同 IM 平台之间的媒体格式差异与交互鸿沟。因此，TQSync 坚守**职责单一与轻量专注**的设计原则：
- 🎯 **聚焦消息与媒体桥接**：深耕文本、图片、语音（自动转码）、视频、文件、贴纸（转动图）、表情、合并转发、引用回复、撤回同步与置顶公告互通。
- 🚫 **剔除无用冗余功能**：**明确不引入**群管类功能（如禁言/解禁、踢人、设管理员、改名片、入群审核）以及非必要的群拓展/娱乐功能（如群相册、签到打卡、群待办、戳一戳、文件目录操作等），避免权限膨胀与复杂度上升，保障桥接服务的稳定性与纯粹性。

## 双向同步功能支持矩阵

| 模块分类 | 功能特性 | 支持状态 | 说明与实现细节 |
| :--- | :--- | :---: | :--- |
| **消息类型** | **文本消息** | ✅ 已支持 | 双向完整支持文本换行与基础排版，自动转义 MarkdownV2 特殊符号 |
| | **图片消息** | ✅ 已支持 | 双向高清原图/压缩图同步，内置防 NapCat 缓存清理的本地暂存机制 |
| | **语音消息** | ✅ 已支持 | 双向全自动转码：QQ (AMR/Silk) ↔ Telegram (OGG Opus)（依赖 FFmpeg） |
| | **视频消息** | ✅ 已支持 | 双向流媒体转发，智能推导并补全视频文件名及扩展名 |
| | **文件与文档** | ✅ 已支持 | 双向文件同步，基于文件魔数 (Magic Bytes) 智能纠正扩展名，大文件分块流式传输 |
| | **贴纸 / 动图** | ✅ 已支持 | Telegram 贴纸转 QQ GIF：支持静态 WebP、Lottie/TGS 动画（rlottie）与 WebM 视频贴纸 |
| | **表情 / 大表情** | ✅ 已支持 | 支持 QQ 商城大表情 (mface) 提取与转发，基础表情段与 Emoji 兼容 |
| | **合并转发** | ✅ 已支持 | QQ 合并转发解析转 Telegram MarkdownV2 卡片清单；系统通知合并转发发送至 QQ |
| | **引用回复** | ✅ 已支持 | 双向消息 ID 映射 (`message_mapping`)，跨平台精准还原上下文回复关联 |
| | **消息撤回** | ✅ 已支持 | 双向撤回事件感知，任意端撤回消息，对端关联消息自动级联撤回 |
| | **@ 成员提及** | ✅ 已支持 | 识别 Telegram `@username` 与 QQ `@` 消息段，联动已绑定用户实现跨平台精准 @ |
| | **置顶与群公告** | ✅ 已支持 | Telegram 消息置顶 ↔ QQ 群公告双向自动感知同步，内置 SHA-256 去重防环 |
| **核心机制** | **防死循环机制** | ✅ 已支持 | 自动过滤 Bot 自身消息与非目标群消息，全链路避免回环转发死循环 |
| | **账号双向绑定** | ✅ 已支持 | 支持 `/bind` 动态验证码校验与绑定，建立 Telegram 与 QQ 用户唯一映射关系 |
| | **自定义昵称前缀** | ✅ 已支持 | 支持 `/setprefix` 自定义跨群发言身份前缀，未绑定用户自动附带 `[未绑定]` |
| | **屏蔽词 / 敏感词** | ✅ 已支持 | 支持 `/blockword` 动态增删黑名单关键词，实时拦截过滤敏感消息 |
| | **并发限流与容错** | ✅ 已支持 | 异步任务队列限制并发，所有网络与 API 调用配备指数退避重试 (Exponential Backoff) |
| | **插件扩展架构** | ✅ 已支持 | 基于 `PluginBase` 的热插拔插件系统，支持根据匹配规则拦截与自定义处理消息 |
| **系统与运维** | **WebUI 管理后台** | ✅ 已支持 | 基于 FastAPI + Vue 3，提供系统状态监控、配置热修改、用户绑定管理、敏感词及日志审计 |
| | **Docker 部署** | ✅ 已支持 | 官方多架构镜像 (`amd64`/`arm64`)，内置完整 FFmpeg 环境与 Gosu 权限自动降权保护 |
| | **平滑重启与自愈** | ✅ 已支持 | 运行时异常阶梯式自愈重启；支持 `/reboot` 指令并发送重启耗时回执 |
| | **全自动更新检测** | ✅ 已支持 | 后台定时检查 GitHub 仓库最新 Commit 与 Release，支持 `/checkupdate` 一键热更 |

> [!NOTE]
> **非目标设计说明**：为了保持架构精炼并降低风险，TQSync **不提供**任何群管理（踢人/禁言/审批/改名片等）、群相册、群签到或闲聊娱乐功能。


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

支持 Debian/Ubuntu、CentOS/RHEL、Arch 系发行版。脚本会自动：创建 `venv` 虚拟环境、安装依赖、安装 `ffmpeg`/`screen`、生成 `config.yaml`，并写入快捷命令。

```bash
bash scripts/install.sh
```

安装完成后，重启终端或执行 `source ~/.bashrc`，即可使用快捷命令：

| 命令 | 说明 |
| --- | --- |
| `tqstart` | 在 screen 后台启动机器人 |
| `tqlog` | 回到运行日志窗口 (退出按 `Ctrl+A` 再按 `D`) |
| `tqstop` | 停止机器人 |
| `tqrestart` | 重启机器人 |
| `tqstatus` | 查看运行状态 |
| `tqlogs` | 查看最近日志 |

不想用别名时，也可直接调用管理脚本：

```bash
bash scripts/tqsync.sh start      # 启动
bash scripts/tqsync.sh attach     # 回到日志窗口 (Ctrl+A D 退出)
bash scripts/tqsync.sh stop       # 停止
bash scripts/tqsync.sh status     # 状态
```

> **说明:** 机器人在 `screen` 会话中后台运行，`/reboot` 与自动更新会在会话内自动重启，无需手动干预。

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

