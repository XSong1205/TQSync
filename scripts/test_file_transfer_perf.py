"""core/file_transfer.py HTTP 连接复用 / temp 目录缓存验证脚本。

用法::

    .\\.venv\\Scripts\\python.exe scripts\\test_file_transfer_perf.py

脚本不依赖外网：用 aiohttp 在 127.0.0.1 上起一个内存静态文件服务，
连续下载 N=30 个文件，验证以下行为：

1. _resolve_temp_dir() 进程内只 mkdir 一次，且反复调用返回同一路径；
2. 多次下载复用同一个模块级共享 ClientSession（连接池）；
3. aclose_http_session() 幂等，关闭后再次下载能自动重建 session；
4. 手工把 session close() 后再次下载也能自动重建；
5. 下载文件大小/内容、resolve() 链路、并发下载行为保持正确；
6. 下载失败（HTTP 404 / 连接中断）时仍会删除半成品临时文件。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback

# 先压低日志级别，避免 30 次下载的 INFO 日志刷屏干扰测试输出（不影响文件日志配置）
os.environ.setdefault('LOG_LEVEL', 'WARNING')

# 允许从仓库根目录或 scripts/ 目录直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web  # noqa: E402

import core.file_transfer as ft  # noqa: E402

N_DOWNLOADS = 30                       # 顺序下载次数
N_CONCURRENT = 10                      # 并发下载次数
PAYLOAD = bytes((i * 37 + 11) % 256 for i in range(128 * 1024))  # 128 KiB 确定性内容

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    """记录并打印一项检查结果。"""
    _results.append((name, ok, detail))
    tag = 'PASS' if ok else 'FAIL'
    print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))


async def _handle(request: web.Request) -> web.StreamResponse:
    """任意路径都返回同一份固定内容（模拟静态文件服务）。"""
    if 'missing' in request.path:
        return web.Response(status=404)
    if 'abort' in request.path:
        # 声明 chunked 流，只发一部分就断开连接，模拟下载中断
        resp = web.StreamResponse(status=200)
        await resp.prepare(request)
        try:
            await resp.write(PAYLOAD[:65536])
        except Exception:
            pass
        if request.transport is not None:
            request.transport.close()
        return resp
    return web.Response(body=PAYLOAD, content_type='application/octet-stream')


async def _download_once(base_url: str, index: int) -> str:
    """调用被测的 _http_download() 下载一个文件，返回本地路径。"""
    name = f'media_{index}.bin'
    return await ft.FileTransfer._http_download(f'{base_url}/{name}', name)


def test_temp_dir_cache() -> None:
    """验证 _resolve_temp_dir() 只执行一次 makedirs，且返回路径一致。"""
    ft._temp_dir_cache = None
    real_makedirs = os.makedirs
    calls: list[str] = []

    def counting_makedirs(path, *args, **kwargs):
        calls.append(os.path.normcase(str(path)))
        return real_makedirs(path, *args, **kwargs)

    os.makedirs = counting_makedirs
    try:
        p1 = ft._resolve_temp_dir()
        p2 = ft._resolve_temp_dir()
        p3 = ft._resolve_temp_dir()
    finally:
        os.makedirs = real_makedirs

    mkdir_calls = sum(1 for c in calls if c == os.path.normcase(p1))
    check(
        'temp 目录只 mkdir 一次',
        mkdir_calls == 1 and p1 == p2 == p3 and os.path.isdir(p1),
        f'makedirs 调用 {mkdir_calls} 次, path={p1}',
    )


async def test_download_reuse(base_url: str) -> list[str]:
    """顺序下载 N 个文件，断言全程复用同一个 ClientSession。"""
    paths: list[str] = []
    sessions: list[object] = []

    t0 = time.perf_counter()
    for i in range(N_DOWNLOADS):
        paths.append(await _download_once(base_url, i))
        sessions.append(ft._http_session)
    elapsed = time.perf_counter() - t0

    first = sessions[0]
    same_session = first is not None and all(s is first for s in sessions)
    alive = all(s is not None and not s.closed for s in sessions)
    check(
        f'{N_DOWNLOADS} 次下载复用同一共享 session',
        same_session and alive,
        f'session id={id(first)}, 不同对象 {len({id(s) for s in sessions})} 个',
    )
    ops = N_DOWNLOADS / elapsed if elapsed > 0 else 0.0
    print(
        f'    顺序下载 {N_DOWNLOADS} 个文件 (每个 {len(PAYLOAD) / 1024:.0f} KiB) '
        f'总耗时 {elapsed * 1000:.1f} ms | {ops:.1f} ops/s | '
        f'平均 {elapsed / N_DOWNLOADS * 1000:.3f} ms/op'
    )

    sizes_ok = all(os.path.getsize(p) == len(PAYLOAD) for p in paths)
    with open(paths[0], 'rb') as f:
        content_ok = f.read() == PAYLOAD
    check('下载文件大小/内容正确', sizes_ok and content_ok,
          f'{N_DOWNLOADS} 个文件均为 {len(PAYLOAD)} 字节')
    return paths


async def test_resolve_path(base_url: str) -> list[str]:
    """验证 resolve() 走 HTTP 下载的完整链路仍然正常。"""
    src = ft.FileSource(http_url=f'{base_url}/resolve_me.bin', file_name='resolve_me.bin')
    await ft.FileTransfer.resolve(src)
    ok = bool(src.local_path) and os.path.exists(src.local_path) and src.file_size == len(PAYLOAD)
    check('resolve() HTTP 下载链路正常', ok,
          f'local_path={os.path.basename(src.local_path) if src.local_path else None}, '
          f'size={src.file_size}')
    return [src.local_path] if src.local_path else []


async def test_aclose_and_rebuild(base_url: str) -> list[str]:
    """验证 aclose_http_session() 幂等，且关闭后能自动重建 session。"""
    old = ft._http_session
    await ft.aclose_http_session()
    await ft.aclose_http_session()  # 幂等：重复调用不抛异常
    check('aclose_http_session() 幂等且关闭 session',
          old is not None and old.closed and ft._http_session is None,
          f'closed={old.closed if old else None}, 全局引用已置空={ft._http_session is None}')

    path = await _download_once(base_url, N_DOWNLOADS)
    rebuilt = ft._http_session
    check('aclose 后再次下载自动重建 session',
          rebuilt is not None and not rebuilt.closed and rebuilt is not old,
          f'旧 id={id(old)} → 新 id={id(rebuilt)}')
    return [path]


async def test_closed_session_rebuild(base_url: str) -> list[str]:
    """验证共享 session 被外部 close() 后，下一次下载会自动重建。"""
    current = ft._http_session
    await current.close()

    path = await _download_once(base_url, N_DOWNLOADS + 1)
    rebuilt = ft._http_session
    check('session.closed 时自动重建',
          rebuilt is not None and not rebuilt.closed and rebuilt is not current,
          f'旧 id={id(current)} → 新 id={id(rebuilt)}')
    return [path]


async def test_concurrent_downloads(base_url: str) -> list[str]:
    """并发下载，验证共享连接池在并发下仍然只用一个 session 且全部成功。"""
    session_before = ft._http_session
    t0 = time.perf_counter()
    paths = await asyncio.gather(*[
        _download_once(base_url, 1000 + i) for i in range(N_CONCURRENT)
    ])
    elapsed = time.perf_counter() - t0

    ok = (
        all(os.path.getsize(p) == len(PAYLOAD) for p in paths)
        and ft._http_session is session_before
        and session_before is not None
        and not session_before.closed
    )
    check(f'{N_CONCURRENT} 个并发下载共享同一 session',
          ok, f'总耗时 {elapsed * 1000:.1f} ms | '
              f'{N_CONCURRENT / elapsed:.1f} ops/s')
    return list(paths)


async def test_failure_cleanup(base_url: str) -> None:
    """验证下载失败/中断时仍会删除半成品临时文件（保持旧行为）。"""
    temp_dir = ft._resolve_temp_dir()

    # 1) HTTP 404
    before = set(os.listdir(temp_dir))
    raised = False
    try:
        await ft.FileTransfer._http_download(f'{base_url}/missing.bin', 'missing.bin')
    except Exception:
        raised = True
    leftover = set(os.listdir(temp_dir)) - before
    check('HTTP 404 时抛异常且不残留文件', raised and not leftover,
          f'异常已抛出={raised}, 残留文件={sorted(leftover) if leftover else "无"}')

    # 2) 下载中途连接断开：此时半成品文件已写入，应被清理
    before = set(os.listdir(temp_dir))
    raised = False
    try:
        await ft.FileTransfer._http_download(f'{base_url}/abort.bin', 'abort.bin')
    except Exception:
        raised = True
    leftover = set(os.listdir(temp_dir)) - before
    check('下载中断时清理半成品文件', raised and not leftover,
          f'异常已抛出={raised}, 残留文件={sorted(leftover) if leftover else "无"}')


async def run() -> None:
    """启动本地服务并执行全部检查。"""
    downloaded: list[str] = []

    # 1) temp 目录缓存
    test_temp_dir_cache()

    # 2) 本地静态文件服务 (仅监听 127.0.0.1，不依赖外网)
    app = web.Application()
    app.router.add_get('/{tail:.*}', _handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = runner.addresses[0][1]
    base_url = f'http://127.0.0.1:{port}'
    print(f'    本地测试服务: {base_url}')

    try:
        downloaded += await test_download_reuse(base_url)
        downloaded += await test_resolve_path(base_url)
        downloaded += await test_aclose_and_rebuild(base_url)
        downloaded += await test_closed_session_rebuild(base_url)
        downloaded += await test_concurrent_downloads(base_url)
        await test_failure_cleanup(base_url)
    finally:
        # 清理共享 session、本地服务与测试临时文件
        try:
            await ft.aclose_http_session()
        except Exception:
            pass
        await runner.cleanup()
        _cleanup_files(downloaded)


def _cleanup_files(paths: list[str]) -> None:
    """删除测试生成的临时文件。"""
    removed = 0
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                removed += 1
        except Exception:
            pass
    if removed:
        print(f'    已清理测试临时文件 {removed} 个')


def main() -> int:
    print('=== TQSync 文件下载连接复用测试 ===')
    try:
        asyncio.run(run())
    except Exception:
        print('[FAIL] 测试执行异常:')
        traceback.print_exc()
        return 1

    failed = [r for r in _results if not r[1]]
    print('-' * 60)
    if failed:
        print(f'FAIL: {len(failed)}/{len(_results)} 项检查未通过')
        for name, _, detail in failed:
            print(f'  - {name} {detail}')
        return 1
    print(f'PASS: 全部 {len(_results)} 项检查通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
