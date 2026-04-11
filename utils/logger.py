import sys
import os
import json
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

# 文件输出（JSON，适合机器人服务端）
def json_formatter(record):
    # 提取 record 中的日志数据
    log = record["record"]
    # 构造 JSON 字典
    payload = {
        "time": log["time"].strftime("%Y-%m-%d %H:%M:%S"),
        "level": log["level"].name,
        "message": log["message"],
        "module": log["module"],
        "line": log["line"],
        "extra": log["extra"],
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"

logger.add(os.path.join(log_dir, "tqsync.log"), level="INFO", rotation="20 MB",
           retention="7 days", format=json_formatter, encoding="utf-8")

# 导出 logger 供其他模块使用
__all__ = ["logger"]
