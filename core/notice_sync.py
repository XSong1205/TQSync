import asyncio
import hashlib
import html
import re
import time
from typing import Optional
from telegram import Bot, Message
from config.config_loader import config_loader
from handlers.qq_handler import onebot_client
from db.database import db
from utils.logger import logger


def normalize_notice_text(text: str) -> str:
    """清理并规范化公告文本
    
    1. 解码 HTML 实体编码 (如 &#10; -> \n, &nbsp; -> 空格, &amp; -> &)
    2. 统一各种空白字符与换行
    3. 移除系统添加的【QQ 群公告】等前缀，保证两端比对哈希完全一致
    """
    if not text:
        return ""
    # 解码 HTML 实体
    t = html.unescape(text)
    # 替换非标准空格 (不间断空格、全角空格等)
    t = t.replace('\xa0', ' ').replace('\u3000', ' ')
    # 统一换行符 (\r\n / \r -> \n)
    t = t.replace('\r\n', '\n').replace('\r', '\n')
    # 替换可能存在的 HTML <br> 换行标签
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    # 逐行去除尾部空白并去除首尾空白
    t = '\n'.join(line.rstrip() for line in t.splitlines()).strip()
    # 移除首部的公告标识前缀 (例如 📢 【QQ 群公告】 等)
    t = re.sub(r'^(📢\s*)?(【(QQ\s*)?群公告】\s*)?', '', t).strip()
    return t



def get_notice_hash(text: str) -> str:
    """计算规范化文本的 SHA256 哈希值，用于绝对防回环"""
    norm = normalize_notice_text(text)
    if not norm:
        return ""
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()


