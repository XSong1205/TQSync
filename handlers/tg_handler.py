from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from config.config_loader import config_loader
from core.sync_engine import SyncEngine
from db.database import db
import logging

logger = logging.getLogger(__name__)

async def handle_tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != config_loader.get('telegram.group_id'):
        return
    
    user = update.effective_user
    engine = SyncEngine.get_instance()
    msg = update.message
    
    # 诊断日志：打印媒体类型
    logger.info(f"Received TG message - Photo: {bool(msg.photo)}, Video: {bool(msg.video)}, Doc: {bool(msg.document)}, Anim: {bool(msg.animation)}, Voice: {bool(msg.voice)}")

    # 处理图片消息
    if msg.photo:
        file_id = msg.photo[-1].file_id
        caption = msg.caption or ""
        await engine.forward_image_to_qq(user.id, user.username or str(user.id), file_id, caption)
        return

    # 处理视频消息 (优先于 document 判断)
    if msg.video:
        file_id = msg.video.file_id
        logger.info(f"Detected video from {user.username}, forwarding to QQ...")
        await engine.forward_video_to_qq(user.id, user.username or str(user.id), file_id)
        return

    # 处理通用文件
    if msg.document:
        file_id = msg.document.file_id
        filename = msg.document.file_name or "unknown_file"
        await engine.forward_file_to_qq(user.id, user.username or str(user.id), file_id, filename)
        return

    # 处理文本消息
    text = update.message.text
    if text:
        try:
            await engine.forward_to_qq(user.id, user.username or str(user.id), text)
        except RuntimeError as e:
            print(f"Error: {e}")

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
        CommandHandler('bind', handle_bind_command)
    ]
