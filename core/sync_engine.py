from telegram import Bot
import logging
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
