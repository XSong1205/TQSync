# GEMINI.md

This file provides project context and guidance for Gemini / AI assistants when working with code and APIs in this repository.

## Project Overview

TQSync is an asynchronous Python bot bridging Telegram and QQ groups with bidirectional message synchronization.
- **Telegram Side**: `python-telegram-bot` (v21+)
- **QQ Side**: NapCat (OneBot v11 HTTP API)
- **Web / Admin**: FastAPI + Vue WebUI
- **Persistence**: SQLite (`aiosqlite`)

---

## NapCat QQ API Reference

> **重要提示 / Important**:
> 当需要调用、扩展或排查 QQ 侧功能（发送群/私聊消息、合并转发、文件上传下载、戳一戳、群设置、表情等）时，请务必优先参考本地文档：
> - **[NapCatQQAPI.md](file:///d:/TQSync/NapCatQQAPI.md)**

### API 规范与文档来源
- **本地 API 清单**: [NapCatQQAPI.md](file:///d:/TQSync/NapCatQQAPI.md)（已同步 NapCatQQ 4.18.37 官方 OpenAPI 规范，共 178 个 HTTP 端点及 39 个数据模型）。
- **同步脚本**: [scripts/sync_napcat_api.py](file:///d:/TQSync/scripts/sync_napcat_api.py)（后续如官方发布新版本，可直接执行此脚本重新同步）。
- **在线官方文档**:
  - NapCatQQ 官方站点: https://napneko.github.io/api/4.18.37
  - NapCatDocs OpenAPI Spec: `https://raw.githubusercontent.com/NapNeko/NapCatDocs/main/src/api/4.18.37/openapi.json`

### 常用 QQ 接口与封装 (`handlers/qq_handler.py`)
- 发送群消息: `/send_group_msg`
- 发送私聊消息: `/send_private_msg`
- 撤回消息: `/delete_msg`
- 发送群合并转发: `/send_group_forward_msg`
- 获取/下载文件: `/get_file`, `/download_file`
- 更多扩展功能请检索 [NapCatQQAPI.md](file:///d:/TQSync/NapCatQQAPI.md) 中的对应接口端点。

---

## 自动化发版与工作流规范 (Mandatory Workflow)

> **核心规则 / Core Rule**:
> 每次完成**功能性新增/调整 (Features)** 或 **问题修复 (Bugfixes)** 更改后，**必须自动执行以下流程**：
> 1. **自动递增版本号 (Bump Version)**:
>    - 修复/日常调整默认 bump patch：`py utils/version_bumper.py -patch`（也可根据重大程度使用 `-minor` 或 `-major`）
> 2. **自动 Git 提交 (Commit)**:
>    - `git add .`
>    - `git commit -m "<清晰明了的更改描述> (vX.Y.Z)"`
> 3. **自动推送到远程仓库 (Push to GitHub)**:
>    - `git push`

