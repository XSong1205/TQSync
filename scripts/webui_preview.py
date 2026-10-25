#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TQSync WebUI 本地预览服务器（Mock 数据版）。

用途
----
真实机器人在本机无法启动（没有 Telegram / QQ / NapCat 网络），但新版 WebUI 需要
做端到端联调与截图。本脚本因此提供一个"假后端 + 真前端"的预览服务：

1. 用 FastAPI ``StaticFiles(directory=web, html=True)`` 原样托管仓库里真实的
   ``web/`` 目录（挂载在 ``/``，且最后注册，保证 ``/admin/*`` 先匹配）；
2. 用纯内存示例数据实现 ``api/admin_api.py`` 里全部管理接口，字段名、响应结构、
   HTTP 状态码、中文错误文案都尽量与真实后端逐字对齐；
3. 所有状态只保存在进程内存中，重启即恢复初始示例数据。

**不会读写** ``config.yaml``、SQLite、``plugins/`` 等任何真实文件；上传插件、
启用/禁用插件等操作只在内存中模拟。

用法
----
.. code-block:: console

    D:\\TQSync\\.venv\\Scripts\\python.exe scripts/webui_preview.py --port 8099 --host 127.0.0.1

浏览器打开 ``http://127.0.0.1:8099/``，登录时的 API Key 输入 ``preview-key``。
"""

from __future__ import annotations

import argparse
import datetime
import math
import os
import random
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 目录与全局常量
# ---------------------------------------------------------------------------

# 以脚本自身位置定位仓库根目录，保证从任意 cwd 启动都能找到 web/
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WEB_DIR = REPO_ROOT / "web"

# 进程启动时间（对应真实后端的 GLOBAL_START_TIME）
START_TIME = time.time()

# 预览用 API Key；--api-key 可覆盖
DEFAULT_API_KEY = "preview-key"

# 权限等级定义（与 api/admin_api.py 一致）
PERM_LEVEL_USER = 0   # 普通用户：仅查看状态
PERM_LEVEL_ADMIN = 1  # 管理员：所有操作

# 真实后端在 GET /admin/config 中标记 masked 的敏感项
SENSITIVE_CONFIG_KEYS = {
    "telegram.bot_token",
    "qq.access_token",
    "server.admin_api_key",
}

# 模拟的 git commit hash（真实后端通过 get_git_commit_hash() 读取，用于拼版本号）
_MOCK_COMMIT = "9f3c2a1"


# ---------------------------------------------------------------------------
# 初始示例数据
# ---------------------------------------------------------------------------

def _default_config() -> Dict[str, Any]:
    """初始配置：键与 config.yaml.example 完全一致，值使用可展示的示例数据。"""
    return {
        "telegram": {
            "bot_token": "7123456789:AAH-preview-token-not-a-real-one",
            "group_id": -1002345678901,
            "proxy_url": "",
        },
        "qq": {
            "napcat_api_url": "http://127.0.0.1:3000",
            "access_token": "",
            "group_id": 728349156,
        },
        "server": {
            "host": "0.0.0.0",
            "qq_webhook_port": 8080,
            "admin_api_port": 8081,
            "webhook_path": "/webhook/qq",
            "webhook_token": "",
            "admin_api_key": DEFAULT_API_KEY,  # 预览环境固定为 preview-key
            "admin_user_ids": [7123456789, 2856231471],
        },
        "database": {
            "path": "db/tqsync.db",
        },
        "sync": {
            "direction": "both",
            "sync_notice": True,
            "sync_reaction": True,
            "face_as_image": True,
            "worker_count": 3,
            "queue_size": 50,
        },
        "debug": {
            "sticker_conversion_chat_id": None,
        },
    }


def _default_bindings() -> List[Dict[str, Any]]:
    """已绑定的 TG ↔ QQ 用户（字段与 bindings 表前 5 列一致）。"""
    return [
        {
            "tg_user_id": 7123456789,
            "qq_user_id": 2856231471,
            "tg_username": "alice_wu",
            "qq_nickname": "浅巷墨漓",
            "uid": "8f14e45f-ceea-467f-a1b0-4f2a3c9d7e11",
        },
        {
            "tg_user_id": 6987654321,
            "qq_user_id": 3749182650,
            "tg_username": "bob_lin",
            "qq_nickname": "夜半听风",
            "uid": "c9f0f895-fb98-4e2a-9c1b-2d3e4f5a6b7c",
        },
        {
            "tg_user_id": 5233445566,
            "qq_user_id": 1902847365,
            "tg_username": "carol_z",
            "qq_nickname": "柠檬不太酸",
            "uid": "45c48cce-2e2d-4fbd-aa1f-6a7b8c9d0e1f",
        },
        {
            "tg_user_id": 6677889900,
            "qq_user_id": 2610374859,
            "tg_username": "dave_chan",
            "qq_nickname": "山间清雾",
            "uid": "d3d94468-02a4-4d3f-a2b7-8c9d0e1f2a3b",
        },
    ]


def _default_synced_qq_users() -> List[int]:
    """同步过消息但尚未绑定 TG 的 QQ 用户（对应 message_mapping 的 DISTINCT sender）。"""
    return [4487215360, 5533108924]


def _default_plugins() -> Dict[str, Dict[str, Any]]:
    """5 个示例插件：3 个可用、1 个禁用、1 个加载失败，覆盖 WebUI 各种展示状态。"""
    return {
        "CountDown": {
            "name": "CountDown",
            "version": "1.2.0",
            "description": "群倒计时：设置目标时间后每日播报剩余天数，到期自动 @全体成员",
            "author": "TQSync",
            "file": "CountDown.py",
            "enabled": True,
            "loaded": True,
            "load_time_ms": 12,
            "error": None,
            "matchers": [
                {"type": "prefix", "pattern": "/countdown", "description": "倒计时管理 (set/list/del)"},
                {"type": "exact", "pattern": "倒计时", "description": "查看当前倒计时状态"},
            ],
        },
        "QQThumbsUp": {
            "name": "QQThumbsUp",
            "version": "2.1",
            "description": "QQ点赞：手动赞我 / 自动点赞列表管理 / 定时批量点赞",
            "author": "TQSync",
            "file": "QQThumbsUp.py",
            "enabled": True,
            "loaded": True,
            "load_time_ms": 19,
            "error": None,
            "matchers": [
                {"type": "exact", "pattern": "赞我", "description": "给QQ资料卡点赞"},
                {"type": "prefix", "pattern": "/autothumbsup", "description": "自动点赞管理 (help/likeall/status等)"},
            ],
        },
        "Welcome": {
            "name": "Welcome",
            "version": "1.0.3",
            "description": "入群欢迎：新成员加入时发送自定义欢迎语，支持 {nickname} 变量",
            "author": "XSong",
            "file": "Welcome.py",
            "enabled": True,
            "loaded": True,
            "load_time_ms": 9,
            "error": None,
            "matchers": [
                {"type": "prefix", "pattern": "/welcome", "description": "设置入群欢迎语与模板"},
            ],
        },
        "AntiSpam": {
            "name": "AntiSpam",
            "version": "1.4.1",
            "description": "反刷屏：短时间内重复消息或连续 @ 自动警告并撤回",
            "author": "TQSync",
            "file": "AntiSpam.py",
            "enabled": False,
            "loaded": True,
            "load_time_ms": 23,
            "error": None,
            "matchers": [
                {"type": "regex", "pattern": r"(?i)^(.{1,4})\1{9,}$", "description": "检测连续重复字符刷屏"},
            ],
        },
        "Weather": {
            # 加载失败的插件在真实后端里只有文件名和错误信息（version='-' / 作者与描述为空）
            "name": "Weather",
            "version": "-",
            "description": "",
            "author": "",
            "file": "Weather.py",
            "enabled": False,
            "loaded": False,
            "load_time_ms": 0,
            "error": "TimeoutError: 天气 API 连接超时 (https://api.open-meteo.com/v1/forecast)",
            "matchers": [],
        },
    }


def _default_plugin_data() -> Dict[str, Dict[str, str]]:
    """插件 KV 存储示例数据（plugin_data 表）。"""
    return {
        "CountDown": {
            "target_time": "2026-12-31 23:59:59",
            "title": "元旦倒计时",
            "notified": "false",
        },
        "QQThumbsUp": {
            "like_count": "10",
            "like_time": "08:00",
            "auto_like_list": "[2856231471, 3749182650]",
        },
        "Welcome": {
            "template": "欢迎 {nickname} 加入本群！进群请先看群公告，有问题 @管理员～",
        },
        "AntiSpam": {
            "max_repeat": "5",
            "mute_seconds": "60",
        },
    }


def _default_blocked_words() -> List[str]:
    """屏蔽词示例（其中一条带 ``/``，用于验证 :path 路由）。"""
    return [
        "加微信",
        "代开发票",
        "免费领红包",
        "http://spam.example.com",
        "刷单返利",
    ]


# ---------------------------------------------------------------------------
# 进程内状态（模块级 dict，重启服务即还原）
# ---------------------------------------------------------------------------

_STATE: Dict[str, Any] = {
    "config": _default_config(),          # 模拟 config_loader.config
    "bindings": _default_bindings(),      # 模拟 bindings 表（已绑定）
    "synced_qq_users": _default_synced_qq_users(),  # 模拟 message_mapping 中同步过的 QQ
    "blocked_words": _default_blocked_words(),
    "plugins": _default_plugins(),        # 模拟 PluginManager.plugins
    "plugin_data": _default_plugin_data(),  # 模拟 plugin_data 表
    "sync_count": 12847,                  # 模拟 message_mapping 总条数
}


# ---------------------------------------------------------------------------
# 配置读写工具（对齐 config/config_loader.py 的 get / update_config 语义）
# ---------------------------------------------------------------------------

def _get_config(key: str, default: Any = None) -> Any:
    """按 ``a.b.c`` 点号路径读取配置。"""
    current: Any = _STATE["config"]
    for part in key.split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        else:
            return default
    return current


def _set_config(key: str, value: Any) -> None:
    """按点号路径写入配置；中间层级不存在或不是 dict 时自动补 dict（同真实 loader）。"""
    parts = key.split(".")
    current: Dict[str, Any] = _STATE["config"]
    for part in parts[:-1]:
        if not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _coerce_config_value(raw: Any) -> Any:
    """复刻真实后端的配置类型转换：true/false -> bool，纯数字 -> int，其余原样返回。"""
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        if lowered.isdigit():
            return int(lowered)
    return raw


def _flatten_config(prefix: str, obj: Any, out: List[Dict[str, Any]]) -> None:
    """把嵌套配置拍平成 [{"key","value","masked","section"}]，与真实后端一致。"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            _flatten_config(f"{prefix}.{key}" if prefix else key, value, out)
        return
    key = prefix
    value = obj
    if isinstance(value, list):
        value = ",".join(str(item) for item in value)
    out.append(
        {
            "key": key,
            "value": str(value) if value is not None else "",
            "masked": key in SENSITIVE_CONFIG_KEYS,
            "section": key.split(".")[0],
        }
    )


def _read_version() -> str:
    """读取仓库 VERSION 文件（失败时退化为 1.0.0）。"""
    try:
        content = (REPO_ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()
        return content or "1.0.0"
    except OSError:
        return "1.0.0"


def _full_version_string() -> str:
    """模拟 utils.version_utils.get_full_version_string() 的格式。"""
    return f"v{_read_version()} ({_MOCK_COMMIT})"


# ---------------------------------------------------------------------------
# 插件 / 绑定 / 状态等数据组装工具
# ---------------------------------------------------------------------------

def _plugins_status_list() -> List[Dict[str, Any]]:
    """返回与 PluginManager.get_plugins_status() 完全同构的插件列表。"""
    return [
        {
            "name": info["name"],
            "version": info["version"],
            "description": info["description"],
            "author": info["author"],
            "file": info["file"],
            "enabled": info["enabled"],
            "loaded": info["loaded"],
            "load_time_ms": info["load_time_ms"],
            "error": info["error"],
            "matchers": [dict(matcher) for matcher in info["matchers"]],
        }
        for info in _STATE["plugins"].values()
    ]


def _bindings_result() -> List[Dict[str, Any]]:
    """拼装 GET /admin/bindings 的返回：已绑定在前，未绑定（同步过消息）在后。"""
    bound_qq_ids = set()
    result: List[Dict[str, Any]] = []
    for binding in _STATE["bindings"]:
        bound_qq_ids.add(binding["qq_user_id"])
        result.append(
            {
                "tg_user_id": binding["tg_user_id"],
                "qq_user_id": binding["qq_user_id"],
                "tg_username": binding["tg_username"],
                "qq_nickname": binding["qq_nickname"],
                "status": "已绑定",
                "uid": binding["uid"],
            }
        )
    for qq_id in sorted(_STATE["synced_qq_users"]):
        if qq_id in bound_qq_ids:
            continue
        result.append(
            {
                "tg_user_id": None,
                "qq_user_id": qq_id,
                "tg_username": None,
                "qq_nickname": None,
                "status": "未绑定",
                "uid": None,
            }
        )
    # 与真实后端一致的排序：已绑定优先，其次按 QQ 号升序
    result.sort(key=lambda item: (0 if item["status"] == "已绑定" else 1, item["qq_user_id"] or 0))
    return result


def _process_metrics() -> Dict[str, str]:
    """模拟 psutil 的性能指标：用小幅正弦波动制造平滑变化，磁盘取真实值。

    数值按真实 bot 空闲时的量级设置（独占内存约 70~80 MB、CPU 个位数），
    避免预览界面出现明显偏离实际的占用数字。
    """
    now = time.time()
    cpu_percent = max(0.2, 2.6 + 1.8 * math.sin(now / 11.0))
    memory_mb = 76.8 + 2.4 * math.sin(now / 17.0 + 0.8)
    try:
        usage = shutil.disk_usage(str(REPO_ROOT))
        disk_percent = usage.used / max(usage.total, 1) * 100.0
    except OSError:
        disk_percent = 46.8
    db_size_kb = 422.7 + 0.8 * math.sin(now / 29.0)
    return {
        "cpu_usage": f"{cpu_percent:.1f}%",
        "memory_usage": f"{memory_mb:.1f} MB",
        "disk_usage": f"{disk_percent:.1f}%",
        "db_size": f"{db_size_kb:.1f} KB",
    }


# 24 个 UTC 整点的示例同步量（低活夜间 / 傍晚高峰），用于同步历史图表
_SYNC_HISTORY_HOURLY: List[int] = [
    12, 9, 6, 4, 3, 2, 3, 7,
    15, 27, 38, 46, 52, 49, 41, 36,
    47, 58, 69, 83, 77, 61, 38, 21,
]

# 日志模板：(级别, 模块, 行号, 消息)。消息内容与真实 bot 的运行日志风格保持一致。
_LOG_TEMPLATES: List[tuple] = [
    ("INFO", "main", 618, "收到 QQ 群消息: sender=2856231471, group=728349156, len=36"),
    ("INFO", "sync_engine", 214, "✅ TG → QQ 文本转发成功 | sender=浅巷墨漓 | msg_id=8821304"),
    ("INFO", "qq_handler", 142, "NapCat send_group_msg 成功 (group_id=728349156, msg_id=1473201)"),
    ("INFO", "tg_handler", 168, "收到 TG 消息: chat_id=-1002345678901, user=7123456789, type=text"),
    ("WARNING", "file_transfer", 412, "QQ CDN 文件下载超时，正在重试 (2/3): https://multimedia.nt.qq.com.cn/download?appid=1407"),
    ("ERROR", "sync_engine", 301, "视频转发失败: File is too big (48.2 MB > 45 MB)，已跳过"),
    ("INFO", "command_handler", 152, "[状态] 已同步消息 12847 条 | 绑定用户 4 人 | 运行正常"),
    ("WARNING", "plugin_manager", 230, "插件 Weather 未加载，跳过匹配器路由"),
    ("INFO", "config_loader", 47, "配置已保存到 config.yaml (sync.direction=both)"),
    ("ERROR", "qq_handler", 121, "NapCat API 返回 retcode=100: 账号风控中，请稍后再试 (重试 3/3)"),
    ("INFO", "sync_engine", 262, "同步队列空闲，当前队列长度 0"),
    ("WARNING", "main", 741, "QQ Webhook Token 未配置，跳过鉴权校验"),
    ("INFO", "plugin_manager", 122, "✅ 插件已加载: QQThumbsUp (耗时 19ms)"),
    ("INFO", "db", 86, "数据库连接建立成功: db/tqsync.db (WAL 模式)"),
    ("ERROR", "file_transfer", 520, "语音转码失败: FFmpeg 未安装，无法将 OGG 转为 AMR"),
    ("INFO", "tg_handler", 402, "TG 消息已撤回，同步撤回 QQ 消息 msg_id=1473198"),
    ("WARNING", "sync_engine", 340, "同步任务重试中 (1/3): 网络连接超时，300ms 后重试"),
    ("INFO", "main", 312, "QQ Webhook 服务已启动: 0.0.0.0:8080/webhook/qq"),
    ("INFO", "update_checker", 88, "检查更新完成: 当前版本 v1.3.66 已是最新"),
    ("WARNING", "tg_handler", 233, "未绑定用户 5856231471 尝试发送消息，已附加 [未绑定] 前缀"),
]


# ---------------------------------------------------------------------------
# 请求体模型（必须在注册路由前定义）
# ---------------------------------------------------------------------------

class ConfigUpdate(BaseModel):
    key: str
    value: str


class ConfigBatchUpdate(BaseModel):
    """预览扩展：新版 WebUI 的 config 批量保存接口使用该请求体。"""
    items: List[ConfigUpdate]


class ChangePasswordRequest(BaseModel):
    new_password: str


class BindingUpdate(BaseModel):
    tg_user_id: int
    qq_user_id: int
    tg_username: Optional[str] = None
    qq_nickname: Optional[str] = None


class BlockedWordAdd(BaseModel):
    word: str


class PluginDataUpdate(BaseModel):
    key: str
    value: str


class SyncDirectionUpdate(BaseModel):
    direction: str


# ---------------------------------------------------------------------------
# FastAPI 应用与鉴权
# ---------------------------------------------------------------------------

app = FastAPI(title="TQSync Admin API")

# 与真实后端一致：允许任意来源（方便从其他 origin 的页面调试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _static_no_cache(request: Request, call_next):
    """WebUI 静态资源不缓存（与真实后端新增的中间件一致），保证刷新即拿到新前端。"""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css", ".json")):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


def get_permission_level(x_api_key: str = Header(None)) -> int:
    """根据 X-API-Key 计算权限等级；无效 Key 返回 -1（与真实后端一致）。"""
    correct_key = _get_config("server.admin_api_key")
    if not correct_key or x_api_key != correct_key:
        return -1
    return PERM_LEVEL_ADMIN


def require_permission(level: int):
    """权限校验依赖项工厂。"""

    async def permission_checker(x_api_key: str = Header(None)) -> bool:
        current_level = get_permission_level(x_api_key)
        if current_level < level:
            raise HTTPException(status_code=403, detail="Forbidden: Insufficient permissions")
        return True

    return permission_checker


# ---------------------------------------------------------------------------
# 健康检查 / 系统状态 / 同步历史 / 日志
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, str]:
    """容器健康检查专用接口（无需鉴权）。"""
    return {"status": "ok"}


@app.get("/admin/status", dependencies=[Depends(require_permission(PERM_LEVEL_USER))])
async def get_status() -> Dict[str, Any]:
    """系统状态：版本、运行时长、绑定数、同步数、性能指标、插件概览。"""
    now = time.time()
    uptime_seconds = max(0, int(now - START_TIME))
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    metrics = _process_metrics()
    plugins = _plugins_status_list()

    return {
        "version": _full_version_string(),
        "uptime_seconds": uptime_seconds,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "bound_users": len(_STATE["bindings"]),
        "sync_count": _STATE["sync_count"],
        "qq_group_id": _get_config("qq.group_id"),
        "tg_group_id": _get_config("telegram.group_id"),
        "cpu_usage": metrics["cpu_usage"],
        "memory_usage": metrics["memory_usage"],
        "disk_usage": metrics["disk_usage"],
        "db_size": metrics["db_size"],
        "is_initial_token": bool(_get_config("server.is_initial_token", False)),
        "plugins": {
            "total": len(plugins),
            "loaded": sum(1 for item in plugins if item["loaded"]),
            "enabled": sum(1 for item in plugins if item["enabled"]),
            "list": plugins,
        },
    }


@app.get("/admin/stats/sync_history", dependencies=[Depends(require_permission(PERM_LEVEL_USER))])
async def get_sync_history() -> Dict[str, Any]:
    """按 UTC 整点聚合最近 24 小时的同步消息数，返回 24 个桶（空桶补 0）。"""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_hour = now_utc.hour
    buckets: List[Dict[str, int]] = []
    # 以当前 UTC 小时为末尾倒推 24 个整点桶（hour 为 UTC 小时号，前端转本地标签）
    for index in range(24):
        hour = (now_hour - 23 + index) % 24
        buckets.append({"hour": hour, "count": _SYNC_HISTORY_HOURLY[hour]})
    return {"buckets": buckets, "generated_at": now_utc.isoformat()}


@app.get("/admin/logs", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_logs(lines: int = 50) -> Dict[str, List[str]]:
    """返回最近 N 行日志（loguru 单行文本格式），并保留 INFO/WARNING/ERROR 混合。"""
    count = max(1, min(lines, 5000))
    rng = random.Random(20261024)  # 固定种子，同一次请求的间隔分布稳定可复现

    # 先生成从旧到新的时间戳序列，最新一行贴近"现在"
    timestamps: List[float] = []
    cursor = time.time()
    for _ in range(count):
        timestamps.append(cursor)
        cursor -= rng.randint(8, 75)
    timestamps.reverse()

    logs: List[str] = []
    template_count = len(_LOG_TEMPLATES)
    for index, timestamp in enumerate(timestamps):
        level, module, lineno, message = _LOG_TEMPLATES[(index * 7) % template_count]
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        # 对齐真实 loguru FILE_FORMAT: "{time} | {level: <8} | {name}:{line} - {message}"
        logs.append(f"{time_str} | {level:<8} | {module}:{lineno} - {message}")
    return {"logs": logs}


# ---------------------------------------------------------------------------
# 配置管理
# ---------------------------------------------------------------------------

@app.get("/admin/config", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_config() -> Dict[str, Any]:
    """获取所有配置项（敏感字段标记 masked，由前端决定如何遮蔽展示）。"""
    items: List[Dict[str, Any]] = []
    _flatten_config("", _STATE["config"], items)
    return {"config": items}


@app.put("/admin/config/batch", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def update_config_batch(update: ConfigBatchUpdate) -> Dict[str, Any]:
    """批量更新配置（与新版真实后端 /admin/config/batch 的返回结构一致）。

    注意：本路由必须注册在 ``/admin/config/{config_key}`` 之前，否则 ``batch``
    会被动态路由当作配置键吞掉。
    """
    updated = 0
    failed: List[Dict[str, Any]] = []
    for item in update.items:
        key = (item.key or "").strip()
        if not key:
            failed.append({"key": item.key, "error": "配置键为空"})
            continue
        try:
            _set_config(key, _coerce_config_value(item.value))
            updated += 1
            if key == "server.admin_api_key":
                _set_config("server.is_initial_token", False)
        except Exception as exc:  # 逐项收集失败原因，不中断其他配置项
            failed.append({"key": key, "error": str(exc)})
    return {
        "status": "success" if not failed else "partial",
        "updated": updated,
        "failed": failed,
        "message": f"已更新 {updated} 项配置" + (f"，{len(failed)} 项失败" if failed else ""),
    }


@app.put("/admin/config/{config_key}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def update_config(config_key: str, update: ConfigUpdate) -> Dict[str, Any]:
    """更新单个配置项（类型自动转换，与真实后端一致）。"""
    try:
        _set_config(config_key, _coerce_config_value(update.value))
        if config_key == "server.admin_api_key":
            _set_config("server.is_initial_token", False)
        return {"status": "success", "message": f"Config {config_key} updated"}
    except Exception as exc:  # 与真实后端一致：内部异常转 500 并返回 detail
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 绑定管理
# ---------------------------------------------------------------------------

@app.get("/admin/bindings", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_bindings() -> List[Dict[str, Any]]:
    """TG ↔ QQ 绑定列表（已绑定在前，未绑定的已同步 QQ 用户在后）。"""
    return _bindings_result()


@app.put("/admin/bindings", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def add_binding(binding: BindingUpdate) -> Dict[str, str]:
    """新增 / 覆盖一条绑定。

    真实后端把 ``tg_username`` 同时写进了 ``qq_nickname`` 列（历史行为）；
    预览环境优先使用请求里的 ``qq_nickname``，缺省时才回退到 ``tg_username``，
    以便 WebUI 展示更真实。
    """
    tg_username = binding.tg_username
    qq_nickname = binding.qq_nickname or tg_username

    # 保留同一 TG/QQ 用户原有的 uid（真实数据库按 tg_user_id / qq_user_id 复用 UID）
    existing = next(
        (
            item
            for item in _STATE["bindings"]
            if item["tg_user_id"] == binding.tg_user_id or item["qq_user_id"] == binding.qq_user_id
        ),
        None,
    )
    uid = existing["uid"] if existing else str(uuid.uuid4())

    # 先剔除与本次 TG / QQ 冲突的旧记录，避免出现重复绑定
    _STATE["bindings"] = [
        item
        for item in _STATE["bindings"]
        if item["tg_user_id"] != binding.tg_user_id and item["qq_user_id"] != binding.qq_user_id
    ]
    _STATE["bindings"].append(
        {
            "tg_user_id": binding.tg_user_id,
            "qq_user_id": binding.qq_user_id,
            "tg_username": tg_username,
            "qq_nickname": qq_nickname,
            "uid": uid,
        }
    )
    return {"status": "success"}


@app.delete("/admin/bindings/{tg_user_id}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_binding(tg_user_id: int) -> Dict[str, str]:
    """删除绑定；该 QQ 用户若同步过消息，会以"未绑定"身份重新出现在列表中（同真实后端）。"""
    removed = next((item for item in _STATE["bindings"] if item["tg_user_id"] == tg_user_id), None)
    _STATE["bindings"] = [item for item in _STATE["bindings"] if item["tg_user_id"] != tg_user_id]
    if removed is not None and removed["qq_user_id"] not in _STATE["synced_qq_users"]:
        _STATE["synced_qq_users"].append(removed["qq_user_id"])
    return {"status": "success"}


# ---------------------------------------------------------------------------
# 管理员管理
# ---------------------------------------------------------------------------

@app.get("/admin/admins", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_admins() -> Dict[str, Any]:
    """获取机器人指令管理员 ID 列表（来自 server.admin_user_ids）。"""
    admins = _get_config("server.admin_user_ids", [])
    if not isinstance(admins, list):
        admins = []
    return {"admins": admins}


@app.post("/admin/admins", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def toggle_admin(user_id: int) -> Dict[str, Any]:
    """切换管理员：已存在则移除，不存在则添加（query 参数 user_id）。"""
    admins = _get_config("server.admin_user_ids", [])
    if not isinstance(admins, list):
        admins = []
    admins = list(admins)

    if user_id in admins:
        admins.remove(user_id)
        message = f"已取消用户 {user_id} 的管理员权限"
    else:
        admins.append(user_id)
        message = f"已将用户 {user_id} 设为管理员"

    _set_config("server.admin_user_ids", admins)
    return {"status": "success", "message": message, "admins": admins}


# ---------------------------------------------------------------------------
# 屏蔽词管理
# ---------------------------------------------------------------------------

@app.get("/admin/blocked_words", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_blocked_words() -> Dict[str, Any]:
    words = list(_STATE["blocked_words"])
    return {"words": words, "count": len(words)}


@app.post("/admin/blocked_words", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def add_blocked_word(body: BlockedWordAdd) -> Dict[str, str]:
    word = (body.word or "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="屏蔽词不能为空")
    if len(word) > 200:
        raise HTTPException(status_code=400, detail="屏蔽词过长（最多 200 字符）")
    if word in _STATE["blocked_words"]:
        raise HTTPException(status_code=409, detail="屏蔽词已存在")
    _STATE["blocked_words"].append(word)
    return {"status": "success", "message": f"已添加屏蔽词: {word}", "word": word}


@app.delete("/admin/blocked_words/{word:path}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_blocked_word(word: str) -> Dict[str, str]:
    """删除屏蔽词（:path 转换器用于支持包含 ``/`` 的屏蔽词）。"""
    from urllib.parse import unquote

    word = unquote(word).strip()
    if not word:
        raise HTTPException(status_code=400, detail="屏蔽词不能为空")
    if word not in _STATE["blocked_words"]:
        raise HTTPException(status_code=404, detail="屏蔽词不存在")
    _STATE["blocked_words"].remove(word)
    return {"status": "success", "message": f"已删除屏蔽词: {word}", "word": word}


# ---------------------------------------------------------------------------
# 插件管理
# ---------------------------------------------------------------------------

@app.get("/admin/plugins", dependencies=[Depends(require_permission(PERM_LEVEL_USER))])
async def get_plugins() -> Dict[str, Any]:
    """获取所有插件状态和详细信息。"""
    plugins = _plugins_status_list()
    return {
        "total": len(plugins),
        "loaded": sum(1 for item in plugins if item["loaded"]),
        "enabled": sum(1 for item in plugins if item["enabled"]),
        "plugins": plugins,
    }


@app.post("/admin/plugins/{plugin_name}/enable", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def enable_plugin(plugin_name: str) -> Dict[str, str]:
    plugin = _STATE["plugins"].get(plugin_name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在")
    plugin["enabled"] = True
    return {"status": "success", "message": f"插件 {plugin_name} 已启用"}


@app.post("/admin/plugins/{plugin_name}/disable", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def disable_plugin(plugin_name: str) -> Dict[str, str]:
    plugin = _STATE["plugins"].get(plugin_name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在")
    plugin["enabled"] = False
    return {"status": "success", "message": f"插件 {plugin_name} 已禁用"}


@app.post("/admin/plugins/{plugin_name}/reload", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def reload_plugin(plugin_name: str) -> Dict[str, Any]:
    """模拟热重载：加载时间重新生成，失败状态清除（预览环境不做真实 import）。"""
    plugin = _STATE["plugins"].get(plugin_name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在或加载失败")
    load_time_ms = random.randint(8, 26)
    plugin.update(
        {
            "enabled": True,
            "loaded": True,
            "load_time_ms": load_time_ms,
            "error": None,
        }
    )
    return {
        "status": "success",
        "message": f"插件 {plugin_name} 已重载",
        "load_time_ms": load_time_ms,
        "error": None,
    }


@app.delete("/admin/plugins/{plugin_name}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_plugin(plugin_name: str) -> Dict[str, str]:
    """从内存注册表移除插件（不删除磁盘文件，预览环境无真实插件文件）。"""
    if plugin_name not in _STATE["plugins"]:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在")
    del _STATE["plugins"][plugin_name]
    return {"status": "success", "message": f"插件 {plugin_name} 已删除"}


def _extract_attr(content: bytes, attr: str) -> Optional[str]:
    """从上传的插件源码里粗略提取类属性（version / description / author）。"""
    pattern = rb"^\s*" + re.escape(attr.encode("utf-8")) + rb"\s*=\s*[\"']([^\"']*)[\"']"
    match = re.search(pattern, content, re.MULTILINE)
    if match is None:
        return None
    return match.group(1).decode("utf-8", "replace")


@app.post("/admin/plugins/upload", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def upload_plugin(file: UploadFile = File(...)) -> Dict[str, Any]:
    """上传并"加载"插件：仅做内存模拟，绝不写磁盘（预览环境不污染 plugins/）。"""
    raw_filename = file.filename or ""
    filename = os.path.basename(raw_filename)  # 去路径，避免生成奇怪的插件名
    if not filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="只允许上传 .py 文件")

    content = await file.read()
    plugin_name = filename[:-3]
    load_time_ms = random.randint(8, 26)
    _STATE["plugins"][plugin_name] = {
        "name": plugin_name,
        "version": _extract_attr(content, "version") or "0.1",
        "description": _extract_attr(content, "description") or "（预览环境上传的示例插件）",
        "author": _extract_attr(content, "author") or "Unknown",
        "file": filename,
        "enabled": True,
        "loaded": True,
        "load_time_ms": load_time_ms,
        "error": None,
        "matchers": [],
    }
    return {
        "status": "success",
        "message": f"插件 {filename} 已上传并加载",
        "plugin": {
            "name": plugin_name,
            "version": _STATE["plugins"][plugin_name]["version"],
            "load_time_ms": load_time_ms,
            "error": None,
        },
    }


# ---------------------------------------------------------------------------
# 插件数据存储
# ---------------------------------------------------------------------------

@app.get("/admin/plugins/data", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_all_plugin_data_overview() -> Dict[str, Any]:
    """获取所有插件的存储数据概览。"""
    return {"plugins": {name: dict(data) for name, data in _STATE["plugin_data"].items()}}


@app.get("/admin/plugins/{plugin_name}/data", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_plugin_data(plugin_name: str, key: Optional[str] = None) -> Dict[str, Any]:
    """获取指定插件的存储数据，可选指定 key。"""
    data = _STATE["plugin_data"].get(plugin_name, {})
    if key:
        return {"plugin_name": plugin_name, "key": key, "value": data.get(key)}
    return {"plugin_name": plugin_name, "data": dict(data), "count": len(data)}


@app.put("/admin/plugins/{plugin_name}/data", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def set_plugin_data(plugin_name: str, update: PluginDataUpdate) -> Dict[str, str]:
    """设置/更新插件的键值数据。"""
    _STATE["plugin_data"].setdefault(plugin_name, {})[update.key] = update.value
    return {"status": "success", "message": f"Plugin {plugin_name} data '{update.key}' updated"}


@app.delete("/admin/plugins/{plugin_name}/data/{key}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_plugin_data(plugin_name: str, key: str) -> Dict[str, str]:
    """删除插件指定键的数据。"""
    _STATE["plugin_data"].get(plugin_name, {}).pop(key, None)
    return {"status": "success", "message": f"Plugin {plugin_name} data '{key}' deleted"}


# ---------------------------------------------------------------------------
# 同步方向控制
# ---------------------------------------------------------------------------

# 与真实后端逐字一致：value / label / desc 三个字段
_SYNC_DIRECTION_OPTIONS: List[Dict[str, str]] = [
    {"value": "both", "label": "双向同步", "desc": "TG ↔ QQ 消息互通"},
    {"value": "tg_to_qq", "label": "仅 TG → QQ", "desc": "TG 消息同步到 QQ，反之不转发"},
    {"value": "qq_to_tg", "label": "仅 QQ → TG", "desc": "QQ 消息同步到 TG，反之不转发"},
]


@app.get("/admin/sync/direction", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_sync_direction() -> Dict[str, Any]:
    """获取当前同步方向及可选值。"""
    return {
        "direction": _get_config("sync.direction", "both"),
        "options": [dict(option) for option in _SYNC_DIRECTION_OPTIONS],
    }


@app.put("/admin/sync/direction", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def update_sync_direction(update: SyncDirectionUpdate) -> Dict[str, str]:
    """修改同步方向。"""
    valid = {"both", "tg_to_qq", "qq_to_tg"}
    if update.direction not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"无效的同步方向，可选值: {', '.join(valid)}",
        )
    _set_config("sync.direction", update.direction)
    return {
        "status": "success",
        "message": f"同步方向已设为: {update.direction}",
        "direction": update.direction,
    }


# ---------------------------------------------------------------------------
# 安全 / 运维
# ---------------------------------------------------------------------------

@app.post("/admin/change-password", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def change_password(req: ChangePasswordRequest) -> Dict[str, str]:
    """修改管理 API Key（内存生效，重启恢复为 preview-key）。"""
    new_password = (req.new_password or "").strip()
    if not new_password:
        raise HTTPException(status_code=400, detail="新密码不能为空")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于 6 位")

    _set_config("server.admin_api_key", new_password)
    _set_config("server.is_initial_token", False)
    return {"status": "success", "message": "密码修改成功"}


@app.post("/admin/restart", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def trigger_restart() -> Dict[str, str]:
    """模拟重启：预览服务不真正退出，仅返回与真实后端一致的响应。"""
    return {"status": "restarting", "message": "系统正在优雅重启..."}


# ---------------------------------------------------------------------------
# 更新检查（--demo-update 时模拟“有新版本可用”，便于联调更新提示）
# ---------------------------------------------------------------------------

# 是否模拟发现新版本，由 CLI 参数 --demo-update 打开
_DEMO_UPDATE = False

_DEMO_UPDATE_CHANGELOG: List[Dict[str, str]] = [
    {"commit": "a1b2c3d", "subject": "feat(webui): 打开控制台时静默检查更新并展示更新日志 (v1.3.68)"},
    {"commit": "b2c3d4e", "subject": "fix(webui): 修复移动端日志面板标题换行与重复计数"},
    {"commit": "c3d4e5f", "subject": "feat(webui): 支持下拉刷新与触觉反馈，优化长列表滚动性能"},
    {"commit": "d4e5f6a", "subject": "chore: 同步 NapCat API 文档并更新依赖版本"},
]


@app.get("/admin/update/check", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def check_update(force: bool = False) -> Dict[str, Any]:
    """更新检查：默认返回“已是最新”，--demo-update 时返回模拟的新版本与日志。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    current_version = _full_version_string()
    local_commit = _MOCK_COMMIT
    if not _DEMO_UPDATE:
        return {
            "ok": True,
            "available": False,
            "current_version": current_version,
            "branch": "Next",
            "local_commit": local_commit,
            "remote_commit": local_commit,
            "changelog": [],
            "result": f"当前已是最新版本 (分支: Next, Commit: {local_commit})，无需更新。",
            "compare_url": "",
            "repo_url": "https://github.com/XSong1205/TQSync",
            "checked_at": now.isoformat(),
            "cached": not force,
            "reason": "",
        }

    remote_commit = "d4e5f6a"
    return {
        "ok": True,
        "available": True,
        "current_version": current_version,
        "branch": "Next",
        "local_commit": local_commit,
        "remote_commit": remote_commit,
        "changelog": [dict(item) for item in _DEMO_UPDATE_CHANGELOG],
        "result": (
            "检测到新版本可用！\n"
            "分支: Next\n"
            f"当前版本: {local_commit} => 远程最新: {remote_commit}"
        ),
        "compare_url": f"https://github.com/XSong1205/TQSync/compare/{local_commit}...{remote_commit}",
        "repo_url": "https://github.com/XSong1205/TQSync",
        "checked_at": now.isoformat(),
        "cached": not force,
        "reason": "",
    }


# ---------------------------------------------------------------------------
# 静态资源托管（必须最后注册，保证 /admin/* 路由优先匹配）
# ---------------------------------------------------------------------------

if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="webui")
else:
    # web/ 不存在时不崩溃，给出可读提示（正常仓库里不会走到这里）
    @app.get("/", response_class=HTMLResponse)
    async def web_dir_missing() -> str:
        return (
            "<h1>未找到 web 目录</h1>"
            f"<p>预览服务器期望的静态目录：<code>{WEB_DIR}</code></p>"
        )


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TQSync WebUI 预览服务器（Mock 数据，不连接真实 Telegram / QQ）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8099, help="监听端口")
    parser.add_argument("--api-key", dest="api_key", default=DEFAULT_API_KEY, help="登录 WebUI 使用的 API Key")
    parser.add_argument(
        "--demo-update",
        dest="demo_update",
        action="store_true",
        help="模拟发现新版本（用于联调更新提示与更新日志弹窗）",
    )
    return parser.parse_args(argv)


def _print_banner(host: str, port: int, api_key: str, demo_update: bool = False) -> None:
    """启动横幅：打印访问地址、API Key 和静态目录。"""
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    lines = [
        "=" * 68,
        "TQSync WebUI 预览服务（Mock 数据，不连接真实 Telegram / QQ）",
        f"  访问地址 : http://{display_host}:{port}/",
        f"  API Key  : {api_key}",
        f"  静态目录 : {WEB_DIR}",
        "  数据说明 : 全部保存在内存中，重启服务即恢复初始示例数据",
    ]
    if demo_update:
        lines.append("  更新模拟 : 已开启（打开控制台会弹出「发现新版本」更新日志）")
    lines.append("=" * 68)
    print("\n".join(lines), flush=True)


def main(argv: Optional[List[str]] = None) -> None:
    global _DEMO_UPDATE

    # Windows 控制台默认编码可能是 GBK，尽量切到 UTF-8 以免中文横幅打印异常
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = _parse_args(argv)
    _DEMO_UPDATE = bool(args.demo_update)
    # 用命令行参数覆盖初始 API Key，保证 /admin/config 与鉴权使用同一个值
    _set_config("server.admin_api_key", args.api_key)
    _print_banner(args.host, args.port, args.api_key, _DEMO_UPDATE)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
