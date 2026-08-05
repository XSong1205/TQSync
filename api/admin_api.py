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

# 权限等级定义
PERM_LEVEL_USER = 0   # 普通用户：仅查看状态
PERM_LEVEL_ADMIN = 1  # 管理员：所有操作

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

class BindingUpdate(BaseModel):
    tg_user_id: int
    qq_user_id: int
    tg_username: Optional[str] = None
    qq_nickname: Optional[str] = None

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
    mem_info = process.memory_info()
    cpu_percent = process.cpu_percent(interval=0.1)
    
    # 磁盘使用情况
    disk_usage = psutil.disk_usage('/')
    
    # 数据库文件大小
    db_size = 0
    if os.path.exists('data/tqsync.db'):
        db_size = os.path.getsize('data/tqsync.db')
    
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
        "memory_usage": f"{mem_info.rss / 1024 / 1024:.1f} MB",
        "disk_usage": f"{disk_usage.percent:.1f}%",
        "db_size": f"{db_size / 1024:.1f} KB",
        "plugins": {
            "total": len(plugins_status),
            "loaded": sum(1 for p in plugins_status if p['loaded']),
            "enabled": sum(1 for p in plugins_status if p['enabled']),
            "list": plugins_status
        }
    }

@app.get("/admin/logs", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_logs(lines: int = 50):
    log_file = os.path.join(os.getcwd(), 'logs', 'tqsync.log')
    try:
        if not os.path.exists(log_file):
            return {"logs": ["日志文件未找到，请检查系统是否正常运行。"]}
        
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_n_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
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

@app.put("/admin/config/{config_key}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
def update_config(config_key: str, update: ConfigUpdate):
    try:
        # 尝试转换类型
        value = update.value
        if update.value.lower() in ['true', 'false']:
            value = update.value.lower() == 'true'
        elif update.value.isdigit():
            value = int(update.value)
        
        config_loader.update_config(config_key, value)
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
    if not body.word.strip():
        raise HTTPException(status_code=400, detail="屏蔽词不能为空")
    success = await db.add_blocked_word(body.word)
    if not success:
        raise HTTPException(status_code=409, detail="屏蔽词已存在")
    return {"status": "success", "message": f"已添加屏蔽词: {body.word}", "word": body.word}

@app.delete("/admin/blocked_words/{word}", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def delete_blocked_word(word: str):
    from urllib.parse import unquote
    word = unquote(word)
    success = await db.remove_blocked_word(word)
    if not success:
        raise HTTPException(status_code=404, detail="屏蔽词不存在")
    return {"status": "success", "message": f"已删除屏蔽词: {word}"}


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

class BlockedWordAdd(BaseModel):
    word: str


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
