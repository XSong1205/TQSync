"""
消息同步核心模块
负责QQ和Telegram之间消息的双向同步
"""

import asyncio
import time
from typing import Dict, Any
from utils.logger import get_logger
from utils.config import get_config
from utils.filter_prefix import get_filter_prefix_handler
from utils.user_binding import get_user_binding_manager
from utils.message_id_mapper import get_message_id_mapper
from utils.media_handler import get_media_handler
from utils.stats_manager import get_stats_manager
from bots.telegram_bot import get_telegram_bot
from bots.qq_bot import get_qq_bot

logger = get_logger()

class MessageSync:
    """消息同步器"""
    
    def __init__(self):
        """初始化消息同步器"""
        self.config = get_config()
        self.sync_config = self.config.get_sync_config()
        
        # 机器人实例
        self.telegram_bot = None
        self.qq_bot = None
        
        # 消息缓存（防止重复转发）
        self.message_cache = {}
        self.cache_ttl = 300  # 缓存5分钟
        
        # 消息冷却时间控制
        self.last_send_times = {
            'telegram': 0,
            'qq': 0
        }
        
        # 统计信息
        self.stats = {
            'telegram_received': 0,
            'qq_received': 0,
            'telegram_sent': 0,
            'qq_sent': 0,
            'filtered': 0,
            'prefix_filtered': 0,
            'commands_processed': 0
        }
        
        # 过滤前缀处理器
        self.filter_prefix_handler = None
        
        # 媒体处理器
        self.media_handler = None
        
        # 用户绑定管理器
        self.user_binding_manager = None
        
        # 消息 ID 映射管理器
        self.message_id_mapper = None
                
        # 统计数据管理器
        self.stats_manager = None
    
    async def initialize(self):
        """初始化同步器"""
        try:
            # 获取机器人实例
            self.telegram_bot = await get_telegram_bot()
            self.qq_bot = await get_qq_bot()
            
            # 初始化用户绑定管理器
            self.user_binding_manager = await get_user_binding_manager()
            await self.user_binding_manager.initialize_database()
            await self.user_binding_manager.start_cleanup_task()
            
            # 初始化消息 ID 映射管理器
            self.message_id_mapper = await get_message_id_mapper()
            await self.message_id_mapper.start_cleanup_task()
                        
            # 初始化统计数据管理器
            self.stats_manager = await get_stats_manager()
                        
            # 设置消息回调
            self.telegram_bot.set_message_callback(self._on_telegram_message)
            self.qq_bot.set_message_callback(self._on_qq_message)
            
            logger.info("消息同步器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"消息同步器初始化失败: {e}")
            return False
    
    async def _on_telegram_message(self, message_data: Dict[Any, Any]):
        """处理来自 Telegram 的消息"""
        try:
            self.stats['telegram_received'] += 1
                
            # 定期更新统计数据到数据库
            if self.stats_manager and self.stats['telegram_received'] % 10 == 0:
                await self.stats_manager.update_stats(self.stats)
            
            # 检查是否需要转发到QQ
            if not self.sync_config.get('bidirectional', True):
                logger.debug("单向同步模式，不转发Telegram消息到QQ")
                return
            
            # 消息过滤检查
            if self._should_filter_message(message_data):
                self.stats['filtered'] += 1
                logger.debug("消息被过滤")
                return
            
            # 冷却时间检查
            if not self._check_cooldown('qq'):
                logger.debug("QQ发送冷却中")
                return
            
            message_type = message_data.get('type', 'text')
            
            if message_type == 'media':
                # 处理媒体消息
                await self._handle_telegram_media_message(message_data)
            else:
                # 处理文本消息
                await self._handle_telegram_text_message(message_data)
                
        except Exception as e:
            logger.error(f"处理Telegram消息时出错: {e}")
    
    async def _handle_telegram_text_message(self, message_data: Dict[Any, Any]):
        """处理Telegram文本消息"""
        try:
            # 格式化消息
            formatted_message = self._format_telegram_message(message_data)
            
            # 发送到QQ
            success = await self.qq_bot.send_group_message(formatted_message)
            if success:
                self.stats['qq_sent'] += 1
                self._update_send_time('qq')
                # 缓存消息ID防止重复
                self._cache_message_id('telegram', message_data.get('message_id'))
            else:
                logger.error("发送文本消息到QQ失败")
        except Exception as e:
            logger.error(f"处理Telegram文本消息时出错: {e}")
    
    async def _handle_telegram_media_message(self, message_data: Dict[Any, Any]):
        """处理 Telegram 媒体消息""" 
        try:
            media_type = message_data.get('media_type')
            file_url = message_data.get('file_url')
            caption = message_data.get('caption', '')
                
            logger.info(f"处理 Telegram 媒体消息：{media_type} - {file_url}")
            
            # 初始化媒体处理器
            if not self.media_handler:
                self.media_handler = await get_media_handler()
                await self.media_handler.initialize()
            
            # 特殊处理贴纸和 GIF
            if media_type in ['sticker', 'animation']:
                logger.info(f"正在处理特殊媒体类型：{media_type}")
                # 对于贴纸和 GIF，使用 document 类型下载
                local_file_path = await self.media_handler.download_media(
                    file_url, 
                    f"{media_type}_{message_data.get('message_id', '')}.webp"
                )
            else:
                # 下载媒体文件
                local_file_path = await self.media_handler.download_media(file_url)
            
            if not local_file_path:
                logger.error(f"下载 Telegram 媒体文件失败：{file_url}")
                # 如果下载失败，降级为文本格式
                formatted_message = self._format_telegram_media_message(message_data)
                success = await self.qq_bot.send_group_message(formatted_message)
                if success:
                    self.stats['qq_sent'] += 1
                    self._update_send_time('qq')
                    self._cache_message_id('telegram', message_data.get('message_id'))
                return
            
            logger.info(f"Telegram 媒体文件已下载到：{local_file_path}")
            
            # 使用新的 QQ 媒体发送功能
            qq_file_type = self._map_telegram_type_to_qq(media_type)
            logger.info(f"映射媒体类型：{media_type} -> {qq_file_type}")
            
            send_result = await self.qq_bot.send_media_message(
                local_file_path,
                qq_file_type,
                caption
            )
            
            if send_result:
                self.stats['qq_sent'] += 1
                self._update_send_time('qq')
                self._cache_message_id('telegram', message_data.get('message_id'))
                
                # 记录消息 ID 映射
                if self.message_id_mapper and send_result.get('message_id'):
                    await self.message_id_mapper.add_mapping(
                        'telegram', message_data.get('message_id'),
                        'qq', send_result.get('message_id')
                    )
                
                logger.info(f"Telegram 媒体消息已成功发送到 QQ: {send_result.get('message_id')}")
            else:
                logger.error("发送媒体文件到 QQ 失败，降级为文本格式")
                # 降级处理
                formatted_message = self._format_telegram_media_message(message_data)
                success = await self.qq_bot.send_group_message(formatted_message)
                if success:
                    self.stats['qq_sent'] += 1
                    self._update_send_time('qq')
                    self._cache_message_id('telegram', message_data.get('message_id'))
                    
        except Exception as e:
            logger.error(f"处理 Telegram 媒体消息时出错：{e}")
            import traceback
            traceback.print_exc()
    
    async def _on_qq_message(self, message_data: Dict[Any, Any]):
        """处理来自 QQ 的消息"""
        try:
            # 检查是否为事件消息
            if message_data.get('event_type') == 'message_delete':
                await self._handle_qq_message_delete(message_data)
                return
                
            self.stats['qq_received'] += 1
                
            # 定期更新统计数据到数据库
            if self.stats_manager and self.stats['qq_received'] % 10 == 0:
                await self.stats_manager.update_stats(self.stats)
            
            # 检查是否需要转发到Telegram
            if not self.sync_config.get('bidirectional', True):
                logger.debug("单向同步模式，不转发QQ消息到Telegram")
                return
            
            # 消息过滤检查
            if self._should_filter_message(message_data):
                self.stats['filtered'] += 1
                logger.debug("消息被过滤")
                return
            
            # 冷却时间检查
            if not self._check_cooldown('telegram'):
                logger.debug("Telegram发送冷却中")
                return
            
            message_type = message_data.get('type', 'text')
            
            if message_type == 'media':
                # 处理媒体消息
                await self._handle_qq_media_message(message_data)
            else:
                # 处理文本消息
                await self._handle_qq_text_message(message_data)
                
        except Exception as e:
            logger.error(f"处理QQ消息时出错: {e}")
    
    async def _handle_qq_message_delete(self, event_data: Dict[Any, Any]):
        """处理QQ消息撤回事件"""
        try:
            message_id = event_data.get('message_id')
            operator_id = event_data.get('operator_id')
            user_id = event_data.get('user_id')
            group_id = event_data.get('group_id')
            
            logger.info(f"[QQ] 处理消息撤回事件 - 消息ID: {message_id}, 操作者: {operator_id}")
            
            # 尝试精准同步：查找绑定的Telegram用户并删除其消息
            if self.user_binding_manager and user_id:
                bound_tg_user = self.user_binding_manager.get_bound_user('qq', str(user_id))
                if bound_tg_user and self.message_id_mapper:
                    # 查找对应的消息ID映射
                    target_message_id = self.message_id_mapper.get_target_message_id(
                        'qq', message_id, 'telegram'
                    )
                    
                    if target_message_id:
                        # 尝试精准删除Telegram消息
                        delete_success = await self.telegram_bot.delete_message(target_message_id)
                        if delete_success:
                            notification_message = f"[QQ消息撤回] ✅ 已同步删除绑定用户 {operator_id} 的消息"
                            logger.info(f"[QQ] 精准撤回成功: QQ({message_id}) → Telegram({target_message_id})")
                            # 移除消息ID映射
                            self.message_id_mapper.remove_mapping('qq', message_id)
                        else:
                            notification_message = f"[QQ消息撤回] ⚠️ 无法删除绑定用户 {operator_id} 的消息（可能已过期）"
                            logger.warning(f"[QQ] 精准撤回失败: Telegram消息 {target_message_id} 删除失败")
                    else:
                        # 未找到映射关系，发送通知
                        notification_message = f"[QQ消息撤回] ⚠️ 未找到绑定用户 {operator_id} 对应的Telegram消息"
                        logger.info(f"[QQ] 未找到消息映射: QQ({message_id})")
                elif bound_tg_user:
                    # 有绑定但无映射管理器
                    notification_message = f"[QQ消息撤回] ⚠️ 绑定用户 {operator_id} 的消息无法精准删除（缺少映射）"
                    logger.warning(f"[QQ] 有绑定但无映射管理器")
                else:
                    # 未绑定用户，发送普通通知
                    notification_message = f"[QQ消息撤回] 用户 {operator_id} 撤回了一条消息"
                    logger.info(f"[QQ] 未绑定用户，发送普通通知")
            else:
                # 没有绑定管理器或用户ID，发送普通通知
                notification_message = f"[QQ消息撤回] 用户 {operator_id} 撤回了一条消息"
                logger.info(f"[QQ] 无绑定管理器，发送普通通知")
            
            # 发送到Telegram
            success = await self.telegram_bot.send_message(notification_message)
            if success:
                logger.info(f"[QQ] 撤回通知已发送到Telegram")
                self.stats['telegram_sent'] += 1
            else:
                logger.error("[QQ] 发送撤回通知到Telegram失败")
                
        except Exception as e:
            logger.error(f"处理QQ消息撤回事件时出错: {e}")
    
    async def _handle_qq_text_message(self, message_data: Dict[Any, Any]):
        """处理 QQ 文本消息"""
        try:
            logger.debug(f"[QQ 消息] message_data: {message_data}")
                
            message_type = message_data.get('type', 'text')
            
            if message_type == 'forward':
                # 处理转发消息
                await self._handle_qq_forward_message(message_data)
            else:
                # 检查是否为回复消息
                reply_to_message_id = message_data.get('reply_to_message_id')
                                        
                # 使用原生回复功能发送
                formatted_message = self._format_qq_message(message_data)
                sent_message = await self.telegram_bot.send_message_with_result(
                    text=formatted_message,
                    reply_to_message_id=reply_to_message_id
                )
                            
                if sent_message:
                    self.stats['telegram_sent'] += 1
                    self._update_send_time('telegram')
                    # 缓存消息 ID 防止重复
                    self._cache_message_id('qq', message_data.get('message_id'))
                                
                    # 记录消息 ID 映射
                    telegram_message_id = sent_message.message_id
                    qq_message_id = message_data.get('message_id')
                    if self.message_id_mapper and telegram_message_id and qq_message_id:
                        success = self.message_id_mapper.add_mapping(
                            'qq', qq_message_id,
                            'telegram', telegram_message_id
                        )
                        if success:
                            logger.info(f"[ID 映射] QQ({qq_message_id}) → Telegram({telegram_message_id})")
                        else:
                            logger.error(f"[ID 映射] 添加失败：QQ({qq_message_id}) → Telegram({telegram_message_id})")
                    else:
                        logger.warning(f"[ID 映射] 无法添加映射：mapper={self.message_id_mapper is not None}, tg_id={telegram_message_id}, qq_id={qq_message_id}")
                else:
                    logger.error("发送文本消息到 Telegram 失败")
        except Exception as e:
            logger.error(f"处理QQ文本消息时出错: {e}")
    
    async def _handle_qq_forward_message(self, message_data: Dict[Any, Any]):
        """处理QQ转发消息"""
        try:
            forward_messages = message_data.get('forward_messages', [])
            if not forward_messages:
                logger.warning("转发消息为空")
                return
            
            # 初始化转发解析器
            from utils.forward_parser import get_forward_parser
            forward_parser = get_forward_parser()
            
            # 格式化为Telegram消息
            formatted_messages = forward_parser.format_for_telegram(forward_messages)
            
            # 逐条发送到Telegram
            success_count = 0
            for i, formatted_msg in enumerate(formatted_messages):
                success = await self.telegram_bot.send_message(formatted_msg)
                if success:
                    success_count += 1
                    self.stats['telegram_sent'] += 1
                await asyncio.sleep(0.2)  # 妈了个逼的我说怎么有这么大延迟，调低了
            
            self._update_send_time('telegram')
            self._cache_message_id('qq', message_data.get('message_id'))
            
            logger.info(f"转发消息发送完成: {success_count}/{len(formatted_messages)} 条成功")
            
        except Exception as e:
            logger.error(f"处理QQ转发消息时出错: {e}")
    
    async def _handle_qq_media_message(self, message_data: Dict[Any, Any]):
        """处理QQ媒体消息"""
        try:
            media_type = message_data.get('media_type')
            file_url = message_data.get('file_url')
            file_name = message_data.get('file_name', '')
            
            logger.info(f"处理QQ媒体消息: {media_type} - {file_url}")
            
            # 初始化媒体处理器
            if not self.media_handler:
                self.media_handler = await get_media_handler()
                await self.media_handler.initialize()
            
            # 下载媒体文件
            local_file_path = await self.media_handler.download_media(file_url, file_name)
            if not local_file_path:
                logger.error(f"下载媒体文件失败: {file_url}")
                # 如果下载失败，降级为文本格式
                formatted_message = self._format_qq_media_message(message_data)
                success = await self.telegram_bot.send_message(formatted_message)
                if success:
                    self.stats['telegram_sent'] += 1
                    self._update_send_time('telegram')
                    self._cache_message_id('qq', message_data.get('message_id'))
                return
            
            # 上传到Telegram
            telegram_file_type = self._map_media_type_to_telegram(media_type)
            upload_result = await self.media_handler.upload_to_telegram(
                local_file_path, 
                str(self.telegram_bot.chat_id), 
                telegram_file_type
            )
            
            if upload_result and upload_result.get('success'):
                self.stats['telegram_sent'] += 1
                self._update_send_time('telegram')
                self._cache_message_id('qq', message_data.get('message_id'))
                logger.info(f"QQ媒体消息已成功上传到Telegram: {upload_result.get('message_id')}")
            else:
                logger.error("上传媒体文件到Telegram失败，降级为文本格式")
                # 降级处理
                formatted_message = self._format_qq_media_message(message_data)
                success = await self.telegram_bot.send_message(formatted_message)
                if success:
                    self.stats['telegram_sent'] += 1
                    self._update_send_time('telegram')
                    self._cache_message_id('qq', message_data.get('message_id'))
                
        except Exception as e:
            logger.error(f"处理QQ媒体消息时出错: {e}")
    
    def _should_filter_message(self, message_data: Dict[Any, Any]) -> bool:
        """检查消息是否应该被过滤"""
        try:
            # 对于媒体消息，不需要检查文本内容
            message_type = message_data.get('type', 'text')
            if message_type == 'media':
                return False
            
            text = message_data.get('text', '')
            if not text:
                return True
            
            # 初始化过滤前缀处理器
            if not self.filter_prefix_handler:
                self.filter_prefix_handler = get_filter_prefix_handler()
            
            # 检查过滤前缀
            should_filter, filtered_text = self.filter_prefix_handler.should_filter_message(message_data)
            if should_filter:
                self.stats['prefix_filtered'] += 1
                logger.info(f"消息被过滤前缀过滤: {text[:50]}...")
                
                # 处理命令
                command_info = self.filter_prefix_handler.extract_command(message_data)
                if command_info:
                    # 异步处理命令
                    asyncio.create_task(self._handle_command_response(message_data, command_info))
                
                return True
            
            # 检查绑定相关命令
            if self._is_binding_command(text):
                logger.info(f"检测到绑定命令：{text}")
                asyncio.create_task(self._handle_binding_command(message_data))
                return True
            
            # 检查关键词过滤
            filter_keywords = self.sync_config.get('filter_keywords', [])
            for keyword in filter_keywords:
                if keyword.lower() in text.lower():
                    self.stats['filtered'] += 1
                    return True
            
            # 检查消息长度
            max_length = self.sync_config.get('max_message_length', 4096)
            if len(text) > max_length:
                logger.warning(f"消息长度超过限制: {len(text)} > {max_length}")
                self.stats['filtered'] += 1
                return True
            
            # 检查是否为重复消息
            platform = message_data.get('platform')
            message_id = message_data.get('message_id')
            if self._is_message_cached(platform, message_id):
                logger.debug("检测到重复消息")
                self.stats['filtered'] += 1
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"消息过滤检查出错: {e}")
            return True
    
    async def _handle_command_response(self, original_message: Dict[Any, Any], command_info: Dict[str, Any]):
        """处理命令响应"""
        try:
            # 处理命令
            response = await self.filter_prefix_handler.handle_command(command_info)
            
            if response:
                self.stats['commands_processed'] += 1
                platform = original_message.get('platform')
                
                # 发送响应到原平台
                if platform == 'telegram':
                    await self.telegram_bot.send_message(response, reply_to_message_id=original_message.get('message_id'))
                elif platform == 'qq':
                    # QQ回复需要特殊处理
                    formatted_response = f"[命令响应] {response}"
                    await self.qq_bot.send_group_message(formatted_response)
                
                logger.info(f"已处理{platform.upper()}命令: {command_info.get('command')}")
                
        except Exception as e:
            logger.error(f"处理命令响应时出错: {e}")
    
    def _is_binding_command(self, text: str) -> bool:
        """检查是否为绑定相关命令"""
        text_lower = text.lower().strip()
        return text_lower.startswith('!bind') or text_lower.startswith('！bind')
    
    async def _handle_binding_command(self, message_data: Dict[Any, Any]):
        """处理绑定命令"""
        try:
            platform = message_data.get('platform')
            text = message_data.get('text', '').strip()
            
            # 获取用户ID
            if platform == 'telegram':
                user_id = str(message_data.get('from_user', {}).get('id'))
            else:  # qq
                user_id = str(message_data.get('sender', {}).get('user_id'))
            
            if not user_id:
                logger.warning(f"无法获取{platform.upper()}用户ID")
                return
            
            # 解析命令
            parts = text.split()
            if len(parts) == 1:
                # 发起绑定：!bind
                result = await self.user_binding_manager.initiate_binding(platform, user_id)
            elif len(parts) == 2:
                # 完成绑定：!bind ABCD1234
                verification_code = parts[1].upper()
                result = await self.user_binding_manager.complete_binding(platform, user_id, verification_code)
            else:
                result = {
                    'success': False,
                    'message': '❌ 命令格式错误，请使用：!bind 或 !bind [验证码]'
                }
            
            # 发送响应
            if result['success']:
                await self._send_binding_response(platform, message_data, result['message'], success=True)
            else:
                await self._send_binding_response(platform, message_data, result['message'], success=False)
                
        except Exception as e:
            logger.error(f"处理绑定命令时出错: {e}")
            error_msg = "❌ 处理绑定命令时发生错误，请稍后重试"
            await self._send_binding_response(
                message_data.get('platform'), 
                message_data, 
                error_msg, 
                success=False
            )
    
    async def _send_binding_response(self, platform: str, original_message: Dict[Any, Any], 
                                   message: str, success: bool = True):
        """发送绑定响应消息"""
        try:
            if platform == 'telegram':
                # Telegram响应
                reply_to_id = original_message.get('message_id')
                await self.telegram_bot.send_message(
                    text=message,
                    reply_to_message_id=reply_to_id
                )
            else:
                # QQ响应
                await self.qq_bot.send_group_message(f"[账号绑定] {message}")
                
            status = "成功" if success else "失败"
            logger.info(f"[{platform.upper()}] 发送绑定响应 {status}: {message}")
            
        except Exception as e:
            logger.error(f"发送绑定响应时出错: {e}")
    
    def _format_telegram_message(self, message_data: Dict[Any, Any]) -> str:
        """格式化 Telegram 消息为 QQ 格式"""
        try:
            sender = message_data.get('from_user', {})
            username = sender.get('username') or sender.get('first_name', 'Unknown')
            text = message_data.get('text', '')
            
            # 清理用户名中的特殊字符
            username = self._clean_username(username)
            
            return f"[TG] {username}: {text}"
            
        except Exception as e:
            logger.error(f"格式化 Telegram 消息出错：{e}")
            return f"[TG] Unknown: {message_data.get('text', '')}"
    
    def _format_qq_message(self, message_data: Dict[Any, Any]) -> str:
        """格式化 QQ 消息为 Telegram 格式"""
        try:
            sender = message_data.get('sender', {})
            nickname = sender.get('card') or sender.get('nickname', 'Unknown')
            text = message_data.get('text', '')
            
            # 清理昵称中的特殊字符
            nickname = self._clean_username(nickname)
            
            return f"[QQ] {nickname}: {text}"
            
        except Exception as e:
            logger.error(f"格式化 QQ 消息出错：{e}")
            return f"[QQ] Unknown: {message_data.get('text', '')}"
    
    def _format_telegram_media_message(self, message_data: Dict[Any, Any]) -> str:
        """格式化 Telegram 媒体消息为 QQ 格式"""
        try:
            sender = message_data.get('from_user', {})
            username = sender.get('username') or sender.get('first_name', 'Unknown')
            media_type = message_data.get('media_type', 'media')
            caption = message_data.get('caption', '')
            
            # 清理用户名中的特殊字符
            username = self._clean_username(username)
            
            # 构造媒体消息格式
            if caption:
                formatted = f"[TG-{media_type.upper()}] {username}: {caption}"
            else:
                formatted = f"[TG-{media_type.upper()}] {username} 发送了一个{media_type}"
            
            return formatted
            
        except Exception as e:
            logger.error(f"格式化Telegram媒体消息出错: {e}")
            return f"[TG-MEDIA] Unknown 发送了一个媒体文件"
    
    def _format_qq_media_message(self, message_data: Dict[Any, Any]) -> str:
        """格式化QQ媒体消息"""
        try:
            sender = message_data.get('sender', {})
            nickname = sender.get('card') or sender.get('nickname', 'Unknown')
            media_type = message_data.get('media_type', 'media')
            file_name = message_data.get('file_name', '')
            
            # 清理昵称中的特殊字符
            nickname = self._clean_username(nickname)
            
            # 构造媒体消息格式
            if file_name:
                formatted = f"[QQ-{media_type.upper()}] {nickname}: {file_name}"
            else:
                formatted = f"[QQ-{media_type.upper()}] {nickname} 发送了一个{media_type}"
            
            return formatted
            
        except Exception as e:
            logger.error(f"格式化QQ媒体消息出错: {e}")
            return f"[QQ-MEDIA] Unknown 发送了一个媒体文件"
    
    async def _find_telegram_reply_target(self, replied_to_user: Any, replied_to_message: Optional[str]) -> Optional[int]:
        """
        查找被回复的Telegram消息ID
        
        Args:
            replied_to_user: 被回复的用户信息
            replied_to_message: 被回复的消息内容
            
        Returns:
            int: Telegram消息ID，如果找不到则返回None
        """
        try:
            # 这是一个简化的实现
            # 在实际应用中，你可能需要维护一个消息映射表
            # 来跟踪QQ消息和Telegram消息之间的对应关系
            
            # 目前返回None，让Telegram使用文本格式化而非原生回复
            # 后续可以扩展为智能匹配逻辑
            logger.debug(f"查找Telegram回复目标: {replied_to_user}, {replied_to_message}")
            return None
            
        except Exception as e:
            logger.error(f"查找Telegram回复目标时出错: {e}")
            return None
    
    async def _find_qq_reply_target(self, replied_to_user: Any, replied_to_message: Optional[str]) -> Optional[int]:
        """
        查找被回复的 QQ 消息 ID
        
        Args:
            replied_to_user: 被回复的用户信息
            replied_to_message: 被回复的消息内容
            
        Returns:
            int: QQ 消息 ID，如果找不到则返回 None
        """
        try:
            # 使用 NapCat API 的 get_msg 接口获取消息详情
            # 通过消息内容和用户信息匹配找到对应的消息 ID
            if not self.qq_bot or not self.qq_bot.session:
                logger.debug("QQ Bot 未初始化")
                return None
            
            # 如果是从消息映射中查找（推荐方式）
            # 这里应该使用 message_id_mapper 来查找
            # 但由于参数限制，我们采用另一种策略
            
            logger.debug(f"查找 QQ 回复目标：用户={replied_to_user}, 消息={replied_to_message}")
            
            # 方案 1: 从最近的聊天记录中查找匹配的消息
            # 使用 get_group_msg_history API 获取群聊历史消息
            group_id = self.qq_bot.group_id
            
            try:
                url = f"{self.qq_bot.http_url}/get_group_msg_history"
                payload = {
                    'group_id': int(group_id),
                    'count': 20  # 获取最近 20 条消息
                }
                
                async with self.qq_bot.session.post(url, json=payload, 
                                                  timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('status') == 'ok':
                            messages = result.get('data', {}).get('messages', [])
                            
                            # 遍历历史消息，查找匹配的消息
                            for msg in reversed(messages):  # 从旧到新排序
                                msg_sender = msg.get('sender', {})
                                msg_user_id = str(msg_sender.get('user_id', ''))
                                msg_content = msg.get('raw_message', '')
                                msg_id = msg.get('message_id')
                                
                                # 检查是否匹配
                                user_match = (str(replied_to_user) == msg_user_id)
                                content_match = (replied_to_message and replied_to_message in msg_content)
                                
                                if user_match and content_match:
                                    logger.info(f"找到匹配的 QQ 消息：ID={msg_id}")
                                    return msg_id
                            
                            logger.warning(f"未在历史消息中找到匹配的消息")
                        else:
                            logger.error(f"获取群历史消息失败：{result}")
                    else:
                        logger.error(f"HTTP 请求失败：{response.status}")
                        
            except Exception as e:
                logger.error(f"查询群历史消息时出错：{e}")
            
            # 方案 2: 如果无法通过历史消息找到，返回 None
            # 让上层使用文本格式化而非原生回复
            return None
            
        except Exception as e:
            logger.error(f"查找 QQ 回复目标时出错：{e}")
            return None
    
    def _clean_username(self, username: str) -> str:
        """清理用户名中的特殊字符"""
        if not username:
            return "Unknown"
        
        # 移除可能导致格式问题的字符，但保留下划线用于格式化变量
        forbidden_chars = ['*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        cleaned = username
        for char in forbidden_chars:
            cleaned = cleaned.replace(char, '')
        
        return cleaned.strip() or "Unknown"
    
    def _map_media_type_to_telegram(self, qq_media_type: str) -> str:
        """将QQ媒体类型映射到Telegram文件类型"""
        mapping = {
            'image': 'photo',
            'photo': 'photo',
            'video': 'video',
            'record': 'voice',  # QQ语音对应Telegram语音
            'voice': 'voice',
            'audio': 'audio',
            'file': 'document'
        }
        return mapping.get(qq_media_type.lower(), 'document')
    
    def _map_telegram_type_to_qq(self, telegram_media_type: str) -> str:
        """将 Telegram 媒体类型映射到 QQ 文件类型"""
        mapping = {
            'photo': 'image',
            'video': 'video',
            'audio': 'audio',
            'voice': 'record',
            'document': 'file',
            'sticker': 'image',  # 贴纸作为图片发送
            'animation': 'image'  # GIF 作为图片发送
        }
        return mapping.get(telegram_media_type.lower(), 'file')
    
    def _check_cooldown(self, platform: str) -> bool:
        """检查发送冷却时间"""
        current_time = time.time()
        last_send = self.last_send_times.get(platform, 0)
        cooldown = self.sync_config.get('cooldown_time', 1)
        
        return current_time - last_send >= cooldown
    
    def _update_send_time(self, platform: str):
        """更新最后发送时间"""
        self.last_send_times[platform] = time.time()
    
    def _cache_message_id(self, platform: str, message_id):
        """缓存消息ID"""
        cache_key = f"{platform}:{message_id}"
        self.message_cache[cache_key] = time.time()
    
    def _is_message_cached(self, platform: str, message_id) -> bool:
        """检查消息是否已在缓存中"""
        cache_key = f"{platform}:{message_id}"
        cached_time = self.message_cache.get(cache_key, 0)
        
        # 清理过期缓存
        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self.message_cache.items()
            if current_time - timestamp > self.cache_ttl
        ]
        for key in expired_keys:
            del self.message_cache[key]
        
        return cache_key in self.message_cache
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        stats = self.stats.copy()
        
        # 添加计算字段
        total_received = stats['telegram_received'] + stats['qq_received']
        total_sent = stats['telegram_sent'] + stats['qq_sent']
        total_filtered = stats['filtered'] + stats['prefix_filtered']
        
        stats.update({
            'total_received': total_received,
            'total_sent': total_sent,
            'total_filtered': total_filtered,
            'sync_rate': round((total_sent / total_received * 100) if total_received > 0 else 0, 2)
        })
        
        return stats
    
    async def start(self):
        """启动消息同步"""
        try:
            logger.info("启动消息同步服务...")
            
            # 初始化
            if not await self.initialize():
                raise Exception("初始化失败")
            
            # 创建任务列表
            tasks = []
            
            # 启动QQ机器人
            qq_task = asyncio.create_task(self.qq_bot.start())
            tasks.append(qq_task)
            
            # 启动Telegram机器人
            telegram_task = asyncio.create_task(self.telegram_bot.start())
            tasks.append(telegram_task)
            
            # 等待任意一个任务完成
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            # 取消剩余任务
            for task in pending:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
        except Exception as e:
            logger.error(f"启动消息同步服务失败: {e}")
            raise
    
    async def stop(self):
        """停止消息同步"""
        try:
            if self.telegram_bot:
                await self.telegram_bot.stop()
            if self.qq_bot:
                await self.qq_bot.stop()
            
            # 停止用户绑定管理器
            if self.user_binding_manager:
                await self.user_binding_manager.stop_cleanup_task()
                
            logger.info("消息同步服务已停止")
        except Exception as e:
            logger.error(f"停止消息同步服务失败: {e}")

# 全局实例
message_sync = MessageSync()

async def get_message_sync() -> MessageSync:
    """获取消息同步器实例"""
    return message_sync