"""
统计数据管理器
将 MessageSync 的统计数据保存到数据库，供 Web Dashboard 读取
"""

import asyncio
import time
import aiosqlite
from pathlib import Path
from typing import Dict, Any, Optional
from utils.logger import get_logger

logger = get_logger()

class StatsManager:
    """统计数据管理器"""
    
    def __init__(self, db_path: str = "data/dashboard_stats.db"):
        """初始化统计数据管理器"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计缓存
        self.cached_stats = {
            'telegram_received': 0,
            'qq_received': 0,
            'telegram_sent': 0,
            'qq_sent': 0,
            'filtered': 0,
            'prefix_filtered': 0,
            'commands_processed': 0,
            'uptime': '0h 0m',
            'last_update': 0
        }
        
        # 启动时间
        self.start_time = time.time()
        
        # 自动保存任务
        self.save_task: Optional[asyncio.Task] = None
        self.running = False
    
    async def initialize(self):
        """初始化数据库"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS stats (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        telegram_received INTEGER DEFAULT 0,
                        qq_received INTEGER DEFAULT 0,
                        telegram_sent INTEGER DEFAULT 0,
                        qq_sent INTEGER DEFAULT 0,
                        filtered INTEGER DEFAULT 0,
                        prefix_filtered INTEGER DEFAULT 0,
                        commands_processed INTEGER DEFAULT 0,
                        uptime TEXT DEFAULT '0h 0m',
                        last_update REAL
                    )
                """)
                await db.commit()
            
            logger.info("统计数据数据库初始化成功")
            
            # 加载历史数据
            await self.load_stats()
            
            # 启动自动保存任务
            self.running = True
            self.save_task = asyncio.create_task(self._auto_save_task())
            
            return True
            
        except Exception as e:
            logger.error(f"统计数据数据库初始化失败：{e}")
            return False
    
    async def load_stats(self):
        """从数据库加载统计数据"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT * FROM stats WHERE id = 1"
                ) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        self.cached_stats = {
                            'telegram_received': row[1],
                            'qq_received': row[2],
                            'telegram_sent': row[3],
                            'qq_sent': row[4],
                            'filtered': row[5],
                            'prefix_filtered': row[6],
                            'commands_processed': row[7],
                            'uptime': row[8],
                            'last_update': row[9]
                        }
                        logger.debug(f"加载历史统计数据：{self.cached_stats}")
                    else:
                        logger.debug("未找到历史统计数据")
                        
        except Exception as e:
            logger.error(f"加载统计数据失败：{e}")
    
    async def update_stats(self, stats: Dict[str, Any]):
        """更新统计数据"""
        try:
            # 更新缓存
            for key, value in stats.items():
                if key in self.cached_stats:
                    self.cached_stats[key] = value
            
            # 计算运行时间
            uptime_seconds = time.time() - self.start_time
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            self.cached_stats['uptime'] = f"{hours}h {minutes}m"
            self.cached_stats['last_update'] = time.time()
            
            # 立即保存到数据库
            await self._save_to_db()
            
        except Exception as e:
            logger.error(f"更新统计数据失败：{e}")
    
    async def _save_to_db(self):
        """保存到数据库"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO stats 
                    (id, telegram_received, qq_received, telegram_sent, qq_sent, 
                     filtered, prefix_filtered, commands_processed, uptime, last_update)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    1,
                    self.cached_stats['telegram_received'],
                    self.cached_stats['qq_received'],
                    self.cached_stats['telegram_sent'],
                    self.cached_stats['qq_sent'],
                    self.cached_stats['filtered'],
                    self.cached_stats['prefix_filtered'],
                    self.cached_stats['commands_processed'],
                    self.cached_stats['uptime'],
                    self.cached_stats['last_update']
                ))
                await db.commit()
            
            logger.debug(f"统计数据已保存：{self.cached_stats}")
            
        except Exception as e:
            logger.error(f"保存统计数据失败：{e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取最新统计数据"""
        try:
            # 计算运行时间
            uptime_seconds = time.time() - self.start_time
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            
            stats = self.cached_stats.copy()
            stats['uptime'] = f"{hours}h {minutes}m"
            stats['last_update'] = time.time()
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计数据失败：{e}")
            return self.cached_stats
    
    async def _auto_save_task(self):
        """定期自动保存任务"""
        try:
            while self.running:
                await asyncio.sleep(10)  # 每 10 秒保存一次
                await self._save_to_db()
                logger.debug("统计数据自动保存完成")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"自动保存任务出错：{e}")
    
    async def shutdown(self):
        """关闭管理器"""
        try:
            self.running = False
            
            if self.save_task:
                self.save_task.cancel()
                try:
                    await self.save_task
                except asyncio.CancelledError:
                    pass
            
            # 最后一次保存
            await self._save_to_db()
            logger.info("统计数据管理器已关闭")
            
        except Exception as e:
            logger.error(f"关闭统计数据管理器失败：{e}")


# 全局实例
_stats_manager: Optional[StatsManager] = None

async def get_stats_manager() -> StatsManager:
    """获取全局统计数据管理器实例"""
    global _stats_manager
    
    if _stats_manager is None:
        _stats_manager = StatsManager()
        await _stats_manager.initialize()
    
    return _stats_manager
