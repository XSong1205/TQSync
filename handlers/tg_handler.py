from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
try:
    # 表情回应 handler 需要 PTB >= 21.2；低版本降级为不注册，其它功能不受影响
    from telegram.ext import MessageReactionHandler
except ImportError:  # pragma: no cover
    MessageReactionHandler = None
from config.config_loader import config_loader
from core.sync_engine import SyncEngine
from db.database import db
from handlers.qq_handler import onebot_client
from handlers.command_handler import handle_setprefix_command as handle_setprefix_command_logic, handle_help_command as handle_help_command_logic, handle_status_command, handle_update_command, handle_checkupdate_command, handle_reboot_command as handle_reboot_command_logic, handle_blockword_command as handle_blockword_command_logic, handle_unblockword_command as handle_unblockword_command_logic, handle_blockwords_command as handle_blockwords_command_logic, handle_webui_command as handle_webui_command_logic
from core.plugin_manager import PluginManager
from utils.qq_text import tg_emoji_to_qq_emoji_id
import uuid
from utils.logger import logger
from utils.auth import is_admin

async def handle_message_deleted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 Telegram 消息删除事件，同步撤回到 QQ"""
    # PTB v21+ 中，deleted_message_ids 位于 update.channel_post 或 update.message 之外，直接在 update 对象上
    deleted_ids = getattr(update, 'deleted_message_ids', [])
    
    if not deleted_ids:
        logger.debug("更新中未找到 deleted_message_ids")
        return

    logger.info(f"收到 Telegram 消息撤回事件 (IDs: {deleted_ids})")

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

    msg = update.message
    if not msg:
        return

    user = update.effective_user
    # 忽略 Bot 自身的消息，防止同步循环
    if user and user.is_bot:
        return

    if user:
        user_id = user.id
        username = user.username or str(user.id)
        sender_name = user.username or f"{user.first_name or ''} {user.last_name or ''}".strip() or str(user.id)
    elif msg.sender_chat:
        user_id = msg.sender_chat.id
        username = msg.sender_chat.username or msg.sender_chat.title or str(msg.sender_chat.id)
        sender_name = msg.sender_chat.title or str(msg.sender_chat.id)
    else:
        return
    
    engine = SyncEngine.get_instance()
    
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
                logger.info(f"[屏蔽] TG用户 {user_id}(@{username}) 的消息被拦截 (关键词: {blocked_word})")
                return
        caption_hint = f" ({caption[:30]})" if caption else ""
        logger.info(f"[TG] {sender_name}: [图片]{caption_hint}")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user_id,
            username, file_id,
            caption=caption,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理视频消息 (优先于 document 判断)
    if msg.video:
        file_id = msg.video.file_id
        file_name = msg.video.file_name or f'video_{uuid.uuid4().hex[:8]}.mp4'
        caption = msg.caption or ""
        if caption:
            blocked_word = await db.check_blocked_word_in_text(caption.strip())
            if blocked_word:
                logger.info(f"[屏蔽] TG用户 {user_id}(@{username}) 的消息被拦截 (关键词: {blocked_word})")
                return
        caption_hint = f" ({caption[:30]})" if caption else ""
        logger.info(f"[TG] {sender_name}: [视频: {file_name}]{caption_hint}")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user_id,
            username, file_id,
            file_name=file_name, file_size=msg.video.file_size or 0,
            caption=caption,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理通用文件
    if msg.document:
        file_id = msg.document.file_id
        filename = msg.document.file_name or f"file_{uuid.uuid4().hex[:8]}.dat"
        caption = msg.caption or ""
        if caption:
            blocked_word = await db.check_blocked_word_in_text(caption.strip())
            if blocked_word:
                logger.info(f"[屏蔽] TG用户 {user_id}(@{username}) 的消息被拦截 (关键词: {blocked_word})")
                return
        caption_hint = f" ({caption[:30]})" if caption else ""
        logger.info(f"[TG] {sender_name}: [文件: {filename}]{caption_hint}")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user_id,
            username, file_id,
            file_name=filename, file_size=msg.document.file_size or 0,
            caption=caption,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理贴纸消息 (Sticker)
    if msg.sticker:
        file_id = msg.sticker.file_id
        is_animated = msg.sticker.is_animated or msg.sticker.is_video
        logger.info(f"[TG] {sender_name}: [贴纸{'(动态)' if is_animated else ''}]")
        engine.enqueue_sync_task(engine.forward_sticker_to_qq, user_id, username, file_id, is_animated, reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理语音消息 (Voice) - 仅限 Telegram 的语音消息
    if msg.voice:
        file_id = msg.voice.file_id
        logger.info(f"[TG] {sender_name}: [语音消息]")
        engine.enqueue_sync_task(engine.forward_voice_to_qq, user_id, username, file_id, reply_segment=reply_segment, tg_message_id=msg.message_id)
        return
    
    # 处理音频文件 (Audio) - 如 .flac, .mp3, .wav 等，作为通用文件发送
    if msg.audio:
        file_id = msg.audio.file_id
        filename = msg.audio.file_name or f"audio_{msg.audio.file_unique_id}.mp3"
        logger.info(f"[TG] {sender_name}: [音频: {filename}]")
        engine.enqueue_sync_task(engine.forward_media_to_qq, user_id,
            username, file_id,
            file_name=filename, file_size=msg.audio.file_size or 0,
            reply_segment=reply_segment, tg_message_id=msg.message_id)
        return

    # 处理文本消息
    text = msg.text
    if text:
        blocked_word = await db.check_blocked_word_in_text(text.strip())
        if blocked_word:
            logger.info(f"[屏蔽] TG用户 {user_id}(@{username}) 的消息被拦截 (关键词: {blocked_word})")
            return

        pm = PluginManager.get_instance()
        if await pm.route_message('tg', user_id, engine.tg_group_id, text.strip()):
            return

        text_preview = (text[:60] + '...') if len(text) > 60 else text
        text_preview = text_preview.replace('\n', ' ')
        logger.info(f"[TG] {sender_name}: {text_preview}")
        engine.enqueue_sync_task(engine.forward_to_qq, user_id, username, text,
            reply_segment=reply_segment, tg_message_id=msg.message_id,
            entities=msg.entities)
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
    
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("您的权限不足以执行此操作")
        return
        
    response = await handle_reboot_command_logic('tg')
    await update.message.reply_text(response)
    asyncio.create_task(graceful_restart('tg'))


async def handle_update_command_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio
    from main import graceful_restart
    from config.config_loader import config_loader

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("您的权限不足以执行此操作")
        return

    status_msg = await update.message.reply_text("🔍 正在检查并更新...")
    info = await handle_update_command()

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

handle_checkupdate_command_tg = handle_update_command_tg


async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = await handle_help_command_logic()
    await update.message.reply_text(response)

async def handle_webui_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = await handle_webui_command_logic()
    await update.message.reply_text(f"WebUI 管理面板地址:\n{url}")

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
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("您的权限不足以执行此操作")
        return
    response = await handle_blockword_command_logic(context.args or [], user_id, 'tg')
    await update.message.reply_text(response)

async def handle_unblockword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /unblockword <关键词> (管理员)"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
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
    msg = update.message
    if not msg:
        return

    user = update.effective_user
    if not user or user.is_bot:
        return

    text = msg.text
    if not text:
        return

    chat = update.effective_chat
    is_group = chat and chat.id == config_loader.get('telegram.group_id')
    
    # 群聊：所有人都可使用插件命令
    # 私聊：仅管理员可使用插件命令
    if is_group:
        pass
    else:
        if not is_admin(user.id):
            return

    engine = SyncEngine.get_instance()
    pm = PluginManager.get_instance()
    if await pm.route_message('tg', user.id, engine.tg_group_id, text.strip()):
        return

    await msg.reply_text('Unknown command. Type "/help" for help. ')

async def handle_tg_pinned_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 Telegram 消息置顶事件，自动感知并同步发布到 QQ 群公告"""
    if not update.effective_chat or update.effective_chat.id != config_loader.get('telegram.group_id'):
        return

    msg = update.message
    if not msg or not msg.pinned_message:
        return

    from core.notice_sync import notice_sync_manager
    pinned = msg.pinned_message

    # 优先拦截 Bot 自身发布的公告置顶事件，杜绝回环
    if pinned.message_id in notice_sync_manager.bot_pinned_msg_ids or await db.is_tg_msg_id_synced_notice(pinned.message_id):
        logger.debug(f"[TG] 忽略由 Bot 自身同步发布的公告置顶事件 (Msg ID: {pinned.message_id})，防止回环")
        return

    success = await notice_sync_manager.sync_tg_pinned_to_qq(pinned, update.effective_user)
    if success:
        logger.info(f"[TG->QQ] 置顶消息已成功同步为 QQ 群公告 (TG Msg ID: {pinned.message_id})")


