import sys
import os
from loguru import logger

# Windows 终端 UTF-8 编码支持与容错
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 清除默认 handler
logger.remove()

# 支持环境变量指定日志等级（默认 INFO）
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# 单行控制台格式：时间 | 等级 | 模块:行号 - 消息
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# 文件日志格式（供 JSON 序列化 text 字段使用）
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"

# 控制台日志 Sink
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    colorize=True,
    format=CONSOLE_FORMAT,
    backtrace=True,
    diagnose=False
)

# 文件持久化 Sink
log_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(log_dir, exist_ok=True)

logger.add(
    os.path.join(log_dir, "tqsync.log"),
    level=LOG_LEVEL,
    rotation="20 MB",
    retention="7 days",
    serialize=True,
    encoding="utf-8",
    format=FILE_FORMAT
)

__all__ = ["logger"]