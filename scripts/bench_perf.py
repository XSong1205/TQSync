"""TQSync 性能基准脚本。

用法:
    python scripts/bench_perf.py [--ops 300]

测量三件对机器人吞吐影响最大的事:
1. 数据库热路径（消息映射写入/查询、绑定查询、屏蔽词检测）的吞吐与单次延迟
2. 日志写入对事件循环的阻塞程度
3. 上述操作期间事件循环的最大停顿（event loop lag）

脚本使用独立的临时数据库，不会污染真实 db/tqsync.db。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Database  # noqa: E402
from utils.logger import logger  # noqa: E402


class LagMonitor:
    """以固定间隔醒来，统计事件循环被阻塞的时间。"""

    def __init__(self, interval: float = 0.005):
        self.interval = interval
        self.lags: list[float] = []
        self._stop = False
        self._task: asyncio.Task | None = None

    async def _run(self):
        while not self._stop:
            t0 = time.perf_counter()
            await asyncio.sleep(self.interval)
            elapsed = time.perf_counter() - t0
            self.lags.append(max(0.0, elapsed - self.interval))

    def start(self):
        self._stop = False
        self.lags = []
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> dict:
        self._stop = True
        if self._task:
            await self._task
        if not self.lags:
            return {"p50_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
        lags = sorted(self.lags)
        p99 = lags[min(len(lags) - 1, int(len(lags) * 0.99))]
        return {
            "p50_ms": statistics.median(lags) * 1000,
            "p99_ms": p99 * 1000,
            "max_ms": lags[-1] * 1000,
        }


def _fmt(result: dict) -> str:
    return (
        f"耗时 {result['elapsed_ms']:.1f}ms | "
        f"{result['ops_per_sec']:.0f} ops/s | "
        f"单次 {result['avg_ms']:.3f}ms | "
        f"lag p50 {result['lag']['p50_ms']:.2f}ms "
        f"p99 {result['lag']['p99_ms']:.2f}ms "
        f"max {result['lag']['max_ms']:.2f}ms"
    )


async def _measure(name: str, n: int, coro_factory) -> dict:
    """执行 n 次 coro_factory() 并统计。"""
    monitor = LagMonitor()
    monitor.start()
    t0 = time.perf_counter()
    for _ in range(n):
        await coro_factory()
    elapsed = time.perf_counter() - t0
    lag = await monitor.stop()
    result = {
        "name": name,
        "ops": n,
        "elapsed_ms": elapsed * 1000,
        "ops_per_sec": n / elapsed if elapsed else 0.0,
        "avg_ms": elapsed / n * 1000 if n else 0.0,
        "lag": lag,
    }
    print(f"{name:<34} {_fmt(result)}")
    return result


async def bench_db(n: int) -> list[dict]:
    tmpdir = tempfile.mkdtemp(prefix="tqsync_bench_")
    db = Database()
    db.db_path = os.path.join(tmpdir, "bench.db")
    await db.init_db()
    await db.set_setting("blocked_words", '["spam", "广告", "广告词"]')
    await db.add_binding(10001, 20001, "benchuser", "bench")
    await db.save_message_mapping(10001, 20001, sender_tg_id=10001)

    results = []
    results.append(await _measure(
        "DB save_message_mapping", n,
        lambda: db.save_message_mapping(10002, 20002, sender_qq_id=20002)))
    results.append(await _measure(
        "DB get_tg_msg_id_by_qq", n,
        lambda: db.get_tg_msg_id_by_qq(20001)))
    results.append(await _measure(
        "DB get_binding_by_qq", n,
        lambda: db.get_binding_by_qq(20001)))
    results.append(await _measure(
        "DB check_blocked_word_in_text", n,
        lambda: db.check_blocked_word_in_text("这是一条包含广告的正常聊天消息")))
    results.append(await _measure(
        "DB get_setting(hot key)", n,
        lambda: db.get_setting("blocked_words")))
    results.append(await _measure(
        "DB get_custom_prefix_by_uid", n,
        lambda: db.get_custom_prefix_by_uid("nonexistent-uid")))

    try:
        await db.close()
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)
    return results


async def bench_logger(n: int) -> list[dict]:
    results = []
    results.append(await _measure(
        "logger.info (file+console)", n,
        lambda: _log_once()))
    return results


async def _log_once():
    logger.info("[bench] 一条典型的同步日志：QQ 用户 123456 发送了一条文本消息")


async def bench_config(n: int) -> list[dict]:
    from config.config_loader import config_loader

    def _one():
        config_loader.get("qq.group_id")
        config_loader.get("sync.direction", "both")
        config_loader.get("telegram.group_id")

    async def _coro():
        _one()

    return [await _measure("config.get x3 (no-op async)", n, _coro)]


async def main_async(n: int) -> int:
    print(f"TQSync 性能基准 — 每组 {n} 次\n" + "-" * 100)
    await bench_db(n)
    await bench_logger(n)
    await bench_config(n)
    print("-" * 100)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TQSync 性能基准")
    parser.add_argument("--ops", type=int, default=300, help="每项测量次数 (默认 300)")
    args = parser.parse_args()
    return asyncio.run(main_async(args.ops))


if __name__ == "__main__":
    raise SystemExit(main())
