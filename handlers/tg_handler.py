from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from config.config_loader import config_loader
from core.sync_engine import SyncEngine
from db.database import db

async def handle_tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != config_loader.get('telegram.group_id'):
        return
    
    user = update.effective_user
    engine = SyncEngine.get_instance()
    
    # 处理图片消息
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await engine.forward_image_to_qq(user.id, user.username or str(user.id), file_id)
        return

    # 处理视频消息
    if update.message.video:
        file_id = update.message.video.file_id
        await engine.forward_video_to_qq(user.id, user.username or str(user.id), file_id)
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
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tg_message),
        CommandHandler('bind', handle_bind_command)
    ]