async def handle_notice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /notice <公告内容> 或 /announce <公告内容> 指令"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("您的权限不足以发布群公告")
        return

    if not context.args:
        await update.message.reply_text("使用方式: /notice <公告内容>")
        return

    content = " ".join(context.args).strip()
    from core.notice_sync import notice_sync_manager, normalize_notice_text, get_notice_hash
    clean_content = normalize_notice_text(content)
    import html
    escaped_text = html.escape(clean_content)
    tg_text = f"📢 <b>【群公告】</b>\n\n{escaped_text}"
    sent = await context.bot.send_message(chat_id=update.effective_chat.id, text=tg_text, parse_mode="HTML")
    if sent:
        notice_sync_manager.bot_pinned_msg_ids.add(sent.message_id)
        try:
            await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=sent.message_id, disable_notification=False)
        except Exception as e:
            logger.warning(f"Telegram 置顶公告失败: {e}")

    # 同时同步到 QQ 群公告
    qq_gid = config_loader.get('qq.group_id')
    res = await onebot_client.send_group_notice(group_id=qq_gid, content=clean_content, pinned=1)
    if res.get('retcode') == 0:
        h = get_notice_hash(clean_content)
        if h:
            notice_sync_manager.seen_content_hashes.add(h)
        if sent:
            await db.record_synced_notice(source='tg', content_hash=h, tg_message_id=sent.message_id)
        await update.message.reply_text("✅ 公告已成功在 Telegram 置顶并同步至 QQ 群公告！")
    else:
        await update.message.reply_text(f"⚠️ Telegram 公告已置顶，但 QQ 群公告发布失败: {res.get('message', res)}")


