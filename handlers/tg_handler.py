from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from config.config_loader import config_loader
from core.sync_engine import SyncEngine
from db.database import db
from handlers.qq_handler import onebot_client
from handlers.command_handler import handle_setprefix_command as handle_setprefix_command_logic, handle_help_command as handle_help_command_logic, handle_status_command, handle_checkupdate_command, handle_reboot_command as handle_reboot_command_logic, handle_blockword_command as handle_blockword_command_logic, handle_unblockword_command as handle_unblockword_command_logic, handle_blockwords_command as handle_blockwords_command_logic
from core.plugin_manager import PluginManager
import uuid
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
            logger.info(f"[TG] 映射回复消息至 {original_qq_id}")

    # 处理图片消息
    if msg.photo:
        file_id = msg.photo[-1].file_id
        caption = msg.caption or ""
        if caption:
            blocked_word = await db.check_blocked_word_in_text(caption.strip())
            if blocked_word:
                logger.info(f"[屏蔽] TG用户 {user.id}(@{user.username}) 的消息被拦截 (关键词: {blocked_word})")
                return
        logger.info(f"[TG] {user.username} 发送了一张图片")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user.id,
            user.username or str(user.id), file_id,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理视频消息 (优先于 document 判断)
    if msg.video:
        file_id = msg.video.file_id
        file_name = msg.video.file_name or f'video_{uuid.uuid4().hex[:8]}.mp4'
        logger.info(f"[TG] {user.username} 发送了一个视频")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user.id,
            user.username or str(user.id), file_id,
            file_name=file_name, file_size=msg.video.file_size or 0,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理通用文件
    if msg.document:
        file_id = msg.document.file_id
        filename = msg.document.file_name or f"file_{uuid.uuid4().hex[:8]}.dat"
        logger.info(f"[TG] {user.username} 发送了一个文件 ({filename})")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user.id,
            user.username or str(user.id), file_id,
            file_name=filename, file_size=msg.document.file_size or 0,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理贴纸消息 (Sticker)
    if msg.sticker:
        file_id = msg.sticker.file_id
        is_animated = msg.sticker.is_animated or msg.sticker.is_video
        logger.info(f"[TG] {user.username} 发送了一个贴纸 (动态: {is_animated})")
        engine.enqueue_sync_task(engine.forward_sticker_to_qq, user.id, user.username or str(user.id), file_id, is_animated, reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理语音消息 (Voice) - 仅限 Telegram 的语音消息
    if msg.voice:
        file_id = msg.voice.file_id
        logger.info(f"[TG] {user.username} 发送了一个语音消息")
        engine.enqueue_sync_task(engine.forward_voice_to_qq, user.id, user.username or str(user.id), file_id, reply_segment=reply_segment, tg_message_id=msg.message_id)
        return
    
    # 处理音频文件 (Audio) - 如 .flac, .mp3, .wav 等，作为通用文件发送
    if msg.audio:
        file_id = msg.audio.file_id
        filename = msg.audio.file_name or f"audio_{msg.audio.file_unique_id}.mp3"
        logger.info(f"[TG] {user.username} 发送了一个文件: {filename}")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user.id,
            user.username or str(user.id), file_id,
            file_name=filename, file_size=msg.audio.file_size or 0,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理文本消息
    text = update.message.text
    if text:
        blocked_word = await db.check_blocked_word_in_text(text.strip())
        if blocked_word:
            logger.info(f"[屏蔽] TG用户 {user.id}(@{user.username}) 的消息被拦截 (关键词: {blocked_word})")
            return

        pm = PluginManager.get_instance()
        if await pm.route_message('tg', user.id, engine.tg_group_id, text.strip()):
            return

        logger.info(f"[TG] {user.username} 发送了一条文本消息")
        engine.enqueue_sync_task(engine.forward_to_qq, user.id, user.username or str(user.id), text, reply_segment=reply_segment, tg_message_id=msg.message_id)
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
        response = "运行时间计算异常，请尝试重启机器人"
    else:
        response = await handle_status_command(GLOBAL_START_TIME)
    await update.message.reply_text(response)

async def handle_reboot_command_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    from main import graceful_restart
    
    admin_ids = config_loader.get('server.admin_user_ids', [])
    user_id = update.effective_user.id
    
    if admin_ids and user_id not in admin_ids:
        await update.message.reply_text("您的权限不足以执行此操作")
        return
        
    response = await handle_reboot_command_logic('tg')
    await update.message.reply_text(response)
    asyncio.create_task(graceful_restart('tg'))


async def handle_checkupdate_command_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    from main import graceful_restart
    from config.config_loader import config_loader

    admin_ids = config_loader.get('server.admin_user_ids', [])
    user_id = update.effective_user.id

    if admin_ids and user_id not in admin_ids:
        await update.message.reply_text("您的权限不足以执行此操作")
        return

    status_msg = await update.message.reply_text("🔍 正在检查更新...")
    info = await handle_checkupdate_command()

    if info.get("update_found") and info.get("update_notice"):
        await update.message.reply_text(info["update_notice"])
        await asyncio.sleep(1)

    try:
        await status_msg.edit_text(info["result"])
    except Exception:
        pass

    if info.get("need_restart"):
        await asyncio.sleep(2)
        asyncio.create_task(graceful_restart('tg'))

async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = await handle_help_command_logic()
    await update.message.reply_text(response)

async def handle_bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 TG 端的 /bind <验证码> 指令"""
    if not context.args:
        await update.message.reply_text(
            "请使用验证码完成绑定：\n"
            "1. 在 QQ 群中发送 /bind 获取验证码\n"
            "2. 在 Telegram 中使用 /bind <验证码>"
        )
        return
    
    verification_code = context.args[0]
    tg_user = update.effective_user
    
    # 调用验证逻辑
    result = await db.verify_and_consume_code(verification_code)
    
    if not result['valid']:
        await update.message.reply_text(f"绑定失败: {result['reason']}")
        return
    
    qq_user_id = result['qq_user_id']
    
    # 检查是否已被其他 TG 用户绑定
    existing_binding = await db.get_binding_by_qq(qq_user_id)
    if existing_binding and existing_binding[0] != tg_user.id:
        await update.message.reply_text("该 QQ 号已被其他用户绑定，请勿尝试重复绑定")
        return
    
    # 建立绑定关系
    await db.add_binding(tg_user.id, qq_user_id, tg_user.username)
    
    # 通知 TG 用户
    await update.message.reply_text(
        f"✅ 绑定成功！\n"
        f"QQ: {qq_user_id}\n"
        f"Telegram: @{tg_user.username or tg_user.id}\n"
        f"现在您的消息将更好地双向同步。"
    )
    
    # 通知 QQ 用户（通过私聊或群消息@）
    try:
        from handlers.qq_handler import onebot_client
        from core.sync_engine import SyncEngine
        engine = SyncEngine.get_instance()
        
        notify_msg = f"✅ 您的 QQ 已成功绑定到 Telegram (@{tg_user.username or tg_user.id})"
        await onebot_client.send_private_msg(qq_user_id, notify_msg)
    except Exception as e:
        logger.warning(f"无法发送 QQ 绑定成功通知: {e}")
        # 降级：在群内@用户
        try:
            await onebot_client.send_group_msg(engine.qq_group_id, [
                {"type": "at", "data": {"qq": str(qq_user_id)}},
                {"type": "text", "data": {"text": f" 您的 QQ 已成功绑定到 Telegram"}}
            ])
        except:
            pass

async def handle_confirm_ffmpeg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /confirm 指令，触发 FFmpeg 自动下载"""
    from utils.ffmpeg_manager import ffmpeg_manager
    
    status = await db.get_setting('ffmpeg_auto_download_confirmed')
    if status == 'confirmed':
        await update.message.reply_text("您已经确认过自动下载，无需重复操作。")
        return

    msg = await update.message.reply_text("正在开始下载并安装 FFmpeg")
    
    async def progress(percent):
        try:
            await msg.edit_text(f"正在下载 FFmpeg... {percent}%")
        except:
            pass

    success = await ffmpeg_manager.download_and_install(progress_callback=progress)
    
    if success:
        await db.set_setting('ffmpeg_auto_download_confirmed', 'confirmed')
        await msg.edit_text("FFmpeg 自动下载并安装成功！现在您可以使用动态贴纸和语音同步功能了。")
    else:
        await msg.edit_text("FFmpeg 下载失败，请检查网络连接或尝试手动安装。")

async def handle_cancel_ffmpeg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /cancel 指令，取消 FFmpeg 自动下载提示"""
    await db.set_setting('ffmpeg_auto_download_confirmed', 'cancelled')
    await update.message.reply_text("已取消自动下载。如果您以后需要，可以手动安装 FFmpeg。")

async def handle_blockword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /blockword <关键词> (管理员)"""
    admin_ids = config_loader.get('server.admin_user_ids', [])
    user_id = update.effective_user.id
    if admin_ids and user_id not in admin_ids:
        await update.message.reply_text("您的权限不足以执行此操作")
        return
    response = await handle_blockword_command_logic(context.args or [], user_id, 'tg')
    await update.message.reply_text(response)

async def handle_unblockword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /unblockword <关键词> (管理员)"""
    admin_ids = config_loader.get('server.admin_user_ids', [])
    user_id = update.effective_user.id
    if admin_ids and user_id not in admin_ids:
        await update.message.reply_text("您的权限不足以执行此操作")
        return
    response = await handle_unblockword_command_logic(context.args or [], user_id, 'tg')
    await update.message.reply_text(response)

async def handle_blockwords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /blockwords (查看屏蔽词列表)"""
    response = await handle_blockwords_command_logic()
    await update.message.reply_text(response)

async def handle_unhandled_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """路由未被前置 CommandHandler 处理的 /command 到插件系统"""
    user = update.effective_user
    if user.is_bot:
        return

    text = update.message.text
    if not text:
        return

    chat = update.effective_chat
    is_group = chat and chat.id == config_loader.get('telegram.group_id')
    
    # 群聊：所有人都可使用插件命令
    # 私聊：仅管理员可使用插件命令
    if is_group:
        pass
    else:
        admin_ids = config_loader.get('server.admin_user_ids', [])
        if not admin_ids or user.id not in admin_ids:
            return

    engine = SyncEngine.get_instance()
    pm = PluginManager.get_instance()
    if await pm.route_message('tg', user.id, engine.tg_group_id, text.strip()):
        return

    await update.message.reply_text('Unknown command. Type "/help" for help. ')

def get_tg_handlers():
    return [
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_tg_message),
        CommandHandler('bind', handle_bind_command),
        CommandHandler('setprefix', handle_setprefix_command),
        CommandHandler('help', handle_help_command),
        CommandHandler('status', handle_status_command_tg),
        CommandHandler('reboot', handle_reboot_command_tg),
        CommandHandler('checkupdate', handle_checkupdate_command_tg),
        CommandHandler('confirm', handle_confirm_ffmpeg),
        CommandHandler('cancel', handle_cancel_ffmpeg),
        CommandHandler('blockword', handle_blockword_command),
        CommandHandler('unblockword', handle_unblockword_command),
        CommandHandler('blockwords', handle_blockwords_command),
        MessageHandler(filters.COMMAND, handle_unhandled_command),
    ]
