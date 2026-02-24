"""
消息ID映射管理模块
负责维护跨平台消息ID的映射关系，实现精准消息撤回
"""

import asyncio
import time
from typing import Dict, Any, Optional, Tuple
from utils.logger import get_logger

logger = get_logger()

class MessageIdMapper:
    """消息ID映射管理器"""
    
    def __init__(self):
        """初始化映射管理器"""
        # 存储消息ID映射 {source_platform:message_id: {target_platform: target_message_id, timestamp: float}}
        self.id_mappings = {}
        
        # 存储反向映射 {target_platform:target_message_id: source_info}
        self.reverse_mappings = {}
        
        # 映射有效期（秒）- 与消息撤回时间窗口匹配
        self.mapping_ttl = 172800  # 48小时（Telegram消息撤回限制）
        
        # 清理任务
        self.cleanup_task = None
        
        # 统计信息
        self.stats = {
            'total_mappings': 0,
            'active_mappings': 0,
            'expired_mappings': 0,
            'mapping_requests': 0,
            'mapping_success': 0
        }
    
    async def start_cleanup_task(self):
        """启动清理过期映射的任务"""
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_mappings())
    
    async def stop_cleanup_task(self):
        """停止清理任务"""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
    
    def add_mapping(self, source_platform: str, source_message_id: Any, 
                   target_platform: str, target_message_id: Any) -> bool:
        """
        添加消息ID映射
        
        Args:
            source_platform: 源平台 (qq/telegram)
            source_message_id: 源消息ID
            target_platform: 目标平台 (qq/telegram)  
            target_message_id: 目标消息ID
            
        Returns:
            bool: 是否添加成功
        """
        try:
            self.stats['mapping_requests'] += 1
            
            # 创建映射键
            source_key = f"{source_platform}:{source_message_id}"
            target_key = f"{target_platform}:{target_message_id}"
            
            current_time = time.time()
            
            # 添加正向映射
            self.id_mappings[source_key] = {
                'target_platform': target_platform,
                'target_message_id': target_message_id,
                'timestamp': current_time,
                'source_platform': source_platform,
                'source_message_id': source_message_id
            }
            
            # 添加反向映射
            self.reverse_mappings[target_key] = {
                'source_platform': source_platform,
                'source_message_id': source_message_id,
                'timestamp': current_time,
                'target_platform': target_platform,
                'target_message_id': target_message_id
            }
            
            self.stats['total_mappings'] += 1
            self.stats['active_mappings'] += 1
            self.stats['mapping_success'] += 1
            
            logger.debug(f"添加消息映射: {source_key} ↔ {target_key}")
            return True
            
        except Exception as e:
            logger.error(f"添加消息映射失败: {e}")
            return False
    
    def get_target_message_id(self, source_platform: str, source_message_id: Any,
                            target_platform: str) -> Optional[Any]:
        """
        根据源消息ID获取目标消息ID
        
        Args:
            source_platform: 源平台
            source_message_id: 源消息ID
            target_platform: 目标平台
            
        Returns:
            Optional[Any]: 目标消息ID，如果不存在则返回None
        """
        try:
            source_key = f"{source_platform}:{source_message_id}"
            mapping = self.id_mappings.get(source_key)
            
            if not mapping:
                logger.debug(f"未找到源消息映射: {source_key}")
                return None
            
            # 检查平台匹配
            if mapping['target_platform'] != target_platform:
                logger.debug(f"平台不匹配: 期望{target_platform}, 实际{mapping['target_platform']}")
                return None
            
            # 检查是否过期
            if time.time() - mapping['timestamp'] > self.mapping_ttl:
                logger.debug(f"映射已过期: {source_key}")
                self._remove_expired_mapping(source_key)
                return None
            
            return mapping['target_message_id']
            
        except Exception as e:
            logger.error(f"获取目标消息ID失败: {e}")
            return None
    
    def get_source_message_info(self, target_platform: str, target_message_id: Any) -> Optional[Dict[str, Any]]:
        """
        根据目标消息ID获取源消息信息
        
        Args:
            target_platform: 目标平台
            target_message_id: 目标消息ID
            
        Returns:
            Optional[Dict]: 源消息信息，如果不存在则返回None
        """
        try:
            target_key = f"{target_platform}:{target_message_id}"
            mapping = self.reverse_mappings.get(target_key)
            
            if not mapping:
                return None
            
            # 检查是否过期
            if time.time() - mapping['timestamp'] > self.mapping_ttl:
                self._remove_expired_reverse_mapping(target_key)
                return None
            
            return {
                'source_platform': mapping['source_platform'],
                'source_message_id': mapping['source_message_id'],
                'timestamp': mapping['timestamp']
            }
            
        except Exception as e:
            logger.error(f"获取源消息信息失败: {e}")
            return None
    
    def remove_mapping(self, source_platform: str, source_message_id: Any) -> bool:
        """
        移除消息映射
        
        Args:
            source_platform: 源平台
            source_message_id: 源消息ID
            
        Returns:
            bool: 是否移除成功
        """
        try:
            source_key = f"{source_platform}:{source_message_id}"
            
            if source_key in self.id_mappings:
                mapping = self.id_mappings[source_key]
                target_key = f"{mapping['target_platform']}:{mapping['target_message_id']}"
                
                # 移除双向映射
                del self.id_mappings[source_key]
                if target_key in self.reverse_mappings:
                    del self.reverse_mappings[target_key]
                
                self.stats['active_mappings'] -= 1
                logger.debug(f"移除消息映射: {source_key}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"移除消息映射失败: {e}")
            return False
    
    async def _cleanup_expired_mappings(self):
        """定期清理过期的映射"""
        try:
            while True:
                await asyncio.sleep(3600)  # 每小时检查一次
                
                current_time = time.time()
                expired_count = 0
                
                # 清理正向映射
                expired_keys = []
                for key, mapping in self.id_mappings.items():
                    if current_time - mapping['timestamp'] > self.mapping_ttl:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    self._remove_expired_mapping(key)
                    expired_count += 1
                
                # 清理反向映射
                expired_reverse_keys = []
                for key, mapping in self.reverse_mappings.items():
                    if current_time - mapping['timestamp'] > self.mapping_ttl:
                        expired_reverse_keys.append(key)
                
                for key in expired_reverse_keys:
                    del self.reverse_mappings[key]
                    expired_count += 1
                
                if expired_count > 0:
                    self.stats['expired_mappings'] += expired_count
                    logger.info(f"清理了 {expired_count} 个过期消息映射")
                    
        except asyncio.CancelledError:
            logger.info("消息映射清理任务已取消")
        except Exception as e:
            logger.error(f"清理过期映射时出错: {e}")
    
    def _remove_expired_mapping(self, source_key: str):
        """移除过期的映射"""
        try:
            if source_key in self.id_mappings:
                mapping = self.id_mappings[source_key]
                target_key = f"{mapping['target_platform']}:{mapping['target_message_id']}"
                
                del self.id_mappings[source_key]
                if target_key in self.reverse_mappings:
                    del self.reverse_mappings[target_key]
                
                self.stats['active_mappings'] -= 1
                
        except Exception as e:
            logger.error(f"移除过期映射失败: {e}")
    
    def _remove_expired_reverse_mapping(self, target_key: str):
        """移除过期的反向映射"""
        try:
            if target_key in self.reverse_mappings:
                mapping = self.reverse_mappings[target_key]
                source_key = f"{mapping['source_platform']}:{mapping['source_message_id']}"
                
                del self.reverse_mappings[target_key]
                if source_key in self.id_mappings:
                    del self.id_mappings[source_key]
                
                self.stats['active_mappings'] -= 1
                
        except Exception as e:
            logger.error(f"移除过期反向映射失败: {e}")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        try:
            # 更新活跃映射数量
            current_time = time.time()
            active_count = 0
            
            for mapping in self.id_mappings.values():
                if current_time - mapping['timestamp'] <= self.mapping_ttl:
                    active_count += 1
            
            self.stats['active_mappings'] = active_count
            
            return self.stats.copy()
            
        except Exception as e:
            logger.error(f"获取映射统计失败: {e}")
            return self.stats.copy()
    
    def clear_all_mappings(self):
        """清空所有映射（谨慎使用）"""
        try:
            old_count = len(self.id_mappings)
            self.id_mappings.clear()
            self.reverse_mappings.clear()
            self.stats['active_mappings'] = 0
            
            logger.info(f"已清空所有消息映射，共 {old_count} 个")
            
        except Exception as e:
            logger.error(f"清空消息映射失败: {e}")

# 全局实例
message_id_mapper = MessageIdMapper()

async def get_message_id_mapper() -> MessageIdMapper:
    """获取消息ID映射管理器实例"""
    return message_id_mapper