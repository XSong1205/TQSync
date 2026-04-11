from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from config.config_loader import config_loader
from core.sync_engine import SyncEngine
from db.database import db
from handlers.qq_handler import onebot_client
from handlers.command_handler import handle_setprefix_command as handle_setprefix_command_logic, handle_help_command as handle_help_command_logic, handle_status_command
import time
from utils.logger import logger

async def handle_message_deleted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 Telegram 消息删除事件，同步撤回到 QQ"""
    logger.info(f"收到 Telegram 删除消息事件: {update}")
    
    # PTB v21+ 中，deleted_message_ids 位于 update.channel_post 或 update.message 之外，直接在 update 对象上
    deleted_ids = getattr(update, 'deleted_message_ids', [])
    
    if not deleted_ids:
        logger.warning("更新中未找到 deleted_message_ids")
        return

    # 检查聊天 ID (优先使用 effective_chat)
    chat_id = None
    if update.effective_chat:
        chat_id = update.effective_chat.id
    elif hasattr(update, 'chat'):
        chat_id = update.chat.id
    
    if chat_id != config_loader.get('telegram.group_id'):
        logger.warning(f"群组 ID 不匹配: {chat_id} vs {config_loader.get('telegram.group_id')}")
        return
    
    for msg_id in deleted_ids:
        logger.info(f"正在处理 TG 消息撤回 (ID: {msg_id})")
        qq_msg_id = await db.get_qq_msg_id_by_tg(msg_id)
        if qq_msg_id:
            try:
                await onebot_client.delete_msg(qq_msg_id)
                logger.info(f"已同步撤回：TG (ID: {msg_id}) -> QQ (ID: {qq_msg_id})")
                await db.delete_mapping_by_tg(msg_id)
            except Exception as e:
                logger.error(f"在 QQ 端执行撤回失败: {e}")
        else:
            logger.warning(f"未找到 TG 消息 ID {msg_id} 对应的 QQ 映射记录")

async def handle_tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != config_loader.get('telegram.group_id'):
        return
    
    user = update.effective_user
    # 忽略 Bot 自身的消息，防止同步循环
    if user.is_bot:
        return
    
    engine = SyncEngine.get_instance()
    msg = update.message
    
    # 诊断日志：打印媒体类型
    logger.debug(f"收到 TG 消息 - 图片: {bool(msg.photo)}, 视频: {bool(msg.video)}, 文件: {bool(msg.document)}")

    # 解析回复逻辑 (TG -> QQ)
    reply_segment = []
    if msg.reply_to_message:
        original_tg_id = msg.reply_to_message.message_id
        original_qq_id = await db.get_qq_msg_id_by_tg(original_tg_id)
        if original_qq_id:
            reply_segment.append({"type": "reply", "data": {"id": str(original_qq_id)}})
            logger.info(f"检测到 TG 回复，映射到 QQ 消息 ID: {original_qq_id}")

    # 处理图片消息
    if msg.photo:
        file_id = msg.photo[-1].file_id
        caption = msg.caption or ""
        logger.info(f"检测到来自 {user.username} 的图片，已加入异步同步队列")
        engine.enqueue_sync_task(engine.forward_image_to_qq, user.id, user.username or str(user.id), file_id, caption)
        return

    # 处理视频消息 (优先于 document 判断)
    if msg.video:
        file_id = msg.video.file_id
        logger.info(f"检测到来自 {user.username} 的视频，已加入异步同步队列")
        engine.enqueue_sync_task(engine.forward_video_to_qq, user.id, user.username or str(user.id), file_id)
        return

    # 处理通用文件 (包括 GIF/Animation)
    if msg.document:
        file_id = msg.document.file_id
        filename = msg.document.file_name or f"file_{uuid.uuid4().hex[:8]}.dat"
        logger.info(f"检测到来自 {user.username} 的文件 ({filename})，已加入异步同步队列")
        engine.enqueue_sync_task(engine.forward_file_to_qq, user.id, user.username or str(user.id), file_id, filename)
        return

    # 处理贴纸消息 (Sticker)
    if msg.sticker:
        file_id = msg.sticker.file_id
        is_animated = msg.sticker.is_animated or msg.sticker.is_video
        logger.info(f"检测到来自 {user.username} 的贴纸 (动态: {is_animated})，已加入异步同步队列")
        engine.enqueue_sync_task(engine.forward_sticker_to_qq, user.id, user.username or str(user.id), file_id, is_animated)
        return

    # 处理语音消息 (Voice/Audio)
    if msg.voice or msg.audio:
        file_id = (msg.voice or msg.audio).file_id
        logger.info(f"检测到来自 {user.username} 的语音消息，已加入异步同步队列")
        engine.enqueue_sync_task(engine.forward_voice_to_qq, user.id, user.username or str(user.id), file_id)
        return

    # 处理文本消息
    text = update.message.text
    if text:
        logger.info(f"检测到来自 {user.username} 的文本消息，已加入异步同步队列")
        engine.enqueue_sync_task(engine.forward_to_qq, user.id, user.username or str(user.id), text)
        return

async def handle_setprefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setprefix <nickname>")
        return
    
    tg_user = update.effective_user
    response = await handle_setprefix_command_logic(tg_user.id, 'tg', context.args)
    await update.message.reply_text(response)

async def handle_status_command_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from main import GLOBAL_START_TIME
    # 增加合理性检查，防止显示异常时长
    if GLOBAL_START_TIME < 1704067200: 
        response = "系统时间记录异常，请尝试重启机器人。"
    else:
        response = await handle_status_command(GLOBAL_START_TIME)
    await update.message.reply_text(response)

async def handle_reboot_command_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    from main import graceful_restart
    from config.config_loader import config_loader
    
    admin_ids = config_loader.get('server.admin_user_ids', [])
    user_id = update.effective_user.id
    
    if admin_ids and user_id not in admin_ids:
        await update.message.reply_text("⛔ 权限不足：仅管理员可执行重启操作")
        return
        
    await update.message.reply_text("🔄 正在执行优雅重启，服务将在数秒后恢复...")
    asyncio.create_task(graceful_restart())

async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = await handle_help_command_logic()
    await update.message.reply_text(response)

async def handle_bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /bind <qq_number>")
        return
    
    qq_number = int(context.args[0])
    tg_user = update.effective_user
    
    # 简单绑定逻辑：直接建立映射
    await db.add_binding(tg_user.id, qq_number, tg_user.username)
    await update.message.reply_text(f"Successfully bound to QQ: {qq_number}")

def get_tg_handlers():
    return [
        # 使用 filters.ALL 接收所有消息，然后在 handle_tg_message 内部进行类型判断
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_tg_message),
        CommandHandler('bind', handle_bind_command),
        CommandHandler('setprefix', handle_setprefix_command),
        CommandHandler('help', handle_help_command),
        CommandHandler('status', handle_status_command_tg),
        CommandHandler('reboot', handle_reboot_command_tg)
    ]