class NoticeSyncManager:
    """群公告双向自动感知同步管理器 (彻底防回环版)"""

    _instance: Optional["NoticeSyncManager"] = None

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.tg_group_id: Optional[int] = None
        self.qq_group_id: Optional[int] = None
        self.seen_notice_ids: set[str] = set()
        self.seen_content_hashes: set[str] = set()
        self.bot_pinned_msg_ids: set[int] = set()
        self.start_time: float = time.time()
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
        """初始化公告同步管理器，预加载历史公告与哈希，彻底避免启动刷屏与回环"""
        async with self._lock:
            if self.initialized:
                return

            self.bot = bot
            self.start_time = time.time()
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

            # 2. 从 QQ 侧预读取现有历史公告并加入过滤集合
            try:
                if self.qq_group_id:
                    res = await onebot_client.get_group_notice(self.qq_group_id)
                    if res.get("retcode") == 0 and isinstance(res.get("data"), list):
                        for item in res["data"]:
                            nid = str(item.get("notice_id") or item.get("fid") or "")
                            if nid:
                                self.seen_notice_ids.add(nid)
                            msg_obj = item.get("message")
                            raw_t = ""
                            if isinstance(msg_obj, dict):
                                raw_t = msg_obj.get("text", "")
                            elif isinstance(msg_obj, str):
                                raw_t = msg_obj
                            else:
                                raw_t = item.get("content") or item.get("text") or ""
                            
                            h = get_notice_hash(raw_t)
                            if h:
                                self.seen_content_hashes.add(h)
                        logger.info(f"QQ 群公告同步初始化完成，已自动缓存 {len(res['data'])} 条历史公告，防止启动重复推送")
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

            def get_pub_time(item):
                try:
                    return int(item.get("publish_time") or 0)
                except:
                    return 0

            sorted_notices = sorted(notices, key=get_pub_time)

            for item in sorted_notices:
                nid = str(item.get("notice_id") or item.get("fid") or "")
                pub_time = get_pub_time(item)

                # 提取原始文本与图片
                msg_obj = item.get("message")
                raw_text = ""
                images = []
                if isinstance(msg_obj, dict):
                    raw_text = msg_obj.get("text", "")
                    images = msg_obj.get("images") or msg_obj.get("image") or []
                elif isinstance(msg_obj, str):
                    raw_text = msg_obj
                else:
                    raw_text = item.get("content") or item.get("text") or ""

                clean_text = normalize_notice_text(raw_text)
                if not clean_text:
                    if nid:
                        self.seen_notice_ids.add(nid)
                    continue

                content_hash = get_notice_hash(clean_text)

                # 如果不是强制同步，过滤历史公告与已同步公告
                if not force:
                    # 1. 过滤启动前的老公告 (避免首次启动时全量刷屏)
                    if 0 < pub_time < (self.start_time - 5):
                        if nid:
                            self.seen_notice_ids.add(nid)
                        if content_hash:
                            self.seen_content_hashes.add(content_hash)
                        continue

                    # 2. 过滤已同步的 notice_id
                    if nid and nid in self.seen_notice_ids:
                        continue
                    if nid and await db.is_notice_id_synced(nid):
                        self.seen_notice_ids.add(nid)
                        continue

                    # 3. 过滤已同步的内容哈希 (防止 TG->QQ 同步过来的公告被再次反弹)
                    if content_hash in self.seen_content_hashes:
                        if nid:
                            self.seen_notice_ids.add(nid)
                        continue
                    if await db.is_notice_synced(content_hash):
                        if nid:
                            self.seen_notice_ids.add(nid)
                        self.seen_content_hashes.add(content_hash)
                        continue

                # 格式化公告消息 (HTML 模式)，注意: clean_text 已经将 &#10; 恢复为真正的 \n 换行
                escaped_body = html.escape(clean_text)
                tg_caption = f"📢 <b>【QQ 群公告】</b>\n\n{escaped_body}"

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

                # 立即将该消息 ID 加入已发送集合，并在置顶时防止触发回环
                if sent_msg:
                    self.bot_pinned_msg_ids.add(sent_msg.message_id)

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
                    if content_hash:
                        self.seen_content_hashes.add(content_hash)
                    await db.record_synced_notice(
                        source="qq",
                        content_hash=content_hash,
                        notice_id=nid,
                        tg_message_id=sent_msg.message_id,
                    )
                    logger.info(f"已成功同步 QQ 群公告至 Telegram 并置顶 (Notice ID: {nid})")
                    synced_count += 1

        except Exception as e:
            logger.error(f"检查并同步 QQ 群公告异常: {e}")

        return synced_count

    async def sync_tg_pinned_to_qq(self, pinned_msg: Message, tg_user=None) -> bool:
        """处理 Telegram 侧置顶消息，自动感知并同步发布到 QQ 群公告 (绝对防回环)"""
        if not self.qq_group_id:
            return False

        # 方向与开关检查
        if not config_loader.get("sync.sync_notice", True):
            return False
        direction = config_loader.get("sync.direction", "both")
        if direction == "qq_to_tg":
            return False

        # 防回环 1: 消息 ID 比对 (Bot 自身刚刚发送并置顶的消息)
        if pinned_msg.message_id in self.bot_pinned_msg_ids:
            logger.debug(f"忽略 Bot 自身刚刚发布的公告置顶事件 (Msg ID: {pinned_msg.message_id})，防止回环")
            return False

        # 防回环 2: 数据库历史记录比对
        if await db.is_tg_msg_id_synced_notice(pinned_msg.message_id):
            logger.debug(f"忽略数据库已记录的公告置顶消息 (Msg ID: {pinned_msg.message_id})，防止回环")
            return False

        # 防回环 3: 发送者为 Bot 自身
        if self.bot and pinned_msg.from_user and pinned_msg.from_user.id == self.bot.id:
            logger.debug("忽略由 Bot 账号自身发送的置顶消息，防止回环")
            return False

        raw_text = (pinned_msg.text or pinned_msg.caption or "").strip()
        if not raw_text:
            return False

        # 防回环 4: 文本前缀标记无条件过滤 (无论由谁置顶)
        if "【QQ 群公告】" in raw_text or "【群公告】" in raw_text or raw_text.startswith("📢"):
            logger.debug("置顶消息包含群公告标识，判定为已有公告，忽略同步至 QQ")
            return False

        # 规范化文本并计算统一哈希
        clean_text = normalize_notice_text(raw_text)
        if not clean_text:
            return False

        content_hash = get_notice_hash(clean_text)

        # 防回环 5: 规范化内容哈希比对 (两端即便空格或格式略有差异也能准确拦截)
        if content_hash in self.seen_content_hashes or await db.is_notice_synced(content_hash):
            logger.debug(f"检测到已存在的公告内容哈希 ({content_hash[:8]})，忽略同步，防止回环")
            return False

        logger.info(f"检测到 Telegram 群置顶消息，正在自动同步至 QQ 群公告: {clean_text[:30]}...")

        try:
            res = await onebot_client.send_group_notice(
                group_id=self.qq_group_id,
                content=clean_text,
                pinned=1,
            )
            if res.get("retcode") == 0:
                self.seen_content_hashes.add(content_hash)
                await db.record_synced_notice(
                    source="tg",
                    content_hash=content_hash,
                    tg_message_id=pinned_msg.message_id,
                )
                logger.info(f"已成功将 Telegram 置顶消息同步至 QQ 群公告 (Msg ID: {pinned_msg.message_id})")
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
