from __future__ import annotations
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File 
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sys
import os
import time
import asyncio
import psutil
from utils.version_utils import get_full_version_string
from config.config_loader import config_loader
from db.database import db
from utils.logger import logger

app = FastAPI(title="TQSync Admin API")

# 增加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _static_no_cache(request, call_next):
    """WebUI 静态资源不缓存，保证升级后用户刷新即拿到新控制台。"""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css", ".json")):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response

# 权限等级定义
PERM_LEVEL_USER = 0   # 普通用户：仅查看状态
PERM_LEVEL_ADMIN = 1  # 管理员：所有操作


def _read_tail_lines(path: str, n: int, block_size: int = 64 * 1024) -> list:
    """从文件尾部按块回读最后 n 行，避免对大日志文件做 readlines 全量加载。"""
    with open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = min(size, block_size)
        chunks = []
        while True:
            f.seek(size - block)
            chunks.append(f.read(block))
            text = b''.join(reversed(chunks)).decode('utf-8', errors='replace')
            parts = text.splitlines()
            if len(parts) > n or block >= size:
                return parts[-n:] if n > 0 else []
            block = min(size, block * 2)

@app.get("/health")
async def health():
    """容器健康检查专用接口（无需鉴权）"""
    return {"status": "ok"}

def get_permission_level(x_api_key: str = Header(None)):
    """获取当前 API Key 的权限等级"""
    correct_key = config_loader.get('server.admin_api_key')
    if not correct_key or x_api_key != correct_key:
        return -1  # 无效 Key
    return PERM_LEVEL_ADMIN  # 管理面板 Key 默认为 Level 1

def require_permission(level: int):
    """权限校验依赖项工厂"""
    async def permission_checker(x_api_key: str = Header(None)):
        current_level = get_permission_level(x_api_key)
        if current_level < level:
            raise HTTPException(status_code=403, detail="Forbidden: Insufficient permissions")
        return True
    return permission_checker

class ConfigUpdate(BaseModel):
    key: str
    value: str

class ChangePasswordRequest(BaseModel):
    new_password: str

class BindingUpdate(BaseModel):
    tg_user_id: int
    qq_user_id: int
    tg_username: Optional[str] = None
    qq_nickname: Optional[str] = None

class BlockedWordAdd(BaseModel):
    """屏蔽词新增请求体。

    注意：这类请求体模型必须在路由注册前定义。使用
    ``from __future__ import annotations`` 时注解是字符串，FastAPI 在
    注册路由时若解析不到模型会把参数当成 query 参数，导致请求恒 422。
    """
    word: str

