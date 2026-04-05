import asyncio
import logging
import os
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from aiohttp import web
import uvicorn

from config.config_loader import config_loader
from db.database import db
from core.sync_engine import SyncEngine
from handlers.tg_handler import get_tg_handlers
from handlers.command_handler import handle_bind_command, handle_setprefix_command, handle_help_command, handle_status_command
from handlers.qq_handler import onebot_client
from api.admin_api import app as admin_app

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
            return web.Response(text="ok")

        # 仅处理群消息
        if data.get('message_type') == 'group':
            # [新增] 校验群组 ID，防止同步非目标群组的消息
            target_group_id = config_loader.get('qq.group_id')
            if data.get('group_id') != target_group_id:
                logger.debug(f"忽略非目标群组消息: {data.get('group_id')}")
                return web.Response(text="ok")
            
            sender = data.get('sender', {})
            qq_id = data['user_id']
            nickname = sender.get('card') or sender.get('nickname') or str(qq_id)
            
            engine = SyncEngine.get_instance()
            
            # 处理消息段数组 (OneBot v11)
            message_array = data.get('message', [])
            text_parts = []
            image_url = None
            video_url = None
            file_url = None
            file_name = "unknown_file"
            at_tg_ids = []
            
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
            
            combined_text = "".join(text_parts).strip()
            
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
                    response = await handle_status_command(start_time)
                else:
                    response = "Unknown command. Use /help for more info."
                
                if response:
                    await onebot_client.send_group_msg(engine.qq_group_id, response)
                return web.Response(text="ok")

            # 解析回复逻辑 (QQ -> TG)
            reply_to_tg_id = None
            for msg_part in message_array:
                if msg_part.get('type') == 'reply':
                    original_qq_id = int(msg_part['data'].get('id', 0))
                    if original_qq_id:
                        reply_to_tg_id = await db.get_tg_msg_id_by_qq(original_qq_id)
                        if reply_to_tg_id:
                            logger.info(f"检测到 QQ 回复，映射到 TG 消息 ID: {reply_to_tg_id}")
                        break
            
            combined_text = "".join(text_parts).strip()
            
            # 构造 TG 的 HTML 消息以支持 @
            if at_tg_ids:
                display_name = await engine.get_display_name(qq_user_id=qq_id, fallback_name=nickname)
                html_text = f"[QQ] <b>{display_name}</b>: "
                for tid in at_tg_ids:
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
                try:
                    await engine.forward_image_to_tg(qq_id, nickname, image_url, combined_text, reply_to_message_id=reply_to_tg_id)
                except Exception as e:
                    logger.error(f"同步图片至 Telegram 失败: {e}")
                    error_msg = [{"type": "text", "data": {"text": f"❌ 同步到 Telegram 失败: {str(e)[:30]}"}}, 
                                 {"type": "reply", "data": {"id": str(data.get('message_id'))}}]
                    await onebot_client.send_group_msg(engine.qq_group_id, error_msg)
            elif video_url:
                try:
                    await engine.forward_video_to_tg(qq_id, nickname, video_url, combined_text, reply_to_message_id=reply_to_tg_id)
                except Exception as e:
                    logger.error(f"同步视频至 Telegram 失败: {e}")
                    error_msg = [{"type": "text", "data": {"text": f"❌ 同步到 Telegram 失败: {str(e)[:30]}"}}, 
                                 {"type": "reply", "data": {"id": str(data.get('message_id'))}}]
                    await onebot_client.send_group_msg(engine.qq_group_id, error_msg)
            elif file_url:
                try:
                    await engine.forward_file_to_tg(qq_id, nickname, file_url, file_name, reply_to_message_id=reply_to_tg_id)
                except Exception as e:
                    logger.error(f"同步文件至 Telegram 失败: {e}")
                    error_msg = [{"type": "text", "data": {"text": f"❌ 同步到 Telegram 失败: {str(e)[:30]}"}}, 
                                 {"type": "reply", "data": {"id": str(data.get('message_id'))}}]
                    await onebot_client.send_group_msg(engine.qq_group_id, error_msg)
            elif combined_text:
                try:
                    result = await engine.forward_to_tg(qq_id, nickname, combined_text, reply_to_message_id=reply_to_tg_id)
                    if result:
                        await db.save_message_mapping(
                            tg_message_id=result.message_id,
                            qq_message_id=data.get('message_id'),
                            sender_qq_id=qq_id
                        )
                except Exception as e:
                    logger.error(f"同步文本至 Telegram 失败: {e}")
                    error_msg = [{"type": "text", "data": {"text": f"❌ 同步到 Telegram 失败: {str(e)[:30]}"}}, 
                                 {"type": "reply", "data": {"id": str(data.get('message_id'))}}]
                    await onebot_client.send_group_msg(engine.qq_group_id, error_msg)
        
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

start_time = 0.0
restart_event = asyncio.Event()
background_tasks = []

async def graceful_restart():
    """优雅重启：取消所有后台任务并重新加载进程"""
    logger.info("正在触发优雅重启...")
    restart_event.set()
    for task in background_tasks:
        task.cancel()
    # 等待一小段时间让任务清理资源
    await asyncio.sleep(1)
    os.execv(sys.executable, ['python'] + sys.argv)

async def main():
    global start_time
    start_time = time.time()
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
    
    # 发送启动成功通知
    engine = SyncEngine.get_instance()
    await engine.send_startup_notification()
    
    # 等待重启信号或任务结束
    try:
        await restart_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("TQSync 正在关闭...")
        # 确保数据库连接关闭
        await db.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
