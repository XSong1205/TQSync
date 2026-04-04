from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from config.config_loader import config_loader
from core.sync_engine import SyncEngine
from db.database import db
from handlers.qq_handler import onebot_client
import logging

logger = logging.getLogger(__name__)

async def handle_message_deleted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 Telegram 消息删除事件，同步撤回到 QQ"""
    logger.info(f"Received deleted message update: {update}")
    
    # PTB v21+ 中，deleted_message_ids 位于 update.channel_post 或 update.message 之外，直接在 update 对象上
    deleted_ids = getattr(update, 'deleted_message_ids', [])
    
    if not deleted_ids:
        return

    # 检查聊天 ID (PTB v21 中可能在 update.chat 或通过其他方式获取)
    chat_id = None
    if hasattr(update, 'chat'):
        chat_id = update.chat.id
    elif hasattr(update, 'channel_post') and update.channel_post:
        chat_id = update.channel_post.chat.id
    
    if chat_id != config_loader.get('telegram.group_id'):
        return
    
    for msg_id in deleted_ids:
        logger.info(f"Processing deletion for TG msg_id: {msg_id}")
        qq_msg_id = await db.get_qq_msg_id_by_tg(msg_id)
        if qq_msg_id:
            try:
                await onebot_client.delete_msg(qq_msg_id)
                logger.info(f"Synced deletion from TG (msg_id: {msg_id}) to QQ (msg_id: {qq_msg_id})")
                await db.delete_mapping_by_tg(msg_id)
            except Exception as e:
                logger.error(f"Failed to delete message in QQ: {e}")
        else:
            logger.warning(f"No mapping found for TG msg_id: {msg_id}")

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
            # 解析 @ (Mention) 实体
            message_array = []
            last_offset = 0
            entities = update.message.entities or []
            
            for entity in entities:
                if entity.type in ['mention', 'text_mention']:
                    # 提取 mention 之前的文本
                    if entity.offset > last_offset:
                        message_array.append({"type": "text", "data": {"text": text[last_offset:entity.offset]}})
                    
                    # 处理 @ 逻辑
                    target_tg_id = None
                    if entity.type == 'text_mention':
                        target_tg_id = entity.user.id
                    elif entity.type == 'mention':
                        # 简单处理：这里需要根据 mention 的名字去查 TG ID，比较复杂，先简化为纯文本
                        pass 

                    if target_tg_id:
                        binding = await db.get_binding_by_tg(target_tg_id)
                        if binding:
                            message_array.append({"type": "at", "data": {"qq": binding[1]}})
                        else:
                            message_array.append({"type": "text", "data": {"text": text[entity.offset:entity.offset+entity.length]}})
                    else:
                        message_array.append({"type": "text", "data": {"text": text[entity.offset:entity.offset+entity.length]}})
                    
                    last_offset = entity.offset + entity.length

            # 添加剩余文本
            if last_offset < len(text):
                message_array.append({"type": "text", "data": {"text": text[last_offset:]}})
            
            if not message_array:
                message_array.append({"type": "text", "data": {"text": text}})

            display_name = await engine.get_display_name(tg_user_id=user.id, fallback_name=user.username or str(user.id))
            final_message = [{"type": "text", "data": {"text": f"[TG] {display_name}: "}}] + message_array
            
            result = await onebot_client.send_group_msg(engine.qq_group_id, final_message)
            # 存储映射关系（如果是纯文本）
            if result and result.get('data', {}).get('message_id'):
                await db.save_message_mapping(
                    tg_message_id=update.message.message_id,
                    qq_message_id=result['data']['message_id'],
                    sender_tg_id=user.id
                )
        except RuntimeError as e:
            print(f"Error: {e}")

async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 TQSync 帮助文档\n\n"
        "可用命令：\n"
        "/bind <qq_number> - 绑定您的 QQ 号以启用同步\n"
        "/setprefix <nickname> - 设置您在双端显示的统一昵称\n"
        "/help - 显示此帮助信息\n\n"
        "提示：绑定后，您在 Telegram 和 QQ 的消息将自动双向同步。"
    )
    await update.message.reply_text(help_text)

async def handle_setprefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setprefix <nickname>")
        return
    
    new_prefix = " ".join(context.args)
    tg_user = update.effective_user
    binding = await db.get_binding_by_tg(tg_user.id)
    
    if not binding:
        await update.message.reply_text("You are not bound to a QQ account yet. Use /bind first.")
        return
    
    uid = binding[4]
    await db.update_custom_prefix(uid, new_prefix)
    await update.message.reply_text(f"Your unified display name has been updated to: {new_prefix}")

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
        CommandHandler('help', handle_help_command)
    ]
