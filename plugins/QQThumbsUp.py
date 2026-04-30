import json
import asyncio
import aiohttp
from datetime import datetime, date
from core.plugin_base import PluginBase
from utils.logger import logger


class QQThumbsUp(PluginBase):
    name = "QQThumbsUp"
    version = "2.0"
    description = "QQ点赞：手动赞我 / 自动点赞列表管理 / 定时批量点赞"
    author = "TQSync"

    def get_matchers(self):
        return [
            {"type": "exact", "pattern": "赞我", "description": "给QQ资料卡点赞"},
            {"type": "prefix", "pattern": "/autothumbsup", "description": "自动点赞管理"},
        ]

    async def on_load(self):
        self._scheduler_task = None

        # 确保数据库中有默认值
        if not await self.ctx.db.get_plugin_data(self.name, "like_count"):
            await self.ctx.db.set_plugin_data(self.name, "like_count", "50")
        if not await self.ctx.db.get_plugin_data(self.name, "like_time"):
            await self.ctx.db.set_plugin_data(self.name, "like_time", "08:00")
        if not await self.ctx.db.get_plugin_data(self.name, "auto_like_list"):
            await self.ctx.db.set_plugin_data(self.name, "auto_like_list", "[]")

        # 向 QQ 群发送加载提示
        like_time = await self.ctx.db.get_plugin_data(self.name, "like_time") or "08:00"
        try:
            await self.ctx.qq_client.send_group_msg(
                self.ctx.qq_group_id,
                f"[QQThumbsUp] 插件已加载 | 定时点赞: 每日 {like_time}"
            )
        except Exception as e:
            logger.error(f"[{self.name}] on_load 通知发送失败: {e}")

        # 启动后台定时调度
        self._scheduler_task = asyncio.create_task(self._daily_like_scheduler())
        logger.info(f"[{self.name}] 插件已加载，定时任务已启动")

    async def on_unload(self):
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info(f"[{self.name}] 插件已卸载")

    async def on_message(self, platform, user_id, group_id, message):
        if platform != 'qq':
            return False

        if message.strip() == "赞我":
            await self._handle_manual_like(user_id, group_id)
            return True

        if message.startswith("/autothumbsup"):
            await self._handle_autothumbsup(user_id, group_id, message)
            return True

        return False

    # ========== 手动点赞 ==========

    async def _handle_manual_like(self, user_id, group_id):
        try:
            like_count = int(await self.ctx.db.get_plugin_data(self.name, "like_count") or "50")
            result = await self.send_like(user_id, like_count)
            if result and result.get('retcode') == 0:
                await self.ctx.qq_client.send_group_msg(group_id, f"已赞 ({like_count}次)")
            else:
                error_msg = result.get('wording', '未知错误') if result else '无响应'
                await self.ctx.qq_client.send_group_msg(group_id, f"点赞失败: {error_msg}")
        except Exception as e:
            logger.error(f"[{self.name}] 手动点赞异常: {e}")
            await self.ctx.qq_client.send_group_msg(group_id, f"点赞失败: {e}")

    # ========== 命令路由 ==========

    async def _handle_autothumbsup(self, user_id, group_id, message):
        parts = message.split(maxsplit=2)

        # /autothumbsup - 将自己加入自动点赞列表
        if len(parts) == 1:
            await self._add_to_auto_list(user_id, group_id)
            return

        subcmd = parts[1].lower()
        arg = parts[2].strip() if len(parts) >= 3 else ""

        if subcmd == "status":
            await self._show_status(group_id)

        elif subcmd == "add":
            if not await self._is_admin(group_id, user_id):
                await self.ctx.qq_client.send_group_msg(group_id, "仅群管理员可使用 add 命令")
                return
            if not arg.isdigit():
                await self.ctx.qq_client.send_group_msg(group_id, "QQ号格式错误")
                return
            await self._add_to_auto_list(int(arg), group_id)

        elif subcmd == "remove":
            if not await self._is_admin(group_id, user_id):
                await self.ctx.qq_client.send_group_msg(group_id, "仅群管理员可使用 remove 命令")
                return
            if not arg.isdigit():
                await self.ctx.qq_client.send_group_msg(group_id, "QQ号格式错误")
                return
            await self._remove_from_auto_list(int(arg), group_id)

        elif subcmd == "settime":
            if not await self._is_admin(group_id, user_id):
                await self.ctx.qq_client.send_group_msg(group_id, "仅群管理员可使用 settime 命令")
                return
            await self._set_like_time(arg, group_id)

        else:
            await self._show_help(group_id)

    # ========== 列表管理 ==========

    async def _add_to_auto_list(self, target_qq, group_id):
        raw = await self.ctx.db.get_plugin_data(self.name, "auto_like_list") or "[]"
        qq_list = json.loads(raw)
        target_str = str(target_qq)
        if target_str in qq_list:
            await self.ctx.qq_client.send_group_msg(group_id, f"QQ {target_qq} 已在自动点赞列表中")
            return
        qq_list.append(target_str)
        await self.ctx.db.set_plugin_data(self.name, "auto_like_list", json.dumps(qq_list))
        await self.ctx.qq_client.send_group_msg(group_id, f"已添加 QQ {target_qq} 到自动点赞列表 (当前{len(qq_list)}人)")

    async def _remove_from_auto_list(self, target_qq, group_id):
        raw = await self.ctx.db.get_plugin_data(self.name, "auto_like_list") or "[]"
        qq_list = json.loads(raw)
        target_str = str(target_qq)
        if target_str not in qq_list:
            await self.ctx.qq_client.send_group_msg(group_id, f"QQ {target_qq} 不在自动点赞列表中")
            return
        qq_list.remove(target_str)
        await self.ctx.db.set_plugin_data(self.name, "auto_like_list", json.dumps(qq_list))
        await self.ctx.qq_client.send_group_msg(group_id, f"已移除 QQ {target_qq} 从自动点赞列表 (当前{len(qq_list)}人)")

    async def _set_like_time(self, time_str, group_id):
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await self.ctx.qq_client.send_group_msg(group_id, "时间格式错误，请使用 HH:MM 格式 (如 08:00)")
            return
        await self.ctx.db.set_plugin_data(self.name, "like_time", time_str)
        await self.ctx.qq_client.send_group_msg(group_id, f"每日自动点赞时间已设为 {time_str}")
        logger.info(f"[{self.name}] 点赞时间已更新为 {time_str}")

    async def _show_status(self, group_id):
        like_time = await self.ctx.db.get_plugin_data(self.name, "like_time") or "08:00"
        like_count = await self.ctx.db.get_plugin_data(self.name, "like_count") or "50"
        raw = await self.ctx.db.get_plugin_data(self.name, "auto_like_list") or "[]"
        qq_list = json.loads(raw)
        last_date = await self.ctx.db.get_plugin_data(self.name, "last_batch_date") or "无"
        await self.ctx.qq_client.send_group_msg(
            group_id,
            f"[自动点赞状态]\n"
            f"定时: 每日 {like_time}\n"
            f"次数: {like_count}次\n"
            f"今日已执行: {'是' if last_date == date.today().isoformat() else '否'}\n"
            f"列表({len(qq_list)}人): {', '.join(qq_list) if qq_list else '空'}"
        )

    async def _show_help(self, group_id):
        await self.ctx.qq_client.send_group_msg(
            group_id,
            "[自动点赞] 用法:\n"
            "/autothumbsup - 将自己加入自动点赞\n"
            "/autothumbsup add <QQ> - 添加 (管理员)\n"
            "/autothumbsup remove <QQ> - 移除 (管理员)\n"
            "/autothumbsup settime HH:MM - 设定时 (管理员)\n"
            "/autothumbsup status - 查看状态\n"
            "赞我 - 手动点赞"
        )

    # ========== 定时批量调度 ==========

    async def _daily_like_scheduler(self):
        """后台任务：每60秒检查是否到达定时点赞时间"""
        while True:
            try:
                like_time_str = await self.ctx.db.get_plugin_data(self.name, "like_time") or "08:00"
                today = date.today().isoformat()
                last_date = await self.ctx.db.get_plugin_data(self.name, "last_batch_date")

                now = datetime.now()
                scheduled_h, scheduled_m = map(int, like_time_str.split(":"))

                if (now.hour == scheduled_h and now.minute == scheduled_m
                        and last_date != today):
                    logger.info(f"[{self.name}] 到达定时点赞时间 {like_time_str}，开始批量点赞")
                    await self._run_batch_like()
                    await self.ctx.db.set_plugin_data(self.name, "last_batch_date", today)
            except Exception as e:
                logger.error(f"[{self.name}] 定时任务异常: {e}")

            await asyncio.sleep(60)

    async def _run_batch_like(self):
        """对自动点赞列表中所有用户执行批量点赞"""
        raw = await self.ctx.db.get_plugin_data(self.name, "auto_like_list") or "[]"
        qq_list = json.loads(raw)
        like_count = int(await self.ctx.db.get_plugin_data(self.name, "like_count") or "50")

        if not qq_list:
            logger.info(f"[{self.name}] 自动点赞列表为空，跳过批量")
            return

        success = 0
        fail = 0
        for qq in qq_list:
            try:
                result = await self.send_like(int(qq), like_count)
                if result and result.get('retcode') == 0:
                    success += 1
                else:
                    fail += 1
                    logger.warning(f"[{self.name}] 批量点赞失败: {qq} {result}")
                await asyncio.sleep(1)
            except Exception as e:
                fail += 1
                logger.error(f"[{self.name}] 批量点赞异常 {qq}: {e}")

        try:
            await self.ctx.qq_client.send_group_msg(
                self.ctx.qq_group_id,
                f"[自动点赞] 定时批量完成: 成功 {success}, 失败 {fail} (共 {len(qq_list)} 人, {like_count}次/人)"
            )
        except Exception as e:
            logger.error(f"[{self.name}] 批量点赞通知失败: {e}")

    # ========== 核心 API ==========

    async def send_like(self, user_id: int, times: int = 1):
        """给指定QQ用户资料卡点赞"""
        url = f"{self.ctx.qq_client.base_url}/send_like"
        payload = {
            "user_id": str(user_id),
            "times": times
        }
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, json=payload, headers=self.ctx.qq_client.headers) as resp:
                result = await resp.json()
                logger.info(f"[{self.name}] send_like user={user_id} times={times} -> {result}")
                return result

    async def _is_admin(self, group_id, user_id):
        """通过 NapCat API 检查用户是否为群管理员/群主"""
        try:
            url = f"{self.ctx.qq_client.base_url}/get_group_member_info"
            payload = {"group_id": str(group_id), "user_id": str(user_id)}
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, headers=self.ctx.qq_client.headers) as resp:
                    result = await resp.json()
                    if result.get('retcode') == 0:
                        role = result.get('data', {}).get('role', 'member')
                        return role in ('owner', 'admin')
        except Exception as e:
            logger.error(f"[{self.name}] 管理员检查失败: {e}")
        return False
