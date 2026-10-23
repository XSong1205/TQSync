"""QQ (NapCat) 主动健康监测。

历史问题：旧实现靠「10 分钟没收到 QQ webhook 消息」这一被动信号判断离线，
并且每 30 分钟重发一次告警。群安静时会误报（半夜尤其明显），真正离线时又会
反复刷屏，检测延迟还高达 10 分钟。

现方案：
1. 定时主动请求 NapCat 的 HTTP 接口（/get_status，接口异常时降级 /get_login_info）；
   连接失败 / 超时 / 无有效响应 → 判定连接断开。
2. 连续 2 次探测失败才确认断开（间隔 3 秒），避免单次网络抖动误报。
3. 只在「状态翻转」时向 TG 发消息：断开 1 条、恢复 1 条；离线期间不重复提醒。
   断开告警带 30 分钟抑制窗口（反复掉线/崩溃重启不刷屏），但抑制到期或发送失败
   会自动补发，保证每一段持续离线最终至少有一条通知。
4. 冷启动（没有历史状态）时若 NapCat 还在登录，先给 5 分钟观察期再告警，
   避免「启动即断开 + 登录完成即恢复」的假告警。
5. 最近一次状态与「本次断开是否已告警」落库（system_settings），进程崩溃重启后
   不会对同一次故障重复告警，恢复通知里的中断时长也跨重启连续。
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime

from db.database import db
from handlers.qq_handler import onebot_client
from utils.logger import logger

STATE_UNKNOWN = "unknown"
STATE_ONLINE = "online"
STATE_OFFLINE = "offline"


def _fmt_duration(seconds: float) -> str:
    """把秒数格式化成「12 分钟」「1 小时 5 分钟」这类人类可读文案。"""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"
    days, hours = divmod(hours, 24)
    return f"{days} 天 {hours} 小时" if hours else f"{days} 天"


def _fmt_clock(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


class QQHealthMonitor:
    """NapCat 连接健康监测（主动探测 + 状态翻转告警）。"""

    # 探测节奏与判定阈值
    PROBE_INTERVAL = 60.0             # 探测间隔（秒）
    PROBE_TIMEOUT = 5.0               # 单次探测超时（秒）
    CONFIRM_FAILURES = 2              # 连续失败达到该次数才确认断开
    CONFIRM_GAP = 3.0                 # 确认断开前两次探测的间隔（秒）
    STARTUP_DELAY = 90.0              # 启动后延迟，避开 NapCat 自身启动/登录过程
    STARTUP_OFFLINE_GRACE = 300.0     # 冷启动首次判定断开后的观察期（秒），避免登录中误报
    ALERT_SUPPRESS_WINDOW = 1800.0    # 同一故障重复告警的抑制窗口（秒）
    ALERT_RETRY_BACKOFF = 300.0       # 告警/恢复通知发送失败后的重试间隔（秒）
    SETTING_KEY = "qq_health_state"

    def __init__(self, **overrides):
        # 允许测试覆盖节奏参数（只接受已知的类属性，避免拼写错误被静默吞掉）
        for key, value in overrides.items():
            if not hasattr(type(self), key):
                raise TypeError(f"未知的 QQHealthMonitor 配置项: {key}")
            setattr(self, key, value)

        self.state = STATE_UNKNOWN
        self.since = time.time()
        self.last_probe_at = 0.0
        self.last_ok_at = 0.0
        self.last_error: str | None = None
        self.latency_ms: int | None = None

        self._last_alert_at = 0.0
        self._suppress_until = 0.0
        self._next_alert_attempt = 0.0
        self._startup_grace_until = 0.0
        self._offline_alert_sent = False
        self._restored_since = 0.0
        self._recovery_pending: dict | None = None
        self._bot = None
        self._chat_id = None
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ 生命周期
    def bind(self, bot, chat_id) -> None:
        """绑定用于发送通知的 TG Bot 与目标群。"""
        self._bot = bot
        self._chat_id = chat_id

    async def start(self) -> asyncio.Task:
        """加载上次运行状态并启动探测任务，返回后台任务（便于 main 统一回收）。"""
        if self._task is not None and not self._task.done():
            return self._task
        await self._load_state()
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        """停止探测任务（关闭流程调用，避免关闭后仍重建 HTTP session / 发告警）。"""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"QQ 健康监测任务停止异常（忽略）: {e}")

    async def run(self) -> None:
        logger.debug(
            f"QQ 健康监测已启动：每 {int(self.PROBE_INTERVAL)}s 探测一次 "
            f"{onebot_client.base_url}（启动延迟 {int(self.STARTUP_DELAY)}s）"
        )
        await asyncio.sleep(self.STARTUP_DELAY)
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"QQ 健康监测异常: {e}")
            await asyncio.sleep(self.PROBE_INTERVAL)

    # ------------------------------------------------------------------ 探测
    async def _probe(self) -> tuple[bool, str | None]:
        """执行一次探测，返回 (是否连通, 错误描述)。"""
        self.last_probe_at = time.time()
        try:
            result = await onebot_client.probe_health(timeout=self.PROBE_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        if result.get("ok"):
            self.last_ok_at = self.last_probe_at
            self.latency_ms = result.get("latency_ms")
            self.last_error = None
            return True, None

        self.last_error = result.get("error") or "NapCat 无响应"
        return False, self.last_error

    async def check_once(self) -> bool:
        """跑一轮健康检查：成功即在线；连续失败达到阈值才确认断开。"""
        ok, error = await self._probe()
        if not ok:
            # 单次失败可能只是瞬时抖动，再确认（CONFIRM_FAILURES-1 次）
            for _ in range(max(0, self.CONFIRM_FAILURES - 1)):
                await asyncio.sleep(self.CONFIRM_GAP)
                ok, error = await self._probe()
                if ok:
                    break

        if ok:
            await self._set_state(STATE_ONLINE)
        else:
            await self._set_state(STATE_OFFLINE, error)

        # 离线期间持续静默探测时，负责补发被抑制/发送失败的断开告警，以及恢复通知
        await self._maybe_send_pending_alert()
        await self._flush_pending_recovery()
        return self.state == STATE_ONLINE

    # ------------------------------------------------------------------ 状态迁移
    async def _set_state(self, new_state: str, error: str | None = None) -> None:
        if self.state == new_state:
            return

        old_state, old_since = self.state, self.since
        now = time.time()
        self.state = new_state
        self.since = now

        if new_state == STATE_OFFLINE:
            if old_state == STATE_UNKNOWN and self._restored_since:
                # 进程重启前就处于断开状态：沿用原断开时间，恢复通知里的中断时长才连续
                self.since = min(now, self._restored_since)
            elif old_state == STATE_UNKNOWN:
                # 冷启动首次判定断开：NapCat 可能还在登录，给一个观察期再告警
                self._startup_grace_until = now + self.STARTUP_OFFLINE_GRACE
        else:
            self._startup_grace_until = 0.0
            self._next_alert_attempt = 0.0

        logger.info(
            f"QQ 健康状态: {old_state} -> {new_state}"
            f"{f'（{error}）' if error else ''}"
        )

        if new_state == STATE_OFFLINE:
            await self._notify_offline(now)
        elif old_state == STATE_OFFLINE:
            await self._notify_recovery(old_since, now)
        else:
            # UNKNOWN -> ONLINE：启动即正常，静默不打扰；顺带清掉重启读回的告警标记，
            # 避免之后一次「未告警的断开」却发出恢复通知
            self._offline_alert_sent = False

        await self._persist()

    # ------------------------------------------------------------------ 通知
    def _alert_due_at(self) -> float:
        """断开告警最早可发送的时间（抑制窗口 / 启动观察期 / 发送失败退避）。"""
        return max(self._suppress_until, self._startup_grace_until, self._next_alert_attempt)

    async def _maybe_send_pending_alert(self) -> None:
        """离线期间补发告警：抑制窗口到期或上次发送失败后重试。"""
        if self.state != STATE_OFFLINE or self._offline_alert_sent:
            return
        now = time.time()
        if now < self._alert_due_at():
            return
        await self._notify_offline(now)

    async def _notify_offline(self, now: float) -> None:
        due = self._alert_due_at()
        if now < due:
            logger.debug(
                f"QQ 健康监测: 连接断开，告警暂缓 {int(due - now)}s 后补发"
                f"（抑制窗口/启动观察期/重试退避）"
            )
            return

        text = (
            "⚠️ TQSync: QQ 端连接断开\n"
            f"主动探测 NapCat 连续 {max(1, self.CONFIRM_FAILURES)} 次失败"
            f"{f'（{self.last_error}）' if self.last_error else ''}\n"
            f"断开时间: {_fmt_clock(self.since)}\n"
            "断开期间 QQ ↔ TG 消息无法同步；恢复后会自动通知，期间不再重复提醒。"
        )
        if not await self._send(text):
            self._next_alert_attempt = now + self.ALERT_RETRY_BACKOFF
            logger.warning(
                f"QQ 健康监测: 断开通告发送失败，{int(self.ALERT_RETRY_BACKOFF)}s 后重试"
            )
            return

        self._offline_alert_sent = True
        self._last_alert_at = now
        self._suppress_until = now + self.ALERT_SUPPRESS_WINDOW
        self._next_alert_attempt = 0.0
        self._startup_grace_until = 0.0
        # 先落库：尽量缩小「已发送但未持久化」被崩溃打断导致重启后重复告警的窗口
        await self._persist()
        logger.warning(f"QQ 健康监测: 连接断开，已通知 TG（{self.last_error}）")

    async def _notify_recovery(self, old_since: float, now: float) -> None:
        if not self._offline_alert_sent:
            # 本次断开没告警过（抑制窗口内/重启前已告警），恢复也保持静默，
            # 避免出现"没有断开通知却有恢复通知"的困惑消息
            logger.info("QQ 健康监测: 连接恢复（本次断开未告警，恢复通知一并静默）")
            return

        self._offline_alert_sent = False
        downtime = max(0.0, now - old_since)
        text = (
            "✅ TQSync: QQ 端连接已恢复\n"
            f"中断时长: {_fmt_duration(downtime)}"
            f"（{_fmt_clock(old_since)} → {_fmt_clock(now)}）\n"
            "消息同步已恢复正常。"
        )
        if await self._send(text):
            self._recovery_pending = None
            logger.info(f"QQ 健康监测: 连接恢复，中断 {_fmt_duration(downtime)}")
        else:
            # 恢复通知发送失败：状态已回到在线，靠后续探测周期补发（最多 3 次）
            self._recovery_pending = {
                "text": text,
                "due": now + self.ALERT_RETRY_BACKOFF,
                "retries": 1,
            }
            logger.warning("QQ 健康监测: 恢复通知发送失败，稍后重试")

    async def _flush_pending_recovery(self) -> None:
        pending = self._recovery_pending
        if not pending or time.time() < pending["due"]:
            return
        if await self._send(pending["text"]):
            self._recovery_pending = None
            logger.info("QQ 健康监测: 恢复通知已补发成功")
            return
        pending["retries"] += 1
        if pending["retries"] >= 3:
            self._recovery_pending = None
            logger.error("QQ 健康监测: 恢复通知多次发送失败，放弃（状态已恢复在线）")
        else:
            pending["due"] = time.time() + self.ALERT_RETRY_BACKOFF

    async def _send(self, text: str) -> bool:
        if self._bot is None:
            logger.warning("QQ 健康监测: TG Bot 未绑定，跳过通知")
            return False
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"QQ 健康监测: 发送 TG 通知失败: {e}")
            return False

    # ------------------------------------------------------------------ 状态展示
    def status_text(self) -> str:
        """供 /status 等命令展示的一行状态文案。"""
        if self.state == STATE_ONLINE:
            latency = f" (延迟 {self.latency_ms}ms)" if self.latency_ms is not None else ""
            return f"✅ 正常{latency}"
        if self.state == STATE_OFFLINE:
            return f"❌ 已断开 {_fmt_duration(time.time() - self.since)}"
        return "⏳ 检测中"

    # ------------------------------------------------------------------ 持久化
    async def _load_state(self) -> None:
        """读回上次运行状态：已知警过的断开不再重复刷屏，未告警的会补发。"""
        try:
            raw = await db.get_setting(self.SETTING_KEY)
            data = json.loads(raw) if raw else None
        except Exception as e:
            logger.debug(f"QQ 健康监测: 读取历史状态失败（忽略）: {e}")
            return
        if not isinstance(data, dict) or data.get("state") != STATE_OFFLINE:
            return

        now = time.time()
        try:
            last_alert_at = float(data.get("last_alert_at") or 0)
            restored_since = float(data.get("since") or 0)
        except (TypeError, ValueError):
            return

        # 时间戳范围校验：损坏的值会让抑制窗口/中断时长显示错乱
        if not (0 < restored_since <= now + 60):
            restored_since = 0.0
        if not (0 < last_alert_at <= now + 60):
            last_alert_at = 0.0
        if restored_since:
            self._restored_since = restored_since

        # 关键：只有持久化里明确「本次断开已告警」时才抑制；
        # 不能只看 last_alert_at（它可能来自上一段已恢复的故障），否则会漏掉本段告警
        if bool(data.get("alerted")) and last_alert_at:
            self._offline_alert_sent = True
            self._last_alert_at = last_alert_at
            self._suppress_until = last_alert_at + self.ALERT_SUPPRESS_WINDOW

        logger.info(
            "QQ 健康监测: 上次运行结束时 QQ 处于断开状态"
            f"（已持续 {_fmt_duration(now - (restored_since or now))}，"
            f"{'已告警' if self._offline_alert_sent else '未告警（将补发）'}）"
        )

    async def _persist(self) -> None:
        try:
            await db.set_setting(
                self.SETTING_KEY,
                json.dumps(
                    {
                        "state": self.state,
                        "since": self.since,
                        "alerted": self._offline_alert_sent,
                        "last_alert_at": self._last_alert_at,
                    }
                ),
            )
        except Exception as e:
            logger.warning(f"QQ 健康监测: 保存状态失败（跨重启去重可能失效）: {e}")


# 全局单例（main.py 启动时 bind + start，关闭时 stop）
qq_health_monitor = QQHealthMonitor()
