"""
消息过滤前缀处理器
处理带有特定前缀的消息，阻止其同步到其他平台
"""

import re
from typing import Dict, Any, Tuple, Optional
from utils.logger import get_logger
from utils.config import get_config

logger = get_logger()

class FilterPrefixHandler:
    """消息过滤前缀处理器"""
    
    def __init__(self):
        """初始化过滤前缀处理器"""
        self.config = get_config()
        self.sync_config = self.config.get_sync_config()
        self.filter_prefix = self.sync_config.get('filter_prefix', '!')
        
    def should_filter_message(self, message_data: Dict[Any, Any]) -> Tuple[bool, Optional[str]]:
        """
        检查消息是否应该被过滤
        
        Args:
            message_data (dict): 消息数据
            
        Returns:
            tuple: (是否过滤, 处理后的消息内容)
        """
        try:
            text = message_data.get('text', '')
            if not text:
                return False, None
            
            # 检查是否以过滤前缀开头
            if text.startswith(self.filter_prefix):
                # 移除前缀
                filtered_text = text[len(self.filter_prefix):].strip()
                
                logger.info(f"检测到过滤前缀消息: {text[:50]}...")
                return True, filtered_text
            
            return False, None
            
        except Exception as e:
            logger.error(f"检查消息过滤时出错: {e}")
            return False, None
    
    def extract_command(self, message_data: Dict[Any, Any]) -> Optional[Dict[str, Any]]:
        """
        从过滤前缀消息中提取命令
        
        Args:
            message_data (dict): 消息数据
            
        Returns:
            dict: 命令信息，如果不是命令则返回None
        """
        try:
            filtered, filtered_text = self.should_filter_message(message_data)
            
            if not filtered or not filtered_text:
                return None
            
            # 解析命令
            command_parts = filtered_text.split()
            if not command_parts:
                return None
            
            command = command_parts[0].lower()
            args = command_parts[1:] if len(command_parts) > 1 else []
            
            return {
                'command': command,
                'args': args,
                'original_text': filtered_text,
                'platform': message_data.get('platform'),
                'from_user': message_data.get('from_user')
            }
            
        except Exception as e:
            logger.error(f"提取命令时出错: {e}")
            return None
    
    async def handle_command(self, command_info: Dict[str, Any]) -> Optional[str]:
        """
        处理命令
        
        Args:
            command_info (dict): 命令信息
            
        Returns:
            str: 命令响应，如果不需要响应则返回None
        """
        try:
            command = command_info.get('command')
            args = command_info.get('args', [])
            platform = command_info.get('platform')
            
            logger.info(f"处理{platform.upper()}命令: {command} {args}")
            
            # 内置命令处理
            if command == 'ping':
                return 'pong!'
            
            elif command == 'status':
                return self._get_status_info()
            
            elif command == 'stats':
                return self._get_stats_info()
            
            elif command == 'help':
                return self._get_help_info()
            
            elif command == 'filter':
                return self._handle_filter_command(args)
            
            else:
                return f"未知命令: {command}. 输入 !help 查看可用命令"
                
        except Exception as e:
            logger.error(f"处理命令时出错: {e}")
            return "命令处理出错"
    
    def _get_status_info(self) -> str:
        """获取状态信息"""
        return "✅ 机器人运行正常"
    
    def _get_stats_info(self) -> str:
        """获取统计信息"""
        # TODO: 从消息同步器获取真实统计数据
        return """
📊 同步统计:
• Telegram接收: 0
• QQ接收: 0
• Telegram发送: 0
• QQ发送: 0
• 已过滤: 0
        """.strip()
    
    def _get_help_info(self) -> str:
        """获取帮助信息"""
        return """
🤖 可用命令:
!ping - 测试机器人连通性
!status - 查看机器人状态
!stats - 查看同步统计
!help - 显示此帮助信息
!filter [add/remove/list] [关键词] - 管理消息过滤
        """.strip()
    
    def _handle_filter_command(self, args: list) -> str:
        """处理过滤命令"""
        if not args:
            return "用法: !filter [add|remove|list] [关键词]"
        
        action = args[0].lower()
        
        if action == 'list':
            # 显示当前过滤关键词
            filter_keywords = self.sync_config.get('filter_keywords', [])
            if filter_keywords:
                return f"当前过滤关键词: {', '.join(filter_keywords)}"
            else:
                return "没有设置过滤关键词"
        
        elif action in ['add', 'remove']:
            if len(args) < 2:
                return f"用法: !filter {action} [关键词]"
            
            keyword = args[1]
            filter_keywords = self.sync_config.get('filter_keywords', [])
            
            if action == 'add':
                if keyword not in filter_keywords:
                    filter_keywords.append(keyword)
                    # TODO: 保存到配置文件
                    return f"已添加过滤关键词: {keyword}"
                else:
                    return f"关键词已存在: {keyword}"
            
            elif action == 'remove':
                if keyword in filter_keywords:
                    filter_keywords.remove(keyword)
                    # TODO: 保存到配置文件
                    return f"已移除过滤关键词: {keyword}"
                else:
                    return f"关键词不存在: {keyword}"
        
        else:
            return "无效的操作，请使用 add/remove/list"

# 全局实例
filter_prefix_handler = FilterPrefixHandler()

def get_filter_prefix_handler() -> FilterPrefixHandler:
    """获取过滤前缀处理器实例"""
    return filter_prefix_handler