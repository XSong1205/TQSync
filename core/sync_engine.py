from telegram import Bot
import logging
import base64
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

    async def forward_image_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """将 Telegram 图片转发到 QQ (采用 Base64 中转方案以确保稳定性)"""
        binding = await db.get_binding_by_tg(tg_user_id)
        nickname = binding[3] if binding and binding[3] else tg_username
        
        try:
            # 1. 获取 Telegram 文件对象并构建下载链接
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            logger.info(f"Downloading image from TG: {file_url}")

            # 2. 下载图片到内存并转为 Base64
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Failed to download image from TG, status: {resp.status}")
                    image_bytes = await resp.read()
            
            base64_str = base64.b64encode(image_bytes).decode('utf-8')
            base64_data = f"base64://{base64_str}"
            logger.info(f"Image converted to Base64. Length: {len(base64_str)}")

            # 3. 构造 OneBot v11 消息段数组
            message_array = [
                {
                    "type": "text",
                    "data": {
                        "text": f"[TG] {nickname} 发送了一张图片\n"
                    }
                },
                {
                    "type": "image",
                    "data": {
                        "file": base64_data
                    }
                }
            ]
            
            logger.info(f"Sending payload to NapCat: {message_array}")
            
            # 4. 调用 OneBot API 发送
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"NapCat Response: {result}")

        except Exception as e:
            logger.error(f"Failed to forward image to QQ: {e}", exc_info=True)

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
