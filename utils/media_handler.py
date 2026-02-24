"""
媒体文件处理模块
负责媒体文件的下载、存储、转发和清理
"""

import asyncio
import aiohttp
import aiofiles
import os
import tempfile
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from utils.logger import get_logger

logger = get_logger()

class MediaHandler:
    """媒体文件处理器"""
    
    def __init__(self, temp_dir: str = "temp/media"):
        """初始化媒体处理器"""
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.download_semaphore = asyncio.Semaphore(5)  # 限制并发下载数
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self):
        """初始化HTTP会话"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300)  # 5分钟超时
            )
    
    async def download_media(self, url: str, filename: Optional[str] = None) -> Optional[str]:
        """
        下载媒体文件
        
        Args:
            url (str): 文件URL
            filename (str, optional): 指定文件名
            
        Returns:
            str: 本地文件路径，失败返回None
        """
        async with self.download_semaphore:
            try:
                await self.initialize()
                
                # 生成文件名
                if not filename:
                    filename = self._generate_filename(url)
                
                file_path = self.temp_dir / filename
                
                # 检查文件是否已存在
                if file_path.exists():
                    logger.info(f"文件已存在: {file_path}")
                    return str(file_path)
                
                logger.info(f"开始下载媒体文件: {url}")
                
                # 下载文件
                async with self.session.get(url) as response:
                    if response.status == 200:
                        # 分块下载大文件
                        async with aiofiles.open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        
                        file_size = file_path.stat().st_size
                        logger.info(f"媒体文件下载完成: {file_path} ({file_size} bytes)")
                        return str(file_path)
                    else:
                        logger.error(f"下载失败，HTTP状态码: {response.status}")
                        return None
                        
            except asyncio.TimeoutError:
                logger.error(f"下载超时: {url}")
                return None
            except Exception as e:
                logger.error(f"下载媒体文件时出错: {e}")
                return None
    
    async def upload_to_telegram(self, file_path: str, chat_id: str, 
                               file_type: str = "document") -> Optional[Dict[Any, Any]]:
        """
        上传文件到Telegram
        
        Args:
            file_path (str): 本地文件路径
            chat_id (str): 聊天ID
            file_type (str): 文件类型 (photo, video, audio, document, voice)
            
        Returns:
            dict: Telegram API响应，失败返回None
        """
        try:
            await self.initialize()
            
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return None
            
            file_size = os.path.getsize(file_path)
            logger.info(f"准备上传到Telegram: {file_path} ({file_size} bytes)")
            
            # 根据文件类型选择上传方法
            upload_methods = {
                'photo': self._upload_photo,
                'video': self._upload_video,
                'audio': self._upload_audio,
                'voice': self._upload_voice,
                'document': self._upload_document
            }
            
            upload_method = upload_methods.get(file_type, self._upload_document)
            return await upload_method(file_path, chat_id)
            
        except Exception as e:
            logger.error(f"上传到Telegram时出错: {e}")
            return None
    
    async def _upload_photo(self, file_path: str, chat_id: str) -> Optional[Dict[Any, Any]]:
        """上传图片"""
        try:
            logger.info(f"正在上传图片到Telegram: {file_path}")
            
            # 直接创建Telegram Bot实例进行上传
            from telegram.ext import Application
            from utils.config import get_config
            
            config = get_config()
            token = config.get('telegram.token')
            
            if not token:
                logger.error("Telegram token未配置")
                return None
            
            # 创建临时应用实例用于上传
            app = Application.builder().token(token).build()
            await app.initialize()
            
            # 使用Telegram Bot上传图片
            with open(file_path, 'rb') as photo_file:
                result = await app.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    read_timeout=60,
                    write_timeout=60
                )
            
            await app.shutdown()
            
            logger.info(f"图片上传成功: {result.message_id}")
            return {
                'message_id': result.message_id,
                'file_id': result.photo[-1].file_id if result.photo else None,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"上传图片到Telegram失败: {e}")
            return None
    
    async def _upload_video(self, file_path: str, chat_id: str) -> Optional[Dict[Any, Any]]:
        """上传视频"""
        try:
            logger.info(f"正在上传视频到Telegram: {file_path}")
            
            # 直接创建Telegram Bot实例进行上传
            from telegram.ext import Application
            from utils.config import get_config
            
            config = get_config()
            token = config.get('telegram.token')
            
            if not token:
                logger.error("Telegram token未配置")
                return None
            
            # 创建临时应用实例用于上传
            app = Application.builder().token(token).build()
            await app.initialize()
            
            # 使用Telegram Bot上传视频
            with open(file_path, 'rb') as video_file:
                result = await app.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    read_timeout=120,
                    write_timeout=120
                )
            
            await app.shutdown()
            
            logger.info(f"视频上传成功: {result.message_id}")
            return {
                'message_id': result.message_id,
                'file_id': result.video.file_id if result.video else None,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"上传视频到Telegram失败: {e}")
            return None
    
    async def _upload_audio(self, file_path: str, chat_id: str) -> Optional[Dict[Any, Any]]:
        """上传音频"""
        try:
            logger.info(f"正在上传音频到Telegram: {file_path}")
            
            # 直接创建Telegram Bot实例进行上传
            from telegram.ext import Application
            from utils.config import get_config
            
            config = get_config()
            token = config.get('telegram.token')
            
            if not token:
                logger.error("Telegram token未配置")
                return None
            
            # 创建临时应用实例用于上传
            app = Application.builder().token(token).build()
            await app.initialize()
            
            # 使用Telegram Bot上传音频
            with open(file_path, 'rb') as audio_file:
                result = await app.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    read_timeout=120,
                    write_timeout=120
                )
            
            await app.shutdown()
            
            logger.info(f"音频上传成功: {result.message_id}")
            return {
                'message_id': result.message_id,
                'file_id': result.audio.file_id if result.audio else None,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"上传音频到Telegram失败: {e}")
            return None
    
    async def _upload_voice(self, file_path: str, chat_id: str) -> Optional[Dict[Any, Any]]:
        """上传语音"""
        try:
            logger.info(f"正在上传语音到Telegram: {file_path}")
            
            # 直接创建Telegram Bot实例进行上传
            from telegram.ext import Application
            from utils.config import get_config
            
            config = get_config()
            token = config.get('telegram.token')
            
            if not token:
                logger.error("Telegram token未配置")
                return None
            
            # 创建临时应用实例用于上传
            app = Application.builder().token(token).build()
            await app.initialize()
            
            # 使用Telegram Bot上传语音
            with open(file_path, 'rb') as voice_file:
                result = await app.bot.send_voice(
                    chat_id=chat_id,
                    voice=voice_file,
                    read_timeout=120,
                    write_timeout=120
                )
            
            await app.shutdown()
            
            logger.info(f"语音上传成功: {result.message_id}")
            return {
                'message_id': result.message_id,
                'file_id': result.voice.file_id if result.voice else None,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"上传语音到Telegram失败: {e}")
            return None
    
    async def _upload_document(self, file_path: str, chat_id: str) -> Optional[Dict[Any, Any]]:
        """上传文档"""
        try:
            logger.info(f"正在上传文档到Telegram: {file_path}")
            
            # 直接创建Telegram Bot实例进行上传
            from telegram.ext import Application
            from utils.config import get_config
            
            config = get_config()
            token = config.get('telegram.token')
            
            if not token:
                logger.error("Telegram token未配置")
                return None
            
            # 创建临时应用实例用于上传
            app = Application.builder().token(token).build()
            await app.initialize()
            
            # 获取文件名
            file_name = os.path.basename(file_path)
            
            # 使用Telegram Bot上传文档
            with open(file_path, 'rb') as doc_file:
                result = await app.bot.send_document(
                    chat_id=chat_id,
                    document=doc_file,
                    filename=file_name,
                    read_timeout=120,
                    write_timeout=120
                )
            
            await app.shutdown()
            
            logger.info(f"文档上传成功: {result.message_id}")
            return {
                'message_id': result.message_id,
                'file_id': result.document.file_id if result.document else None,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"上传文档到Telegram失败: {e}")
            return None
    
    async def send_to_qq(self, file_path: str, group_id: str, 
                        file_type: str = "file") -> bool:
        """
        发送文件到QQ
        
        Args:
            file_path (str): 本地文件路径
            group_id (str): QQ群号
            file_type (str): 文件类型
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return False
            
            file_size = os.path.getsize(file_path)
            logger.info(f"准备发送到QQ: {file_path} ({file_size} bytes)")
            
            # 通过napcat API上传文件
            from utils.config import get_config
            config = get_config()
            http_url = config.get('qq.http_url')
            
            if not http_url:
                logger.error("QQ HTTP URL未配置")
                return False
            
            # 上传文件到QQ服务器
            upload_url = f"{http_url}/upload_file"
            
            # 读取文件内容
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # 准备上传数据
            import base64
            encoded_content = base64.b64encode(file_content).decode('utf-8')
            
            upload_payload = {
                'file': encoded_content,
                'name': os.path.basename(file_path)
            }
            
            # 上传文件
            async with aiohttp.ClientSession() as session:
                async with session.post(upload_url, json=upload_payload, 
                                      timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        upload_result = await response.json()
                        if upload_result.get('status') == 'ok':
                            file_id = upload_result.get('data', {}).get('file_id')
                            if file_id:
                                logger.info(f"文件上传成功，File ID: {file_id}")
                                
                                # 发送文件到群组
                                send_url = f"{http_url}/send_group_msg"
                                send_payload = {
                                    'group_id': int(group_id),
                                    'message': [
                                        {
                                            'type': 'image' if file_type == 'photo' else 'file',
                                            'data': {
                                                'file': file_id
                                            }
                                        }
                                    ]
                                }
                                
                                async with session.post(send_url, json=send_payload,
                                                      timeout=aiohttp.ClientTimeout(total=30)) as send_response:
                                    if send_response.status == 200:
                                        send_result = await send_response.json()
                                        if send_result.get('status') == 'ok':
                                            logger.info(f"文件已成功发送到QQ群 {group_id}")
                                            return True
                                        else:
                                            logger.error(f"发送文件到QQ失败: {send_result}")
                                            return False
                                    else:
                                        logger.error(f"发送请求失败: {send_response.status}")
                                        return False
                            else:
                                logger.error("文件上传返回的file_id为空")
                                return False
                        else:
                            logger.error(f"文件上传失败: {upload_result}")
                            return False
                    else:
                        logger.error(f"上传请求失败: {response.status}")
                        return False
            
        except Exception as e:
            logger.error(f"发送到QQ时出错: {e}")
            return False
    
    def _generate_filename(self, url: str) -> str:
        """根据URL生成唯一文件名"""
        # 使用URL的哈希值作为文件名基础
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        # 获取文件扩展名
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        ext = os.path.splitext(parsed_url.path)[1] or '.tmp'
        
        return f"{url_hash}{ext}"
    
    async def cleanup_temp_files(self, max_age_hours: int = 24):
        """
        清理临时文件
        
        Args:
            max_age_hours (int): 最大文件年龄（小时）
        """
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            cleaned_count = 0
            for file_path in self.temp_dir.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        try:
                            file_path.unlink()
                            cleaned_count += 1
                            logger.debug(f"清理临时文件: {file_path}")
                        except Exception as e:
                            logger.error(f"清理文件失败 {file_path}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个临时文件")
                
        except Exception as e:
            logger.error(f"清理临时文件时出错: {e}")
    
    async def close(self):
        """关闭资源"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("媒体处理器已关闭")

# 全局实例
media_handler = MediaHandler()

async def get_media_handler() -> MediaHandler:
    """获取媒体处理器实例"""
    return media_handler