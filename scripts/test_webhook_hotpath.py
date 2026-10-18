"""QQ Webhook 热路径冒烟测试（验证 main.py 优化后行为不变）。

用法:
    python scripts/test_webhook_hotpath.py

覆盖点：
- 普通文本消息 -> 入队 forward_to_tg
- 图片消息（本地 file://）-> 先异步复制进 temp 再入队 forward_media_to_tg
- 命中屏蔽词 -> 不入队
- Bot 自身消息 -> 不入队（反回环）
- 纯媒体消息不再触发无谓的多余文件复制

全部通过输出 PASS。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_checks = 0


def check(cond, msg):
    global _checks
    _checks += 1
    if not cond:
        raise AssertionError(f"FAIL: {msg}")
    print(f"  ok - {msg}")


class FakeRequest:
    def __init__(self, payload: dict, token: str = ''):
        self._payload = payload
        self.remote = '127.0.0.1'
        self.headers = {'Authorization': f'Bearer {token}'} if token else {}

    async def json(self):
        return self._payload


async def run() -> None:
    import main as m
    from config.config_loader import config_loader
    from db.database import db
    from handlers.qq_handler import onebot_client

    tmpdir = tempfile.mkdtemp(prefix="tqsync_webhook_")
    original_cwd = os.getcwd()
    os.chdir(tmpdir)
    os.makedirs('temp', exist_ok=True)

    db.db_path = os.path.join(tmpdir, 'webhook.db')
    await db.init_db()
    await db.set_setting('blocked_words', '["违禁词"]')

    calls: list = []

    class FakeEngine:
        bot = None
        tg_group_id = -1001234567890
        qq_group_id = config_loader.get('qq.group_id')

        # 这些方法只作为入队回调被引用，不需要真实实现
        def forward_to_tg(self, *a, **k):  # noqa: D401
            pass

        def forward_media_to_tg(self, *a, **k):
            pass

        def forward_voice_to_tg(self, *a, **k):
            pass

        def forward_merged_to_tg(self, *a, **k):
            pass

        async def get_display_name(self, **k):
            return 'tester'

        def enqueue_sync_task(self, func, *args, **kwargs):
            calls.append((func.__name__, args, kwargs))

    # 引擎单例与 Bot 号：避免真实网络请求
    m.SyncEngine._instance = FakeEngine()

    async def fake_send_group_msg(group_id, message):
        calls.append(('send_group_msg', (group_id, message), {}))
        return {'status': 'ok', 'retcode': 0, 'data': {'message_id': 1}}

    onebot_client.get_bot_id = lambda: _fake_bot_id()
    onebot_client.send_group_msg = fake_send_group_msg

    bot_qq = 999
    token = config_loader.get('server.webhook_token', '') or ''
    group_id = config_loader.get('qq.group_id')

    async def post(payload):
        return await m.handle_qq_webhook(FakeRequest(payload, token))

    def text_payload(text, user_id=12345):
        return {
            'post_type': 'message',
            'message_type': 'group',
            'group_id': group_id,
            'user_id': user_id,
            'sender': {'nickname': '小明'},
            'message_id': 777,
            'message': [{'type': 'text', 'data': {'text': text}}],
        }

    try:
        # 1. 普通文本
        calls.clear()
        await post(text_payload('你好世界'))
        check(len(calls) == 1 and calls[0][0] == 'forward_to_tg', "文本消息 -> 入队 forward_to_tg")
        check(calls[0][1][2] == '你好世界', "文本内容透传正确")
        check(calls[0][2].get('qq_message_id') == 777, "消息 ID 透传正确")

        # 2. 图片（本地 file://，需先复制到 temp）
        calls.clear()
        src = os.path.join(tmpdir, 'photo.png')
        with open(src, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 64)
        payload = text_payload('')
        payload['message'] = [{'type': 'image', 'data': {'url': f'file:///{src.replace(chr(92), "/")}', 'file': 'photo.png'}}]
        await post(payload)
        check(len(calls) == 1 and calls[0][0] == 'forward_media_to_tg', "图片消息 -> 入队 forward_media_to_tg")
        source = calls[0][1][2]
        check(bool(source.local_path), "FileSource 已解析出本地路径")
        check(os.path.dirname(os.path.abspath(source.local_path)) == os.path.join(tmpdir, 'temp'),
              "本地图片已异步复制到 temp（防止 NapCat 清缓存）")
        check(os.path.basename(source.local_path).startswith('webhook_'), "复制文件命名符合原有约定")

        # 3. 屏蔽词
        calls.clear()
        await post(text_payload('这条有违禁词'))
        check(calls == [], "命中屏蔽词的消息不入队")

        # 4. Bot 自身消息（反回环）
        calls.clear()
        await post(text_payload('机器人自己发的', user_id=bot_qq))
        check(calls == [], "Bot 自身消息被过滤（反回环）")

        # 5. 混合消息：4 个媒体段只应复制实际使用的那一个
        calls.clear()
        temp_before = set(os.listdir(os.path.join(tmpdir, 'temp')))
        payload = text_payload('带图')
        payload['message'] = [
            {'type': 'text', 'data': {'text': '带图'}},
            {'type': 'image', 'data': {'url': f'file:///{src.replace(chr(92), "/")}', 'file': 'photo.png'}},
            {'type': 'file', 'data': {'url': f'file:///{src.replace(chr(92), "/")}', 'file': 'doc.txt', 'name': 'doc.txt'}},
        ]
        await post(payload)
        temp_after = set(os.listdir(os.path.join(tmpdir, 'temp')))
        check(len(calls) == 1 and calls[0][0] == 'forward_media_to_tg', "混合媒体消息入队一次")
        check(len(temp_after - temp_before) == 1, f"只复制实际使用的 1 个文件（实际 {len(temp_after - temp_before)}）")

        print(f"\nPASS - {_checks} 项断言全部通过")
    finally:
        m.SyncEngine._instance = None
        os.chdir(original_cwd)
        try:
            await db.close()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


async def _fake_bot_id():
    return 999


if __name__ == "__main__":
    asyncio.run(run())
