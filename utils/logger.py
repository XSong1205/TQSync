import asyncio
import os
import sys

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
# catch=True：sink 自身写失败时只打印错误，不向业务代码抛出异常
# 说明（实测结论）：这里刻意 **不开 enqueue**。loguru 的 enqueue 只是把 sink 的
# 写出搬到后台线程，而每条日志的格式化 + JSON serialize + 跨线程投递仍然发生在
# 调用线程，实测单次调用从 ~0.06ms 涨到 ~0.45ms（4~7 倍），对"每条消息几次日志"
# 的机器人反而是净损失。日志量稀疏时同步写（OS 缓冲 + 一次打开的文件句柄）不会
# 卡住事件循环；真正需要防护的是进程被 os._exit 强杀时丢尾行，已由
# shutdown_logger() 在重启路径处理。
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    colorize=True,
    format=CONSOLE_FORMAT,
    backtrace=True,
    diagnose=False,
    catch=True
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
    format=FILE_FORMAT,
    catch=True
)


async def shutdown_logger(timeout: float = 2.0) -> None:
    """等待日志 sink 中已排队的消息处理完成（进程退出/重启前调用）。

    当前 sink 均为同步写，正常情况下写盘在 logger 调用返回时已完成，本函数几乎
    零开销；保留它作为退出路径的统一收口，若将来启用 enqueue=True 或异步 sink，
    调用方不必再改。

    Args:
        timeout: 最长等待秒数，超时后放弃等待。

    注意：本函数幂等，可在多个退出路径重复调用；不会移除任何 sink，
    调用后 logger 仍可继续正常使用；异常与超时只写 stderr，不再经 logger 记录
    （避免退出阶段继续向 sink 追加消息）。
    """
    try:
        await asyncio.wait_for(logger.complete(), timeout=timeout)
    except asyncio.TimeoutError:
        sys.stderr.write(f"[logger] shutdown_logger 等待超时（{timeout:.2f}s），部分日志可能未落盘\n")
    except Exception as e:
        sys.stderr.write(f"[logger] shutdown_logger 异常: {e}\n")
    finally:
        try:
            sys.stderr.flush()
        except Exception:
            pass


__all__ = ["logger", "shutdown_logger"]
