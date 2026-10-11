import asyncio
import hashlib
import html
from typing import Optional
from telegram import Bot, Message
from config.config_loader import config_loader
from handlers.qq_handler import onebot_client
from db.database import db
from utils.logger import logger


class NoticeSyncManager:
    """群公告双向自动感知同步管理器

    1. QQ -> Telegram:
       - 定时轮询及 Webhook 触发 QQ 群公告变更检测
       - 新发布的群公告自动转发至 Telegram 目标群组并自动执行置顶 (pin_chat_message)
    2. Telegram -> QQ:
       - 监听 Telegram 群消息置顶事件 (filters.StatusUpdate.PINNED_MESSAGE)
       - 自动调用 NapCat /_send_group_notice 在 QQ 群发布对应公告并置顶
    3. 防环机制 (Anti-Loop):
       - 内容哈希 (SHA256) 记录与过滤
       - 消息来源与专属标识比对，彻底杜绝双端回环
    """

    _instance: Optional["NoticeSyncManager"] = None

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.tg_group_id: Optional[int] = None
        self.qq_group_id: Optional[int] = None
        self.seen_notice_ids: set[str] = set()
        self.seen_content_hashes: set[str] = set()
        self.initialized = False
        self.is_running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "NoticeSyncManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, bot: Bot):
        """初始化公告同步管理器，加载已有历史公告防止初次启动刷屏"""
        async with self._lock:
            if self.initialized:
                return

            self.bot = bot
            self.tg_group_id = config_loader.get("telegram.group_id")
            self.qq_group_id = config_loader.get("qq.group_id")

            # 1. 从本地数据库载入已同步过的记录
            try:
                db_hashes = await db.get_all_synced_notice_hashes()
                self.seen_content_hashes.update(db_hashes)
                db_ids = await db.get_all_synced_notice_ids()
                self.seen_notice_ids.update(db_ids)
                logger.debug(f"已从数据库载入 {len(db_ids)} 条公告记录及 {len(db_hashes)} 个哈希")
            except Exception as e:
                logger.warning(f"载入已同步公告记录异常: {e}")

            # 2. 从 QQ 侧预读取现有公告并加入过滤集，避免重启后把老公告重复发到 TG
            try:
                if self.qq_group_id:
                    res = await onebot_client.get_group_notice(self.qq_group_id)
                    if res.get("retcode") == 0 and isinstance(res.get("data"), list):
                        for item in res["data"]:
                            nid = str(item.get("notice_id") or item.get("fid") or "")
                            if nid:
                                self.seen_notice_ids.add(nid)
                            msg_obj = item.get("message")
                            text = ""
                            if isinstance(msg_obj, dict):
                                text = msg_obj.get("text", "")
                            elif isinstance(msg_obj, str):
                                text = msg_obj
                            else:
                                text = item.get("content") or item.get("text") or ""
                            if text.strip():
                                h = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
                                self.seen_content_hashes.add(h)
                        logger.info(f"QQ 群公告同步初始化成功，已缓存 {len(res['data'])} 条已有历史公告")
            except Exception as e:
                logger.warning(f"预读取 QQ 现有公告失败 (非致命): {e}")

            self.initialized = True

    def start_polling(self, interval: int = 30):
        """启动后台轮询任务"""
        if self._poll_task and not self._poll_task.done():
            return
        self.is_running = True
        self._poll_task = asyncio.create_task(self._poll_loop(interval))
        logger.info(f"群公告后台自动同步轮询器已启动 (间隔: {interval}s)")

    async def stop(self):
        """停止轮询"""
        self.is_running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.debug("群公告后台同步轮询器已停止")

    async def _poll_loop(self, interval: int):
        while self.is_running:
            try:
                await asyncio.sleep(interval)
                await self.check_and_sync_qq_notices()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"群公告自动同步轮询异常: {e}")

    async def check_and_sync_qq_notices(self, force: bool = False) -> int:
        """检查并同步 QQ 侧的新公告到 Telegram"""
        if not self.bot or not self.qq_group_id or not self.tg_group_id:
            return 0

        # 方向与开关检查
        if not config_loader.get("sync.sync_notice", True):
            return 0
        direction = config_loader.get("sync.direction", "both")
        if direction == "tg_to_qq":
            return 0

        synced_count = 0
        try:
            res = await onebot_client.get_group_notice(self.qq_group_id)
            if res.get("retcode") != 0:
                logger.debug(f"获取 QQ 群公告返回非零状态: {res}")
                return 0

            notices = res.get("data", [])
            if not isinstance(notices, list):
                return 0

            # 按发布时间升序排列，保证按顺序同步
            def get_pub_time(item):
                try:
                    return int(item.get("publish_time") or 0)
                except:
                    return 0

            sorted_notices = sorted(notices, key=get_pub_time)

            for item in sorted_notices:
                nid = str(item.get("notice_id") or item.get("fid") or "")
                if not force and nid and nid in self.seen_notice_ids:
                    continue

                msg_obj = item.get("message")
                text = ""
                images = []
                if isinstance(msg_obj, dict):
                    text = msg_obj.get("text", "")
                    images = msg_obj.get("images") or msg_obj.get("image") or []
                elif isinstance(msg_obj, str):
                    text = msg_obj
                else:
                    text = item.get("content") or item.get("text") or ""

                text = text.strip()
                if not text:
                    if nid:
                        self.seen_notice_ids.add(nid)
                    continue

                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

                if not force:
                    if content_hash in self.seen_content_hashes:
                        if nid:
                            self.seen_notice_ids.add(nid)
                        continue
                    if await db.is_notice_synced(content_hash):
                        if nid:
                            self.seen_notice_ids.add(nid)
                        self.seen_content_hashes.add(content_hash)
                        continue

                # 格式化公告消息
                escaped_text = html.escape(text)
                tg_caption = f"📢 <b>【QQ 群公告】</b>\n\n{escaped_text}"

                # 尝试附带图片发送
                sent_msg: Optional[Message] = None
                img_url = None
                if images and isinstance(images, list):
                    first = images[0]
                    if isinstance(first, dict):
                        img_url = first.get("url") or first.get("file")
                    elif isinstance(first, str):
                        img_url = first

                if img_url and img_url.startswith("http"):
                    try:
                        sent_msg = await self.bot.send_photo(
                            chat_id=self.tg_group_id,
                            photo=img_url,
                            caption=tg_caption[:1024],
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning(f"同步 QQ 公告附带图片至 TG 失败，降级为文本发送: {e}")

                if not sent_msg:
                    sent_msg = await self.bot.send_message(
                        chat_id=self.tg_group_id,
                        text=tg_caption,
                        parse_mode="HTML",
                    )

                # 置顶消息
                if sent_msg:
                    try:
                        await self.bot.pin_chat_message(
                            chat_id=self.tg_group_id,
                            message_id=sent_msg.message_id,
                            disable_notification=False,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Telegram 置顶群公告失败 (可能缺少 can_pin_messages 权限): {e}"
                        )

                    # 记录已同步状态
                    if nid:
                        self.seen_notice_ids.add(nid)
                    self.seen_content_hashes.add(content_hash)
                    await db.record_synced_notice(
                        source="qq",
                        content_hash=content_hash,
                        notice_id=nid,
                        tg_message_id=sent_msg.message_id,
                    )
                    logger.info(f"已自动同步 QQ 群公告至 Telegram 并置顶 (Notice ID: {nid})")
                    synced_count += 1

        except Exception as e:
            logger.error(f"检查并同步 QQ 群公告异常: {e}")

        return synced_count

    async def sync_tg_pinned_to_qq(self, pinned_msg: Message, tg_user=None) -> bool:
        """处理 Telegram 侧置顶消息，自动感知并同步发布到 QQ 群公告"""
        if not self.qq_group_id:
            return False

        # 方向与开关检查
        if not config_loader.get("sync.sync_notice", True):
            return False
        direction = config_loader.get("sync.direction", "both")
        if direction == "qq_to_tg":
            return False

        text = (pinned_msg.text or pinned_msg.caption or "").strip()
        if not text:
            return False

        # 防回环检测 1: 消息由 Bot 自身发送且包含 QQ 群公告标识
        if pinned_msg.from_user and pinned_msg.from_user.is_bot:
            if "【QQ 群公告】" in text:
                logger.debug("忽略由 QQ 群公告同步生成的 Telegram 置顶消息，防止回环")
                return False

        # 防回环检测 2: 检查内容哈希是否已记录
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if content_hash in self.seen_content_hashes or await db.is_notice_synced(content_hash):
            logger.debug("检测到已记录的公告内容哈希，忽略同步，防止回环")
            return False

        logger.info(f"检测到 Telegram 群置顶消息，正在自动同步至 QQ 群公告: {text[:30]}...")

        try:
            res = await onebot_client.send_group_notice(
                group_id=self.qq_group_id,
                content=text,
                pinned=1,
            )
            if res.get("retcode") == 0:
                self.seen_content_hashes.add(content_hash)
                await db.record_synced_notice(
                    source="tg",
                    content_hash=content_hash,
                    tg_message_id=pinned_msg.message_id,
                )
                logger.info(f"已成功将 Telegram 置顶消息同步至 QQ 群公告 (v{config_loader.get('app.version', '')})")
                return True
            else:
                logger.warning(
                    f"同步 Telegram 置顶消息至 QQ 群公告失败 (NapCat 返回: {res})。"
                    "请确认 QQ 机器人账号是否拥有目标群管理员或群主权限。"
                )
                return False
        except Exception as e:
            logger.error(f"同步 Telegram 置顶消息至 QQ 群公告异常: {e}")
            return False


notice_sync_manager = NoticeSyncManager.get_instance()
