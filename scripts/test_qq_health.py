"""QQ 主动健康监测冒烟测试。

用法:
    python scripts/test_qq_health.py

覆盖点：
- 在线时不发任何消息（安静）
- 连续探测失败 -> 只告警 1 条；离线期间继续失败保持静默（不刷屏）
- 恢复在线 -> 只发 1 条恢复通知，且中断时长正确
- 单次抖动（一次失败后立刻恢复）不误报
- 进程重启后同一次故障不重复告警，恢复通知里的中断时长跨重启连续
- /status 状态文案

全部通过输出 PASS。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import qq_health as qh

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

    async def send_message(self, chat_id, text):
        self.messages.append(text)


class FakeOneBot:
    """probe_health 桩：可用 script 队列逐个消费，默认返回 default。"""

    def __init__(self):
        self.default = {"ok": True, "latency_ms": 12, "error": None}
        self.script = []
        self.calls = 0

    async def probe_health(self, timeout=5.0):
        self.calls += 1
        if self.script:
            return dict(self.script.pop(0))
        return dict(self.default)


class FakeDB:
    def __init__(self):
        self.store = {}

    async def get_setting(self, key, default=None):
        return self.store.get(key, default)

    async def set_setting(self, key, value):
        self.store[key] = value


def new_monitor(bot, setting_key=None):
    mon = qh.QQHealthMonitor(
        CONFIRM_GAP=0,
        STARTUP_DELAY=0,
        PROBE_INTERVAL=0.01,
        **({"SETTING_KEY": setting_key} if setting_key else {}),
    )
    mon.bind(bot, -100123)
    return mon


async def main():
    fake_bot = FakeBot()
    fake_ob = FakeOneBot()
    fake_db = FakeDB()
    qh.db = fake_db
    qh.onebot_client = fake_ob
    key = qh.QQHealthMonitor.SETTING_KEY

    print("[1] 在线时保持安静")
    mon = new_monitor(fake_bot)
    check(mon.state == qh.STATE_UNKNOWN, "初始状态 unknown")
    check(await mon.check_once() is True, "探测成功返回 True")
    check(mon.state == qh.STATE_ONLINE, "状态切换为 online")
    check(fake_bot.messages == [], "在线不发送任何 TG 消息")
    check("✅" in mon.status_text() and "12ms" in mon.status_text(),
          f"状态文案含延迟: {mon.status_text()}")

    print("[2] 断开只告警一次，离线期间不刷屏")
    fake_ob.default = {"ok": False, "error": "ClientConnectorError: refused", "latency_ms": None}
    check(await mon.check_once() is False, "探测失败返回 False")
    check(mon.state == qh.STATE_OFFLINE, "状态切换为 offline")
    check(len(fake_bot.messages) == 1, "断开只发 1 条告警")
    alert = fake_bot.messages[0]
    check("断开" in alert and "ClientConnectorError" in alert, "告警内容包含断开与原因")
    check("不再重复提醒" in alert, "告警写明离线期间静默")
    check("已断开" in mon.status_text(), f"状态文案为断开: {mon.status_text()}")

    await mon.check_once()
    await mon.check_once()
    check(len(fake_bot.messages) == 1, "持续离线不再发送任何消息")

    print("[3] 恢复只通知一次，含中断时长")
    fake_ob.default = {"ok": True, "latency_ms": 8, "error": None}
    check(await mon.check_once() is True, "恢复后探测成功")
    check(mon.state == qh.STATE_ONLINE, "状态回到 online")
    check(len(fake_bot.messages) == 2, "恢复只发 1 条通知（共 2 条）")
    check("恢复" in fake_bot.messages[1] and "中断时长" in fake_bot.messages[1],
          "恢复通知包含中断时长")

    print("[3b] 抑制窗口内再次掉线：断开与恢复都静默")
    fake_ob.default = {"ok": False, "error": "ClientConnectorError: refused", "latency_ms": None}
    await mon.check_once()
    check(mon.state == qh.STATE_OFFLINE, "再次判定断开")
    check(len(fake_bot.messages) == 2, "30 分钟抑制窗口内不再告警")
    fake_ob.default = {"ok": True, "latency_ms": 7, "error": None}
    await mon.check_once()
    check(mon.state == qh.STATE_ONLINE, "恢复在线")
    check(len(fake_bot.messages) == 2, "未告警过的故障恢复也保持静默")

    print("[4] 单次抖动不误报")
    flap_bot = FakeBot()
    flap_mon = new_monitor(flap_bot)
    fake_ob.script = [{"ok": False, "error": "timeout"}, {"ok": True, "latency_ms": 6, "error": None}]
    check(await flap_mon.check_once() is True, "第二次探测成功后不判定断开")
    check(flap_mon.state == qh.STATE_ONLINE, "抖动后保持 online")
    check(flap_bot.messages == [], "抖动不发送任何消息")

    print("[5] 进程重启后同一故障不重复告警")
    fake_db.store[key] = json.dumps({
        "state": qh.STATE_OFFLINE,
        "since": time.time() - 600,
        "last_alert_at": time.time() - 60,
    })
    restart_bot = FakeBot()
    restart_mon = new_monitor(restart_bot)
    await restart_mon._load_state()
    fake_ob.default = {"ok": False, "error": "ClientConnectorError: refused", "latency_ms": None}
    check(await restart_mon.check_once() is False, "重启后探测仍判定断开")
    check(restart_bot.messages == [], "30 分钟窗口内不重复告警")
    check(restart_mon.state == qh.STATE_OFFLINE, "重启后状态为 offline")
    check(json.loads(fake_db.store[key])["state"] == qh.STATE_OFFLINE, "状态已落库")

    fake_ob.default = {"ok": True, "latency_ms": 9, "error": None}
    await restart_mon.check_once()
    check(len(restart_bot.messages) == 1 and "恢复" in restart_bot.messages[0],
          "恢复仍会通知")
    check("10 分钟" in restart_bot.messages[0],
          f"中断时长跨重启连续: {restart_bot.messages[0]!r}")

    print("[5b] 重启后先恢复、再在抑制窗口内掉线：全程静默")
    fake_db.store[key] = json.dumps({
        "state": qh.STATE_OFFLINE,
        "since": time.time() - 120,
        "last_alert_at": time.time() - 60,
    })
    quiet_bot = FakeBot()
    quiet_mon = new_monitor(quiet_bot)
    await quiet_mon._load_state()
    fake_ob.default = {"ok": True, "latency_ms": 10, "error": None}
    await quiet_mon.check_once()
    check(quiet_mon.state == qh.STATE_ONLINE and quiet_bot.messages == [], "重启后探测正常，静默")
    fake_ob.default = {"ok": False, "error": "ClientConnectorError: refused", "latency_ms": None}
    await quiet_mon.check_once()
    check(quiet_mon.state == qh.STATE_OFFLINE and quiet_bot.messages == [], "抑制窗口内断开静默")
    fake_ob.default = {"ok": True, "latency_ms": 10, "error": None}
    await quiet_mon.check_once()
    check(quiet_mon.state == qh.STATE_ONLINE and quiet_bot.messages == [],
          "未告警过的断开，恢复也保持静默")

    print("[6] 工具函数")
    check(qh._fmt_duration(0) == "0 秒", "_fmt_duration(0)")
    check(qh._fmt_duration(90) == "1 分钟", "_fmt_duration(90)")
    check(qh._fmt_duration(3700) == "1 小时 1 分钟", "_fmt_duration(3700)")
    check(qh._fmt_duration(90000) == "1 天 1 小时", "_fmt_duration(90000)")

    print(f"\nPASS ({_checks} checks)")


if __name__ == "__main__":
    asyncio.run(main())
