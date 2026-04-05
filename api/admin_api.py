from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sys
import os
import time
import asyncio
from config.config_loader import config_loader
from db.database import db

app = FastAPI(title="TQSync Admin API")

# 增加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_api_key(x_api_key: str = Header(None)):
    """简单的 API Key 验证依赖项"""
    correct_key = config_loader.get('server.admin_api_key')
    if not correct_key or x_api_key != correct_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

class ConfigUpdate(BaseModel):
    key: str
    value: str

class BindingUpdate(BaseModel):
    tg_user_id: int
    qq_user_id: int
    tg_username: Optional[str] = None
    qq_nickname: Optional[str] = None

@app.post("/admin/restart")
async def trigger_restart(api_key: bool = Depends(verify_api_key)):
    from main import graceful_restart
    # 异步触发重启，避免 API 请求因进程关闭而报错
    asyncio.create_task(graceful_restart())
    return {"status": "restarting", "message": "系统正在优雅重启..."}

@app.get("/admin/status")
async def get_status(api_key: bool = Depends(verify_api_key)):
    try:
        from main import start_time
        current_start_time = start_time
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
    return {
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "bound_users": len(bindings),
        "qq_group_id": config_loader.get('qq.group_id'),
        "tg_group_id": config_loader.get('telegram.group_id')
    }

@app.get("/admin/logs")
async def get_logs(api_key: bool = Depends(verify_api_key)):
    # 这里可以对接一个内存中的日志队列，目前先返回一个简单的示例
    return {"logs": ["System running...", "Webhook server started"]}

@app.put("/admin/config/{config_key}")
def update_config(config_key: str, update: ConfigUpdate, api_key: bool = Depends(verify_api_key)):
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

@app.get("/admin/bindings")
async def get_bindings(api_key: bool = Depends(verify_api_key)):
    bindings = await db.get_all_bindings()
    return [{"tg_user_id": b[0], "qq_user_id": b[1], "tg_username": b[2], "qq_nickname": b[3]} for b in bindings]

@app.delete("/admin/bindings/{tg_user_id}")
async def delete_binding(tg_user_id: int, api_key: bool = Depends(verify_api_key)):
    await db.delete_binding(tg_user_id=tg_user_id)
    return {"status": "success"}

@app.put("/admin/bindings")
async def add_binding(binding: BindingUpdate, api_key: bool = Depends(verify_api_key)):
    await db.add_binding(binding.tg_user_id, binding.qq_user_id, binding.tg_username, binding.tg_username)
    return {"status": "success"}

@app.get("/admin/admins")
async def get_admins(api_key: bool = Depends(verify_api_key)):
    admins = config_loader.get('server.admin_user_ids', [])
    if not isinstance(admins, list):
        admins = []
    return {"admins": admins}

@app.post("/admin/admins")
async def toggle_admin(user_id: int, api_key: bool = Depends(verify_api_key)):
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
