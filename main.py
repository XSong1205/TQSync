#!/usr/bin/env python3
"""
Telegram-QQ消息同步机器人主程序
"""

import asyncio
import signal
import sys
from utils.logger import setup_logger, get_logger
from utils.config import get_config
from core.message_sync import get_message_sync

logger = get_logger()

class BotManager:
    """机器人管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self.message_sync = None
        self.is_running = False
    
    async def initialize(self):
        """初始化机器人"""
        try:
            logger.info("开始初始化机器人...")
            
            # 获取消息同步器
            self.message_sync = await get_message_sync()
            
            logger.info("机器人初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"机器人初始化失败: {e}")
            return False
    
    async def start(self):
        """启动机器人"""
        try:
            self.is_running = True
            logger.info("=" * 50)
            logger.info("🚀 Telegram-QQ消息同步机器人启动")
            logger.info("=" * 50)
            
            # 初始化
            if not await self.initialize():
                logger.error("初始化失败，退出程序")
                return
            
            # 启动消息同步
            await self.message_sync.start()
            
        except KeyboardInterrupt:
            logger.info("\n收到中断信号，正在优雅关闭...")
        except Exception as e:
            logger.error(f"运行时发生错误: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """关闭机器人"""
        try:
            logger.info("正在关闭机器人...")
            self.is_running = False
            
            if self.message_sync:
                await self.message_sync.stop()
            
            # 显示最终统计
            if self.message_sync:
                stats = self.message_sync.get_stats()
                logger.info("=" * 30)
                logger.info("📊 运行统计:")
                logger.info(f"Telegram接收: {stats['telegram_received']}")
                logger.info(f"QQ接收: {stats['qq_received']}")
                logger.info(f"Telegram发送: {stats['telegram_sent']}")
                logger.info(f"QQ发送: {stats['qq_sent']}")
                logger.info(f"过滤消息: {stats['filtered']}")
                logger.info("=" * 30)
            
            logger.info("机器人已安全关闭")
            
        except Exception as e:
            logger.error(f"关闭过程中发生错误: {e}")

async def main():
    """主函数"""
    # 配置日志
    config = get_config()
    logging_config = config.get_logging_config()
    
    setup_logger(
        log_level=logging_config['level'],
        log_file=logging_config['file']
    )
    
    # 验证配置
    if not config.validate_config():
        logger.error("配置验证失败，请检查配置文件")
        sys.exit(1)
    
    # 创建机器人管理器
    bot_manager = BotManager()
    
    # 设置信号处理器
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，准备退出...")
        # 在异步环境中安全地停止
        if hasattr(bot_manager, 'message_sync') and bot_manager.message_sync:
            # 创建新的任务来处理关闭
            loop = asyncio.get_running_loop()
            loop.create_task(bot_manager.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动机器人
    await bot_manager.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序异常退出: {e}")