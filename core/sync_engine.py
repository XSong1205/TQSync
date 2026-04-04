from telegram import Bot
import logging
import os
import uuid
import aiohttp
from config.config_loader import config_loader
from handlers.qq_handler import onebot_client
from db.database import db

logger = logging.getLogger(__name__)

class SyncEngine:
    _instance = None

    def __init__(self, bot: Bot):
        if SyncEngine._instance is not None:
            return
        self.bot = bot
        self.tg_group_id = config_loader.get('telegram.group_id')
        self.qq_group_id = config_loader.get('qq.group_id')
        SyncEngine._instance = self

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("SyncEngine has not been initialized. Call SyncEngine(bot) first.")
        return cls._instance

    async def _download_to_temp(self, file_url: str, filename: str) -> str:
        """下载文件到 temp 目录并返回本地绝对路径"""
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = os.path.join(temp_dir, filename)
        logger.info(f"Downloading to local temp: {file_path}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Download failed with status {resp.status}")
                with open(file_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
        return os.path.abspath(file_path)

    def _cleanup_temp(self, file_path: str):
        """清理临时文件"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

    async def forward_image_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """将 Telegram 图片转发到 QQ (本地文件中转方案)"""
        binding = await db.get_binding_by_tg(tg_user_id)
        nickname = binding[3] if binding and binding[3] else tg_username
        temp_path = None
        
        try:
            # 1. 获取 Telegram 文件链接
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            # 2. 下载到本地 temp
            ext = os.path.splitext(file_url)[1] or '.jpg'
            temp_filename = f"img_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            # 3. 构造消息段 (使用 file:/// 协议或绝对路径)
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {nickname} 发送了一张图片\n"}},
                {"type": "image", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"Image sent to QQ. Result: {result}")

        except Exception as e:
            logger.error(f"Failed to forward image to QQ: {e}", exc_info=True)
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_video_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """将 Telegram 视频转发到 QQ"""
        binding = await db.get_binding_by_tg(tg_user_id)
        nickname = binding[3] if binding and binding[3] else tg_username
        temp_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(file_url)[1] or '.mp4'
            temp_filename = f"vid_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {nickname} 发送了一个视频\n"}},
                {"type": "video", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"Video sent to QQ. Result: {result}")

        except Exception as e:
            logger.error(f"Failed to forward video to QQ: {e}", exc_info=True)
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_image_to_tg(self, qq_user_id: int, qq_nickname: str, image_url: str):
        """将 QQ 图片转发到 Telegram"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        
        try:
            # Telegram send_photo 支持 URL
            await self.bot.send_photo(chat_id=self.tg_group_id, photo=image_url, caption=f"{prefix} 发送了一张图片")
        except Exception as e:
            logger.error(f"Failed to forward image to TG: {e}")

    async def forward_to_qq(self, tg_user_id: int, tg_username: str, text: str):
        binding = await db.get_binding_by_tg(tg_user_id)
        if binding:
            prefix = f"[TG] {binding[3] or tg_username}"
        else:
            prefix = f"[TG] {tg_username}"
        
        message = f"{prefix}: {text}"
        await onebot_client.send_group_msg(self.qq_group_id, message)

    async def forward_to_tg(self, qq_user_id: int, qq_nickname: str, text: str):
        binding = await db.get_binding_by_qq(qq_user_id)
        if binding:
            prefix = f"[QQ] {binding[2] or qq_nickname}"
        else:
            prefix = f"[QQ] {qq_nickname}"
        
        message = f"{prefix}: {text}"
        try:
            await self.bot.send_message(chat_id=self.tg_group_id, text=message)
        except Exception as e:
            print(f"Error sending to TG: {e}")

    async def send_startup_notification(self):
        """向两个平台发送启动成功通知"""
        message = "🚀 TQSync 机器人已成功启动并正在运行！"
        
        # 发送到 Telegram
        try:
            await self.bot.send_message(chat_id=self.tg_group_id, text=f"[System] {message}")
            logger.info("Startup notification sent to Telegram.")
        except Exception as e:
            logger.error(f"Failed to send startup notification to Telegram: {e}")
            
        # 发送到 QQ
        try:
            await onebot_client.send_group_msg(self.qq_group_id, f"[System] {message}")
            logger.info("Startup notification sent to QQ.")
        except Exception as e:
            logger.error(f"Failed to send startup notification to QQ: {e}")

sync_engine = None  # Will be initialized in main.py with the bot instance
