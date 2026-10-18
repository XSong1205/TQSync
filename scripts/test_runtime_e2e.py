"""运行时端到端冒烟测试（真实事件循环 + 真实 aiohttp/uvicorn + 真实数据库）。

用法:
    python scripts/test_runtime_e2e.py

说明：
- 使用真实的 `main.handle_qq_webhook`、`SyncEngine` 队列与工作者、`FileTransfer` 媒体链路、
  真实 SQLite 数据库、真实 FastAPI Admin API（uvicorn），只有两处是替身：
  Telegram Bot（记录发送调用，不发真实消息）与 NapCat HTTP（不连真实 NapCat）。
- 因此不需要真实 token / 群号，不会向任何真实群发消息，可安全反复运行。

覆盖：
1. 服务启动：Webhook + Admin API 正常监听，健康检查通过
2. 文本消息 QQ -> TG：入队、3 个工作者并发处理、真实写入 DB 映射
3. 媒体消息 QQ -> TG：本地 file:// 文件先异步复制进 temp、PIL 校验、发送后清理
4. 撤回通知：命中映射 -> 调用 TG 删除 + 清理 DB 映射
5. 20 条消息突发：吞吐与事件循环停顿（lag）实测
6. Admin API 状态接口：鉴权 + 统计字段
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_checks = 0


def check(cond, msg):
    global _checks
    _checks += 1
    if not cond:
        raise AssertionError(f"FAIL: {msg}")
    print(f"  ok - {msg}")


class FakeMessage:
    def __init__(self, message_id: int):
        self.message_id = message_id


class _Obj:
    """构造临时对象，用来模拟 PTB 的 MessageReactionUpdated / Chat 等结构。"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeBot:
    """Telegram Bot 替身：记录发送内容，模拟网络延迟。"""

    token = 'fake:token'
    id = 1

    def __init__(self, delay: float = 0.03):
        self.delay = delay
        self.sent = []
        self.deleted = []
        self.photo_exists = []
        self._mid = 1000

    def _next(self) -> int:
        self._mid += 1
        return self._mid

    async def send_message(self, chat_id, text, **kwargs):
        await asyncio.sleep(self.delay)
        mid = self._next()
        self.sent.append(('message', chat_id, text, mid))
        return FakeMessage(mid)

    async def send_photo(self, chat_id, photo, filename=None, caption=None, **kwargs):
        await asyncio.sleep(self.delay)
        self.photo_exists.append(os.path.exists(str(photo)))
        mid = self._next()
        self.sent.append(('photo', chat_id, str(photo), mid))
        return FakeMessage(mid)

    async def send_document(self, chat_id, document, filename=None, **kwargs):
        await asyncio.sleep(self.delay)
        mid = self._next()
        self.sent.append(('document', chat_id, str(document), mid))
        return FakeMessage(mid)

    async def send_video(self, *a, **k):
        return await self.send_document(*a, **k)

    async def send_animation(self, *a, **k):
        return await self.send_document(*a, **k)

    async def send_audio(self, *a, **k):
        return await self.send_document(*a, **k)

    async def send_voice(self, chat_id, voice, caption=None, **kwargs):
        await asyncio.sleep(self.delay)
        mid = self._next()
        self.sent.append(('voice', chat_id, str(getattr(voice, 'name', voice)), mid))
        return FakeMessage(mid)

    async def delete_message(self, chat_id, message_id):
        await asyncio.sleep(0.005)
        self.deleted.append((chat_id, message_id))

    async def get_chat(self, chat_id):
        class _U:
            def mention_html(self):
                return f'<a href="tg://user?id={chat_id}">@u</a>'
        return _U()


class Lag:
    """事件循环停顿采样器。"""

    def __init__(self, interval: float = 0.01):
        self.interval = interval
        self.lags = []
        self._stop = False
        self._task = None

    async def _run(self):
        while not self._stop:
            t0 = time.perf_counter()
            await asyncio.sleep(self.interval)
            self.lags.append(max(0.0, time.perf_counter() - t0 - self.interval))

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop = True
        if self._task:
            await self._task
        return max(self.lags) * 1000 if self.lags else 0.0


