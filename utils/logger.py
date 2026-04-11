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
    # 安全获取字段，防止 KeyError
    time_obj = record.get("time")
    if time_obj and hasattr(time_obj, 'strftime'):
        time_str = time_obj.strftime("%Y-%m-%d %H:%M:%S")
    else:
        time_str = str(time_obj) if time_obj else "Unknown"

    level_obj = record.get("level")
    level_name = level_obj.name if level_obj else "UNKNOWN"
    
    message = record.get("message", "")
    module_name = record.get("module", "unknown")
    line_no = record.get("line", 0)
    extra_data = record.get("extra", {})
    
    # 构造 JSON 字典
    payload = {
        "time": time_str,
        "level": level_name,
        "message": message,
        "module": module_name,
        "line": line_no,
        "extra": extra_data,
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"

logger.add(os.path.join(log_dir, "tqsync.log"), level="INFO", rotation="20 MB",
           retention="7 days", format=json_formatter, encoding="utf-8")

# 导出 logger 供其他模块使用
__all__ = ["logger"]
