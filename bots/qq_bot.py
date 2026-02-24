"""
QQ机器人客户端 (基于napcat)
负责处理QQ消息的接收和发送
"""

import json
import asyncio
import aiohttp
import os
from typing import Callable, Optional, Dict, Any
from utils.logger import get_logger
from utils.config import get_config
from utils.media_handler import get_media_handler
from utils.forward_parser import get_forward_parser

logger = get_logger()

class QQBot:
    """QQ机器人客户端"""
    
    def __init__(self):
        """初始化QQ机器人"""
        self.config = get_config()
        self.qq_config = self.config.get_qq_config()
        
        self.ws_url = self.qq_config['ws_url']
        self.http_url = self.qq_config['http_url']
        self.group_id = self.qq_config['group_id']
        
        # 消息回调函数
        self.message_callback: Optional[Callable] = None
        
        # aiohttp客户端会话
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket = None
        self.is_connected = False
        
        # 重连相关
        self.reconnect_delay = 5  # 重连延迟(秒)
        self.max_reconnect_attempts = 5
        self.reconnect_count = 0
        
        # 媒体处理器
        self.media_handler = None
        
        # 转发消息解析器
        self.forward_parser = None
        
    async def connect_websocket(self):
        """连接到napcat的WebSocket"""
        try:
            logger.info(f"正在连接到QQ WebSocket: {self.ws_url}")
            
            # 创建aiohttp客户端会话
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # 建立WebSocket连接
            self.websocket = await self.session.ws_connect(self.ws_url)
            self.is_connected = True
            self.reconnect_count = 0
            
            logger.info("QQ WebSocket连接成功")
            
            # 开始监听消息
            await self._listen_messages()
            
        except Exception as e:
            logger.error(f"连接QQ WebSocket失败: {e}")
            await self._handle_disconnect()
    
    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            async for msg in self.websocket:
                try:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        # 解析消息
                        data = json.loads(msg.data)
                        await self._handle_websocket_message(data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket错误: {self.websocket.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("QQ WebSocket连接已关闭")
                        break
                except json.JSONDecodeError as e:
                    logger.error(f"解析WebSocket消息失败: {e}")
                except Exception as e:
                    logger.error(f"处理WebSocket消息时出错: {e}")
                    
        except Exception as e:
            logger.error(f"监听WebSocket消息时出错: {e}")
        finally:
            await self._handle_disconnect()
    
    async def _handle_websocket_message(self, data: Dict[Any, Any]):
        """处理WebSocket接收到的消息"""
        try:
            # 检查消息类型
            post_type = data.get('post_type')
            
            if post_type == 'message':
                await self._handle_message_event(data)
            elif post_type == 'notice':
                await self._handle_notice_event(data)
            elif post_type == 'request':
                await self._handle_request_event(data)
            else:
                logger.debug(f"收到未知类型消息: {post_type}")
                
        except Exception as e:
            logger.error(f"处理WebSocket消息时出错: {e}")
    
    async def _handle_message_event(self, data: Dict[Any, Any]):
        """处理消息事件"""
        try:
            message_type = data.get('message_type')
            
            # 只处理群消息
            if message_type != 'group':
                return
            
            group_id = str(data.get('group_id'))
            
            # 检查是否为目标群组
            if group_id != str(self.group_id):
                logger.debug(f"忽略非目标群组消息: {group_id}")
                return
            
            # 初始化转发解析器
            if not self.forward_parser:
                self.forward_parser = get_forward_parser()
            
            # 检查是否为合并转发消息
            is_forward = self.forward_parser.is_forward_message({'raw_data': data})
            
            # 检查是否为媒体消息
            media_info = self._extract_media_info(data.get('message', []))
            
            # 检查是否为回复消息
            is_reply = self._is_reply_message(data)
            replied_to_user = None
            replied_to_message = None
            
            if is_reply:
                replied_info = self._extract_reply_info(data)
                replied_to_user = replied_info.get('user')
                replied_to_message = replied_info.get('message')
            
            # 提取消息信息
            message_data = {
                'platform': 'qq',
                'message_id': data.get('message_id'),
                'message_type': message_type,
                'group_id': group_id,
                'text': self._extract_message_text(data.get('message', [])),
                'is_reply': is_reply,
                'replied_to_user': replied_to_user,
                'replied_to_message': replied_to_message,
                'sender': {
                    'user_id': data.get('sender', {}).get('user_id'),
                    'nickname': data.get('sender', {}).get('nickname'),
                    'card': data.get('sender', {}).get('card')
                },
                'timestamp': data.get('time'),
                'raw_data': data
            }
            
            # 设置消息类型
            if is_forward:
                message_data['type'] = 'forward'
                # 解析转发消息
                forward_messages = self.forward_parser.parse_forward_message(message_data)
                if forward_messages:
                    message_data['forward_messages'] = forward_messages
                logger.info(f"[QQ] 收到合并转发消息: {len(forward_messages or [])} 条记录")
            elif media_info:
                message_data['type'] = 'media'
                message_data.update(media_info)
                logger.info(f"[QQ] 收到媒体消息: {media_info.get('media_type')} - {media_info.get('file_url', 'No URL')}")
            else:
                message_data['type'] = 'text'
            
            if message_data.get('type') == 'media':
                logger.info(f"[QQ] 收到媒体消息: {message_data.get('media_type')} - {message_data.get('text', '')[:50]}...")
            else:
                logger.info(f"[QQ] 收到文本消息: {message_data['text'][:50]}...")
            
            # 调用回调函数
            if self.message_callback:
                await self.message_callback(message_data)
                
        except Exception as e:
            logger.error(f"处理QQ消息事件时出错: {e}")
    
    async def _handle_notice_event(self, data: Dict[Any, Any]):
        """处理通知事件"""
        try:
            notice_type = data.get('notice_type')
            logger.debug(f"[QQ] 收到通知: {notice_type}")
            
            # 处理消息撤回事件
            if notice_type == 'group_recall':
                await self._handle_group_recall(data)
            
        except Exception as e:
            logger.error(f"处理QQ通知事件时出错: {e}")
    
    async def _handle_group_recall(self, data: Dict[Any, Any]):
        """处理群消息撤回事件"""
        try:
            group_id = str(data.get('group_id'))
            message_id = data.get('message_id')
            operator_id = data.get('operator_id')
            user_id = data.get('user_id')
            
            # 检查是否为目标群组
            if group_id != str(self.group_id):
                logger.debug(f"忽略非目标群组撤回消息: {group_id}")
                return
            
            logger.info(f"[QQ] 检测到群消息撤回 - 群ID: {group_id}, 消息ID: {message_id}, 操作者: {operator_id}")
            
            # 构造撤回事件数据
            recall_data = {
                'platform': 'qq',
                'event_type': 'message_delete',
                'group_id': group_id,
                'message_id': message_id,
                'operator_id': operator_id,
                'user_id': user_id,
                'timestamp': data.get('time')
            }
            
            # 调用回调函数
            if self.message_callback:
                await self.message_callback(recall_data)
                
        except Exception as e:
            logger.error(f"处理QQ群撤回事件时出错: {e}")
    
    async def _handle_request_event(self, data: Dict[Any, Any]):
        """处理请求事件"""
        request_type = data.get('request_type')
        logger.debug(f"[QQ] 收到请求: {request_type}")
    
    def _extract_message_text(self, message_elements) -> str:
        """从消息元素中提取文本内容"""
        if isinstance(message_elements, str):
            return message_elements
        
        text_parts = []
        try:
            for element in message_elements:
                if isinstance(element, dict):
                    if element.get('type') == 'text':
                        text_parts.append(element.get('data', {}).get('text', ''))
                elif isinstance(element, str):
                    text_parts.append(element)
        except Exception as e:
            logger.error(f"提取消息文本时出错: {e}")
        
        return ''.join(text_parts).strip()
    
    def _extract_media_info(self, message_elements) -> Optional[Dict[str, Any]]:
        """从消息元素中提取媒体信息"""
        try:
            for element in message_elements:
                if isinstance(element, dict):
                    element_type = element.get('type')
                    
                    # 图片消息
                    if element_type == 'image':
                        return {
                            'media_type': 'image',
                            'file_url': element.get('data', {}).get('url', ''),
                            'file_id': element.get('data', {}).get('file', ''),
                            'width': element.get('data', {}).get('width'),
                            'height': element.get('data', {}).get('height')
                        }
                    
                    # 视频消息
                    elif element_type == 'video':
                        return {
                            'media_type': 'video',
                            'file_url': element.get('data', {}).get('url', ''),
                            'file_id': element.get('data', {}).get('file', ''),
                            'duration': element.get('data', {}).get('duration')
                        }
                    
                    # 语音消息
                    elif element_type == 'record':
                        return {
                            'media_type': 'voice',
                            'file_url': element.get('data', {}).get('url', ''),
                            'file_id': element.get('data', {}).get('file', ''),
                            'duration': element.get('data', {}).get('duration')
                        }
                    
                    # 文件消息
                    elif element_type == 'file':
                        return {
                            'media_type': 'file',
                            'file_url': element.get('data', {}).get('url', ''),
                            'file_id': element.get('data', {}).get('file', ''),
                            'file_name': element.get('data', {}).get('name', ''),
                            'file_size': element.get('data', {}).get('size')
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"提取媒体信息时出错: {e}")
            return None
    
    def _is_reply_message(self, data: Dict[Any, Any]) -> bool:
        """判断是否为回复消息"""
        try:
            # 检查是否有回复相关的字段
            # QQ的回复通常包含reply字段或者特殊的at消息
            message_elements = data.get('message', [])
            
            for element in message_elements:
                if isinstance(element, dict):
                    # 检查是否有at消息（可能是回复）
                    if element.get('type') == 'at':
                        return True
                    
                    # 检查是否有回复标识
                    if element.get('type') == 'reply':
                        return True
            
            return False
        except Exception as e:
            logger.error(f"判断回复消息时出错: {e}")
            return False
    
    def _extract_reply_info(self, data: Dict[Any, Any]) -> Dict[str, Any]:
        """提取回复信息"""
        try:
            message_elements = data.get('message', [])
            reply_info = {'user': None, 'message': None}
            
            # 收集所有文本内容
            text_parts = []
            at_users = []
            
            for element in message_elements:
                if isinstance(element, dict):
                    # 提取at消息中的用户信息
                    if element.get('type') == 'at':
                        qq_id = element.get('data', {}).get('qq')
                        if qq_id and qq_id != 'all':
                            at_users.append(f"QQ用户{qq_id}")
                    
                    # 收集文本内容
                    elif element.get('type') == 'text':
                        text = element.get('data', {}).get('text', '').strip()
                        if text:
                            text_parts.append(text)
            
            # 设置被回复用户（取第一个@的用户）
            if at_users:
                reply_info['user'] = at_users[0]
            
            # 对于QQ回复，我们无法准确区分原始消息和新回复
            # 因为QQ的消息结构是: [@用户] 回复内容
            # 我们将整个回复内容作为新消息，原始消息留空或使用占位符
            if text_parts:
                # 合并所有文本部分作为回复内容
                full_text = ' '.join(text_parts).strip()
                reply_info['message'] = full_text
                
                # 如果有@用户，尝试分离@部分和回复内容
                if at_users and full_text.startswith(at_users[0].replace('QQ用户', '@')):
                    # 移除@用户部分，只保留实际回复内容
                    clean_text = full_text[len(at_users[0].replace('QQ用户', '@')):].strip()
                    if clean_text:
                        reply_info['message'] = clean_text
            
            return reply_info
        except Exception as e:
            logger.error(f"提取回复信息时出错: {e}")
            return {'user': None, 'message': None}
    
    async def send_group_message(self, message: str, reply_to_message_id: Optional[int] = None) -> bool:
        """
        发送群消息
        
        Args:
            message (str): 消息内容
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 确保会话存在
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.http_url}/send_group_msg"
            
            # 构建消息内容，支持原生回复
            if reply_to_message_id:
                # 使用CQ码格式的回复消息
                reply_segment = f"[CQ:reply,id={reply_to_message_id}]"
                final_message = reply_segment + message
            else:
                final_message = message
            
            payload = {
                'group_id': int(self.group_id),
                'message': final_message
            }
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('status') == 'ok':
                        logger.info(f"[QQ] 消息发送成功: {message[:50]}...")
                        return True
                    else:
                        logger.error(f"[QQ] 消息发送失败: {result}")
                        return False
                else:
                    logger.error(f"[QQ] HTTP请求失败: {response.status}")
                    return False
                
        except asyncio.TimeoutError:
            logger.error("[QQ] HTTP请求超时")
            return False
        except Exception as e:
            logger.error(f"[QQ] 发送消息时出错: {e}")
            return False
    
    async def send_media_message(self, file_path: str, media_type: str = "image", 
                               caption: str = "") -> bool:
        """
        发送媒体消息到QQ群
        
        Args:
            file_path (str): 本地文件路径
            media_type (str): 媒体类型 (image/video/record/file)
            caption (str): 附加文本说明
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 确保会话存在
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"[QQ] 文件不存在: {file_path}")
                return False
            
            file_size = os.path.getsize(file_path)
            logger.info(f"[QQ] 准备发送媒体文件: {file_path} ({file_size} bytes)")
            
            # 根据媒体类型构建消息结构
            message_segments = []
            
            # 添加媒体文件段
            if media_type == "image":
                # 对于图片，直接上传并发送
                media_segment = {
                    'type': 'image',
                    'data': {
                        'file': f"file:///{os.path.abspath(file_path)}"
                    }
                }
                message_segments.append(media_segment)
                
            elif media_type == "video":
                # 对于视频，直接上传并发送
                media_segment = {
                    'type': 'video',
                    'data': {
                        'file': f"file:///{os.path.abspath(file_path)}"
                    }
                }
                message_segments.append(media_segment)
                
            elif media_type == "record":
                # 对于语音
                media_segment = {
                    'type': 'record',
                    'data': {
                        'file': f"file:///{os.path.abspath(file_path)}"
                    }
                }
                message_segments.append(media_segment)
                
            elif media_type == "file":
                # 对于普通文件
                media_segment = {
                    'type': 'file',
                    'data': {
                        'file': f"file:///{os.path.abspath(file_path)}",
                        'name': os.path.basename(file_path)
                    }
                }
                message_segments.append(media_segment)
            
            # 如果有文本说明，添加文本段
            if caption:
                text_segment = {
                    'type': 'text',
                    'data': {
                        'text': caption
                    }
                }
                message_segments.append(text_segment)
            
            # 发送消息
            url = f"{self.http_url}/send_group_msg"
            payload = {
                'group_id': int(self.group_id),
                'message': message_segments
            }
            
            logger.debug(f"[QQ] 发送媒体消息负载: {payload}")
            
            async with self.session.post(url, json=payload, 
                                       timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('status') == 'ok':
                        message_id = result.get('data', {}).get('message_id')
                        logger.info(f"[QQ] 媒体消息发送成功，消息ID: {message_id}")
                        return True
                    else:
                        logger.error(f"[QQ] 媒体消息发送失败: {result}")
                        return False
                else:
                    logger.error(f"[QQ] HTTP请求失败: {response.status}")
                    return False
                    
        except asyncio.TimeoutError:
            logger.error("[QQ] 媒体消息发送超时")
            return False
        except Exception as e:
            logger.error(f"[QQ] 发送媒体消息时出错: {e}")
            return False
    
    async def delete_message(self, message_id: int) -> bool:
        """
        撤回QQ群消息
        
        Args:
            message_id (int): 要撤回的消息ID
            
        Returns:
            bool: 撤回是否成功
        """
        try:
            # 确保会话存在
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            url = f"{self.http_url}/delete_msg"
            
            payload = {
                'message_id': message_id
            }
            
            logger.info(f"[QQ] 尝试撤回消息: {message_id}")
            
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('status') == 'ok':
                        logger.info(f"[QQ] 消息撤回成功: {message_id}")
                        return True
                    else:
                        logger.error(f"[QQ] 消息撤回失败: {result}")
                        return False
                else:
                    logger.error(f"[QQ] HTTP请求失败: {response.status}")
                    return False
                    
        except asyncio.TimeoutError:
            logger.error("[QQ] 消息撤回请求超时")
            return False
        except Exception as e:
            logger.error(f"[QQ] 撤回消息时出错: {e}")
            return False
    
    async def _handle_disconnect(self):
        """处理连接断开"""
        self.is_connected = False
        
        if self.reconnect_count < self.max_reconnect_attempts:
            self.reconnect_count += 1
            logger.info(f"尝试重新连接 ({self.reconnect_count}/{self.max_reconnect_attempts})...")
            
            await asyncio.sleep(self.reconnect_delay)
            await self.connect_websocket()
        else:
            logger.error("达到最大重连次数，停止重连")
    
    def set_message_callback(self, callback: Callable):
        """设置消息回调函数"""
        self.message_callback = callback
    
    async def start(self):
        """启动QQ机器人"""
        logger.info("启动QQ机器人...")
        await self.connect_websocket()
    
    async def stop(self):
        """停止QQ机器人"""
        try:
            self.is_connected = False
            if self.websocket:
                await self.websocket.close()
            if self.session:
                await self.session.close()
                self.session = None
            
            # 关闭媒体处理器
            if self.media_handler:
                await self.media_handler.close()
                self.media_handler = None
                logger.info("QQ媒体处理器已关闭")
                
            logger.info("QQ机器人已停止")
        except Exception as e:
            logger.error(f"停止QQ机器人失败: {e}")

# 全局实例
qq_bot = QQBot()

async def get_qq_bot() -> QQBot:
    """获取QQ机器人实例"""
    return qq_bot