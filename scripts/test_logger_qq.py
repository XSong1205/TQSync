"""TQSync 日志 sink 与 OneBotClient Bot ID 负缓存验证脚本。

用法:
    python scripts/test_logger_qq.py

验证内容:
1. utils.logger 的两个 sink 均保持同步写（实测 enqueue 会让单次 logger 调用慢 4~7 倍），
   logger 对象保持可用；
2. shutdown_logger() 能把 1 万条日志全部冲刷落盘，进程可正常退出；
3. get_bot_id() 失败负缓存：连续失败只请求底层 1 次，负缓存 10 秒后过期，
   invalidate_bot_id() 后重新请求，成功结果长期缓存；
4. warmup() 不向外抛异常；
5. TCPConnector 连接上限与超时参数符合预期。

脚本不发起任何真实网络请求（monkeypatch OneBotClient._get_json / aiohttp 对象），
也不污染仓库 logs/ 目录（日志文件写到系统临时目录）。
"""

from __future__ import annotations

import asyncio
import inspect
import io
import os
import shutil
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# 先按仓库根目录加载配置（ConfigLoader 依赖 cwd 下的 config.yaml），
# 再把 cwd 切到临时目录，让 utils.logger 的文件 sink 写到临时目录下，
# 避免与仓库 logs/tqsync.log（可能被其它进程/测试同时写入）互相干扰。
os.chdir(REPO_ROOT)
from config.config_loader import config_loader  # noqa: E402,F401

TMP_DIR = tempfile.mkdtemp(prefix="tqsync_logger_qq_")
os.chdir(TMP_DIR)

# 控制台 sink 在 import 时绑定 sys.stdout；用内存缓冲替换，避免 1 万条日志刷屏，
# 同时可在测试里断言控制台 sink 的异步写盘是否也全部完成。
_console_buffer = io.StringIO()
_real_stdout = sys.stdout
sys.stdout = _console_buffer
try:
    from utils.logger import logger, shutdown_logger  # noqa: E402
    import handlers.qq_handler as qq_handler  # noqa: E402
    from handlers.qq_handler import (  # noqa: E402
        BOT_ID_FAIL_CACHE_TTL,
        OneBotClient,
        onebot_client,
    )
finally:
    sys.stdout = _real_stdout

LOG_FILE = os.path.join(TMP_DIR, "logs", "tqsync.log")
MARKER = "[test_logger_qq]"
PASSED = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    """断言辅助：通过打印 PASS 行并计数，失败抛 AssertionError。"""
    global PASSED
    if not cond:
        raise AssertionError(f"{label} 失败" + (f": {detail}" if detail else ""))
    PASSED += 1
    print(f"PASS  {label}" + (f"  [{detail}]" if detail else ""))


def test_sinks_are_async() -> None:
    """两个 sink 均为同步写（实测 enqueue 会让单次 logger 调用慢 4~7 倍）。

    enqueue=True 只把 sink 写出搬到后台线程，格式化 + serialize + 跨线程投递仍在
    调用线程，对"每条消息几条日志"的机器人是净损失，因此刻意保持同步写。
    """
    handlers = list(logger._core.handlers.values())
    check(len(handlers) == 2, "logger 仍有 2 个 sink（控制台 + 文件）", f"实际 {len(handlers)}")
    for handler in handlers:
        check(handler._enqueue is False, f"sink {handler._name} 使用同步写（未开 enqueue）")
    check(inspect.iscoroutinefunction(shutdown_logger), "shutdown_logger 是 async 函数")


