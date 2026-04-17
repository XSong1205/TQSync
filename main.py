import asyncio
import os
import sys
import time
import subprocess
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from aiohttp import web
import uvicorn

# 记录全局启动时间，必须在模块加载时立即执行
GLOBAL_START_TIME = time.time()

from config.config_loader import config_loader
from db.database import db
from core.sync_engine import SyncEngine
from handlers.tg_handler import get_tg_handlers
from handlers.command_handler import handle_bind_command, handle_setprefix_command, handle_help_command, handle_status_command
from handlers.qq_handler import onebot_client
from api.admin_api import app as admin_app
from utils.logger import logger

# 记录全局启动时间，用于 Web 面板显示运行时长
# GLOBAL_START_TIME is now defined at the top of the file for immediate initialization

async def handle_qq_webhook(request):
    try:
        data = await request.json()
        
        # 处理撤回通知 (Notice)
        if data.get('post_type') == 'notice' and data.get('notice_type') == 'group_recall':
            qq_msg_id = data.get('message_id')
            if qq_msg_id:
                tg_msg_id = await db.get_tg_msg_id_by_qq(qq_msg_id)
                if tg_msg_id:
                    engine = SyncEngine.get_instance()
                    try:
                        await engine.bot.delete_message(chat_id=engine.tg_group_id, message_id=tg_msg_id)
                        logger.info(f"Synced recall from QQ (msg_id: {qq_msg_id}) to TG (msg_id: {tg_msg_id})")
                    except Exception as e:
                        logger.error(f"Failed to delete message in TG: {e}")
            return web.json_response({})

        # 仅处理群消息
        if data.get('message_type') == 'group':
            # [新增] 校验群组 ID，防止同步非目标群组的消息
            target_group_id = config_loader.get('qq.group_id')
            if data.get('group_id') != target_group_id:
                logger.debug(f"忽略非目标群组消息: {data.get('group_id')}")
                return web.json_response({})
            
            sender = data.get('sender', {})
            qq_id = int(data['user_id'])  # 强制转为整数，防止类型不匹配
            
            # [关键修复] 过滤掉 Bot 自身发送的消息，防止死循环
            bot_qq_id = await onebot_client.get_bot_id()
            if bot_qq_id and qq_id == int(bot_qq_id):
                logger.debug("忽略 Bot 自身消息，防止同步死循环")
                return web.json_response({})
                
            nickname = sender.get('card') or sender.get('nickname') or str(qq_id)
            
            engine = SyncEngine.get_instance()
            
            # 处理消息段数组 (OneBot v11)
            message_array = data.get('message', [])
            text_parts = []
            image_url = None
            video_url = None
            file_url = None
            voice_url = None
            reply_to_tg_id = None
            file_name = "unknown_file"
            at_tg_ids = []
            is_forward = False
            forward_content = None
            
            for msg_part in message_array:
                msg_type = msg_part.get('type')
                if msg_type == 'text':
                    text_parts.append(msg_part['data'].get('text', ''))
                elif msg_type == 'at':
                    target_qq = int(msg_part['data'].get('qq', 0))
                    if target_qq != 0: # 排除 @全体成员
                        binding = await db.get_binding_by_qq(target_qq)
                        if binding:
                            at_tg_ids.append(binding[0]) # tg_user_id
                elif msg_type == 'image' and not image_url:
                    image_url = msg_part['data'].get('url') or msg_part['data'].get('file')
                elif msg_type == 'video' and not video_url:
                    video_url = msg_part['data'].get('url') or msg_part['data'].get('file')
                elif msg_type == 'file' and not file_url:
                    file_url = msg_part['data'].get('url') or msg_part['data'].get('file')
                    file_name = msg_part['data'].get('name', 'unknown_file')
                elif msg_type == 'record':
                    voice_url = msg_part['data'].get('url') or msg_part['data'].get('file')
                elif msg_type == 'forward':
                    is_forward = True
                    forward_content = msg_part.get('data', {})
            
            combined_text = "".join(text_parts).strip()
            
            # 优先处理合并转发消息
            if is_forward and forward_content:
                logger.info(f"检测到来自 {nickname} 的合并转发消息，已加入异步同步队列")
                engine.enqueue_sync_task(engine.forward_merged_to_tg, qq_id, nickname, forward_content)
                return web.json_response({})
            
            # 处理语音消息 (Record)
            if voice_url:
                logger.info(f"检测到来自 {nickname} 的语音消息，已加入异步同步队列")
                engine.enqueue_sync_task(engine.forward_voice_to_tg, qq_id, nickname, voice_url, reply_to_message_id=reply_to_tg_id)
                return web.json_response({})
            
            # 指令识别与路由
            if combined_text.startswith('/'):
                parts = combined_text.split()
                cmd = parts[0].lower()
                args = parts[1:]
                response = ""
                
                if cmd == '/bind':
                    response = await handle_bind_command(qq_id, args)
                elif cmd == '/setprefix':
                    response = await handle_setprefix_command(qq_id, 'qq', args)
                elif cmd == '/help':
                    response = await handle_help_command()
                elif cmd == '/status':
                    response = await handle_status_command()
                elif cmd == '/reboot':
                    admin_ids = config_loader.get('server.admin_user_ids', [])
                    if admin_ids and qq_id not in admin_ids:
                        await onebot_client.send_group_msg(engine.qq_group_id, "权限不足以执行此操作，请联系管理员。")
                        return web.json_response({})
                    
                    await onebot_client.send_group_msg(engine.qq_group_id, "正在重启，请稍候...")
                    asyncio.create_task(graceful_restart('qq'))
                    return web.json_response({})
                else:
                    response = "未知命令。使用 /help 获取更多帮助。"
                
                if response:
                    await onebot_client.send_group_msg(engine.qq_group_id, response)
                return web.json_response({})

            # 解析回复逻辑 (QQ -> TG)
            for msg_part in message_array:
                if msg_part.get('type') == 'reply':
                    original_qq_id = int(msg_part['data'].get('id', 0))
                    if original_qq_id:
                        logger.debug(f"正在查询 QQ 回复映射: original_qq_id={original_qq_id}")
                        reply_to_tg_id = await db.get_tg_msg_id_by_qq(original_qq_id)
                        if reply_to_tg_id:
                            logger.info(f"✅ 成功映射 QQ 回复到 TG 消息 ID: {reply_to_tg_id}")
                        else:
                            logger.warning(f"⚠️ 未能找到 QQ 消息 {original_qq_id} 对应的 TG 映射，回复将作为普通消息发送")
                        break
            
            combined_text = "".join(text_parts).strip()
            
            # 构造 TG 的 HTML 消息以支持 @
            if at_tg_ids:
                display_name = await engine.get_display_name(qq_user_id=qq_id, fallback_name=nickname)
                html_text = f"[QQ] <b>{display_name}</b>: "
                for tid in at_tg_ids:
                    try:
                        user = await engine.bot.get_chat(tid)
                        html_text += f"{user.mention_html()} "
                    except Exception as e:
                        logger.warning(f"获取 TG 用户 {tid} 信息失败: {e}")
                        html_text += f"<a href='tg://user?id={tid}'>@User</a> "
                html_text += combined_text
                try:
                    result = await engine.bot.send_message(chat_id=engine.tg_group_id, text=html_text, parse_mode='HTML', reply_to_message_id=reply_to_tg_id)
                    if result:
                        await db.save_message_mapping(
                            tg_message_id=result.message_id,
                            qq_message_id=data.get('message_id'),
                            sender_qq_id=qq_id
                        )
                except Exception as e:
                    logger.error(f"发送 HTML 消息至 Telegram 失败: {e}")
                    error_msg = [{"type": "text", "data": {"text": f"❌ 同步到 Telegram 失败: {str(e)[:30]}"}}, 
                                 {"type": "reply", "data": {"id": str(data.get('message_id'))}}]
                    await onebot_client.send_group_msg(engine.qq_group_id, error_msg)
            elif image_url:
                logger.info(f"检测到来自 {nickname} 的图片，已加入异步同步队列")
                engine.enqueue_sync_task(engine.forward_image_to_tg, qq_id, nickname, image_url, combined_text, reply_to_message_id=reply_to_tg_id)
            elif video_url:
                logger.info(f"检测到来自 {nickname} 的视频，已加入异步同步队列")
                engine.enqueue_sync_task(engine.forward_video_to_tg, qq_id, nickname, video_url, combined_text, reply_to_message_id=reply_to_tg_id)
            elif file_url:
                logger.info(f"检测到来自 {nickname} 的文件 ({file_name})，已加入异步同步队列")
                engine.enqueue_sync_task(engine.forward_file_to_tg, qq_id, nickname, file_url, file_name, reply_to_message_id=reply_to_tg_id)
            elif combined_text:
                logger.info(f"检测到来自 {nickname} 的文本消息，已加入异步同步队列")
                engine.enqueue_sync_task(engine.forward_to_tg, qq_id, nickname, combined_text, reply_to_message_id=reply_to_tg_id)
        
        return web.Response(text="ok")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(text="error", status=500)

