from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from config.config_loader import config_loader
from core.sync_engine import sync_engine
from db.database import db

async def handle_tg_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id != config_loader.get('telegram.group_id'):
        return
    
    user = update.effective_user
    text = update.message.text
    
    await sync_engine.forward_to_qq(user.id, user.username or str(user.id), text)

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