async def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def run() -> None:
    import aiohttp
    from aiohttp import web
    import uvicorn
    from PIL import Image

    import main as m
    from api.admin_api import app as admin_app
    from config.config_loader import config_loader
    from core.sync_engine import SyncEngine
    from db.database import db
    from handlers.qq_handler import onebot_client
    from utils.qq_text import (format_qq_face, qq_emoji_id_to_emoji,
                               tg_emoji_from_qq, tg_emoji_to_qq_emoji_id)

    # ---- 0. 文本/表情格式化工具 ----
    print("[格式化工具]")
    check(format_qq_face({'id': '14', 'raw': {'faceText': '/微笑'}}) == '[微笑]',
          "face 段优先使用 raw.faceText")
    check(format_qq_face({'id': '13'}) == '[呲牙]', "缺少 faceText 时回退 id->名称表")
    check(format_qq_face({'id': '99999'}) == '[表情]', "未知表情 id 回退为 [表情]")
    check(tg_emoji_to_qq_emoji_id('👍') == '128077', "TG emoji -> 十进制码点")
    check(tg_emoji_to_qq_emoji_id('❤️') == '10084', "多码点 emoji 取基础字符码点")
    check(tg_emoji_from_qq({'emoji_id': '128077'}) == '👍', "NapCat 码点 -> TG emoji")
    check(qq_emoji_id_to_emoji('14') == '', "QQ 内置表情 id 不按码点误判")

    tmpdir = tempfile.mkdtemp(prefix="tqsync_runtime_")
    real_cwd = os.getcwd()
    os.chdir(tmpdir)
    os.makedirs('temp', exist_ok=True)

    bot = FakeBot()
    lag = Lag()
    runner = None
    admin_task = None
    admin_server = None
    engine = None

    try:
        # ---- 初始化运行时 ----
        db.db_path = os.path.join(tmpdir, 'runtime.db')
        await db.init_db()

        engine = SyncEngine(bot)

        async def fake_bot_id():
            return 999
        onebot_client.get_bot_id = fake_bot_id

        async def fake_send_group_msg(group_id, message):
            return {'status': 'ok', 'retcode': 0, 'data': {'message_id': 1}}
        onebot_client.send_group_msg = fake_send_group_msg

        # ---- 启动 Webhook 服务（真实 aiohttp 服务器）----
        webhook_path = config_loader.get('server.webhook_path', '/webhook/qq')
        app = web.Application()
        app.router.add_post(webhook_path, m.handle_qq_webhook)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        webhook_port = site._server.sockets[0].getsockname()[1]

        # ---- 启动 Admin API（真实 uvicorn）----
        admin_port = await _free_port()
        admin_server = uvicorn.Server(uvicorn.Config(
            admin_app, host='127.0.0.1', port=admin_port, log_level='warning'
        ))
        admin_task = asyncio.create_task(admin_server.serve())
        for _ in range(100):
            if admin_server.started:
                break
            await asyncio.sleep(0.05)

        check(admin_server.started, f"Admin API 已启动（127.0.0.1:{admin_port}）")
        check(webhook_port > 0, f"Webhook 服务已启动（127.0.0.1:{webhook_port}{webhook_path}）")

        group_id = config_loader.get('qq.group_id')
        token = config_loader.get('server.webhook_token', '') or ''
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        url = f'http://127.0.0.1:{webhook_port}{webhook_path}'

        def text_payload(text: str, qq_msg_id: int, user_id: int = 12345) -> dict:
            return {
                'post_type': 'message',
                'message_type': 'group',
                'group_id': group_id,
                'user_id': user_id,
                'sender': {'nickname': '测试用户'},
                'message_id': qq_msg_id,
                'message': [{'type': 'text', 'data': {'text': text}}],
            }

        lag.start()
        async with aiohttp.ClientSession() as session:
            async def post(payload):
                async with session.post(url, json=payload, headers=headers) as resp:
                    return resp.status

            # ---- 1. 文本消息 ----
            print("[文本消息 QQ -> TG]")
            t0 = time.perf_counter()
            status = await post(text_payload('运行时冒烟：一条普通文本消息', 90001))
            check(status == 200, f"Webhook 返回 200（实际 {status}）")
            for _ in range(100):
                if bot.sent:
                    break
                await asyncio.sleep(0.01)
            deliver_ms = (time.perf_counter() - t0) * 1000
            check(len(bot.sent) == 1, "消息已被同步工作者投递到 TG（经过真实队列）")
            check('运行时冒烟：一条普通文本消息' in bot.sent[0][2], "TG 文本内容正确")
            check('[QQ]' in bot.sent[0][2] and '[未绑定]' in bot.sent[0][2],
                  "显示名走绑定系统（未绑定后缀）")
            tg_msg_id = bot.sent[0][3]
            mapped = await db.get_tg_msg_id_by_qq(90001)
            check(mapped == tg_msg_id, f"消息映射已写入数据库（QQ 90001 -> TG {mapped}）")
            print(f"       端到端投递延迟 {deliver_ms:.0f} ms（含模拟的 30ms TG 网络延迟）")

            # ---- 2. 媒体消息（本地文件必须被复制到 temp 后才能发送）----
            print("[媒体消息 QQ -> TG]")
            img_path = os.path.join(tmpdir, 'test_image.png')
            Image.new('RGB', (32, 32), (200, 30, 30)).save(img_path)
            payload = text_payload('', 90002)
            payload['message'] = [{
                'type': 'image',
                'data': {'url': f'file:///{img_path.replace(chr(92), "/")}', 'file': 'test_image.png'},
            }]
            await post(payload)
            for _ in range(200):
                if len(bot.sent) >= 2:
                    break
                await asyncio.sleep(0.01)
            check(len(bot.sent) >= 2 and bot.sent[1][0] == 'photo', "图片消息被投递为 TG photo")
            sent_path = bot.sent[1][2]
            check(bot.photo_exists and bot.photo_exists[-1], "发送瞬间文件存在（复制已完成）")
            check(os.path.dirname(os.path.abspath(sent_path)) == os.path.join(tmpdir, 'temp'),
                  "图片确实先被复制进 temp 再发送")
            # 清理发生在发送+写映射之后的 finally 里，等映射落库后再轮询文件消失
            for _ in range(200):
                if await db.get_tg_msg_id_by_qq(90002) is not None:
                    break
                await asyncio.sleep(0.01)
            for _ in range(200):
                if not os.path.exists(sent_path):
                    break
                await asyncio.sleep(0.01)
            check(not os.path.exists(sent_path), "发送后临时文件已被清理")
            check(await db.get_tg_msg_id_by_qq(90002) == bot.sent[1][3], "图片消息映射已写入数据库")

            # ---- 3. 撤回通知 ----
            print("[撤回同步 QQ -> TG]")
            await post({
                'post_type': 'notice', 'notice_type': 'group_recall',
                'group_id': group_id, 'message_id': 90001,
            })
            for _ in range(100):
                if bot.deleted:
                    break
                await asyncio.sleep(0.01)
            check(bot.deleted and bot.deleted[-1][1] == tg_msg_id, "TG 端执行了删除")
            check(await db.get_tg_msg_id_by_qq(90001) is None, "数据库映射已清理")

            # ---- 4. QQ 表情同步 ----
            print("[QQ 表情 -> 文本]")
            payload = text_payload('', 90600)
            payload['message'] = [
                {'type': 'text', 'data': {'text': '表情：'}},
                {'type': 'face', 'data': {'id': '14', 'raw': {'faceText': '/微笑'}}},
                {'type': 'face', 'data': {'id': '13'}},
                {'type': 'text', 'data': {'text': ' 完'}},
            ]
            await post(payload)
            for _ in range(200):
                if any('表情：' in s[2] for s in bot.sent if s[0] == 'message'):
                    break
                await asyncio.sleep(0.01)
            face_text = next((s[2] for s in bot.sent if '表情：' in s[2]), '')
            check('[微笑]' in face_text, f"face 段按 raw.faceText 转成文本（{face_text[:40]}）")
            check('[呲牙]' in face_text, "face 段缺少 faceText 时用内置 id->名称表兜底")

            # ---- 5. 戳一戳 ----
            print("[戳一戳 QQ -> TG]")
            await post({
                'post_type': 'notice', 'notice_type': 'notify', 'sub_type': 'poke',
                'group_id': group_id, 'user_id': 12345, 'target_id': 88888,
            })
            for _ in range(200):
                if any('戳了戳' in s[2] for s in bot.sent):
                    break
                await asyncio.sleep(0.01)
            poke_text = next((s[2] for s in bot.sent if '戳了戳' in s[2]), '')
            check(bool(poke_text), f"戳一戳已同步为 TG 提示（{poke_text[:40]}）")
            check('88888' in poke_text, "戳一戳目标 QQ 号出现在提示里")

            # ---- 6. 表情回应 TG -> QQ ----
            print("[表情回应 TG -> QQ]")
            from handlers import tg_handler
            like_calls = []

            async def fake_set_like(message_id, emoji_id, set_like=True):
                like_calls.append((message_id, emoji_id, set_like))
                return {'retcode': 0, 'status': 'ok'}

            orig_set_like = onebot_client.set_msg_emoji_like
            onebot_client.set_msg_emoji_like = fake_set_like
            try:
                tg_id_for_face = await db.get_tg_msg_id_by_qq(90600)
                check(bool(tg_id_for_face), "表情消息已建立 TG 映射，可用于回应同步")

                reaction_update = _Obj(message_reaction=_Obj(
                    chat=_Obj(id=config_loader.get('telegram.group_id')),
                    message_id=tg_id_for_face,
                    new_reaction=[_Obj(emoji='👍')],
                    old_reaction=[],
                ))
                await tg_handler.handle_message_reaction(reaction_update, None)
                check(len(like_calls) == 1, "新增表情回应触发了一次 QQ 点赞调用")
                check(like_calls[0][0] == 90600, f"回应对应到正确的 QQ 消息（{like_calls[0][0]}）")
                check(like_calls[0][1] == str(ord('👍')), f"emoji 转成十进制码点（{like_calls[0][1]}）")
                check(like_calls[0][2] is True, "新增回应 => set=True")

                # 取消回应
                reaction_update2 = _Obj(message_reaction=_Obj(
                    chat=_Obj(id=config_loader.get('telegram.group_id')),
                    message_id=tg_id_for_face,
                    new_reaction=[],
                    old_reaction=[_Obj(emoji='👍')],
                ))
                await tg_handler.handle_message_reaction(reaction_update2, None)
                check(len(like_calls) == 2 and like_calls[1][2] is False, "取消回应 => set=False")

                # 非目标群 / 无映射时应跳过
                before = len(like_calls)
                await tg_handler.handle_message_reaction(_Obj(message_reaction=_Obj(
                    chat=_Obj(id=-1), message_id=tg_id_for_face,
                    new_reaction=[_Obj(emoji='👍')], old_reaction=[])), None)
                await tg_handler.handle_message_reaction(_Obj(message_reaction=_Obj(
                    chat=_Obj(id=config_loader.get('telegram.group_id')), message_id=999999999,
                    new_reaction=[_Obj(emoji='👍')], old_reaction=[])), None)
                check(len(like_calls) == before, "非目标群/无映射的回应被忽略")
            finally:
                onebot_client.set_msg_emoji_like = orig_set_like

            # ---- 7. 突发吞吐 ----
            print("[20 条消息突发]")
            t0 = time.perf_counter()
            await asyncio.gather(*[
                post(text_payload(f'突发消息 #{i}', 91000 + i, user_id=20000 + i))
                for i in range(20)
            ])
            for _ in range(600):
                if len([s for s in bot.sent if '突发消息' in s[2]]) >= 20:
                    break
                await asyncio.sleep(0.01)
            burst_elapsed = (time.perf_counter() - t0) * 1000
            delivered = len([s for s in bot.sent if '突发消息' in s[2]])
            check(delivered == 20, f"20 条突发消息全部入队并投递（实际 {delivered}）")
            check(engine.sync_queue.qsize() == 0, "队列已排空（无积压）")
            print(f"       20 条消息 {burst_elapsed:.0f} ms 完成 "
                  f"（3 工作者 × 30ms 模拟延迟，理论上限约 {20 / 3 * 30:.0f} ms）")

        max_lag = await lag.stop()
        print(f"       事件循环最大停顿 {max_lag:.1f} ms")
        check(max_lag < 150, f"事件循环无明显停顿（最大 {max_lag:.1f} ms）")

        # ---- 8. Admin API ----
        print("[Admin API]")
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://127.0.0.1:{admin_port}/health') as resp:
                check(resp.status == 200, "健康检查接口 200（无需鉴权）")
            api_key = config_loader.get('server.admin_api_key')
            async with session.get(f'http://127.0.0.1:{admin_port}/admin/status',
                                   headers={'x-api-key': api_key}) as resp:
                check(resp.status == 200, "状态接口 200（带 API Key）")
                data = await resp.json()
            async with session.get(f'http://127.0.0.1:{admin_port}/admin/status') as resp:
                check(resp.status in (401, 403), f"状态接口缺少 API Key 被拒绝（{resp.status}）")
            async with session.get(f'http://127.0.0.1:{admin_port}/admin/logs?lines=20',
                                   headers={'x-api-key': api_key}) as resp:
                logs = await resp.json()
                check(resp.status == 200 and len(logs['logs']) > 0, "日志接口可用（尾部回读）")

        check('uptime' in data and 'db_size' in data and 'sync_count' in data,
              "状态接口字段完整")
        check(data['sync_count'] >= 21, f"状态接口统计到同步条数 {data['sync_count']}")

        print(f"\nPASS - {_checks} 项断言全部通过")
    finally:
        try:
            if engine is not None:
                await engine.stop(timeout=2.0)
        except Exception:
            pass
        if admin_server is not None:
            admin_server.should_exit = True
        if admin_task is not None:
            try:
                await asyncio.wait_for(admin_task, timeout=5)
            except Exception:
                admin_task.cancel()
        if runner is not None:
            await runner.cleanup()
        try:
            await db.close()
        except Exception:
            pass
        os.chdir(real_cwd)
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    if os.environ.get('DUMP_STACK'):
        # 诊断用：60s 未结束则打印所有协程/线程堆栈并退出，便于定位死锁
        import faulthandler
        faulthandler.dump_traceback_later(60, exit=True)
    asyncio.run(run())
