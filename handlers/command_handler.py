from utils.version_utils import get_full_version_string
from utils.message_style import block, bullet, duration, SEP
from db.database import db
from config.config_loader import config_loader
import time
import os
import sys
import subprocess
import re
import asyncio
from datetime import datetime
from utils.logger import logger

HELP_TEXT = (
    "| TQSync Help\n\n"
    "可用命令：\n"
    "/bind - 发起绑定流程（QQ 端获取验证码，TG 端输入验证码）\n"
    "/setprefix <昵称> - 设置您的统一昵称\n"
    "/status - 查看机器人运行状态\n"
    "/update - 检查并从 GitHub 拉取最新源码升级重启（仅限管理员）\n"
    "/reboot - 远程重启机器人（仅限管理员）\n"
    "/notice <内容> - 发布群公告并双端置顶同步（仅限管理员）\n"
    "/syncnotice - 手动拉取 QQ 群最新公告并同步至 TG 置顶\n"
    "/webui - 发送 WebUI 管理面板地址\n"
    "/blockwords - 查看当前屏蔽词列表\n"
    "/help - 显示此帮助信息\n\n"
    "更多配置项（如屏蔽词管理等）请查看 WebUI，或在群内发送 /webui 获取地址。"
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
        bind_msg = block("Bind-User", [
            bullet("验证码", code),
            bullet("有效期", "5 分钟"),
            bullet("下一步", f"在 Telegram 中发送 /bind {code}"),
        ])
        try:
            result = await onebot_client.send_private_msg(qq_user_id, bind_msg)

            if result.get('retcode') == 0:
                return "验证码已通过私聊发送，请注意查收；如未收到，请检查是否开启临时会话权限。"
            else:
                raise Exception(f"OneBot API 错误: {result}")

        except Exception as e:
            logger.warning(f"发送私聊验证码失败 (QQ: {qq_user_id}): {e}")
            # 降级方案：在群内发送验证码
            return block("Bind-User", [
                bullet("说明", "私聊发送失败（可能未开启临时会话权限）"),
                bullet("验证码", code),
                bullet("有效期", "5 分钟"),
                bullet("下一步", f"在 Telegram 中发送 /bind {code}"),
            ])

    elif platform == 'tg':
        # TG 端不再直接绑定，提示使用验证码方式
        return block("Bind", [
            bullet("第一步", "在 QQ 群发送 /bind 获取验证码"),
            bullet("第二步", "在 Telegram 发送 /bind <验证码>"),
        ])

    return "用法：/bind"

async def handle_setprefix_command(user_id: int, platform: str, args: list):
    """处理 /setprefix 指令"""
    if not args:
        return "用法：/setprefix <昵称>"
    
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
        return "您尚未完成绑定，请在 QQ 群发送 /bind 获取验证码。"
    
    await db.update_custom_prefix(uid, new_prefix)
    return f"统一昵称已更新为：{new_prefix}"

async def handle_status_command(start_time: float = None):
    """处理 /status 指令，返回系统状态字符串"""
    if start_time is None:
        from main import GLOBAL_START_TIME
        start_time = GLOBAL_START_TIME
    
    # 1. 获取最后更新时间
    last_update = "Unknown"
    try:
        # subprocess 是阻塞调用（Windows 上启动进程 ~30-100ms），放线程池避免卡事件循环
        result = await asyncio.to_thread(
            subprocess.run, ['git', 'log', '-1', '--format=%ci'],
            capture_output=True, text=True, check=True
        )
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
    if uptime_seconds < 0:
        uptime_seconds = 0
    uptime_str = duration(uptime_seconds)

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

    # 6. 获取插件状态（状态用文字表达，不用 emoji）
    plugin_lines = []
    try:
        from core.plugin_manager import PluginManager
        pm = PluginManager.get_instance()
        plugins = pm.get_plugins_status()
        if plugins:
            enabled_count = sum(1 for p in plugins if p['loaded'] and p['enabled'] and not p['error'])
            plugin_lines.append(f"插件（{enabled_count}/{len(plugins)} 已启用）:")
            for p in plugins:
                if p.get('error'):
                    state = f"加载失败（{p['error']}）"
                elif not p['enabled']:
                    state = "未启用"
                else:
                    state = "已加载"
                cost = f" ({p['load_time_ms']}ms)" if p.get('load_time_ms') else ""
                plugin_lines.append(f"- {p['file']} v{p['version']}{cost} · {state}")
        else:
            plugin_lines.append("插件: 无")
    except Exception:
        plugin_lines.append("插件: 获取失败")

    # 7. QQ 连接状态 (主动探测 NapCat HTTP 接口的实时结果)
    conn_lines = []
    try:
        from core.qq_health import STATE_OFFLINE, qq_health_monitor

        conn_lines.append(bullet("QQ 连接", qq_health_monitor.status_text()))
        if qq_health_monitor.state == STATE_OFFLINE and qq_health_monitor.last_error:
            conn_lines.append(bullet("断开原因", qq_health_monitor.last_error))
    except Exception:
        conn_lines.append(bullet("QQ 连接", "获取失败"))

    body = [
        bullet("版本信息", get_full_version_string()),
        bullet("上次更新", last_update),
        bullet("运行时长", uptime_str),
        bullet("已同步消息", f"{sync_count} 条"),
        bullet("绑定用户数", f"{user_count} 人"),
        bullet("目标 QQ 群", qq_gid),
        bullet("目标 TG 群", tg_gid),
        *conn_lines,
        SEP,
        *plugin_lines,
    ]
    return block("Status", body)

async def _get_public_ip() -> str:
    """通过第三方接口获取服务器公网 IP，失败返回空字符串（兼容旧调用）"""
    from utils.network_utils import get_public_ip
    return await get_public_ip()


async def handle_webui_command():
    """处理 /webui 指令，返回 WebUI 地址"""
    from utils.network_utils import get_webui_url
    url = await get_webui_url()
    return block("WebUI", [url])


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


async def check_for_updates() -> dict:
    """仅检查 GitHub 远程是否有更新（纯只读检查，不执行 pull，不修改本地文件）

    Returns:
        dict 包含:
        - ok: bool
        - update_found: bool
        - current_branch: str
        - local_commit: str
        - remote_commit: str
        - changelog: str
        - result: str
    """
    logger.debug("执行只读更新检查 (git fetch)")
    r = {
        "ok": False,
        "update_found": False,
        "current_branch": "main",
        "local_commit": "",
        "remote_commit": "",
        "changelog": "",
        "result": ""
    }

    # 1. Fetch 远程更新
    try:
        result = subprocess.run(
            ['git', 'fetch', 'origin'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            r["result"] = f"检查更新失败：git fetch 错误\n{result.stderr.strip()[:500]}"
            return r
    except subprocess.TimeoutExpired:
        r["result"] = "检查更新失败：git fetch 超时，请检查网络"
        return r
    except FileNotFoundError:
        r["result"] = "检查更新失败：未找到 git 命令"
        return r
    except Exception as e:
        r["result"] = f"检查更新失败：git fetch 异常\n{e}"
        return r

    # 2. 获取当前分支和提交对比
    try:
        branch_result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        current_branch = branch_result.stdout.strip() or 'main'
        r["current_branch"] = current_branch

        local_result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        local_commit = local_result.stdout.strip()[:7]
        local_full = local_result.stdout.strip()
        r["local_commit"] = local_commit

        remote_result = subprocess.run(
            ['git', 'rev-parse', f'origin/{current_branch}'],
            capture_output=True, text=True, timeout=10
        )
        if remote_result.returncode != 0:
            r["result"] = f"检查更新失败：无法获取远程分支 origin/{current_branch}"
            return r

        remote_commit = remote_result.stdout.strip()[:7]
        remote_full = remote_result.stdout.strip()
        r["remote_commit"] = remote_commit

        if local_full == remote_full:
            r["ok"] = True
            r["update_found"] = False
            r["result"] = block("Update", [
                bullet("状态", "已是最新版本"),
                bullet("分支", current_branch),
                bullet("提交", local_commit),
            ])
            return r

        # 3. 存在更新，提取更新日志
        r["ok"] = True
        r["update_found"] = True

        log_result = subprocess.run(
            ['git', 'log', '--oneline', f'{local_commit}..{remote_commit}', '-n', '10'],
            capture_output=True, text=True, timeout=10
        )
        changelog = log_result.stdout.strip()
        r["changelog"] = changelog

        r["result"] = block(
            "Update",
            [
                bullet("状态", "检测到新版本"),
                bullet("分支", current_branch),
                bullet("当前提交", local_commit),
                bullet("远程提交", remote_commit),
            ],
            footer=["更新日志:", changelog] if changelog else None,
        )
        return r

    except Exception as e:
        r["result"] = f"检查更新异常：{e}"
        return r


async def handle_update_command() -> dict:
    """处理 /update 指令：检查并执行拉取升级与重启

    Returns:
        dict 包含:
        - ok: bool, 是否成功
        - update_found: bool, 是否检测到更新
        - update_notice: str|None, 检测到更新时的通知消息
        - result: str, 执行结果文本
        - need_restart: bool, 是否需要重启
    """
    logger.info("执行 /update 手动更新指令")
    r = {"ok": False, "update_found": False, "update_notice": None, "result": "", "need_restart": False}

    # 1. 先进行只读检查
    check_info = await check_for_updates()
    if not check_info.get("ok"):
        r["result"] = check_info.get("result", "更新检查失败")
        return r

    current_branch = check_info.get("current_branch", "main")
    local_commit = check_info.get("local_commit", "")
    remote_commit = check_info.get("remote_commit", "")
    changelog = check_info.get("changelog", "")

    if not check_info.get("update_found"):
        r["ok"] = True
        r["result"] = check_info.get("result", "已是最新版本，无需更新")
        return r

    # 发现更新，准备拉取
    r["update_found"] = True
    r["update_notice"] = block("Update", [
        bullet("状态", "检测到更新，准备升级"),
        bullet("提交变动", f"{local_commit} => {remote_commit}"),
    ])

    parts = [
        bullet("当前分支", current_branch),
        bullet("版本变动", f"{local_commit} => {remote_commit}"),
    ]

    # 2. 执行 pull（先 stash 本地修改避免冲突）
    try:
        stash_result = subprocess.run(
            ['git', 'stash', 'push', '-m', 'auto-stash before update'],
            capture_output=True, text=True, timeout=10
        )
        stashed = stash_result.returncode == 0 and 'No local changes' not in stash_result.stdout
        if stashed:
            parts.append(bullet("本地修改", "已暂存"))
    except Exception:
        stashed = False

    try:
        pull_result = subprocess.run(
            ['git', 'pull', 'origin', current_branch],
            capture_output=True, text=True, timeout=60
        )
        if pull_result.returncode != 0:
            r["result"] = f"更新失败：git pull 出错\n{pull_result.stderr.strip()[:500]}"
            return r
        parts.append(bullet("拉取代码", "成功"))
        logger.info("git pull 完成")

        if stashed:
            subprocess.run(
                ['git', 'stash', 'drop', 'stash@{0}'],
                capture_output=True, text=True, timeout=10
            )
    except subprocess.TimeoutExpired:
        r["result"] = "更新失败：git pull 超时"
        return r
    except Exception as e:
        r["result"] = f"更新失败：git pull 异常\n{e}"
        return r

    # 3. 安装依赖
    try:
        pip_result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '--quiet'],
            capture_output=True, text=True, timeout=120
        )
        if pip_result.returncode == 0:
            parts.append(bullet("安装依赖", "成功"))
            logger.info("pip install 完成")
        else:
            parts.append(bullet("安装依赖", f"可能存在问题：{pip_result.stderr.strip()[:300]}"))
    except subprocess.TimeoutExpired:
        parts.append(bullet("安装依赖", "超时，将继续重启"))
    except Exception as e:
        parts.append(bullet("安装依赖", f"异常：{e}"))

    parts.append(bullet("状态", "即将重启以应用更新"))
    r["remote_commit"] = remote_commit
    try:
        from utils.version_utils import get_version
        r["version"] = get_version()
    except Exception:
        pass
    r["ok"] = True
    r["need_restart"] = True
    r["result"] = block("Update", parts, footer=["更新日志:", changelog] if changelog else None)
    return r


# 兼容旧接口命名
handle_checkupdate_command = handle_update_command



async def handle_reboot_command(platform: str = 'qq') -> str:
    """处理 /reboot 指令，返回重启提示消息"""
    return "正在重启机器人，请稍候…"


async def handle_blockword_command(args: list, user_id: int = None, platform: str = 'qq') -> str:
    """处理 /blockword <关键词> 指令"""
    if not args:
        return "用法：/blockword <关键词>"
    word = " ".join(args)
    success = await db.add_blocked_word(word)
    if success:
        logger.info(f"[屏蔽词] {platform.upper()}管理员 {user_id} 添加屏蔽词: {word}")
        return f"已添加屏蔽词：{word}"
    else:
        return f"屏蔽词已存在：{word}"


async def handle_unblockword_command(args: list, user_id: int = None, platform: str = 'qq') -> str:
    """处理 /unblockword <关键词> 指令"""
    if not args:
        return "用法：/unblockword <关键词>"
    word = " ".join(args)
    success = await db.remove_blocked_word(word)
    if success:
        logger.info(f"[屏蔽词] {platform.upper()}管理员 {user_id} 删除屏蔽词: {word}")
        return f"已删除屏蔽词：{word}"
    else:
        return f"屏蔽词不存在：{word}"


async def handle_blockwords_command() -> str:
    """处理 /blockwords 指令，返回屏蔽词列表"""
    words = await db.get_blocked_words()
    if words:
        body = [bullet("共", f"{len(words)} 个")]
        body += [f"{i + 1}. {w}" for i, w in enumerate(words)]
        return block("Blockwords", body)
    else:
        return "当前没有屏蔽词。"