async def handle_syncnotice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /syncnotice 指令，手动立即拉取并同步 QQ 群最新公告至 TG"""
    from core.notice_sync import notice_sync_manager
    msg = await update.message.reply_text("🔍 正在拉取 QQ 群最新公告...")
    count = await notice_sync_manager.check_and_sync_qq_notices(force=True)
    if count > 0:
        await msg.edit_text(f"✅ 成功同步 {count} 条 QQ 群公告至 Telegram 并置顶！")
    else:
        await msg.edit_text("已拉取完毕，当前 QQ 群无未同步的有效公告。")

async def handle_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram 表情回应 -> QQ 消息表情点赞（set_msg_emoji_like）。

    - 只处理目标群组内的 emoji 回应（自定义表情贴纸不做映射）；
    - 新增回应 -> set=True，取消回应 -> set=False；
    - 依赖 message_mapping 把 TG 消息 ID 映射回 QQ 消息 ID。
    """
    reaction = getattr(update, 'message_reaction', None)
    if not reaction:
        return

    chat = getattr(reaction, 'chat', None)
    if not chat or chat.id != config_loader.get('telegram.group_id'):
        return
    if not config_loader.get('sync.sync_reaction', True):
        return
    if config_loader.get('sync.direction', 'both') == 'qq_to_tg':
        return

    def _first_emoji(items):
        for item in items or []:
            emoji = getattr(item, 'emoji', None)
            if emoji:
                return emoji
        return None

    added = _first_emoji(reaction.new_reaction)
    removed = _first_emoji(reaction.old_reaction)

    if added:
        emoji, set_like = added, True
    elif removed:
        # 取消回应：把 QQ 侧对应的点赞也撤掉
        emoji, set_like = removed, False
    else:
        return

    qq_msg_id = await db.get_qq_msg_id_by_tg(reaction.message_id)
    if not qq_msg_id:
        logger.debug(f"[TG 表情回应] TG 消息 {reaction.message_id} 没有对应的 QQ 映射，跳过")
        return

    emoji_id = tg_emoji_to_qq_emoji_id(emoji)
    if not emoji_id:
        return

    try:
        res = await onebot_client.set_msg_emoji_like(qq_msg_id, emoji_id, set_like=set_like)
        if res.get('retcode') == 0:
            action = '回应' if set_like else '取消回应'
            logger.info(f"[TG] {emoji} {action}已同步至 QQ 消息 {qq_msg_id}（emoji_id={emoji_id}）")
        else:
            logger.warning(f"[TG] 表情回应同步到 QQ 失败: {res}")
    except Exception as e:
        logger.warning(f"[TG] 表情回应同步异常: {e}")


def get_tg_handlers():
    handlers = [
        MessageHandler(filters.StatusUpdate.PINNED_MESSAGE, handle_tg_pinned_message),
        MessageHandler(filters.UpdateType.MESSAGE & ~filters.COMMAND & ~filters.StatusUpdate.ALL, handle_tg_message),
        CommandHandler('bind', handle_bind_command),
        CommandHandler('setprefix', handle_setprefix_command),
        CommandHandler('help', handle_help_command),
        CommandHandler('webui', handle_webui_command),
        CommandHandler('status', handle_status_command_tg),
        CommandHandler('reboot', handle_reboot_command_tg),
        CommandHandler('update', handle_update_command_tg),
        CommandHandler('checkupdate', handle_update_command_tg),
        CommandHandler('cu', handle_update_command_tg),
        CommandHandler('confirm', handle_confirm_ffmpeg),
        CommandHandler('cancel', handle_cancel_ffmpeg),
        CommandHandler('blockword', handle_blockword_command),
        CommandHandler('unblockword', handle_unblockword_command),
        CommandHandler('blockwords', handle_blockwords_command),
        CommandHandler('notice', handle_notice_command),
        CommandHandler('announce', handle_notice_command),
        CommandHandler('syncnotice', handle_syncnotice_command),
        MessageHandler(filters.UpdateType.MESSAGE & filters.COMMAND, handle_unhandled_command),
    ]
    if MessageReactionHandler is not None:
        handlers.insert(-1, MessageReactionHandler(handle_message_reaction))
    return handlers
