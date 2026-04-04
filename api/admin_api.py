from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os
from config.config_loader import config_loader
from db.database import db

app = FastAPI(title="TQSync Admin API")

class ConfigUpdate(BaseModel):
    key: str
    value: str

class BindingUpdate(BaseModel):
    tg_user_id: int
    qq_user_id: int
    tg_username: Optional[str] = None
    qq_nickname: Optional[str] = None

@app.post("/admin/restart")
def restart_service():
    # 简单重启：退出当前进程，由外部管理器（如 systemd 或 docker）负责重启
    # 或者在这里实现更优雅的重载逻辑
    os.execv(sys.executable, ['python'] + sys.argv)

@app.put("/admin/config/{config_key}")
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

@app.get("/admin/bindings")
async def get_bindings():
    bindings = await db.get_all_bindings()
    return [{"tg_user_id": b[0], "qq_user_id": b[1], "tg_username": b[2], "qq_nickname": b[3]} for b in bindings]

@app.delete("/admin/bindings/{tg_user_id}")
async def delete_binding(tg_user_id: int):
    await db.delete_binding(tg_user_id=tg_user_id)
    return {"status": "success"}

@app.put("/admin/bindings")
async def add_binding(binding: BindingUpdate):
    await db.add_binding(binding.tg_user_id, binding.qq_user_id, binding.tg_username, binding.tg_username)
    return {"status": "success"}
