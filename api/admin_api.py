from fastapi import FastAPI, HTTPException, Depends, Header
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
        "db_size": f"{db_size / 1024:.1f} KB"
    }

@app.get("/admin/logs", dependencies=[Depends(require_permission(PERM_LEVEL_ADMIN))])
async def get_logs(lines: int = 50):
    log_file = os.path.join(os.getcwd(), 'logs', 'tqsync.log')
    try:
        if not os.path.exists(log_file):
            return {"logs": ["Log file not found."]}
        
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_n_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        # 如果是 JSON 格式，尝试提取 message 字段以便前端显示更清晰
        clean_logs = []
        for line in last_n_lines:
            try:
                import json
                log_obj = json.loads(line)
                clean_logs.append(f"{log_obj.get('time', '')} [{log_obj.get('level', '')}] {log_obj.get('message', '')}")
            except:
                clean_logs.append(line.strip())
                
        return {"logs": clean_logs}
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        return {"logs": [f"Error reading logs: {str(e)}"]}

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
    return [{"tg_user_id": b[0], "qq_user_id": b[1], "tg_username": b[2], "qq_nickname": b[3]} for b in bindings]

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
