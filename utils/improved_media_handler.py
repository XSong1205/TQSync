#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改进的媒体处理器实现
根据官方API文档修正QQ和Telegram的媒体发送方式
"""

import asyncio
import aiohttp
import os
import tempfile
from typing import Optional, Dict, Any
from telegram import InputFile, Bot
from telegram.ext import Application

from utils.logger import get_logger
from utils.config import get_config

logger = get_logger()

class ImprovedMediaHandler:
    """改进的媒体处理器"""
    
    def __init__(self):
        self.temp_dir = "temp/media"
        self.session: Optional[aiohttp.ClientSession] = None
        os.makedirs(self.temp_dir, exist_ok=True)
    
    async def initialize(self):
        """初始化媒体处理器"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        logger.info("改进的媒体处理器初始化成功")
    
    async def download_media(self, url: str, filename: Optional[str] = None) -> Optional[str]:
        """下载媒体文件"""
        try:
            if not filename:
                filename = self._generate_filename(url)
            
            file_path = os.path.join(self.temp_dir, filename)
            
            # 如果文件已存在，直接返回
            if os.path.exists(file_path):
                logger.info(f"文件已存在: {file_path}")
                return file_path
            
            # 下载文件
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    
                    file_size = os.path.getsize(file_path)
                    logger.info(f"文件下载成功: {file_path} ({file_size} bytes)")
                    return file_path
                else:
                    logger.error(f"下载失败，HTTP状态码: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"下载媒体文件时出错: {e}")
            return None
    
    async def upload_to_telegram_improved(self, file_path: str, chat_id: str, 
                                        media_type: str = "photo") -> Optional[Dict[str, Any]]:
        """改进的Telegram媒体上传方法"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return None
            
            file_size = os.path.getsize(file_path)
            logger.info(f"准备上传到Telegram: {file_path} ({file_size} bytes)")
            
            config = get_config()
            token = config.get('telegram.token')
            
            if not token:
                logger.error("Telegram token未配置")
                return None
            
            # 使用InputFile对象进行上传（官方推荐方式）
            with open(file_path, 'rb') as media_file:
                input_file = InputFile(media_file)
                
                # 创建Bot实例
                bot = Bot(token=token)
                
                # 根据媒体类型调用相应的方法
                if media_type == "photo":
                    result = await bot.send_photo(
                        chat_id=chat_id,
                        photo=input_file,
                        read_timeout=120,
                        write_timeout=120
                    )
                elif media_type == "video":
                    result = await bot.send_video(
                        chat_id=chat_id,
                        video=input_file,
                        read_timeout=120,
                        write_timeout=120
                    )
                elif media_type == "document":
                    result = await bot.send_document(
                        chat_id=chat_id,
                        document=input_file,
                        read_timeout=120,
                        write_timeout=120
                    )
                elif media_type == "audio":
                    result = await bot.send_audio(
                        chat_id=chat_id,
                        audio=input_file,
                        read_timeout=120,
                        write_timeout=120
                    )
                elif media_type == "voice":
                    result = await bot.send_voice(
                        chat_id=chat_id,
                        voice=input_file,
                        read_timeout=120,
                        write_timeout=120
                    )
                else:
                    logger.error(f"不支持的媒体类型: {media_type}")
                    return None
            
            logger.info(f"Telegram媒体上传成功: {result.message_id}")
            return {
                'message_id': result.message_id,
                'file_id': self._extract_file_id(result, media_type),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"上传到Telegram时出错: {e}")
            return None
    
    async def send_to_qq_improved(self, file_path: str, group_id: str, 
                                file_type: str = "image") -> bool:
        """改进的QQ媒体发送方法"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return False
            
            file_size = os.path.getsize(file_path)
            logger.info(f"准备发送到QQ: {file_path} ({file_size} bytes)")
            
            # 获取配置
            config = get_config()
            http_url = config.get('qq.http_url')
            
            if not http_url:
                logger.error("QQ HTTP URL未配置")
                return False
            
            # 步骤1: 上传文件到QQ服务器（使用正确的API）
            file_id = await self._upload_file_to_qq(http_url, file_path)
            if not file_id:
                return False
            
            # 步骤2: 发送媒体消息
            success = await self._send_media_message_to_qq(
                http_url, group_id, file_id, file_type
            )
            
            return success
            
        except Exception as e:
            logger.error(f"发送到QQ时出错: {e}")
            return False
    
    async def _upload_file_to_qq(self, http_url: str, file_path: str) -> Optional[str]:
        """上传文件到QQ服务器"""
        try:
            # 读取文件内容
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # 使用multipart/form-data格式上传（更符合HTTP标准）
            upload_url = f"{http_url}/upload_file"
            
            # 准备form data
            form_data = aiohttp.FormData()
            form_data.add_field('file', file_content, 
                              filename=os.path.basename(file_path),
                              content_type='application/octet-stream')
            
            async with self.session.post(upload_url, data=form_data,
                                       timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('status') == 'ok':
                        file_id = result.get('data', {}).get('file_id')
                        if file_id:
                            logger.info(f"文件上传成功，File ID: {file_id}")
                            return file_id
                        else:
                            logger.error("上传返回的file_id为空")
                    else:
                        logger.error(f"文件上传失败: {result}")
                else:
                    logger.error(f"上传请求失败: {response.status}")
                    # 记录响应内容用于调试
                    response_text = await response.text()
                    logger.debug(f"响应内容: {response_text}")
            
            return None
            
        except Exception as e:
            logger.error(f"上传文件到QQ时出错: {e}")
            return None
    
    async def _send_media_message_to_qq(self, http_url: str, group_id: str, 
                                      file_id: str, file_type: str) -> bool:
        """发送媒体消息到QQ群"""
        try:
            send_url = f"{http_url}/send_group_msg"
            
            # 根据官方API文档构建消息格式
            message_data = []
            
            if file_type == "image":
                message_data.append({
                    'type': 'image',
                    'data': {
                        'file': file_id
                    }
                })
            elif file_type == "video":
                message_data.append({
                    'type': 'video',
                    'data': {
                        'file': file_id
                    }
                })
            elif file_type == "record":
                message_data.append({
                    'type': 'record',
                    'data': {
                        'file': file_id
                    }
                })
            else:  # file
                message_data.append({
                    'type': 'file',
                    'data': {
                        'file': file_id
                    }
                })
            
            payload = {
                'group_id': int(group_id),
                'message': message_data
            }
            
            logger.debug(f"发送QQ媒体消息，payload: {payload}")
            
            async with self.session.post(send_url, json=payload,
                                       timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('status') == 'ok':
                        logger.info(f"QQ媒体消息发送成功")
                        return True
                    else:
                        logger.error(f"发送QQ媒体消息失败: {result}")
                        # 记录详细错误信息
                        logger.debug(f"完整响应: {result}")
                else:
                    logger.error(f"发送请求失败: {response.status}")
                    response_text = await response.text()
                    logger.debug(f"响应内容: {response_text}")
            
            return False
            
        except Exception as e:
            logger.error(f"发送QQ媒体消息时出错: {e}")
            return False
    
    def _extract_file_id(self, message_result, media_type: str) -> Optional[str]:
        """从Telegram消息结果中提取文件ID"""
        try:
            if media_type == "photo" and hasattr(message_result, 'photo'):
                # 选择最大的图片尺寸
                photo = max(message_result.photo, key=lambda x: x.file_size)
                return photo.file_id
            elif media_type == "video" and hasattr(message_result, 'video'):
                return message_result.video.file_id
            elif media_type == "document" and hasattr(message_result, 'document'):
                return message_result.document.file_id
            elif media_type == "audio" and hasattr(message_result, 'audio'):
                return message_result.audio.file_id
            elif media_type == "voice" and hasattr(message_result, 'voice'):
                return message_result.voice.file_id
            return None
        except Exception as e:
            logger.error(f"提取文件ID时出错: {e}")
            return None
    
    def _generate_filename(self, url: str) -> str:
        """根据URL生成唯一文件名"""
        import hashlib
        from urllib.parse import urlparse
        
        # 使用URL的哈希值作为文件名基础
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        # 获取文件扩展名
        parsed_url = urlparse(url)
        ext = os.path.splitext(parsed_url.path)[1] or '.tmp'
        
        return f"{url_hash}{ext}"
    
    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()
            self.session = None

# 全局实例
improved_media_handler = ImprovedMediaHandler()

async def get_improved_media_handler() -> ImprovedMediaHandler:
    """获取改进的媒体处理器实例"""
    return improved_media_handler

if __name__ == "__main__":
    # 简单测试
    async def test_improved_handler():
        handler = await get_improved_media_handler()
        await handler.initialize()
        
        # 测试下载
        test_url = "https://httpbin.org/image/jpeg"
        file_path = await handler.download_media(test_url, "test.jpg")
        print(f"下载结果: {file_path}")
        
        await handler.cleanup()
    
    asyncio.run(test_improved_handler())