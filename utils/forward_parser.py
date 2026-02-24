"""
QQ合并转发消息解析器
解析QQ合并转发消息并转换为适合Telegram的格式
"""

import json
import time
from typing import Dict, Any, List, Optional
from utils.logger import get_logger

logger = get_logger()

class ForwardMessageParser:
    """QQ合并转发消息解析器"""
    
    def __init__(self):
        """初始化解析器"""
        pass
    
    def is_forward_message(self, message_data: Dict[Any, Any]) -> bool:
        """
        判断是否为合并转发消息
        
        Args:
            message_data (dict): 消息数据
            
        Returns:
            bool: 是否为合并转发消息
        """
        try:
            raw_data = message_data.get('raw_data', {})
            message_elements = raw_data.get('message', [])
            
            # 检查是否有forward节点
            for element in message_elements:
                if isinstance(element, dict) and element.get('type') == 'forward':
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"判断合并转发消息时出错: {e}")
            return False
    
    def parse_forward_message(self, message_data: Dict[Any, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        解析合并转发消息
        
        Args:
            message_data (dict): 消息数据
            
        Returns:
            list: 解析后的消息列表，每个元素包含用户信息和消息内容
        """
        try:
            if not self.is_forward_message(message_data):
                return None
            
            raw_data = message_data.get('raw_data', {})
            message_elements = raw_data.get('message', [])
            
            forward_messages = []
            
            # 查找forward节点
            for element in message_elements:
                if isinstance(element, dict) and element.get('type') == 'forward':
                    content = element.get('data', {}).get('content', [])
                    
                    # 解析转发内容
                    for item in content:
                        parsed_message = self._parse_forward_item(item)
                        if parsed_message:
                            forward_messages.append(parsed_message)
            
            if forward_messages:
                logger.info(f"解析到 {len(forward_messages)} 条转发消息")
                return forward_messages
            else:
                logger.warning("未解析到有效的转发消息")
                return None
                
        except Exception as e:
            logger.error(f"解析合并转发消息时出错: {e}")
            return None
    
    def _parse_forward_item(self, item: Dict[Any, Any]) -> Optional[Dict[str, Any]]:
        """
        解析单个转发项
        
        Args:
            item (dict): 转发项数据
            
        Returns:
            dict: 解析后的消息信息
        """
        try:
            # 提取基本信息
            nickname = item.get('nickname', 'Unknown')
            user_id = item.get('user_id', '')
            message_time = item.get('time', 0)
            message_content = item.get('message', [])
            
            # 提取消息文本
            text_content = self._extract_text_from_message(message_content)
            
            if not text_content:
                return None
            
            # 转换时间戳
            formatted_time = self._format_timestamp(message_time)
            
            return {
                'nickname': nickname,
                'user_id': user_id,
                'timestamp': message_time,
                'formatted_time': formatted_time,
                'text': text_content,
                'raw_item': item
            }
            
        except Exception as e:
            logger.error(f"解析转发项时出错: {e}")
            return None
    
    def _extract_text_from_message(self, message_content) -> str:
        """
        从消息内容中提取文本
        
        Args:
            message_content: 消息内容
            
        Returns:
            str: 提取的文本内容
        """
        try:
            if isinstance(message_content, str):
                return message_content
            
            text_parts = []
            
            if isinstance(message_content, list):
                for element in message_content:
                    if isinstance(element, dict):
                        if element.get('type') == 'text':
                            text_parts.append(element.get('data', {}).get('text', ''))
                    elif isinstance(element, str):
                        text_parts.append(element)
            
            return ''.join(text_parts).strip()
            
        except Exception as e:
            logger.error(f"提取消息文本时出错: {e}")
            return ""
    
    def _format_timestamp(self, timestamp: int) -> str:
        """
        格式化时间戳
        
        Args:
            timestamp (int): Unix时间戳
            
        Returns:
            str: 格式化的时间字符串
        """
        try:
            if timestamp <= 0:
                return "未知时间"
            
            # 转换为本地时间
            import datetime
            dt = datetime.datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
            
        except Exception as e:
            logger.error(f"格式化时间戳时出错: {e}")
            return "时间格式化失败"
    
    def format_for_telegram(self, forward_messages: List[Dict[str, Any]]) -> List[str]:
        """
        将解析的转发消息格式化为Telegram格式
        
        Args:
            forward_messages (list): 解析后的转发消息列表
            
        Returns:
            list: 格式化后的消息列表
        """
        try:
            formatted_messages = []
            
            for i, msg in enumerate(forward_messages, 1):
                # 格式化单条消息
                formatted = (
                    f"[转发消息 {i}/{len(forward_messages)}]\n"
                    f"👤 {msg['nickname']} ({msg['formatted_time']})\n"
                    f"💬 {msg['text']}"
                )
                formatted_messages.append(formatted)
            
            return formatted_messages
            
        except Exception as e:
            logger.error(f"格式化转发消息时出错: {e}")
            return []
    
    def format_for_qq(self, forward_messages: List[Dict[str, Any]]) -> List[str]:
        """
        将解析的转发消息格式化为QQ格式
        
        Args:
            forward_messages (list): 解析后的转发消息列表
            
        Returns:
            list: 格式化后的消息列表
        """
        try:
            formatted_messages = []
            
            for i, msg in enumerate(forward_messages, 1):
                # 格式化单条消息
                formatted = (
                    f"[转发 {i}/{len(forward_messages)}] "
                    f"{msg['nickname']}: {msg['text']}"
                )
                formatted_messages.append(formatted)
            
            return formatted_messages
            
        except Exception as e:
            logger.error(f"格式化转发消息时出错: {e}")
            return []

# 全局实例
forward_parser = ForwardMessageParser()

def get_forward_parser() -> ForwardMessageParser:
    """获取转发消息解析器实例"""
    return forward_parser