async def start_qq_webhook():
    app = web.Application()
    webhook_path = config_loader.get('server.webhook_path', '/webhook/qq')
    app.router.add_post(webhook_path, handle_qq_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config_loader.get('server.host', '0.0.0.0'), config_loader.get('server.qq_webhook_port', 8080))
    logger.info(f"QQ Webhook server started on port {config_loader.get('server.qq_webhook_port')}")
    await site.start()
    
    # 保持运行
    while True:
        await asyncio.sleep(3600)

async def cleanup_temp_files():
    """定时清理 /temp 目录下超过 24 小时的文件"""
    temp_dir = os.path.join(os.getcwd(), 'temp')
    while True:
        try:
            if os.path.exists(temp_dir):
                now = time.time()
                for fname in os.listdir(temp_dir):
                    fpath = os.path.join(temp_dir, fname)
                    if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > 86400:
                        os.remove(fpath)
                        logger.info(f"Cleaned up expired temp file: {fname}")
        except Exception as e:
            logger.error(f"Temp cleanup error: {e}")
        await asyncio.sleep(3600)

start_time = time.time()
restart_event = asyncio.Event()
background_tasks = []

REBOOT_INFO_FILE = "logs/.reboot_info"

async def graceful_restart(platform: str = 'qq'):
    """优雅重启：启动新进程后退出当前进程，实现无缝重启"""
    logger.info("正在触发优雅重启...")
    
    reboot_info = {
        "start_time": time.time() * 1000,
        "platform": platform
    }
    
    os.makedirs("logs", exist_ok=True)
    with open(REBOOT_INFO_FILE, 'w', encoding='utf-8') as f:
        json.dump(reboot_info, f)
    
    # 等待一小段时间确保文件写入完成
    await asyncio.sleep(0.5)
    
    # 尝试取消所有后台任务，让它们有机会清理
    for task in background_tasks:
        if not task.done():
            task.cancel()
    
    # 给任务一点时间取消
    await asyncio.sleep(0.5)
    
    try:
        await db.close()
    except Exception as e:
        logger.debug(f"数据库关闭（预期内）: {e}")
        
    logger.info("正在启动新进程...")
    
    env = os.environ.copy()
    env['TQSYNC_RESTARTED'] = '1'
    
    startup_info = None
    creation_flags = 0
    
    if sys.platform == 'win32':
        startup_info = subprocess.STARTUPINFO(
            dwFlags=subprocess.STARTF_USESHOWWINDOW,
            wShowWindow=subprocess.SW_SHOWNORMAL  # 显示窗口并激活
        )
        # CREATE_NEW_CONSOLE 创建新控制台窗口
        creation_flags = subprocess.CREATE_NEW_CONSOLE
    
    try:
        process = subprocess.Popen(
            [sys.executable] + sys.argv,
            env=env,
            startupinfo=startup_info,
            creationflags=creation_flags
        )
        logger.info(f"新进程已启动 (PID: {process.pid})，当前进程即将退出...")
        
        # Windows 下尝试将焦点切换到新进程窗口
        if sys.platform == 'win32':
            await asyncio.sleep(0.5)  # 等待窗口创建
            try:
                import ctypes
                # 尝试获取新进程的窗口句柄并激活
                user32 = ctypes.windll.user32
                # 枚举窗口找到我们的进程
                def enum_windows_callback(hwnd, lParam):
                    if user32.IsWindowVisible(hwnd):
                        pid = ctypes.c_ulong()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value == process.pid:
                            # 找到窗口，激活它
                            user32.SetForegroundWindow(hwnd)
                            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                            return False
                    return True
                
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                callback = WNDENUMPROC(enum_windows_callback)
                user32.EnumWindows(callback, 0)
            except Exception as e:
                logger.debug(f"切换窗口焦点失败（非致命）: {e}")
    except Exception as e:
        logger.error(f"启动新进程失败: {e}")
        return
    
    # 给一点时间让日志输出完成
    await asyncio.sleep(1.0)
    
    # 使用 os._exit 强制退出，避免 asyncio 的清理逻辑产生额外日志
    os._exit(0)

