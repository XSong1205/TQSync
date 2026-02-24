"""
配置管理模块
支持从yaml文件和环境变量读取配置
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, Optional

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "config.yaml"):
        """
        初始化配置管理器
        
        Args:
            config_file (str): 配置文件路径
        """
        self.config_file = Path(config_file)
        self._config = {}
        self._load_config()
        self._load_env_vars()
    
    def _load_config(self):
        """加载yaml配置文件"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            raise FileNotFoundError(f"配置文件 {self.config_file} 不存在")
    
    def _load_env_vars(self):
        """加载环境变量"""
        # 加载.env文件
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(env_file)
        
        # 优先使用环境变量覆盖配置
        env_mappings = {
            'TELEGRAM_TOKEN': ('telegram', 'token'),
            'TELEGRAM_CHAT_ID': ('telegram', 'chat_id'),
            'QQ_GROUP_ID': ('qq', 'group_id'),
            'NAPCAT_WS_URL': ('qq', 'ws_url'),
            'NAPCAT_HTTP_URL': ('qq', 'http_url'),
            'LOG_LEVEL': ('logging', 'level')
        }
        
        for env_key, config_path in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value:
                self._set_nested_config(config_path, env_value)
    
    def _set_nested_config(self, path: tuple, value: Any):
        """设置嵌套配置值"""
        current = self._config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key_path (str): 配置键路径，用点分隔，如 "telegram.token"
            default (Any): 默认值
            
        Returns:
            Any: 配置值
        """
        keys = key_path.split('.')
        current = self._config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def get_telegram_config(self) -> Dict[str, Any]:
        """获取Telegram配置"""
        return {
            'token': self.get('telegram.token'),
            'chat_id': self.get('telegram.chat_id'),
            'proxy': self.get('telegram.proxy', {})
        }
    
    def get_qq_config(self) -> Dict[str, Any]:
        """获取QQ配置"""
        return {
            'ws_url': self.get('qq.ws_url'),
            'http_url': self.get('qq.http_url'),
            'group_id': self.get('qq.group_id')
        }
    
    def get_sync_config(self) -> Dict[str, Any]:
        """获取同步配置"""
        return {
            'bidirectional': self.get('sync.bidirectional', True),
            'filter_keywords': self.get('sync.filter_keywords', []),
            'max_message_length': self.get('sync.max_message_length', 4096),
            'cooldown_time': self.get('sync.cooldown_time', 1),
            'media': self.get('sync.media', {
                'enable': True,
                'supported_types': ['photo', 'video', 'audio', 'voice', 'document'],
                'max_file_size': 50,
                'temp_file_retention': 24
            }),
            'reply': self.get('sync.reply', {
                'enable': True,
                'format': '[{replier} 回复 {replied}] 原始消息：『{original_message}』，新回复：『{reply_message}』',
                'simple_format': '[回复 @{username}] {message}'
            }),
            'filter_prefix': self.get('sync.filter_prefix', '!')
        }
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return {
            'level': self.get('logging.level', 'INFO'),
            'file': self.get('logging.file', 'logs/bot.log')
        }
    
    def validate_config(self) -> bool:
        """
        验证必要配置是否存在
        
        Returns:
            bool: 配置是否有效
        """
        required_configs = [
            'telegram.token',
            'telegram.chat_id',
            'qq.ws_url',
            'qq.group_id'
        ]
        
        missing_configs = []
        for config_key in required_configs:
            if not self.get(config_key):
                missing_configs.append(config_key)
        
        if missing_configs:
            print(f"缺少必要配置: {', '.join(missing_configs)}")
            return False
        
        return True

# 全局配置实例
config_manager = ConfigManager()

def get_config() -> ConfigManager:
    """获取全局配置管理器实例"""
    return config_manager