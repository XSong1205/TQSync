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
from api.admin_api import app as admin_app

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
            
            # 构造 TG 的 HTML 消息以支持 @
            if at_tg_ids:
                display_name = await engine.get_display_name(qq_user_id=qq_id, fallback_name=nickname)
                html_text = f"[QQ] <b>{display_name}</b>: "
                for tid in at_tg_ids:
                    html_text += f"<a href='tg://user?id={tid}'>@User</a> "
                html_text += combined_text
                try:
                    result = await engine.bot.send_message(chat_id=engine.tg_group_id, text=html_text, parse_mode='HTML')
                    if result:
                        await db.save_message_mapping(
                            tg_message_id=result.message_id,
                            qq_message_id=data.get('message_id'),
                            sender_qq_id=qq_id
                        )
                except Exception as e:
                    logger.error(f"Failed to send HTML message to TG: {e}")
            elif image_url:
                await engine.forward_image_to_tg(qq_id, nickname, image_url, combined_text)
            elif video_url:
                await engine.forward_video_to_tg(qq_id, nickname, video_url, combined_text)
            elif file_url:
                await engine.forward_file_to_tg(qq_id, nickname, file_url, file_name)
            elif combined_text:
                result = await engine.forward_to_tg(qq_id, nickname, combined_text)
                if result:
                    await db.save_message_mapping(
                        tg_message_id=result.message_id,
                        qq_message_id=data.get('message_id'),
                        sender_qq_id=qq_id
                    )
        
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

async def main():
    # 初始化数据库
    await db.init_db()
    
    # 初始化 Telegram Bot
    token = config_loader.get('telegram.bot_token')
    proxy_url = config_loader.get('telegram.proxy_url')
    
    # 配置请求超时时间，防止大文件获取时超时 (连接5s, 读取10s)
    request = HTTPXRequest(connection_pool_size=8, read_timeout=10.0, connect_timeout=5.0)
    
    builder = Application.builder().token(token).request(request)
    if proxy_url:
        logger.info(f"Using Telegram proxy: {proxy_url}")
        builder.proxy_url(proxy_url).get_updates_proxy_url(proxy_url)
    
    application = builder.build()
    
    # 初始化同步引擎 (单例模式)
    global_sync_engine = SyncEngine(application.bot)
    
    # 注册 TG 处理器
    for handler in get_tg_handlers():
        application.add_handler(handler)
    
    # 启动 TG Polling
    await application.initialize()
    await application.start()
    updater_task = asyncio.create_task(application.updater.start_polling(drop_pending_updates=True))
    
    # 启动 QQ Webhook
    webhook_task = asyncio.create_task(start_qq_webhook())
    
    # 启动 Admin API (使用 uvicorn 的 serve 方法在协程中运行)
    config = uvicorn.Config(admin_app, host=config_loader.get('server.host', '0.0.0.0'), port=config_loader.get('server.admin_api_port', 8081), log_level="info")
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())
    
    # 启动临时文件清理任务
    cleanup_task = asyncio.create_task(cleanup_temp_files())
    
    logger.info("TQSync is running...")
    
    # 发送启动成功通知
    engine = SyncEngine.get_instance()
    await engine.send_startup_notification()
    
    # 等待所有任务
    await asyncio.gather(updater_task, webhook_task, api_task, cleanup_task)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
