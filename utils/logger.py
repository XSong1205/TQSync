import sys
import os
from loguru import logger

logger.remove()

LEVEL_NAMES = {
    "DEBUG":    "DEBUG",
    "INFO":     "INFO ",
    "SUCCESS":  " OK  ",
    "WARNING":  "WARN ",
    "ERROR":   "ERROR",
    "CRITICAL": "FATAL",
}

def custom_format(record):
    level_name = record["level"].name
    icon = LEVEL_NAMES.get(level_name, " --- ")
    record["extra"]["icon"] = icon
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
        "<level>{extra[icon]}</level> "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan>\n"
        "    <level>{message}</level>\n"
    )

logger.add(sys.stdout, level="INFO", colorize=True, format=custom_format)

log_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(log_dir, exist_ok=True)

logger.add(
    os.path.join(log_dir, "tqsync.log"), 
    level="INFO", 
    rotation="20 MB",
    retention="7 days", 
    serialize=True,
    encoding="utf-8"
)

__all__ = ["logger"]