async def main():
    global start_time
    # 再次确认赋值，防止模块加载时的时序问题
    start_time = time.time()
    logger.info(f"系统启动时间戳: {start_time}")
    # 初始化数据库
    await db.init_db()
    
    # 初始化 Telegram Bot
    token = config_loader.get('telegram.bot_token')
    proxy_url = config_loader.get('telegram.proxy_url')
    
    # 配置请求超时时间，防止大文件获取时超时 (连接10s, 读取30s)
    request = HTTPXRequest(connection_pool_size=8, read_timeout=30.0, connect_timeout=10.0)
    
    builder = Application.builder().token(token).request(request)
    if proxy_url:
        logger.info(f"Using Telegram proxy: {proxy_url}")
        # 确保代理地址包含协议头，否则 PTB 可能会报错
        if not proxy_url.startswith(('http://', 'https://', 'socks5://')):
            proxy_url = f"http://{proxy_url}"
        builder.proxy_url(proxy_url).get_updates_proxy_url(proxy_url)
    else:
        logger.warning("未配置 Telegram 代理，国内服务器可能无法连接！")
    
    application = builder.build()
    
    # 初始化同步引擎 (单例模式)
    global_sync_engine = SyncEngine(application.bot)
    
    # 注册 TG 处理器
    for handler in get_tg_handlers():
        application.add_handler(handler)
    
    # 注册消息删除监听器 (PTB v21+ 自定义 Handler)
    from telegram.ext import BaseHandler
    class DeletedMessageHandler(BaseHandler):
        def __init__(self):
            super().__init__(callback=None) # PTB v21 requires a callback in init
        
        def check_update(self, update):
            return hasattr(update, 'deleted_message_ids') and update.deleted_message_ids
        
        async def handle_update(self, update, application, check_result, context):
            from handlers.tg_handler import handle_message_deleted
            await handle_message_deleted(update, context)

    application.add_handler(DeletedMessageHandler())
    
    # 启动 TG Polling
    await application.initialize()
    await application.start()
    updater_task = asyncio.create_task(application.updater.start_polling(drop_pending_updates=True))
    background_tasks.append(updater_task)
    
    # 启动 QQ Webhook
    webhook_task = asyncio.create_task(start_qq_webhook())
    background_tasks.append(webhook_task)
    
    # 启动 Admin API (使用 uvicorn 的 serve 方法在协程中运行)
    from fastapi.staticfiles import StaticFiles
    if os.path.exists("web"):
        admin_app.mount("/", StaticFiles(directory="web", html=True), name="web")
    
    config = uvicorn.Config(admin_app, host=config_loader.get('server.host', '0.0.0.0'), port=config_loader.get('server.admin_api_port', 8081), log_level="info")
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())
    background_tasks.append(api_task)
    
    # 启动临时文件清理任务
    cleanup_task = asyncio.create_task(cleanup_temp_files())
    background_tasks.append(cleanup_task)
    
    logger.info("TQSync is running...")
    
    engine = SyncEngine.get_instance()
    
    # 处理重启通知
    if os.path.exists(REBOOT_INFO_FILE):
        try:
            with open(REBOOT_INFO_FILE, 'r', encoding='utf-8') as f:
                reboot_info = json.load(f)
            os.remove(REBOOT_INFO_FILE)
            
            elapsed_ms = int(time.time() * 1000 - reboot_info['start_time'])
            platform = reboot_info.get('platform', 'qq')
            
            reboot_msg = f"✅ 重启完成\n⏱ 耗时: {elapsed_ms}ms"
            
            if platform == 'tg':
                await engine.bot.send_message(engine.tg_group_id, reboot_msg)
            else:
                await onebot_client.send_group_msg(engine.qq_group_id, reboot_msg)
                
            logger.info(f"重启完成，耗时 {elapsed_ms}ms")
        except Exception as e:
            logger.error(f"处理重启信息失败: {e}")
    
    await engine.send_startup_notification()
    
    # 等待重启信号或任务结束
    try:
        await restart_event.wait()
    except asyncio.CancelledError:
        # 这是预期的取消操作（重启过程中），静默忽略
        logger.debug("主循环被取消（预期内的重启行为）")
    except Exception as e:
        logger.error(f"主循环异常: {e}")
    finally:
        logger.info("TQSync 正在关闭...")
        # 确保数据库连接关闭
        try:
            await db.close()
        except Exception as e:
            logger.debug(f"数据库关闭（最终清理）: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
