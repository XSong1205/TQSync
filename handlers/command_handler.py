from utils.version_utils import get_full_version_string
from db.database import db
from config.config_loader import config_loader
import time
import os
import subprocess
from datetime import datetime
from utils.logger import logger

HELP_TEXT = (
    "🤖 TQSync 帮助文档\n\n"
    "可用命令：\n"
    "/bind - 发起绑定流程（QQ端获取验证码，TG端输入验证码）\n"
    "/setprefix <nickname> - 设置您在双端显示的统一昵称\n"
    "/status - 查看机器人运行状态\n"
    "/reboot - 远程重启机器人（仅限管理员）\n"
    "/confirm - 确认自动下载 FFmpeg\n"
    "/cancel - 取消自动下载提示\n"
    "/help - 显示此帮助信息\n\n"
    "绑定流程：\n"
    "1. 在 QQ 群发送 /bind 获取6位验证码\n"
    "2. 在 Telegram 使用 /bind <验证码> 完成绑定\n"
    "3. 绑定后消息将自动双向同步"
)

async def handle_bind_command(user_id: int, platform: str, args: list = None):
    """
    处理 /bind 指令
    - QQ 端: 生成验证码并通过私聊发送
    - TG 端: 提示使用验证码方式
    """
    from handlers.qq_handler import onebot_client
    
    if platform == 'qq':
        qq_user_id = user_id
        
        # 检查是否已绑定
        existing_binding = await db.get_binding_by_qq(qq_user_id)
        if existing_binding:
            return "您已经完成了绑定，无需重复操作。"
        
        # 生成验证码
        code = await db.create_verification_code(qq_user_id, expire_minutes=5)
        
        # 尝试发送私聊消息
        try:
            result = await onebot_client.send_private_msg(qq_user_id, 
                f"【TQSync 绑定验证码】\n"
                f"您的验证码是: {code}\n"
                f"有效期: 5分钟\n"
                f"请在 Telegram 中使用 /bind {code} 完成绑定"
                f"请勿将验证码传递给他人")
            
            if result.get('retcode') == 0:
                return f"验证码已通过私聊发送给您，请查收。\n如果未收到，请检查是否开启了临时会话权限。"
            else:
                raise Exception(f"OneBot API 错误: {result}")
        
        except Exception as e:
            logger.warning(f"发送私聊验证码失败 (QQ: {qq_user_id}): {e}")
            # 降级方案：在群内发送验证码
            return f"私聊发送失败（可能未开启临时会话权限）\n您的验证码是: {code}\n请在 Telegram 中使用 /bind {code} 完成绑定\n有效期: 5分钟"
    
    elif platform == 'tg':
        # TG 端不再直接绑定，提示使用验证码方式
        return "请在 QQ 群中发送 /bind 指令获取验证码，然后在 Telegram 中使用 /bind <验证码> 完成绑定。"
    
    return "Usage: /bind"

async def handle_setprefix_command(user_id: int, platform: str, args: list):
    """处理 /setprefix 指令"""
    if not args:
        return "Usage: /setprefix <nickname>"
    
    new_prefix = " ".join(args)
    
    # 查找 UID
    uid = None
    if platform == 'tg':
        binding = await db.get_binding_by_tg(user_id)
        if binding: uid = binding[4]
    else: # qq
        binding = await db.get_binding_by_qq(user_id)
        if binding: uid = binding[4]
        
    if not uid:
        return "您尚未完成绑定，请使用 /bind 获取验证码。"
    
    await db.update_custom_prefix(uid, new_prefix)
    return f"Your unified display name has been updated to: {new_prefix}"

async def handle_status_command():
    """处理 /status 指令，返回系统状态字符串"""
    from main import GLOBAL_START_TIME
    
    # 1. 获取最后更新时间
    last_update = "Unknown"
    try:
        result = subprocess.run(['git', 'log', '-1', '--format=%ci'], 
                                capture_output=True, text=True, check=True)
        git_time_str = result.stdout.strip()
        last_update = git_time_str.split('+')[0].strip()
    except Exception:
        try:
            mtime = os.path.getmtime('main.py')
            last_update = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass

    # 2. 计算运行时长
    uptime_seconds = int(time.time() - GLOBAL_START_TIME)
    if uptime_seconds < 0: uptime_seconds = 0
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}小时 {minutes}分 {seconds}秒"

    # 3. 获取同步统计 (通过 message_mapping 表行数近似)
    async with db._Database__get_connection() as conn:
        cursor = await conn.execute('SELECT COUNT(*) FROM message_mapping')
        sync_count = (await cursor.fetchone())[0]

    # 4. 获取绑定人数
    bindings = await db.get_all_bindings()
    user_count = len(bindings)

    # 5. 获取配置信息
    qq_gid = config_loader.get('qq.group_id')
    tg_gid = config_loader.get('telegram.group_id')

    # 6. 获取插件状态
    plugin_info_lines = ""
    try:
        from core.plugin_manager import PluginManager
        pm = PluginManager.get_instance()
        plugins = pm.get_plugins_status()
        if plugins:
            plugin_info_lines = "\n🔌 已加载插件:\n"
            for p in plugins:
                status_icon = "✅" if (p['loaded'] and p['enabled'] and not p['error']) else ("⏸" if not p['enabled'] else "❌")
                plugin_info_lines += f"   {status_icon} {p['file']} v{p['version']}"
                if p['load_time_ms'] > 0:
                    plugin_info_lines += f" ({p['load_time_ms']}ms)"
                if p['error']:
                    plugin_info_lines += f" - {p['error']}"
                plugin_info_lines += "\n"
        else:
            plugin_info_lines = "\n🔌 已加载插件: 无\n"
    except Exception:
        plugin_info_lines = "\n🔌 已加载插件: 获取失败\n"

    return (
        f"📊 TQSync 运行状态报告\n"
        f"--------------------------\n"
        f"📦 版本信息: {get_full_version_string()}\n"
        f"🕒 上次更新: {last_update}\n"
        f"⏱️ 运行时长: {uptime_str}\n"
        f"🔗 已同步消息: {sync_count} 条\n"
        f"👥 绑定用户数: {user_count} 人\n"
        f"💬 目标 QQ 群: {qq_gid}\n"
        f"✈️ 目标 TG 群: {tg_gid}\n"
        f"{plugin_info_lines}"
        f"--------------------------"
    )

async def handle_help_command():
    """处理 /help 指令"""
    return HELP_TEXT