async def test_bot_id_negative_cache() -> None:
    """失败负缓存 / 过期 / invalidate / 成功长期缓存。"""
    calls = 0

    async def fake_fail(endpoint, *args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("模拟 NapCat 不可用")

    client = OneBotClient()
    client._get_json = fake_fail

    results = [await client.get_bot_id() for _ in range(5)]
    check(results == [None] * 5, "失败时连续 5 次 get_bot_id() 均返回 None", f"{results}")
    check(calls == 1, "失败结果负缓存：底层只请求了 1 次", f"实际 {calls} 次")
    check(
        BOT_ID_FAIL_CACHE_TTL == 10.0,
        "负缓存 TTL 为 10 秒（反回环安全窗口）",
        f"{BOT_ID_FAIL_CACHE_TTL}s",
    )
    remaining = client._bot_id_fail_until - time.monotonic()
    check(0 < remaining <= BOT_ID_FAIL_CACHE_TTL + 0.5, "负缓存窗口约为 10 秒", f"剩余 {remaining:.2f}s")

    # 模拟负缓存过期（不改动全局 time 模块，直接回拨窗口时间戳）
    client._bot_id_fail_until = time.monotonic() - 0.01
    check(await client.get_bot_id() is None, "负缓存过期后再次失败仍返回 None")
    check(calls == 2, "负缓存过期后会重新请求底层", f"实际 {calls} 次")

    # invalidate 之后即使仍在负缓存窗口内也必须重新请求
    client.invalidate_bot_id()
    check(await client.get_bot_id() is None, "invalidate_bot_id() 后失败请求返回 None")
    check(calls == 3, "invalidate_bot_id() 清除负缓存并重新请求", f"实际 {calls} 次")

    async def fake_ok(endpoint, *args, **kwargs):
        nonlocal calls
        calls += 1
        return {"retcode": 0, "data": {"user_id": 10001}}

    client._get_json = fake_ok
    client.invalidate_bot_id()
    bot_id = await client.get_bot_id()
    check(bot_id == 10001, "成功获取 Bot QQ 号", f"bot_id={bot_id}")
    check(calls == 4, "成功结果写入缓存", f"实际 {calls} 次")
    for _ in range(3):
        await client.get_bot_id()
    check(calls == 4, "成功结果长期缓存：后续调用不再请求", f"实际 {calls} 次")

    client.invalidate_bot_id()
    check(await client.get_bot_id() == 10001, "invalidate_bot_id() 后重新请求成功")
    check(calls == 5, "invalidate_bot_id() 后底层被再次调用", f"实际 {calls} 次")

    # 公共 API 形态检查
    check(callable(getattr(onebot_client, "invalidate_bot_id", None)), "全局实例提供 invalidate_bot_id()")
    check(callable(getattr(onebot_client, "warmup", None)), "全局实例提供 warmup()")


async def test_warmup_swallows_errors() -> None:
    """warmup() 只做预热，失败不得向调用方冒泡。"""
    calls = 0

    async def fake_fail(endpoint, *args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("模拟 NapCat 不可用")

    client = OneBotClient()
    client._get_json = fake_fail
    try:
        await client.warmup()
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"warmup() 不应抛出异常，实际: {e!r}") from e
    check(calls == 1, "warmup() 失败被吞掉且底层只请求 1 次", f"实际 {calls} 次")


async def test_connector_tuning() -> None:
    """TCPConnector 连接上限调优，超时语义保持不变。"""
    captured: dict = {}

    class FakeConnector:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["connector"] = self

    class FakeSession:
        def __init__(self, connector=None, timeout=None):
            self.connector = connector
            self.timeout = timeout
            self.closed = False
            captured["session"] = self

    real_connector = qq_handler.aiohttp.TCPConnector
    real_session = qq_handler.aiohttp.ClientSession
    qq_handler.aiohttp.TCPConnector = FakeConnector
    qq_handler.aiohttp.ClientSession = FakeSession
    try:
        client = OneBotClient()
        await client._ensure_session()
        connector = captured["connector"].kwargs
        timeout = captured["session"].timeout
        check(connector.get("limit") == 50, "TCPConnector limit=50", f"{connector.get('limit')}")
        check(
            connector.get("limit_per_host") == 20,
            "TCPConnector limit_per_host=20",
            f"{connector.get('limit_per_host')}",
        )
        check(
            connector.get("enable_cleanup_closed") is True,
            "TCPConnector enable_cleanup_closed=True",
        )
        check(connector.get("ssl") is False, "TCPConnector ssl=False（保持原语义）")
        check(
            getattr(timeout, "total", None) == 30 and getattr(timeout, "connect", None) == 10,
            "超时语义不变（total=30, connect=10）",
            f"total={getattr(timeout, 'total', None)}, connect={getattr(timeout, 'connect', None)}",
        )
    finally:
        qq_handler.aiohttp.TCPConnector = real_connector
        qq_handler.aiohttp.ClientSession = real_session


async def test_log_throughput_and_flush() -> None:
    """1 万条日志：异步入队耗时可控，shutdown_logger() 后全部落盘。"""
    n = 10_000
    t0 = time.monotonic()
    for i in range(n):
        logger.info(f"{MARKER} 第 {i} 条日志，模拟同步链路日志写入")
    enqueue_elapsed = time.monotonic() - t0
    print(
        f"INFO  入队 {n} 条日志耗时 {enqueue_elapsed * 1000:.1f}ms "
        f"({n / enqueue_elapsed:.0f} 条/秒)"
    )
    # enqueue=True 只把磁盘 IO 移到后台线程，入队本身仍需格式化 + 队列投递；
    # 阈值放宽到 20s，主要防止队列卡死/死锁类回归。
    check(enqueue_elapsed < 20.0, "1 万条日志入队耗时正常", f"{enqueue_elapsed:.2f}s < 20s")

    t0 = time.monotonic()
    await shutdown_logger(timeout=10.0)
    flush_elapsed = time.monotonic() - t0
    print(f"INFO  shutdown_logger() 冲刷耗时 {flush_elapsed * 1000:.1f}ms")
    check(flush_elapsed < 10.0, "shutdown_logger() 在超时上限内完成", f"{flush_elapsed:.2f}s")

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    # serialize=True 的记录里 message 与 text 各出现一次，因此每条日志命中 2 次 MARKER
    marker_count = content.count(MARKER)
    check(
        marker_count == 2 * n,
        f"文件 sink 落盘完整（{n} 条日志均在文件中）",
        f"MARKER 命中 {marker_count}/{2 * n} 次",
    )
    marker_lines = sum(1 for line in content.splitlines() if MARKER in line)
    check(marker_lines == n, f"文件 sink 行数完整", f"{marker_lines}/{n} 行")

    console_count = _console_buffer.getvalue().count(MARKER)
    check(console_count == n, f"控制台 sink 落盘完整", f"MARKER 命中 {console_count}/{n} 次")

    # shutdown_logger 之后 logger 仍可继续使用，且可重复调用（幂等）
    logger.info(f"{MARKER} shutdown 之后仍可写入")
    await shutdown_logger(timeout=5.0)
    await shutdown_logger(timeout=5.0)
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        after = f.read()
    check(after.count(MARKER) == 2 * n + 2, "shutdown 后 logger 仍可用且可重复冲刷")


def main() -> int:
    try:
        print(f"临时日志目录: {TMP_DIR}")
        test_sinks_are_async()
        asyncio.run(_run_async_tests())
        print(f"\n全部 {PASSED} 项断言 PASS")
        return 0
    except AssertionError as e:
        print(f"\nFAIL  {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"\nFAIL  未预期异常: {e}")
        return 1
    finally:
        # 清理：先移除 sink（停止后台写盘线程、关闭文件句柄），
        # 切回仓库根目录（Windows 下不能删除当前工作目录），再删临时目录
        try:
            logger.remove()
        except Exception:
            pass
        try:
            os.chdir(REPO_ROOT)
        except Exception:
            pass
        try:
            shutil.rmtree(TMP_DIR, ignore_errors=True)
        except Exception:
            pass


async def _run_async_tests() -> None:
    await test_bot_id_negative_cache()
    await test_warmup_swallows_errors()
    await test_connector_tuning()
    await test_log_throughput_and_flush()


if __name__ == "__main__":
    raise SystemExit(main())
