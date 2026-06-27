from utils.version_utils import get_full_version_string
from db.database import db
from config.config_loader import config_loader
import time
import os
import sys
import subprocess
import re
from datetime import datetime
from utils.logger import logger

HELP_TEXT = (
    "| TQSync Help\n\n"
    "可用命令：\n"
    "/bind - 发起绑定流程（QQ端获取验证码，TG端输入验证码）\n"
    "/setprefix <nickname> - 设置您在双端显示的统一昵称\n"
    "/status - 查看机器人运行状态\n"
    "/checkupdate - 从 GitHub 拉取最新源码并自动重启更新（仅限管理员）\n"
    "/reboot - 远程重启机器人（仅限管理员）\n"
    "/webui - 发送在config中配置的 WebUI 地址\n"
    "/blockword <关键词> - 添加屏蔽词（仅限管理员）\n"
    "/unblockword <关键词> - 删除屏蔽词（仅限管理员）\n"
    "/blockwords - 查看当前屏蔽词列表\n"
    "/confirm - 确认自动下载 FFmpeg\n"
    "/cancel - 取消自动下载提示\n"
    "/help - 显示此帮助信息"
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

async def handle_status_command(start_time: float = None):
    """处理 /status 指令，返回系统状态字符串"""
    if start_time is None:
        from main import GLOBAL_START_TIME
        start_time = GLOBAL_START_TIME
    
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
    uptime_seconds = int(time.time() - start_time)
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
            plugin_info_lines = "\n已加载插件:\n"
            for p in plugins:
                status_icon = "✅" if (p['loaded'] and p['enabled'] and not p['error']) else ("⏸" if not p['enabled'] else "❌")
                plugin_info_lines += f"   {status_icon} {p['file']} v{p['version']}"
                if p['load_time_ms'] > 0:
                    plugin_info_lines += f" ({p['load_time_ms']}ms)"
                if p['error']:
                    plugin_info_lines += f" - {p['error']}"
                plugin_info_lines += "\n"
        else:
            plugin_info_lines = "\n已加载插件: 无\n"
    except Exception:
        plugin_info_lines = "\n已加载插件: 获取失败\n"

    return (
        f"| TQSync Status\n"
        f"--------------------------\n"
        f"- 版本信息: {get_full_version_string()}\n"
        f"- 上次更新: {last_update}\n"
        f"- 运行时长: {uptime_str}\n"
        f"- 已同步消息: {sync_count} 条\n"
        f"- 绑定用户数: {user_count} 人\n"
        f"- 目标 QQ 群: {qq_gid}\n"
        f"- 目标 TG 群: {tg_gid}\n"
        f"--------------------------"
        f"{plugin_info_lines}"
        f"--------------------------"
    )

async def handle_help_command():
    """处理 /help 指令"""
    plugin_lines = ""
    try:
        from core.plugin_manager import PluginManager
        pm = PluginManager.get_instance()
        plugins = pm.get_plugins_status()
        if plugins:
            for p in plugins:
                if not (p['loaded'] and p['enabled']):
                    continue
                for m in p.get('matchers', []):
                    pattern = m.get('pattern', '')
                    desc = m.get('description', p.get('description', ''))
                    if not pattern:
                        continue
                    # 只显示主命令，跳过正则类型
                    if m.get('type') == 'regex':
                        continue
                    # 清理描述中的子命令部分（如 "/cd add <名称> <日期>"）
                    desc = re.sub(r'\s*/\S+.*$', '', desc)
                    plugin_lines += f"/{pattern.lstrip('/')} - {desc}\n"
    except Exception:
        pass

    base = HELP_TEXT.rstrip()
    if plugin_lines:
        base += "\n\n插件命令：\n" + plugin_lines.rstrip()
    return base


async def handle_checkupdate_command() -> dict:
    """处理 /checkupdate 指令

    Returns:
        dict 包含:
        - ok: bool, 是否成功
        - update_found: bool, 是否检测到更新
        - update_notice: str|None, 检测到更新时的通知消息 (含版本/commit)
        - result: str, 执行结果文本
        - need_restart: bool, 是否需要重启
    """
    logger.info("执行 /checkupdate 更新检查")
    r = {"ok": False, "update_found": False, "update_notice": None, "result": "", "need_restart": False}

    # 1. Fetch 远程更新
    try:
        result = subprocess.run(
            ['git', 'fetch', 'origin'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            r["result"] = f"更新失败：git fetch \n{result.stderr.strip()[:500]}"
            return r
        logger.info("git fetch 完成")
    except subprocess.TimeoutExpired:
        r["result"] = "更新失败：git fetch 超时，请检查网络"
        return r
    except FileNotFoundError:
        r["result"] = "更新失败：未找到 git 命令，请确认已安装 Git"
        return r
    except Exception as e:
        r["result"] = f"更新失败：git fetch 异常\n{e}"
        return r

    # 2. 获取当前分支和远程对比
    try:
        branch_result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        current_branch = branch_result.stdout.strip()
        if not current_branch:
            current_branch = 'main'

        local_result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        local_commit = local_result.stdout.strip()[:7]
        local_full = local_result.stdout.strip()

        remote_result = subprocess.run(
            ['git', 'rev-parse', f'origin/{current_branch}'],
            capture_output=True, text=True, timeout=10
        )
        if remote_result.returncode != 0:
            r["result"] = f"更新失败：无法获取远程分支 origin/{current_branch}\n请确认远程仓库配置正确"
            return r

        remote_commit = remote_result.stdout.strip()[:7]
        remote_full = remote_result.stdout.strip()

        parts = [f"当前分支: {current_branch}", f"本地: {local_commit}  =>  远程: {remote_commit}"]

        if local_full == remote_full:
            parts.append("已是最新版本，无需更新")
            r["ok"] = True
            r["result"] = "\n".join(parts)
            return r

        # 有更新
        r["update_found"] = True
        r["update_notice"] = (
            f"检测到更新：\n"
            f"TQSync [Commit hash: {remote_commit}]\n"
            f"即将开始更新"
        )

    except Exception as e:
        r["result"] = f"更新失败：版本对比异常\n{e}"
        return r

    # 3. 获取更新日志
    try:
        log_result = subprocess.run(
            ['git', 'log', '--oneline', f'{local_commit}..{remote_commit}', '-n', '10'],
            capture_output=True, text=True, timeout=10
        )
        if log_result.stdout.strip():
            parts.append(f"\n更新日志:\n{log_result.stdout.strip()}")
    except Exception:
        pass

    # 4. 执行 pull
    try:
        pull_result = subprocess.run(
            ['git', 'pull', 'origin', current_branch],
            capture_output=True, text=True, timeout=60
        )
        if pull_result.returncode != 0:
            r["result"] = f"更新失败：git pull 出错\n{pull_result.stderr.strip()[:500]}"
            return r
        parts.append("git pull 成功")
        logger.info("git pull 完成")
    except subprocess.TimeoutExpired:
        r["result"] = "更新失败：git pull 超时"
        return r
    except Exception as e:
        r["result"] = f"更新失败：git pull 异常\n{e}"
        return r

    # 5. 安装依赖
    try:
        pip_result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '--quiet'],
            capture_output=True, text=True, timeout=120
        )
        if pip_result.returncode == 0:
            parts.append("依赖安装成功")
            logger.info("pip install 完成")
        else:
            parts.append(f"依赖安装可能存在问题:\n{pip_result.stderr.strip()[:300]}")
    except subprocess.TimeoutExpired:
        parts.append("依赖安装超时，将继续重启")
    except Exception as e:
        parts.append(f"依赖安装异常: {e}")

    parts.append("\n即将重启以应用更新...")
    r["ok"] = True
    r["need_restart"] = True
    r["result"] = "\n".join(parts)
    return r
