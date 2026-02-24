"""
Telegram机器人客户端
负责处理Telegram消息的接收和发送
"""

import asyncio
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import httpx
from utils.logger import get_logger
from utils.config import get_config
from utils.media_handler import get_media_handler
from utils.retry_manager import get_retry_manager
from typing import Callable, Optional, Dict, Any

logger = get_logger()

class TelegramBot:
    """Telegram机器人客户端"""
    
    def __init__(self):
        """初始化Telegram机器人"""
        self.config = get_config()
        self.telegram_config = self.config.get_telegram_config()
        self.bot_token = self.telegram_config['token']
        self.chat_id = self.telegram_config['chat_id']
        self.proxy_config = self.telegram_config.get('proxy', {})
        
        # 消息回调函数
        self.message_callback: Optional[Callable] = None
        
        # 初始化bot应用
        self.application = None
        self.bot = None
        
        # HTTP客户端（用于代理支持）
        self.http_client = None
        
        # 媒体处理器
        self.media_handler = None
        
        # 重试管理器
        self.retry_manager = None
        
    async def initialize(self):
        """初始化机器人"""
        try:
            # 配置代理
            http_client = await self._setup_http_client()
            
            # 创建应用（带代理支持）
            builder = Application.builder().token(self.bot_token)
            
            if http_client:
                builder = builder.http_client(http_client)
                logger.info("Telegram机器人已配置代理")
            
            self.application = builder.build()
            self.bot = self.application.bot
            
            # 添加文本消息处理器
            self.application.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    self._handle_text_message
                )
            )
            
            # 添加媒体消息处理器
            self.application.add_handler(
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.AUDIO | 
                    filters.VOICE | filters.Document.ALL,
                    self._handle_media_message
                )
            )
            
            # 添加命令处理器
            self.application.add_handler(
                MessageHandler(
                    filters.COMMAND,
                    self._handle_command
                )
            )
            
            logger.info("Telegram机器人初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"Telegram机器人初始化失败: {e}")
            return False
    
    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理接收到的文本消息"""
        try:
            message = update.message
            if not message:
                return
                
            # 检查是否来自目标群组
            if str(message.chat.id) != str(self.chat_id):
                logger.debug(f"忽略非目标群组消息: {message.chat.id}")
                return
            
            # 检查是否为回复消息
            is_reply = False
            replied_to_user = None
            replied_to_message = None
            
            if message.reply_to_message:
                is_reply = True
                replied_to_user = message.reply_to_message.from_user
                replied_to_message = message.reply_to_message.text or "[媒体消息]"
                
                # 如果回复的是机器人自己发送的消息，尝试提取原始发送者信息
                if replied_to_user and replied_to_user.id == self.bot.id:
                    # 从消息文本中提取原始发送者
                    original_sender = self._extract_original_sender(replied_to_message)
                    if original_sender:
                        replied_to_user = {'username': original_sender}
            
            # 构造消息数据
            message_data = {
                'platform': 'telegram',
                'message_id': message.message_id,
                'type': 'text',
                'text': message.text,
                'is_reply': is_reply,
                'replied_to_user': replied_to_user,
                'replied_to_message': replied_to_message,
                'from_user': {
                    'id': message.from_user.id,
                    'username': message.from_user.username,
                    'first_name': message.from_user.first_name,
                    'last_name': message.from_user.last_name
                },
                'timestamp': message.date.timestamp(),
                'chat_id': message.chat.id
            }
            
            logger.info(f"[Telegram] 收到文本消息: {message.text[:50]}...")
            
            # 调用回调函数
            if self.message_callback:
                await self.message_callback(message_data)
                
        except Exception as e:
            logger.error(f"处理Telegram文本消息时出错: {e}")
    
    async def _handle_media_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理接收到的媒体消息"""
        try:
            message = update.message
            if not message:
                return
                
            # 检查是否来自目标群组
            if str(message.chat.id) != str(self.chat_id):
                logger.debug(f"忽略非目标群组消息: {message.chat.id}")
                return
            
            # 初始化媒体处理器
            if not self.media_handler:
                self.media_handler = await get_media_handler()
                await self.media_handler.initialize()
            
            # 识别媒体类型
            media_type = self._identify_media_type(message)
            file_id = self._get_file_id(message, media_type)
            
            if not file_id:
                logger.warning(f"无法获取文件ID，媒体类型: {media_type}")
                return
            
            # 获取文件信息
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            
            # 构造媒体消息数据
            message_data = {
                'platform': 'telegram',
                'message_id': message.message_id,
                'type': 'media',
                'media_type': media_type,
                'file_id': file_id,
                'file_url': file_url,
                'caption': message.caption or '',
                'from_user': {
                    'id': message.from_user.id,
                    'username': message.from_user.username,
                    'first_name': message.from_user.first_name,
                    'last_name': message.from_user.last_name
                },
                'timestamp': message.date.timestamp(),
                'chat_id': message.chat.id
            }
            
            logger.info(f"[Telegram] 收到{media_type}消息: {file_url}")
            
            # 调用回调函数
            if self.message_callback:
                await self.message_callback(message_data)
                
        except Exception as e:
            logger.error(f"处理Telegram媒体消息时出错: {e}")
    
    def _identify_media_type(self, message) -> str:
        """识别媒体类型"""
        if message.photo:
            return 'photo'
        elif message.video:
            return 'video'
        elif message.audio:
            return 'audio'
        elif message.voice:
            return 'voice'
        elif message.document:
            return 'document'
        else:
            return 'unknown'
    
    def _get_file_id(self, message, media_type: str) -> Optional[str]:
        """获取文件ID"""
        try:
            if media_type == 'photo':
                # 选择最高质量的照片
                photo = max(message.photo, key=lambda x: x.file_size)
                return photo.file_id
            elif media_type == 'video':
                return message.video.file_id
            elif media_type == 'audio':
                return message.audio.file_id
            elif media_type == 'voice':
                return message.voice.file_id
            elif media_type == 'document':
                return message.document.file_id
            else:
                return None
        except Exception as e:
            logger.error(f"获取文件ID时出错: {e}")
            return None
    
    def _extract_original_sender(self, message_text: str) -> Optional[str]:
        """从机器人转发的消息中提取原始发送者"""
        try:
            # 匹配 [QQ] 昵称: 消息 或 [TG] 用户名: 消息 格式
            import re
            
            # 匹配QQ格式
            qq_match = re.match(r'\[QQ\]\s*([^:：]+)[:：]\s*(.+)', message_text)
            if qq_match:
                return qq_match.group(1).strip()
            
            # 匹配TG格式
            tg_match = re.match(r'\[TG\]\s*([^:：]+)[:：]\s*(.+)', message_text)
            if tg_match:
                return tg_match.group(1).strip()
            
            return None
        except Exception as e:
            logger.error(f"提取原始发送者时出错: {e}")
            return None
    
    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理命令消息"""
        try:
            message = update.message
            if not message:
                return
                
            command = message.text.split()[0].lower()
            
            # 处理内置命令
            if command == '/ping':
                await message.reply_text('pong!')
            elif command == '/status':
                await message.reply_text('Telegram机器人运行正常')
            elif command == '/help':
                help_text = """
可用命令:
/ping - 测试机器人连通性
/status - 查看机器人状态
/help - 显示帮助信息
                """
                await message.reply_text(help_text)
                
            logger.info(f"[Telegram] 处理命令: {command}")
            
        except Exception as e:
            logger.error(f"处理Telegram命令时出错: {e}")
    
    async def send_message(self, text: str, reply_to_message_id: Optional[int] = None, 
                         is_reply: bool = False, replied_to_user: Optional[Dict] = None,
                         replied_to_message: Optional[str] = None, **kwargs) -> bool:
        """
        发送消息到Telegram（带重试机制和原生回复支持）
        
        Args:
            text (str): 消息文本
            reply_to_message_id (int, optional): 要回复的消息ID
            is_reply (bool): 是否为回复消息
            replied_to_user (dict, optional): 被回复用户信息
            replied_to_message (str, optional): 被回复的消息内容
            **kwargs: 其他参数
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if not self.bot:
                logger.error("Telegram机器人未初始化")
                return False
            
            # 初始化重试管理器
            if not self.retry_manager:
                self.retry_manager = await get_retry_manager()
                self.retry_manager.set_send_callback(self._direct_send_message)
                await self.retry_manager.start()
            
            # 如果是回复消息且有具体的回复ID，则使用原生回复
            if is_reply and reply_to_message_id:
                kwargs['reply_to_message_id'] = reply_to_message_id
                logger.info(f"[Telegram] 使用原生回复功能，回复消息ID: {reply_to_message_id}")
            
            # 直接尝试发送
            success = await self._direct_send_message(text, **kwargs)
            
            if success:
                logger.info(f"[Telegram] 消息发送成功: {text[:50]}...")
                return True
            else:
                # 发送失败，添加到重试队列
                message_data = {
                    'type': 'text',
                    'text': text,
                    'reply_to_message_id': reply_to_message_id,
                    'is_reply': is_reply,
                    'replied_to_user': replied_to_user,
                    'replied_to_message': replied_to_message,
                    'kwargs': kwargs
                }
                await self.retry_manager.add_to_retry_queue(message_data, "首次发送失败")
                logger.warning(f"[Telegram] 消息发送失败，已加入重试队列: {text[:50]}...")
                return False
                
        except Exception as e:
            logger.error(f"[Telegram] 发送消息时出错: {e}")
            return False
    
    async def _direct_send_message(self, text: str, reply_to_message_id: Optional[int] = None, 
                                 is_reply: bool = False, replied_to_user: Optional[Dict] = None,
                                 replied_to_message: Optional[str] = None, **kwargs) -> bool:
        """
        直接发送消息到Telegram（支持原生回复）
        
        Args:
            text (str): 消息文本
            reply_to_message_id (int, optional): 要回复的消息ID
            is_reply (bool): 是否为回复消息
            replied_to_user (dict, optional): 被回复用户信息
            replied_to_message (str, optional): 被回复的消息内容
            **kwargs: 其他参数
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if not self.bot:
                return False
            
            # 准备发送参数
            send_kwargs = {
                'chat_id': self.chat_id,
                'text': text,
                **kwargs
            }
            
            # 如果有回复ID，添加到参数中
            if reply_to_message_id:
                send_kwargs['reply_to_message_id'] = reply_to_message_id
            
            # 发送消息
            sent_message = await self.bot.send_message(**send_kwargs)
            return True
            
        except Exception as e:
            logger.error(f"[Telegram] 直接发送消息失败: {e}")
            return False
    
    async def delete_message(self, message_id: int) -> bool:
        """
        删除Telegram消息
        
        Args:
            message_id (int): 要删除的消息ID
            
        Returns:
            bool: 删除是否成功
        """
        try:
            if not self.bot:
                logger.error("[Telegram] 机器人未初始化")
                return False
            
            logger.info(f"[Telegram] 尝试删除消息: {message_id}")
            
            # 删除消息（只能删除48小时内发送的消息）
            result = await self.bot.delete_message(
                chat_id=self.chat_id,
                message_id=message_id
            )
            
            logger.info(f"[Telegram] 消息删除成功: {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"[Telegram] 删除消息失败: {e}")
            return False
    
    def set_message_callback(self, callback: Callable):
        """设置消息回调函数"""
        self.message_callback = callback
    
    async def start(self):
        """启动机器人"""
        try:
            if not self.application:
                await self.initialize()
            
            logger.info("启动Telegram机器人...")
            # 使用新的API方式启动
            async with self.application:
                await self.application.start()
                await self.application.updater.start_polling()
                # 保持运行直到被中断
                while True:
                    await asyncio.sleep(1)
            
        except asyncio.CancelledError:
            logger.info("Telegram机器人被取消")
        except Exception as e:
            logger.error(f"启动Telegram机器人失败: {e}")
            raise
    
    async def _setup_http_client(self):
        """设置HTTP客户端（用于代理支持）"""
        try:
            # 检查是否启用代理
            if not self.proxy_config.get('enable', False):
                logger.info("Telegram代理未启用，使用直连")
                return None
            
            # 获取代理配置
            proxy_type = self.proxy_config.get('type', 'socks5')
            proxy_host = self.proxy_config.get('host', '127.0.0.1')
            proxy_port = self.proxy_config.get('port', 1080)
            proxy_username = self.proxy_config.get('username', '')
            proxy_password = self.proxy_config.get('password', '')
            
            # 构造代理URL
            if proxy_username and proxy_password:
                proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
            else:
                proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
            
            # 创建HTTP客户端
            if proxy_type == 'socks5':
                # SOCKS5代理
                transport = httpx.AsyncHTTPTransport(proxy=httpx.Proxy(proxy_url))
                self.http_client = httpx.AsyncClient(transport=transport)
            else:
                # HTTP代理
                self.http_client = httpx.AsyncClient(proxy=proxy_url)
            
            logger.info(f"Telegram代理已配置: {proxy_type}://{proxy_host}:{proxy_port}")
            return self.http_client
            
        except Exception as e:
            logger.error(f"配置Telegram代理失败: {e}")
            return None
    
    async def stop(self):
        """停止机器人"""
        try:
            # 关闭HTTP客户端
            if self.http_client:
                await self.http_client.aclose()
                self.http_client = None
                logger.info("Telegram HTTP客户端已关闭")
            
            # 关闭媒体处理器
            if self.media_handler:
                await self.media_handler.close()
                self.media_handler = None
                logger.info("Telegram媒体处理器已关闭")
            
            # 关闭重试管理器
            if self.retry_manager:
                await self.retry_manager.stop()
                self.retry_manager = None
                logger.info("Telegram重试管理器已关闭")
            
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                logger.info("Telegram机器人已停止")
        except Exception as e:
            logger.error(f"停止Telegram机器人失败: {e}")

# 全局实例
telegram_bot = TelegramBot()

async def get_telegram_bot() -> TelegramBot:
    """获取Telegram机器人实例"""
    return telegram_bot