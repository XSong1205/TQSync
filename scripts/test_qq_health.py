"""QQ 主动健康监测冒烟测试。

用法:
    python scripts/test_qq_health.py

覆盖点：
- 在线时保持安静；断开只告警 1 条，离线期间不刷屏；恢复只通知 1 条
- 单次抖动不误报；抑制窗口内再次掉线全程静默；抑制到期后自动补发
- 告警/恢复通知发送失败后自动重试；TG/DB 异常不影响主循环
- 进程重启：已告警的故障不重复告警、中断时长连续；未告警的故障会补发
- 冷启动观察期：NapCat 登录中不误报；观察期结束仍断开才告警
- probe_health 网络层：正常 / online=false / 降级 / HTTP 错误 / 超时降级 / 连接拒绝
- start()/stop() 后台任务生命周期

全部通过输出 PASS。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import qq_health as qh
from handlers.qq_handler import OneBotClient

_checks = 0


def check(cond, msg):
    global _checks
    _checks += 1
    if not cond:
        raise AssertionError(f"FAIL: {msg}")
    print(f"  ok - {msg}")


class FakeBot:
    def __init__(self):
        self.messages = []
        self.fail_times = 0

    async def send_message(self, chat_id, text):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("telegram send failed")
        self.messages.append(text)


class FakeOneBot:
    """probe_health 桩：可用 script 队列逐个消费，默认返回 default。"""

    def __init__(self):
        self.base_url = "http://fake-napcat:3000"
        self.default = {"ok": True, "latency_ms": 12, "error": None}
        self.script = []

    async def probe_health(self, timeout=5.0):
        if self.script:
            return dict(self.script.pop(0))
        return dict(self.default)


class FakeDB:
    def __init__(self):
        self.store = {}
        self.fail = False

    async def get_setting(self, key, default=None):
        if self.fail:
            raise RuntimeError("db read failed")
        return self.store.get(key, default)

    async def set_setting(self, key, value):
        if self.fail:
            raise RuntimeError("db write failed")
        self.store[key] = value


def new_monitor(bot, **overrides):
    opts = dict(
        CONFIRM_GAP=0,
        STARTUP_DELAY=0,
        PROBE_INTERVAL=0.02,
        STARTUP_OFFLINE_GRACE=0,
        ALERT_RETRY_BACKOFF=0,
    )
    opts.update(overrides)
    mon = qh.QQHealthMonitor(**opts)
    mon.bind(bot, -100123)
    return mon


OK_PROBE = {"ok": True, "latency_ms": 12, "error": None}
FAIL_PROBE = {"ok": False, "error": "ClientConnectorError: refused", "latency_ms": None}


async def state_machine_tests(fake_ob, fake_db):
    key = qh.QQHealthMonitor.SETTING_KEY

    print("[1] 在线时保持安静")
    fake_ob.script = []
    fake_ob.default = dict(OK_PROBE)
    bot = FakeBot()
    mon = new_monitor(bot)
    await mon._load_state()
    check(mon.state == qh.STATE_UNKNOWN, "初始状态 unknown")
    check(await mon.check_once() is True, "探测成功返回 True")
    check(mon.state == qh.STATE_ONLINE, "状态切换为 online")
    check(bot.messages == [], "在线不发送任何 TG 消息")
    check("✅" in mon.status_text() and "12ms" in mon.status_text(),
          f"状态文案含延迟: {mon.status_text()}")

    print("[2] 断开只告警一次，离线期间不刷屏")
    fake_ob.default = dict(FAIL_PROBE)
    check(await mon.check_once() is False, "探测失败返回 False")
    check(mon.state == qh.STATE_OFFLINE, "状态切换为 offline")
    check(len(bot.messages) == 1, "断开只发 1 条告警")
    alert = bot.messages[0]
    check("断开" in alert and "ClientConnectorError" in alert, "告警内容包含断开与原因")
    check("不再重复提醒" in alert, "告警写明离线期间静默")
    check("已断开" in mon.status_text(), f"状态文案为断开: {mon.status_text()}")

    await mon.check_once()
    await mon.check_once()
    check(len(bot.messages) == 1, "持续离线不再发送任何消息")

    print("[3] 恢复只通知一次，含中断时长")
    fake_ob.default = dict(OK_PROBE)
    check(await mon.check_once() is True, "恢复后探测成功")
    check(mon.state == qh.STATE_ONLINE, "状态回到 online")
    check(len(bot.messages) == 2, "恢复只发 1 条通知（共 2 条）")
    check("恢复" in bot.messages[1] and "中断时长" in bot.messages[1],
          "恢复通知包含中断时长")

    print("[3b] 抑制窗口内再次掉线：断开与恢复都静默")
    fake_ob.default = dict(FAIL_PROBE)
    await mon.check_once()
    check(mon.state == qh.STATE_OFFLINE, "再次判定断开")
    check(len(bot.messages) == 2, "30 分钟抑制窗口内不再告警")
    fake_ob.default = dict(OK_PROBE)
    await mon.check_once()
    check(mon.state == qh.STATE_ONLINE, "恢复在线")
    check(len(bot.messages) == 2, "未告警过的故障恢复也保持静默")

    print("[4] 单次抖动不误报")
    flap_bot = FakeBot()
    flap_mon = new_monitor(flap_bot)
    await flap_mon._load_state()
    fake_ob.script = [dict(FAIL_PROBE), dict(OK_PROBE)]
    fake_ob.default = dict(OK_PROBE)
    check(await flap_mon.check_once() is True, "第二次探测成功后不判定断开")
    check(flap_mon.state == qh.STATE_ONLINE, "抖动后保持 online")
    check(flap_bot.messages == [], "抖动不发送任何消息")

    print("[5] 进程重启后同一故障不重复告警（已告警）")
    fake_db.store[key] = json.dumps({
        "state": qh.STATE_OFFLINE,
        "since": time.time() - 600,
        "alerted": True,
        "last_alert_at": time.time() - 60,
    })
    restart_bot = FakeBot()
    restart_mon = new_monitor(restart_bot)
    await restart_mon._load_state()
    fake_ob.default = dict(FAIL_PROBE)
    check(await restart_mon.check_once() is False, "重启后探测仍判定断开")
    check(restart_bot.messages == [], "30 分钟窗口内不重复告警")
    check(restart_mon.state == qh.STATE_OFFLINE, "重启后状态为 offline")
    persisted = json.loads(fake_db.store[key])
    check(persisted["state"] == qh.STATE_OFFLINE and persisted["alerted"] is True,
          "状态与 alerted 已落库")

    fake_ob.default = dict(OK_PROBE)
    await restart_mon.check_once()
    check(len(restart_bot.messages) == 1 and "恢复" in restart_bot.messages[0],
          "恢复仍会通知")
    check("10 分钟" in restart_bot.messages[0],
          f"中断时长跨重启连续: {restart_bot.messages[0]!r}")

    print("[5b] 重启后先恢复、再在抑制窗口内掉线：全程静默")
    fake_db.store[key] = json.dumps({
        "state": qh.STATE_OFFLINE,
        "since": time.time() - 120,
        "alerted": True,
        "last_alert_at": time.time() - 60,
    })
    quiet_bot = FakeBot()
    quiet_mon = new_monitor(quiet_bot)
    await quiet_mon._load_state()
    fake_ob.default = dict(OK_PROBE)
    await quiet_mon.check_once()
    check(quiet_mon.state == qh.STATE_ONLINE and quiet_bot.messages == [], "重启后探测正常，静默")
    fake_ob.default = dict(FAIL_PROBE)
    await quiet_mon.check_once()
    check(quiet_mon.state == qh.STATE_OFFLINE and quiet_bot.messages == [], "抑制窗口内断开静默")
    fake_ob.default = dict(OK_PROBE)
    await quiet_mon.check_once()
    check(quiet_mon.state == qh.STATE_ONLINE and quiet_bot.messages == [],
          "未告警过的断开，恢复也保持静默")

    print("[5c] 重启读到「未告警」的故障：补发告警与恢复")
    fake_db.store[key] = json.dumps({
        "state": qh.STATE_OFFLINE,
        "since": time.time() - 600,
        "alerted": False,
        "last_alert_at": time.time() - 7200,
    })
    stale_bot = FakeBot()
    stale_mon = new_monitor(stale_bot)
    await stale_mon._load_state()
    fake_ob.default = dict(FAIL_PROBE)
    await stale_mon.check_once()
    check(len(stale_bot.messages) == 1 and "断开" in stale_bot.messages[0],
          "上一段故障的告警记录不会误抑制本段：补发告警")
    fake_ob.default = dict(OK_PROBE)
    await stale_mon.check_once()
    check(len(stale_bot.messages) == 2 and "恢复" in stale_bot.messages[1],
          "补发告警后恢复会通知")

    print("[6] 抑制到期后自动补发断开告警")
    b6 = FakeBot()
    m6 = new_monitor(b6)
    await m6._load_state()
    fake_ob.default = dict(OK_PROBE)
    await m6.check_once()
    m6._suppress_until = time.time() + 3600  # 模拟刚刚告警过
    fake_ob.default = dict(FAIL_PROBE)
    await m6.check_once()
    check(m6.state == qh.STATE_OFFLINE and b6.messages == [], "抑制窗口内断开静默")
    m6._suppress_until = time.time() - 1
    await m6.check_once()
    check(len(b6.messages) == 1 and "断开" in b6.messages[0], "抑制到期后补发 1 条告警")

    print("[7] 告警/恢复通知发送失败后自动重试")
    fake_db.store.clear()
    b7 = FakeBot()
    b7.fail_times = 1
    m7 = new_monitor(b7)
    await m7._load_state()
    fake_ob.default = dict(FAIL_PROBE)
    await m7.check_once()
    check(len(b7.messages) == 1, "断开通告首次失败后自动重试成功")
    check(m7._offline_alert_sent is True, "发送成功后标记已告警")
    b7.fail_times = 1
    fake_ob.default = dict(OK_PROBE)
    await m7.check_once()
    check(len(b7.messages) == 2 and "恢复" in b7.messages[1], "恢复通知失败后自动补发")

    print("[8] 冷启动观察期避免 NapCat 登录中误报")
    b8 = FakeBot()
    m8 = new_monitor(b8, STARTUP_OFFLINE_GRACE=0.25)
    await m8._load_state()
    fake_ob.default = dict(FAIL_PROBE)
    await m8.check_once()
    check(m8.state == qh.STATE_OFFLINE and b8.messages == [], "观察期内判定断开但不告警")
    await asyncio.sleep(0.3)
    await m8._maybe_send_pending_alert()
    check(len(b8.messages) == 1 and "断开" in b8.messages[0], "观察期结束后补发告警")

    b8b = FakeBot()
    fake_db.store.clear()  # 模拟全新部署，无历史状态
    m8b = new_monitor(b8b, STARTUP_OFFLINE_GRACE=0.25)
    await m8b._load_state()
    fake_ob.default = dict(FAIL_PROBE)
    await m8b.check_once()
    fake_ob.default = dict(OK_PROBE)
    await m8b.check_once()
    check(b8b.messages == [], "登录在观察期内完成：全程静默")

    print("[9] TG/DB 异常不影响主循环")
    fake_db.store.clear()
    fake_db.fail = True
    b9 = FakeBot()
    b9.fail_times = 10
    m9 = new_monitor(b9)
    await m9._load_state()  # DB 读失败被吞掉
    fake_ob.default = dict(FAIL_PROBE)
    await m9.check_once()  # TG 发送失败 + DB 写失败都被吞掉
    check(m9.state == qh.STATE_OFFLINE and b9.messages == [], "发送/落库失败被安全吞掉")
    fake_db.fail = False

    print("[10] start()/stop() 生命周期")
    fake_db.store.clear()
    fake_ob.default = dict(OK_PROBE)
    b10 = FakeBot()
    m10 = new_monitor(b10, STARTUP_DELAY=0.01)
    task = await m10.start()
    await asyncio.sleep(0.1)
    check(not task.done() and m10.state == qh.STATE_ONLINE, "后台探测任务已运行")
    await m10.stop()
    check(task.done(), "stop() 后任务已取消")
    await m10.stop()
    check(True, "重复 stop() 安全")


async def probe_health_tests():
    print("[11] probe_health 网络层（本地假 NapCat）")
    mode = {"m": "ok"}

    async def get_status(request):
        if mode["m"] == "slow":
            await asyncio.sleep(0.5)
        if mode["m"] == "retcode":
            return web.json_response({"status": "failed", "retcode": 1})
        if mode["m"] == "retcode_both":
            return web.json_response({"status": "failed", "retcode": 1})
        if mode["m"] == "offline":
            return web.json_response({"status": "ok", "retcode": 0, "data": {"online": False}})
        if mode["m"] == "no_online":
            return web.json_response({"status": "ok", "retcode": 0, "data": {}})
        if mode["m"] == "legacy":
            return web.Response(status=404, text="404: Not Found")
        if mode["m"] == "http500":
            return web.json_response(
                {"status": "ok", "retcode": 0, "data": {"online": True}}, status=500)
        return web.json_response(
            {"status": "ok", "retcode": 0, "data": {"online": True, "good": True}})

    async def get_login(request):
        if mode["m"] == "retcode_both":
            return web.json_response({"status": "failed", "retcode": 1})
        return web.json_response({"status": "ok", "retcode": 0, "data": {"user_id": 12345}})

    app = web.Application()
    app.router.add_post("/get_status", get_status)
    app.router.add_post("/get_login_info", get_login)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    client = OneBotClient()
    client.base_url = f"http://127.0.0.1:{port}"
    try:
        mode["m"] = "ok"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is True and r["endpoint"] == "/get_status"
              and isinstance(r["latency_ms"], int), "正常响应 → 在线（/get_status）")

        mode["m"] = "offline"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is False and "未登录" in (r["error"] or ""),
              "online=false → 判定断开")

        mode["m"] = "no_online"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is True and r["endpoint"] == "/get_login_info",
              "/get_status 缺 online 字段 → 降级 /get_login_info 确认登录")

        mode["m"] = "legacy"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is True and r["endpoint"] == "/get_login_info",
              "/get_status 不存在 → 降级 /get_login_info")

        mode["m"] = "retcode"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is True and r["endpoint"] == "/get_login_info",
              "retcode 非 0 → 降级 /get_login_info")

        mode["m"] = "http500"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is True and r["endpoint"] == "/get_login_info",
              "HTTP 5xx → 降级 /get_login_info")

        mode["m"] = "retcode_both"
        r = await client.probe_health(timeout=2)
        check(r["ok"] is False and "retcode" in (r["error"] or ""),
              "两个端点都异常 → 判定断开")

        mode["m"] = "slow"
        r = await client.probe_health(timeout=0.2)
        check(r["ok"] is True and r["endpoint"] == "/get_login_info",
              "/get_status 超时 → 降级 /get_login_info")

        client.base_url = "http://127.0.0.1:1"
        r = await client.probe_health(timeout=0.3)
        check(r["ok"] is False and r["error"], f"连接拒绝 → 判定断开（{r['error'][:40]}...）")
    finally:
        await client.close()
        await runner.cleanup()


async def main():
    fake_ob = FakeOneBot()
    fake_db = FakeDB()
    qh.db = fake_db
    qh.onebot_client = fake_ob

    await state_machine_tests(fake_ob, fake_db)
    await probe_health_tests()

    print(f"\nPASS ({_checks} checks)")


if __name__ == "__main__":
    asyncio.run(main())