@app.get("/admin/config", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_config():
    """获取所有配置项（敏感字段自动屏蔽）"""
    sensitive_keys = {'telegram.bot_token', 'qq.access_token', 'server.admin_api_key'}
    config_items = []
    
    def flatten(prefix, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                flatten(f"{prefix}.{k}" if prefix else k, v)
        else:
            key = prefix
            is_sensitive = key in sensitive_keys
            value = obj
            if isinstance(value, list):
                value = ','.join(str(x) for x in value)
            config_items.append({
                "key": key,
                "value": str(value) if value is not None else '',
                "masked": is_sensitive,
                "section": key.split('.')[0]
            })
    
    flatten('', config_loader.config)
    return {"config": config_items}

@app.post("/admin/restart", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def trigger_restart():
    from main import graceful_restart
    # 异步触发重启，避免 API 请求因进程关闭而报错
    asyncio.create_task(graceful_restart())
    return {"status": "restarting", "message": "系统正在优雅重启..."}

@app.get("/admin/status", dependencies=[Depends(require_permission(PERM_LEVEL_USER))])
async def get_status():
    try:
        from main import GLOBAL_START_TIME
        current_start_time = GLOBAL_START_TIME
        # 简单的合理性检查：如果时间戳小于 2024-01-01，则认为无效
        if current_start_time < 1704067200:
            raise ValueError("Invalid start_time detected")
    except (ImportError, AttributeError, ValueError):
        current_start_time = time.time()
        
    uptime_seconds = int(time.time() - current_start_time)
    if uptime_seconds < 0: uptime_seconds = 0
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    bindings = await db.get_all_bindings()
    
    # 性能监控数据
    process = psutil.Process(os.getpid())
    # 内存优先取 USS（独占物理内存），更接近任务管理器/系统监控里的实际占用；
    # 部分平台不支持 memory_full_info 时回退到 RSS。
    try:
        _mem = process.memory_full_info()
        mem_bytes = getattr(_mem, 'uss', None) or _mem.rss
    except Exception:
        mem_bytes = process.memory_info().rss
    # cpu_percent(interval=0.1) 会阻塞 100ms，放到线程里执行，避免 WebUI 刷新时卡住事件循环
    cpu_percent = await asyncio.to_thread(process.cpu_percent, 0.1)
    
    # 磁盘使用情况
    try:
        disk_usage = psutil.disk_usage(os.path.abspath(os.getcwd()))
    except Exception:
        disk_usage = psutil.disk_usage('/')
    
    # 数据库文件大小 (包括 .db, .db-wal, .db-shm)
    db_size = 0
    actual_db_path = getattr(db, 'db_path', 'db/tqsync.db')
    for suffix in ('', '-wal', '-shm'):
        p = f"{actual_db_path}{suffix}"
        if os.path.exists(p):
            try:
                db_size += os.path.getsize(p)
            except OSError:
                pass
    
    # 获取同步消息总数
    try:
        async with db._Database__get_connection() as conn:
            cursor = await conn.execute('SELECT COUNT(*) FROM message_mapping')
            sync_count = (await cursor.fetchone())[0]
    except:
        sync_count = 0

    # 获取插件状态
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()
    plugins_status = pm.get_plugins_status()
    
    return {
        "version": get_full_version_string(),
        "uptime_seconds": uptime_seconds,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "bound_users": len(bindings),
        "sync_count": sync_count,
        "qq_group_id": config_loader.get('qq.group_id'),
        "tg_group_id": config_loader.get('telegram.group_id'),
        "cpu_usage": f"{cpu_percent:.1f}%",
        "memory_usage": f"{mem_bytes / 1024 / 1024:.1f} MB",
        "disk_usage": f"{disk_usage.percent:.1f}%",
        "db_size": f"{db_size / 1024:.1f} KB",
        "is_initial_token": bool(config_loader.get('server.is_initial_token', False)),
        "plugins": {
            "total": len(plugins_status),
            "loaded": sum(1 for p in plugins_status if p['loaded']),
            "enabled": sum(1 for p in plugins_status if p['enabled']),
            "list": plugins_status
        }
    }

@app.get("/admin/stats/sync_history", dependencies=[Depends(require_permission(PERM_LEVEL_USER))])
async def get_sync_history():
    """按 UTC 整点聚合最近 24 小时同步消息数，返回 24 个桶（空桶补 0）"""
    import datetime
    buckets = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_hour = now_utc.hour
    try:
        async with db._Database__get_connection() as conn:
            cursor = await conn.execute('''
                SELECT strftime('%H', created_at) AS h, COUNT(*)
                FROM message_mapping
                WHERE created_at >= datetime('now', '-24 hours')
                GROUP BY h
            ''')
            rows = await cursor.fetchall()
    except Exception:
        rows = []
    hour_map = {}
    for h, count in rows:
        hour_map[int(h)] = count
    # 以当前 UTC 小时为末尾，倒推 24 个整点桶（hour 为 UTC 小时号，前端转本地标签）
    for i in range(24):
        h = (now_hour - 23 + i) % 24
        buckets.append({"hour": h, "count": hour_map.get(h, 0)})
    return {"buckets": buckets, "generated_at": now_utc.isoformat()}


@app.get("/admin/logs", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_logs(lines: int = 50):
    log_file = os.path.join(os.getcwd(), 'logs', 'tqsync.log')
    try:
        if not os.path.exists(log_file):
            return {"logs": ["日志文件未找到，请检查系统是否正常运行。"]}
        
        last_n_lines = await asyncio.to_thread(_read_tail_lines, log_file, max(1, min(lines, 5000)))
            
        clean_logs = []
        for line in last_n_lines:
            line = line.strip()
            if not line: continue
            try:
                import json
                log_obj = json.loads(line)
                
                # Loguru serialize=True 输出的 JSON 包含 'text' 字段（格式化后的日志文本）
                # 优先使用 text 字段，因为它保留了终端显示的完整格式
                log_text = log_obj.get('text', '').strip()
                if log_text:
                    clean_logs.append(log_text)
                    continue
                
                # 兼容旧版或无 text 字段的 JSON 结构
                record = log_obj.get('record', log_obj)
                time_str = record.get('time', '')
                if isinstance(time_str, dict): time_str = time_str.get('timestamp', '')
                
                level_val = record.get('level', '')
                if isinstance(level_val, dict): level_val = level_val.get('name', '')
                
                message = record.get('message', '')
                if message:
                    clean_logs.append(f"{time_str} [{level_val}] {message}")
                else:
                    clean_logs.append(line) # 降级回原始行
            except Exception:
                clean_logs.append(line)
                
        return {"logs": clean_logs}
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        return {"logs": [f"读取日志出错: {str(e)}"]}

@app.post("/admin/change-password", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def change_password(req: ChangePasswordRequest):
    new_pwd = (req.new_password or "").strip()
    if not new_pwd:
        raise HTTPException(status_code=400, detail="新密码不能为空")
    if len(new_pwd) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于 6 位")
    
    config_loader.update_config('server.admin_api_key', new_pwd)
    config_loader.update_config('server.is_initial_token', False)
    logger.info("WebUI 管理员密码已被修改")
    return {"status": "success", "message": "密码修改成功"}

def _coerce_config_value(raw: str):
    """把前端传来的字符串还原成 bool / int，其余保持字符串。"""
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in ('true', 'false'):
            return lowered == 'true'
        if lowered.isdigit():
            return int(lowered)
    return raw


class ConfigBatchUpdate(BaseModel):
    """批量修改配置的请求体。

    WebUI 的“保存”按钮一次性提交所有改动项，避免逐条 PUT 造成
    多次往返；键名格式与 GET /admin/config 返回的扁平 key 一致。
    """
    items: List[ConfigUpdate]


# 注意：批量路由必须注册在 /admin/config/{config_key} 之前，
# 否则 "batch" 会被当成 config_key 匹配到动态路由。
@app.put("/admin/config/batch", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
def update_config_batch(payload: ConfigBatchUpdate):
    """批量更新配置：任一键失败不影响已成功项，失败项单独返回。"""
    updated = 0
    failed = []
    for item in payload.items:
        key = (item.key or '').strip()
        if not key:
            failed.append({"key": item.key, "error": "配置键为空"})
            continue
        try:
            config_loader.update_config(key, _coerce_config_value(item.value))
            updated += 1
            if key == 'server.admin_api_key':
                config_loader.update_config('server.is_initial_token', False)
        except Exception as e:  # noqa: BLE001 - 逐项收集失败原因
            failed.append({"key": key, "error": str(e)})
    return {
        "status": "success" if not failed else "partial",
        "updated": updated,
        "failed": failed,
        "message": f"已更新 {updated} 项配置" + (f"，{len(failed)} 项失败" if failed else ""),
    }


@app.put("/admin/config/{config_key}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
def update_config(config_key: str, update: ConfigUpdate):
    try:
        value = _coerce_config_value(update.value)
        config_loader.update_config(config_key, value)
        if config_key == 'server.admin_api_key':
            config_loader.update_config('server.is_initial_token', False)
        return {"status": "success", "message": f"Config {config_key} updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/bindings", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_bindings():
    bindings = await db.get_all_bindings()
    bound_qq_ids = set()
    result = []
    for b in bindings:
        bound_qq_ids.add(b[1])
        result.append({
            "tg_user_id": b[0],
            "qq_user_id": b[1],
            "tg_username": b[2],
            "qq_nickname": b[3],
            "status": "已绑定",
            "uid": b[4]
        })
    synced_qq = await db.get_synced_qq_users()
    for qq_id in synced_qq:
        if qq_id not in bound_qq_ids:
            result.append({
                "tg_user_id": None,
                "qq_user_id": qq_id,
                "tg_username": None,
                "qq_nickname": None,
                "status": "未绑定",
                "uid": None
            })
    result.sort(key=lambda x: (0 if x["status"] == "已绑定" else 1, x["qq_user_id"] or 0))
    return result

@app.delete("/admin/bindings/{tg_user_id}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_binding(tg_user_id: int):
    await db.delete_binding(tg_user_id=tg_user_id)
    return {"status": "success"}

@app.put("/admin/bindings", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def add_binding(binding: BindingUpdate):
    await db.add_binding(binding.tg_user_id, binding.qq_user_id, binding.tg_username, binding.tg_username)
    return {"status": "success"}

@app.get("/admin/admins", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_admins():
    admins = config_loader.get('server.admin_user_ids', [])
    if not isinstance(admins, list):
        admins = []
    return {"admins": admins}

@app.post("/admin/admins", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def toggle_admin(user_id: int):
    admins = config_loader.get('server.admin_user_ids', [])
    if not isinstance(admins, list):
        admins = []
    
    if user_id in admins:
        admins.remove(user_id)
        msg = f"已取消用户 {user_id} 的管理员权限"
    else:
        admins.append(user_id)
        msg = f"已将用户 {user_id} 设为管理员"
    
    config_loader.update_config('server.admin_user_ids', admins)
    return {"status": "success", "message": msg, "admins": admins}


# ── 屏蔽词管理 API ──

@app.get("/admin/blocked_words", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_blocked_words():
    words = await db.get_blocked_words()
    return {"words": words, "count": len(words)}

@app.post("/admin/blocked_words", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def add_blocked_word(body: BlockedWordAdd):
    word = (body.word or "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="屏蔽词不能为空")
    if len(word) > 200:
        raise HTTPException(status_code=400, detail="屏蔽词过长（最多 200 字符）")
    success = await db.add_blocked_word(word)
    if not success:
        raise HTTPException(status_code=409, detail="屏蔽词已存在")
    return {"status": "success", "message": f"已添加屏蔽词: {word}", "word": word}

@app.delete("/admin/blocked_words/{word:path}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_blocked_word(word: str):
    """删除屏蔽词。

    使用 ``:path`` 转换器：屏蔽词常见会包含 ``/``（如 ``http://``），
    普通路径参数在解码后会被当成分隔符而 404。
    """
    from urllib.parse import unquote
    word = unquote(word).strip()
    if not word:
        raise HTTPException(status_code=400, detail="屏蔽词不能为空")
    success = await db.remove_blocked_word(word)
    if not success:
        raise HTTPException(status_code=404, detail="屏蔽词不存在")
    return {"status": "success", "message": f"已删除屏蔽词: {word}", "word": word}


# ── 插件管理 API ──

@app.get("/admin/plugins", dependencies=[Depends(require_permission(PERM_LEVEL_USER))])
async def get_plugins():
    """获取所有插件状态和详细信息"""
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()
    plugins = pm.get_plugins_status()
    return {
        "total": len(plugins),
        "loaded": sum(1 for p in plugins if p['loaded']),
        "enabled": sum(1 for p in plugins if p['enabled']),
        "plugins": plugins
    }


class PluginReloadResponse(BaseModel):
    plugin_name: str
    status: str
    message: str
    load_time_ms: Optional[int] = None
    error: Optional[str] = None


@app.post("/admin/plugins/{plugin_name}/enable", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def enable_plugin(plugin_name: str):
    """启用指定插件"""
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()
    if plugin_name not in pm.plugins:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在")
    pm.enable_plugin(plugin_name)
    return {"status": "success", "message": f"插件 {plugin_name} 已启用"}


@app.post("/admin/plugins/{plugin_name}/disable", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def disable_plugin(plugin_name: str):
    """禁用指定插件"""
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()
    if plugin_name not in pm.plugins:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在")
    pm.disable_plugin(plugin_name)
    return {"status": "success", "message": f"插件 {plugin_name} 已禁用"}


@app.post("/admin/plugins/{plugin_name}/reload", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def reload_plugin(plugin_name: str):
    """热重载指定插件"""
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()
    info = await pm.reload_plugin(plugin_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在或加载失败")
    return {
        "status": "success",
        "message": f"插件 {plugin_name} 已重载",
        "load_time_ms": info.load_time_ms,
        "error": info.error
    }


@app.delete("/admin/plugins/{plugin_name}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_plugin(plugin_name: str):
    """删除指定插件（卸载并删除文件）"""
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()
    if plugin_name not in pm.plugins:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 不存在")
    await pm.delete_plugin(plugin_name)
    return {"status": "success", "message": f"插件 {plugin_name} 已删除"}


@app.post("/admin/plugins/upload", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def upload_plugin(file: UploadFile = File(...)):
    """上传并加载新插件"""
    from core.plugin_manager import PluginManager
    pm = PluginManager.get_instance()

    if not file.filename.endswith('.py'):
        raise HTTPException(status_code=400, detail="只允许上传 .py 文件")

    filepath = os.path.join(pm.plugin_dir, file.filename)
    content = await file.read()

    with open(filepath, 'wb') as f:
        f.write(content)

    info = await pm.load_plugin(file.filename)
    if info is None:
        raise HTTPException(status_code=500, detail=f"插件文件已保存但加载失败")

    # 向双端广播加载通知
    if info.loaded and not info.error:
        await pm.broadcast_plugin_status(info.name, True, info.load_time_ms)
    else:
        await pm.broadcast_plugin_status(info.name, False, 0, info.error)

    return {
        "status": "success",
        "message": f"插件 {file.filename} 已上传并加载",
        "plugin": {
            "name": info.name,
            "version": info.version,
            "load_time_ms": info.load_time_ms,
            "error": info.error
        }
    }


# ── 插件数据存储 API ──

class PluginDataUpdate(BaseModel):
    key: str
    value: str


@app.get("/admin/plugins/data", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_all_plugin_data_overview():
    """获取所有插件的存储数据概览"""
    names = await db.get_all_plugin_names()
    result = {}
    for name in names:
        data = await db.get_plugin_data(name)
        result[name] = {item['key']: item['value'] for item in data} if data else {}
    return {"plugins": result}


@app.get("/admin/plugins/{plugin_name}/data", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_plugin_data(plugin_name: str, key: Optional[str] = None):
    """获取指定插件的存储数据，可选指定 key"""
    if key:
        value = await db.get_plugin_data(plugin_name, key)
        return {"plugin_name": plugin_name, "key": key, "value": value}
    data = await db.get_plugin_data(plugin_name)
    return {
        "plugin_name": plugin_name,
        "data": {item['key']: item['value'] for item in data} if data else {},
        "count": len(data) if data else 0
    }


@app.put("/admin/plugins/{plugin_name}/data", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def set_plugin_data(plugin_name: str, update: PluginDataUpdate):
    """设置/更新插件的键值数据"""
    await db.set_plugin_data(plugin_name, update.key, update.value)
    return {"status": "success", "message": f"Plugin {plugin_name} data '{update.key}' updated"}


@app.delete("/admin/plugins/{plugin_name}/data/{key}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_plugin_data(plugin_name: str, key: str):
    """删除插件指定键的数据"""
    await db.delete_plugin_data(plugin_name, key)
    return {"status": "success", "message": f"Plugin {plugin_name} data '{key}' deleted"}


# ── 同步方向控制 ──

@app.get("/admin/sync/direction", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_sync_direction():
    """获取当前同步方向"""
    direction = config_loader.get('sync.direction', 'both')
    return {
        "direction": direction,
        "options": [
            {"value": "both", "label": "双向同步", "desc": "TG ↔ QQ 消息互通"},
            {"value": "tg_to_qq", "label": "仅 TG → QQ", "desc": "TG 消息同步到 QQ，反之不转发"},
            {"value": "qq_to_tg", "label": "仅 QQ → TG", "desc": "QQ 消息同步到 TG，反之不转发"},
        ]
    }


class SyncDirectionUpdate(BaseModel):
    direction: str


@app.put("/admin/sync/direction", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
def update_sync_direction(update: SyncDirectionUpdate):
    """修改同步方向"""
    valid = {"both", "tg_to_qq", "qq_to_tg"}
    if update.direction not in valid:
        raise HTTPException(status_code=400, detail=f"无效的同步方向，可选值: {', '.join(valid)}")
    config_loader.update_config('sync.direction', update.direction)
    return {"status": "success", "message": f"同步方向已设为: {update.direction}", "direction": update.direction}

# ── 更新检查 API ──
#
# WebUI 打开时静默调用，返回是否有新提交以及更新日志（git log）。
# 只读执行 `git fetch`，不会修改工作区；结果缓存 10 分钟避免频繁请求 GitHub。

_UPDATE_CHECK_CACHE: dict = {"data": None, "ts": 0.0}
_UPDATE_CHECK_LOCK = asyncio.Lock()
_UPDATE_CHECK_TTL_OK = 600     # 成功结果缓存 10 分钟
_UPDATE_CHECK_TTL_FAIL = 120   # 失败结果缓存 2 分钟，避免网络异常时反复拉取

# 容器内没有 .git 目录，更新需重建镜像
_IS_CONTAINER = os.environ.get('TQSYNC_CONTAINER', '0') == '1'


def _git_origin_url() -> str:
    """读取并规范化 origin 仓库地址（供前端生成 compare 链接）。"""
    import subprocess
    try:
        out = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, timeout=5,
        )
        url = (out.stdout or '').strip()
    except Exception:
        return ''
    if not url:
        return ''
    if url.startswith('git@github.com:'):
        url = 'https://github.com/' + url.split(':', 1)[1]
    if url.endswith('.git'):
        url = url[:-4]
    return url


def _parse_changelog(raw: str) -> list:
    """把 `git log --oneline` 文本解析为 [{commit, subject}]。"""
    items = []
    for line in (raw or '').splitlines():
        line = line.strip().lstrip('*').strip()
        if not line:
            continue
        head, _, rest = line.partition(' ')
        if head and rest and 4 <= len(head) <= 40 and all(c in '0123456789abcdef' for c in head.lower()):
            items.append({"commit": head, "subject": rest.strip()})
        else:
            items.append({"commit": "", "subject": line})
        if len(items) >= 20:
            break
    return items


def _run_update_probe() -> tuple:
    """在线程中执行阻塞的 git 检查，返回 (info, repo_url)。"""
    from handlers.command_handler import check_for_updates
    info = asyncio.run(check_for_updates())
    return info, _git_origin_url()


def _normalize_update_info(info: dict, repo_url: str, cached: bool) -> dict:
    """把 check_for_updates 的结果整理为 WebUI 使用的稳定结构。"""
    import datetime
    local_commit = info.get('local_commit') or ''
    remote_commit = info.get('remote_commit') or ''
    compare_url = ''
    if repo_url and local_commit and remote_commit:
        compare_url = f"{repo_url}/compare/{local_commit}...{remote_commit}"
    return {
        "ok": bool(info.get('ok')),
        "available": bool(info.get('update_found')),
        "current_version": get_full_version_string(),
        "branch": info.get('current_branch') or '',
        "local_commit": local_commit,
        "remote_commit": remote_commit,
        "changelog": _parse_changelog(info.get('changelog') or ''),
        "result": (info.get('result') or '').strip(),
        "compare_url": compare_url,
        "repo_url": repo_url,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cached": cached,
        "reason": '',
    }


@app.get("/admin/update/check", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def check_update(force: bool = False):
    """检查是否有新版本（只读 git fetch，默认使用 10 分钟缓存）。

    - `force=true`：跳过缓存立即重新检查（设置页「检查更新」使用）
    - 容器部署无法 git 更新，直接返回不可用说明
    """
    if _IS_CONTAINER:
        import datetime
        return {
            "ok": True,
            "available": False,
            "current_version": get_full_version_string(),
            "branch": "",
            "local_commit": "",
            "remote_commit": "",
            "changelog": [],
            "result": "容器部署请通过 docker compose pull 更新镜像",
            "compare_url": "",
            "repo_url": "",
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "cached": False,
            "reason": "container",
        }

    def _cached_result() -> Optional[dict]:
        data = _UPDATE_CHECK_CACHE["data"]
        if not data:
            return None
        ttl = _UPDATE_CHECK_TTL_OK if data.get("ok") else _UPDATE_CHECK_TTL_FAIL
        if time.time() - _UPDATE_CHECK_CACHE["ts"] < ttl:
            return {**data, "cached": True}
        return None

    if not force:
        hit = _cached_result()
        if hit:
            return hit

    async with _UPDATE_CHECK_LOCK:
        if not force:
            hit = _cached_result()  # 双重检查，避免并发重复 fetch
            if hit:
                return hit
        try:
            info, repo_url = await asyncio.to_thread(_run_update_probe)
        except Exception as e:  # noqa: BLE001 - 网络/git 异常统一降级
            logger.error(f"WebUI 更新检查失败: {e}")
            info, repo_url = {"ok": False, "update_found": False, "result": f"检查更新失败：{e}"}, ''

        data = _normalize_update_info(info, repo_url, cached=False)
        _UPDATE_CHECK_CACHE["data"] = data
        _UPDATE_CHECK_CACHE["ts"] = time.time()
        logger.info(
            "WebUI 更新检查: " + ("发现新版本 " + data["remote_commit"] if data["available"] else "已是最新")
        )
        return data
