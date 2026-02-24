"""
数据库管理模块
负责用户绑定和消息映射的持久化存储
"""

import sqlite3
import json
import time
import os
from typing import Dict, Any, Optional, List
from utils.logger import get_logger

logger = get_logger()

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str = "tqsync.db"):
        """初始化数据库管理器"""
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建用户绑定表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_bindings (
                    qq_user_id TEXT PRIMARY KEY,
                    tg_user_id TEXT NOT NULL UNIQUE,
                    bind_time REAL NOT NULL,
                    last_active REAL NOT NULL,
                    metadata TEXT
                )
            ''')
            
            # 创建消息映射表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_mappings (
                    source_platform TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    target_platform TEXT NOT NULL,
                    target_message_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    PRIMARY KEY (source_platform, source_message_id)
                )
            ''')
            
            # 创建验证码表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS verification_codes (
                    code TEXT PRIMARY KEY,
                    qq_user_id TEXT NOT NULL,
                    tg_user_id TEXT NOT NULL,
                    expire_time REAL NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    created_time REAL NOT NULL
                )
            ''')
            
            # 创建索引优化查询性能
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_bindings_tg ON user_bindings(tg_user_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_mappings_target ON message_mappings(target_platform, target_message_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_mappings_timestamp ON message_mappings(timestamp)
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info(f"数据库初始化完成: {self.db_path}")
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def save_user_binding(self, qq_user_id: str, tg_user_id: str, metadata: Dict[str, Any] = None) -> bool:
        """
        保存用户绑定关系
        
        Args:
            qq_user_id: QQ用户ID
            tg_user_id: Telegram用户ID
            metadata: 绑定元数据
            
        Returns:
            bool: 保存是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = time.time()
            
            # 插入或更新绑定关系
            cursor.execute('''
                INSERT OR REPLACE INTO user_bindings 
                (qq_user_id, tg_user_id, bind_time, last_active, metadata)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                qq_user_id,
                tg_user_id,
                current_time,
                current_time,
                json.dumps(metadata) if metadata else None
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"用户绑定已保存: QQ({qq_user_id}) ↔ Telegram({tg_user_id})")
            return True
            
        except Exception as e:
            logger.error(f"保存用户绑定失败: {e}")
            return False
    
    def get_user_binding(self, platform: str, user_id: str) -> Optional[str]:
        """
        获取用户绑定关系
        
        Args:
            platform: 平台名称 ('qq' 或 'telegram')
            user_id: 用户ID
            
        Returns:
            Optional[str]: 绑定的对方平台用户ID，如果不存在则返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if platform == 'qq':
                cursor.execute('SELECT tg_user_id FROM user_bindings WHERE qq_user_id = ?', (user_id,))
            else:
                cursor.execute('SELECT qq_user_id FROM user_bindings WHERE tg_user_id = ?', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            logger.error(f"获取用户绑定失败: {e}")
            return None
    
    def remove_user_binding(self, platform: str, user_id: str) -> bool:
        """
        移除用户绑定关系
        
        Args:
            platform: 平台名称 ('qq' 或 'telegram')
            user_id: 用户ID
            
        Returns:
            bool: 移除是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if platform == 'qq':
                cursor.execute('DELETE FROM user_bindings WHERE qq_user_id = ?', (user_id,))
            else:
                cursor.execute('DELETE FROM user_bindings WHERE tg_user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"用户绑定已移除: {platform}({user_id})")
            return True
            
        except Exception as e:
            logger.error(f"移除用户绑定失败: {e}")
            return False
    
    def get_all_bindings(self) -> List[Dict[str, Any]]:
        """
        获取所有绑定关系
        
        Returns:
            List[Dict]: 绑定关系列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT qq_user_id, tg_user_id, bind_time, last_active, metadata FROM user_bindings')
            rows = cursor.fetchall()
            conn.close()
            
            bindings = []
            for row in rows:
                bindings.append({
                    'qq_user_id': row[0],
                    'tg_user_id': row[1],
                    'bind_time': row[2],
                    'last_active': row[3],
                    'metadata': json.loads(row[4]) if row[4] else None
                })
            
            return bindings
            
        except Exception as e:
            logger.error(f"获取所有绑定失败: {e}")
            return []
    
    def save_message_mapping(self, source_platform: str, source_message_id: str,
                           target_platform: str, target_message_id: str) -> bool:
        """
        保存消息ID映射
        
        Args:
            source_platform: 源平台
            source_message_id: 源消息ID
            target_platform: 目标平台
            target_message_id: 目标消息ID
            
        Returns:
            bool: 保存是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO message_mappings 
                (source_platform, source_message_id, target_platform, target_message_id, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                source_platform,
                str(source_message_id),
                target_platform,
                str(target_message_id),
                time.time()
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"消息映射已保存: {source_platform}({source_message_id}) → {target_platform}({target_message_id})")
            return True
            
        except Exception as e:
            logger.error(f"保存消息映射失败: {e}")
            return False
    
    def get_message_mapping(self, source_platform: str, source_message_id: str,
                          target_platform: str) -> Optional[str]:
        """
        获取消息ID映射
        
        Args:
            source_platform: 源平台
            source_message_id: 源消息ID
            target_platform: 目标平台
            
        Returns:
            Optional[str]: 目标消息ID，如果不存在则返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT target_message_id FROM message_mappings 
                WHERE source_platform = ? AND source_message_id = ? AND target_platform = ?
            ''', (source_platform, str(source_message_id), target_platform))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            logger.error(f"获取消息映射失败: {e}")
            return None
    
    def remove_message_mapping(self, source_platform: str, source_message_id: str) -> bool:
        """
        移除消息ID映射
        
        Args:
            source_platform: 源平台
            source_message_id: 源消息ID
            
        Returns:
            bool: 移除是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM message_mappings 
                WHERE source_platform = ? AND source_message_id = ?
            ''', (source_platform, str(source_message_id)))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"消息映射已移除: {source_platform}({source_message_id})")
            return True
            
        except Exception as e:
            logger.error(f"移除消息映射失败: {e}")
            return False
    
    def cleanup_expired_mappings(self, ttl_seconds: int = 172800) -> int:
        """
        清理过期的消息映射
        
        Args:
            ttl_seconds: 生存时间（秒），默认48小时
            
        Returns:
            int: 清理的数量
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            expired_time = time.time() - ttl_seconds
            cursor.execute('DELETE FROM message_mappings WHERE timestamp < ?', (expired_time,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个过期消息映射")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理过期映射失败: {e}")
            return 0
    
    def save_verification_code(self, code: str, qq_user_id: str, tg_user_id: str,
                             expire_time: float) -> bool:
        """
        保存验证码
        
        Args:
            code: 验证码
            qq_user_id: QQ用户ID
            tg_user_id: Telegram用户ID
            expire_time: 过期时间戳
            
        Returns:
            bool: 保存是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO verification_codes 
                (code, qq_user_id, tg_user_id, expire_time, attempts, created_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                code,
                qq_user_id,
                tg_user_id,
                expire_time,
                0,
                time.time()
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"验证码已保存: {code}")
            return True
            
        except Exception as e:
            logger.error(f"保存验证码失败: {e}")
            return False
    
    def get_verification_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取验证码信息
        
        Args:
            code: 验证码
            
        Returns:
            Optional[Dict]: 验证码信息，如果不存在或过期则返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT qq_user_id, tg_user_id, expire_time, attempts, created_time 
                FROM verification_codes 
                WHERE code = ?
            ''', (code,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'qq_user_id': result[0],
                    'tg_user_id': result[1],
                    'expire_time': result[2],
                    'attempts': result[3],
                    'created_time': result[4]
                }
            return None
            
        except Exception as e:
            logger.error(f"获取验证码失败: {e}")
            return None
    
    def increment_verification_attempts(self, code: str) -> bool:
        """
        增加验证码尝试次数
        
        Args:
            code: 验证码
            
        Returns:
            bool: 更新是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('UPDATE verification_codes SET attempts = attempts + 1 WHERE code = ?', (code,))
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"增加验证尝试次数失败: {e}")
            return False
    
    def remove_verification_code(self, code: str) -> bool:
        """
        移除验证码
        
        Args:
            code: 验证码
            
        Returns:
            bool: 移除是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM verification_codes WHERE code = ?', (code,))
            conn.commit()
            conn.close()
            
            logger.debug(f"验证码已移除: {code}")
            return True
            
        except Exception as e:
            logger.error(f"移除验证码失败: {e}")
            return False
    
    def cleanup_expired_verifications(self) -> int:
        """
        清理过期的验证码
        
        Returns:
            int: 清理的数量
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = time.time()
            cursor.execute('DELETE FROM verification_codes WHERE expire_time < ?', (current_time,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个过期验证码")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理过期验证码失败: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取数据库统计信息
        
        Returns:
            Dict: 统计信息
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取各类数据数量
            cursor.execute('SELECT COUNT(*) FROM user_bindings')
            bindings_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM message_mappings')
            mappings_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM verification_codes')
            verifications_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_bindings': bindings_count,
                'total_mappings': mappings_count,
                'pending_verifications': verifications_count
            }
            
        except Exception as e:
            logger.error(f"获取数据库统计失败: {e}")
            return {
                'total_bindings': 0,
                'total_mappings': 0,
                'pending_verifications': 0
            }

# 全局实例
db_manager = DatabaseManager()

def get_db_manager() -> DatabaseManager:
    """获取数据库管理器实例"""
    return db_manager