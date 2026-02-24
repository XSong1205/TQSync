"""
消息重试管理器
负责Telegram消息发送失败的重试机制
"""

import asyncio
import time
import json
import aiosqlite
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from utils.logger import get_logger

logger = get_logger()

class RetryManager:
    """消息重试管理器"""
    
    def __init__(self, db_path: str = "data/retry_queue.db"):
        """初始化重试管理器"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 重试配置
        self.max_retries = 5
        self.base_delay = 1  # 基础延迟(秒)
        self.max_delay = 300  # 最大延迟(秒)
        
        # 重试任务
        self.retry_task: Optional[asyncio.Task] = None
        self.running = False
        
        # 发送函数回调
        self.send_callback: Optional[Callable] = None
        
    async def initialize(self):
        """初始化数据库"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS retry_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_data TEXT NOT NULL,
                        retry_count INTEGER DEFAULT 0,
                        next_retry_time REAL NOT NULL,
                        created_time REAL NOT NULL,
                        error_message TEXT
                    )
                """)
                await db.commit()
            logger.info("重试管理器数据库初始化成功")
        except Exception as e:
            logger.error(f"初始化重试管理器数据库失败: {e}")
            raise
    
    def set_send_callback(self, callback: Callable):
        """设置发送回调函数"""
        self.send_callback = callback
    
    async def add_to_retry_queue(self, message_data: Dict[Any, Any], error_message: str = ""):
        """
        添加消息到重试队列
        
        Args:
            message_data (dict): 消息数据
            error_message (str): 错误信息
        """
        try:
            # 计算下次重试时间（指数退避）
            retry_count = 0
            next_retry_time = time.time() + self._calculate_delay(retry_count)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO retry_queue 
                    (message_data, retry_count, next_retry_time, created_time, error_message)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    json.dumps(message_data, ensure_ascii=False),
                    retry_count,
                    next_retry_time,
                    time.time(),
                    error_message
                ))
                await db.commit()
            
            logger.info(f"消息已添加到重试队列: {message_data.get('text', '')[:50]}...")
            
        except Exception as e:
            logger.error(f"添加消息到重试队列失败: {e}")
    
    async def _process_retry_queue(self):
        """处理重试队列"""
        while self.running:
            try:
                current_time = time.time()
                
                # 查询需要重试的消息
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute("""
                        SELECT id, message_data, retry_count, error_message
                        FROM retry_queue
                        WHERE next_retry_time <= ?
                        ORDER BY next_retry_time ASC
                        LIMIT 10
                    """, (current_time,)) as cursor:
                        rows = await cursor.fetchall()
                    
                    for row in rows:
                        message_id, message_data_json, retry_count, error_message = row
                        message_data = json.loads(message_data_json)
                        
                        # 尝试发送消息
                        success = await self._attempt_send(message_data)
                        
                        if success:
                            # 发送成功，从队列中删除
                            await db.execute("DELETE FROM retry_queue WHERE id = ?", (message_id,))
                            await db.commit()
                            logger.info(f"重试发送成功: {message_data.get('text', '')[:50]}...")
                        else:
                            # 发送失败，更新重试次数
                            retry_count += 1
                            if retry_count >= self.max_retries:
                                # 达到最大重试次数，标记为失败
                                logger.error(f"消息重试失败，达到最大重试次数: {message_data.get('text', '')[:50]}...")
                                await db.execute("DELETE FROM retry_queue WHERE id = ?", (message_id,))
                                await db.commit()
                            else:
                                # 计算下次重试时间
                                next_retry_time = time.time() + self._calculate_delay(retry_count)
                                await db.execute("""
                                    UPDATE retry_queue 
                                    SET retry_count = ?, next_retry_time = ?, error_message = ?
                                    WHERE id = ?
                                """, (retry_count, next_retry_time, error_message, message_id))
                                await db.commit()
                
                # 等待一段时间再检查
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"处理重试队列时出错: {e}")
                await asyncio.sleep(10)
    
    async def _attempt_send(self, message_data: Dict[Any, Any]) -> bool:
        """
        尝试发送消息
        
        Args:
            message_data (dict): 消息数据
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if not self.send_callback:
                logger.error("发送回调函数未设置")
                return False
            
            # 根据消息类型调用不同的发送方法
            message_type = message_data.get('type', 'text')
            
            if message_type == 'media':
                # 媒体消息发送
                return await self._send_media_message(message_data)
            else:
                # 文本消息发送
                return await self._send_text_message(message_data)
                
        except Exception as e:
            logger.error(f"尝试发送消息时出错: {e}")
            return False
    
    async def _send_text_message(self, message_data: Dict[Any, Any]) -> bool:
        """发送文本消息"""
        try:
            text = message_data.get('text', '')
            if not text:
                return False
            
            return await self.send_callback(text)
        except Exception as e:
            logger.error(f"发送文本消息失败: {e}")
            return False
    
    async def _send_media_message(self, message_data: Dict[Any, Any]) -> bool:
        """发送媒体消息"""
        try:
            # TODO: 实现媒体消息发送逻辑
            logger.warning("媒体消息重试发送功能待实现")
            return False
        except Exception as e:
            logger.error(f"发送媒体消息失败: {e}")
            return False
    
    def _calculate_delay(self, retry_count: int) -> float:
        """
        计算重试延迟时间（指数退避）
        
        Args:
            retry_count (int): 重试次数
            
        Returns:
            float: 延迟时间(秒)
        """
        delay = self.base_delay * (2 ** retry_count)
        return min(delay, self.max_delay)
    
    async def get_queue_stats(self) -> Dict[str, int]:
        """获取队列统计信息"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 总消息数
                async with db.execute("SELECT COUNT(*) FROM retry_queue") as cursor:
                    total_count = (await cursor.fetchone())[0]
                
                # 待重试消息数
                current_time = time.time()
                async with db.execute(
                    "SELECT COUNT(*) FROM retry_queue WHERE next_retry_time <= ?",
                    (current_time,)
                ) as cursor:
                    pending_count = (await cursor.fetchone())[0]
                
                return {
                    'total': total_count,
                    'pending': pending_count,
                    'processing': total_count - pending_count
                }
        except Exception as e:
            logger.error(f"获取队列统计信息失败: {e}")
            return {'total': 0, 'pending': 0, 'processing': 0}
    
    async def start(self):
        """启动重试管理器"""
        try:
            await self.initialize()
            self.running = True
            self.retry_task = asyncio.create_task(self._process_retry_queue())
            logger.info("重试管理器已启动")
        except Exception as e:
            logger.error(f"启动重试管理器失败: {e}")
            raise
    
    async def stop(self):
        """停止重试管理器"""
        try:
            self.running = False
            if self.retry_task and not self.retry_task.done():
                self.retry_task.cancel()
                try:
                    await self.retry_task
                except asyncio.CancelledError:
                    pass
            logger.info("重试管理器已停止")
        except Exception as e:
            logger.error(f"停止重试管理器失败: {e}")

# 全局实例
retry_manager = RetryManager()

async def get_retry_manager() -> RetryManager:
    """获取重试管理器实例"""
    return retry_manager