import sys
import os
from loguru import logger

# 移除默认处理器
logger.remove()

# 终端输出（彩色）
logger.add(sys.stdout, level="INFO", colorize=True,
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                  "<level>{level: <8}</level> | "
                  "<cyan>{name}:{line}</cyan> - "
                  "<level>{message}</level>")

# 确保日志目录存在
log_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 文件输出（JSON，使用 Loguru 内置序列化以确保绝对稳定）
logger.add(
    os.path.join(log_dir, "tqsync.log"), 
    level="INFO", 
    rotation="20 MB",
    retention="7 days", 
    serialize=True,  # 开启内置 JSON 序列化，彻底解决自定义 formatter 的 KeyError
    encoding="utf-8"
)

# 导出 logger 供其他模块使用
__all__ = ["logger"]
