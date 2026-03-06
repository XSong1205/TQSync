"""
TQSync Web Dashboard - 主程序
安全的 Web 管理面板
"""

import asyncio
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from jose import JWTError, jwt
from passlib.hash import argon2
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
import aiofiles
import yaml
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入统计数据管理器
try:
    from utils.stats_manager import get_stats_manager
    STATS_ENABLED = True
except ImportError:
    STATS_ENABLED = False
    print("⚠️  警告：无法导入 stats_manager，统计功能将不可用")

app = FastAPI(
    title="TQSync Web Dashboard",
    description="安全的 Web 管理面板",
    version="0.1.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT 配置
SECRET_KEY = "your-secret-key-change-in-production"  # 生产环境应该使用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时

# 安全认证
security = HTTPBearer()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


# ============== 安全认证 ==============

def get_password_hash(password: str) -> str:
    """密码哈希"""
    return argon2.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return argon2.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    return username


# ============== 数据模型 ==============

class LoginRequest(BaseModel):
    username: str
    password: str


class ConfigUpdate(BaseModel):
    config_type: str  # 'env' or 'yaml'
    content: str


class RestartRequest(BaseModel):
    confirm: bool


# ============== API 接口 ==============

@app.post("/api/login")
async def login(request: LoginRequest):
    """用户登录"""
    # 验证密码
    password_file = Path(__file__).parent / "admin_password.hash"
    
    if not password_file.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="管理员密码未设置，请先运行 set_admin_password.py"
        )
    
    with open(password_file, 'r', encoding='utf-8') as f:
        hashed_password = f.read().strip()
    
    # 验证用户名和密码（用户名固定为 admin）
    if request.username != "admin" or not verify_password(request.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 生成 Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": request.username},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/status")
async def get_status(current_user: str = Depends(get_current_user)):
    """获取系统状态"""
    # 检查配置文件是否存在
    env_file = PROJECT_ROOT / ".env"
    config_file = PROJECT_ROOT / "config.yaml"
    
    status_info = {
        "env_exists": env_file.exists(),
        "config_exists": config_file.exists(),
        "timestamp": datetime.now().isoformat(),
    }
    
    # 获取真实统计数据
    if STATS_ENABLED:
        try:
            stats_manager = await get_stats_manager()
            stats = await stats_manager.get_stats()
            status_info["stats"] = stats
        except Exception as e:
            print(f"获取统计数据失败：{e}")
            # 使用默认数据
            status_info["stats"] = {
                "telegram_received": 0,
                "qq_received": 0,
                "telegram_sent": 0,
                "qq_sent": 0,
                "filtered": 0,
                "uptime": "0h 0m",
            }
    else:
        # 使用默认数据
        status_info["stats"] = {
            "telegram_received": 0,
            "qq_received": 0,
            "telegram_sent": 0,
            "qq_sent": 0,
            "filtered": 0,
            "uptime": "0h 0m",
        }
    
    return status_info


@app.get("/api/config/env")
async def get_env_config(current_user: str = Depends(get_current_user)):
    """获取 .env 配置"""
    env_file = PROJECT_ROOT / ".env"
    
    if not env_file.exists():
        return {"content": "", "exists": False}
    
    async with aiofiles.open(env_file, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    return {"content": content, "exists": True}


@app.get("/api/config/yaml")
async def get_yaml_config(current_user: str = Depends(get_current_user)):
    """获取 config.yaml 配置"""
    config_file = PROJECT_ROOT / "config.yaml"
    
    if not config_file.exists():
        return {"content": "", "exists": False}
    
    async with aiofiles.open(config_file, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    return {"content": content, "exists": True}


@app.post("/api/config/update")
async def update_config(
    config_update: ConfigUpdate,
    current_user: str = Depends(get_current_user)
):
    """更新配置文件"""
    if config_update.config_type == "env":
        file_path = PROJECT_ROOT / ".env"
    elif config_update.config_type == "yaml":
        file_path = PROJECT_ROOT / "config.yaml"
    else:
        raise HTTPException(status_code=400, detail="无效的配置类型")
    
    # 保存配置
    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
        await f.write(config_update.content)
    
    return {"message": f"{config_update.config_type} 配置已保存"}


@app.post("/api/restart")
async def restart_bot(
    restart_request: RestartRequest,
    current_user: str = Depends(get_current_user)
):
    """重启机器人"""
    if not restart_request.confirm:
        raise HTTPException(status_code=400, detail="需要确认重启")
    
    # TODO: 实现机器人重载逻辑
    # 注意：不修改现有代码逻辑，通过外部调用实现
    return {"message": "机器人重启请求已接收（功能待实现）"}


# ============== 前端页面 ==============

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """管理面板首页"""
    html_file = Path(__file__).parent / "static" / "index.html"
    
    if not html_file.exists():
        return HTMLResponse("<h1>TQSync Dashboard</h1><p>前端文件未找到</p>")
    
    async with aiofiles.open(html_file, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    return HTMLResponse(content=content)


# 挂载静态文件目录
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 TQSync Web Dashboard 启动中...")
    print("=" * 60)
    print("访问地址：http://localhost:8000")
    print("首次使用请先运行：python set_admin_password.py")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
