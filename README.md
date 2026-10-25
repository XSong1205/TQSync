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
| QQ 表情同步 | ✅ QQ→TG |
| 合并转发同步 | ✅ |
| 引用回复同步 | ✅ |
| 消息撤回同步 | ✅ |
| @ 提及同步 | ✅ |
| 置顶消息 - 群公告同步 | ✅ |
| 小表情转换 | ❌ |
| 戳一戳同步 | ❌ |
| 表情回应同步 | ✅ TG→QQ |




## 技术栈

- **Python 3.12+**
- **Telegram**: `python-telegram-bot` (v20+)
- **QQ**: `aiohttp` (对接 Napcat OneBot v11 HTTP)
- **Web Framework**: `FastAPI` + `Uvicorn` + 原生 ES Module（零构建 WebUI）
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
| `tqlog` | 进入日志窗口（退出按 `Ctrl+A` 再按 `D`）；`tqlog -l 300` 直接看最近 300 行，`tqlog -c 300` 导出到文件 |
| `tqstop` | 停止机器人 |
| `tqrestart` | 重启机器人 |
| `tqstatus` | 查看运行状态 |
| `tqlogs` | 查看最近日志（自动解析 JSON 行），等价于 `tqlog -l 50` |

不想用别名时，也可直接调用管理脚本：

```bash
bash scripts/tqsync.sh start            # 启动
bash scripts/tqsync.sh attach           # 进入日志窗口（Ctrl+A D 退出）
bash scripts/tqsync.sh attach -l 100    # 直接查看最近 100 行
bash scripts/tqsync.sh attach -c 300    # 导出最近 300 行为 logs/tqlog-*.log
bash scripts/tqsync.sh stop             # 停止
bash scripts/tqsync.sh status           # 状态
```

> **说明:** 机器人在 `screen` 会话 `tqsync` 中后台运行，`/reboot` 与自动更新会在会话内自动重启：
> - **回看历史**：先按 `Ctrl+A` 再按 `[` 进入翻页模式，用 `PgUp`/`PgDn` 或方向键滚动，`q` 退出翻页；
> - **退出会话**：先按 `Ctrl+A` 再按 `D`，机器人继续在后台运行；
> - **复制日志**：翻页模式下无法用鼠标框选，可直接 `tqlog -c 500` 导出文件后 `scp` 下载，或用 `tqlog -l` / `tqlogs` 在终端里查看后复制。

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
- **WebUI**：默认运行在 `http://localhost:8081/`，可以查看运行状态、管理绑定关系与管理员、配置屏蔽词（配置 → 消息过滤）、热插拔插件、查看日志以及在线修改配置。
  - 控制台采用 Miuix（小米 HyperOS / MIUI）**官方默认配色与组件规格**的移动端优先设计，零前端依赖、无需构建，支持明暗主题、下拉刷新与离线缓存友好加载；
  - 概览页是监控视角：运行指标每 1.5 秒刷新，内存按独占内存（USS）统计；设置项集中在「设置」页；
  - 打开控制台会静默检查 GitHub 更新，有新版本时弹出更新日志（可忽略该版本，也可在概览 / 设置页手动检查）；
  - 宽屏自动切换为侧边导航布局，手机 / 平板 / 桌面均可正常使用；
  - 开发与预览说明见 [docs/webui_guide.md](docs/webui_guide.md)（无需启动机器人即可用 Mock 服务调试界面）。
- **QQ 连接健康监测**：每分钟主动探测 NapCat HTTP 接口（`/get_status`，接口异常/超时自动降级 `/get_login_info`），连接失败或连续 2 次无有效响应即判定断开；只在「断开 / 恢复」状态变化时向 TG 群各发送 1 条通知，离线期间保持静默不刷屏（冷启动另有 5 分钟观察期，避免 NapCat 登录中被误报）。`/status` 可随时查看实时连接状态与探测延迟。

---

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)

