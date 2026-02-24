"""
日志系统模块
使用loguru进行日志管理
"""

import sys
from loguru import logger
from pathlib import Path
import os

def setup_logger(log_level="INFO", log_file=None):
    """
    配置日志系统
    
    Args:
        log_level (str): 日志级别
        log_file (str): 日志文件路径
    """
    # 移除默认的日志处理器
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True
    )
    
    # 如果指定了日志文件，添加文件输出
    if log_file:
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )
    
    return logger

# 创建全局logger实例
def get_logger():
    """获取logger实例"""
    return logger