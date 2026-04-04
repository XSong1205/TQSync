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
        
        # 全局禁用 SSL 验证以适配国内代理环境
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
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

    async def forward_image_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, caption: str = ""):
        """将 Telegram 图片转发到 QQ (本地文件中转方案，支持 Caption 图文混排)"""
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
            
            # 3. 构造消息段 (实现图文混排：文字在上，图片在下)
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {nickname}\n"}},
            ]
            
            # 如果有 Caption，则添加在图片上方
            if caption:
                message_array.append({"type": "text", "data": {"text": f"{caption}\n"}})
            
            message_array.append({"type": "image", "data": {"file": temp_path}})
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"Image with caption sent to QQ. Result: {result}")

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

    async def forward_gif_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """将 Telegram GIF 转发到 QQ (尝试作为视频发送)"""
        binding = await db.get_binding_by_tg(tg_user_id)
        nickname = binding[3] if binding and binding[3] else tg_username
        temp_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(file_url)[1] or '.gif'
            temp_filename = f"gif_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            # 优先尝试 video 消息段，因为 NapCat 对 GIF 的支持通常通过视频实现
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {nickname} 发送了一个动图\n"}},
                {"type": "video", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"GIF sent to QQ. Result: {result}")

        except Exception as e:
            logger.error(f"Failed to forward GIF to QQ: {e}", exc_info=True)
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_file_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, filename: str):
        """将 Telegram 通用文件转发到 QQ (卡片形式)"""
        binding = await db.get_binding_by_tg(tg_user_id)
        nickname = binding[3] if binding and binding[3] else tg_username
        temp_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(filename)[1]
            temp_filename = f"file_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {nickname} 发送了一个文件: {filename}\n"}},
                {"type": "file", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"File sent to QQ. Result: {result}")

        except Exception as e:
            logger.error(f"Failed to forward file to QQ: {e}", exc_info=True)
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_voice_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """将 Telegram 语音转发到 QQ (保持原格式)"""
        binding = await db.get_binding_by_tg(tg_user_id)
        nickname = binding[3] if binding and binding[3] else tg_username
        temp_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(file_url)[1] or '.ogg'
            temp_filename = f"voice_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {nickname} 发送了一条语音\n"}},
                {"type": "record", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"Voice sent to QQ. Result: {result}")

        except Exception as e:
            logger.error(f"Failed to forward voice to QQ: {e}", exc_info=True)
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def _send_file_to_tg(self, qq_user_id: int, qq_nickname: str, file_url: str, send_func, **kwargs):
        """通用文件转发到 Telegram 方法，支持本地路径中转"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        temp_path = None
        
        try:
            # 判断是否为本地路径或内网地址
            if file_url.startswith(("file:///", "/", "C:\\", "D:\\")) or "127.0.0.1" in file_url or "localhost" in file_url:
                # 处理本地路径
                local_path = file_url.replace("file://", "")
                if os.path.exists(local_path):
                    temp_path = local_path
                else:
                    raise FileNotFoundError(f"Local file not found: {local_path}")
            else:
                # 如果是公网 URL，直接传给 PTB
                temp_path = file_url

            # 准备发送参数
            send_kwargs = {"chat_id": self.tg_group_id}
            
            # 合并 caption：如果 kwargs 里有 caption 则优先使用（用于图片混排），否则用 prefix
            if "caption" in kwargs:
                send_kwargs["caption"] = kwargs.pop("caption")
            else:
                send_kwargs["caption"] = prefix
                
            # 添加其他参数（如 filename）
            send_kwargs.update(kwargs)

            # 打开文件并发送
            if os.path.exists(temp_path) and not temp_path.startswith("http"):
                with open(temp_path, 'rb') as f:
                    # 根据 send_func 确定文件参数的 key (photo, document, voice)
                    file_key = "photo" if "photo" in send_kwargs else "document" if "document" in send_kwargs else "voice"
                    send_kwargs[file_key] = f
                    await send_func(**send_kwargs)
            else:
                file_key = "photo" if "photo" in send_kwargs else "document" if "document" in send_kwargs else "voice"
                send_kwargs[file_key] = temp_path
                await send_func(**send_kwargs)
                
        except Exception as e:
            logger.error(f"Failed to forward to TG: {e}", exc_info=True)

    async def forward_image_to_tg(self, qq_user_id: int, qq_nickname: str, image_url: str, caption: str = ""):
        """将 QQ 图片转发到 Telegram (支持本地文件中转)"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        full_caption = f"{prefix}\n{caption}" if caption else prefix
        await self._send_file_to_tg(qq_user_id, qq_nickname, image_url, self.bot.send_photo, caption=full_caption)

    async def forward_file_to_tg(self, qq_user_id: int, qq_nickname: str, file_url: str, file_name: str = "file"):
        """将 QQ 文件转发到 Telegram (支持本地文件中转)"""
        await self._send_file_to_tg(qq_user_id, qq_nickname, file_url, self.bot.send_document, filename=file_name)

    async def forward_voice_to_tg(self, qq_user_id: int, qq_nickname: str, record_url: str):
        """将 QQ 语音转发到 Telegram (支持本地文件中转)"""
        await self._send_file_to_tg(qq_user_id, qq_nickname, record_url, self.bot.send_voice)

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
