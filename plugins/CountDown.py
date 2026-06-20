import json
import asyncio
import aiohttp
from datetime import datetime, date
from core.plugin_base import PluginBase
from utils.logger import logger


class CountDown(PluginBase):
    name = "CountDown"
    version = "1.0"
    description = "倒数日管理：添加/删除倒数日，每日推送，群名展示最近倒数日"
    author = "TQSync"

    def get_matchers(self):
        return [
            {"type": "prefix", "pattern": "/cd", "description": "倒数日管理 /cd add <名称> <日期>"},
        ]

    async def on_load(self):
        self._scheduler_task = None

        if not await self.ctx.db.get_plugin_data(self.name, "entries"):
            await self.ctx.db.set_plugin_data(self.name, "entries", "[]")
        if not await self.ctx.db.get_plugin_data(self.name, "config"):
            await self.ctx.db.set_plugin_data(self.name, "config", json.dumps({
                "prefix": "", "suffix": "", "no_event_text": "暂无倒数日",
                "last_push_date": "", "last_group_name_date": ""
            }))

        self._scheduler_task = asyncio.create_task(self._daily_scheduler())
        logger.info(f"[{self.name}] 插件已加载")

    async def on_unload(self):
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info(f"[{self.name}] 插件已卸载")

    async def on_message(self, platform, user_id, group_id, message):
        if not message.startswith("/cd"):
            return False

        parts = message.strip().split(maxsplit=3)
        if len(parts) < 2:
            await self._reply(platform, group_id, self._get_help())
            return True

        subcmd = parts[1].lower()

        handlers = {
            "add": self._handle_add,
            "remove": self._handle_remove,
            "list": self._handle_list,
            "admin": self._handle_admin,
            "setprefix": self._handle_setprefix,
            "setsuffix": self._handle_setsuffix,
            "setnotevent": self._handle_setnotevent,
            "help": self._handle_help,
            "gcupdate": self._handle_gcupdate,
            "status": self._handle_status,
        }

        handler = handlers.get(subcmd)
        if handler:
            await handler(platform, user_id, group_id, parts)
        else:
            await self._reply(platform, group_id, self._get_help())

        return True

    async def _handle_gcupdate(self, platform, user_id, group_id, parts=None):
        if not await self._is_admin(platform, user_id):
            await self._reply(platform, group_id, "仅管理员可使用此命令")
            return
        entries = await self._get_entries()
        await self._update_group_name(entries)
        await self._reply(platform, group_id, "✅ 群名已更新")

    async def _handle_add(self, platform, user_id, group_id, parts):
        if len(parts) < 4:
            await self._reply(platform, group_id, "格式: /cd add <名称> <日期>\n例: /cd add 2026辽宁省中考 2026-06-28")
            return

        name = parts[2]
        date_str = parts[3]

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            await self._reply(platform, group_id, "日期格式错误，请使用 YYYY-MM-DD")
            return

        if target_date <= date.today():
            await self._reply(platform, group_id, "日期必须是未来日期")
            return

        entries = await self._get_entries()
        if any(e["name"] == name for e in entries):
            await self._reply(platform, group_id, f"倒数日「{name}」已存在")
            return

        new_id = max([e["id"] for e in entries], default=0) + 1
        entry = {
            "id": new_id, "user_id": user_id,
            "user_platform": platform, "name": name,
            "target_date": date_str,
            "created_at": date.today().isoformat()
        }
        entries.append(entry)
        await self._save_entries(entries)

        remaining = (target_date - date.today()).days
        await self._reply(platform, group_id, f"✅ 已添加倒数日「{name}」，剩余 {remaining} 天")

    async def _handle_remove(self, platform, user_id, group_id, parts):
        if len(parts) < 3:
            await self._reply(platform, group_id, "格式: /cd remove <id>\n使用 /cd list 查看 ID")
            return

        try:
            target_id = int(parts[2])
        except ValueError:
            await self._reply(platform, group_id, "ID 必须是数字")
            return

        entries = await self._get_entries()
        entry = next((e for e in entries if e["id"] == target_id
                      and e["user_id"] == user_id and e["user_platform"] == platform), None)

        if not entry:
            await self._reply(platform, group_id, f"未找到 ID {target_id} 的倒数日，或无权删除")
            return

        entries.remove(entry)
        await self._save_entries(entries)
        await self._reply(platform, group_id, f"已删除倒数日「{entry['name']}」")

    async def _handle_list(self, platform, user_id, group_id, parts=None):
        entries = await self._get_entries()
        today = date.today()

        if not entries:
            await self._reply(platform, group_id, "暂无倒数日\n使用 /cd add <名称> <日期> 添加")
            return

        lines = ["📅 倒数日列表:"]
        for entry in sorted(entries, key=lambda e: e["target_date"]):
            remaining = (datetime.strptime(entry["target_date"], "%Y-%m-%d").date() - today).days
            if remaining <= 0:
                continue
            lines.append(f"#{entry['id']} {entry['name']}: {remaining}天 ({entry['target_date']})")

        if len(lines) == 1:
            lines.append("暂无有效的未来倒数日")

        await self._reply(platform, group_id, "\n".join(lines))

    async def _handle_admin(self, platform, user_id, group_id, parts):
        if not await self._is_admin(platform, user_id):
            await self._reply(platform, group_id, "仅管理员可使用此命令")
            return

        if len(parts) < 3:
            await self._reply(platform, group_id, "格式: /cd admin add <用户ID> <名称> <日期> 或 /cd admin remove <id>")
            return

        admin_subcmd = parts[2].lower()

        if admin_subcmd == "add":
            if len(parts) < 6:
                await self._reply(platform, group_id, "格式: /cd admin add <用户ID> <名称> <日期>")
                return
            try:
                target_user = int(parts[3])
            except ValueError:
                await self._reply(platform, group_id, "用户ID 必须是数字")
                return
            name = parts[4]
            date_str = parts[5]

            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                await self._reply(platform, group_id, "日期格式错误，请使用 YYYY-MM-DD")
                return

            if target_date <= date.today():
                await self._reply(platform, group_id, "日期必须是未来日期")
                return

            entries = await self._get_entries()
            new_id = max([e["id"] for e in entries], default=0) + 1
            entry = {
                "id": new_id, "user_id": target_user,
                "user_platform": platform, "name": name,
                "target_date": date_str,
                "created_at": date.today().isoformat()
            }
            entries.append(entry)
            await self._save_entries(entries)

            remaining = (target_date - date.today()).days
            await self._reply(platform, group_id, f"✅ 管理员已为用户 {target_user} 添加倒数日「{name}」，剩余 {remaining} 天")

        elif admin_subcmd == "remove":
            if len(parts) < 4:
                await self._reply(platform, group_id, "格式: /cd admin remove <id>")
                return
            try:
                target_id = int(parts[3])
            except ValueError:
                await self._reply(platform, group_id, "ID 必须是数字")
                return

            entries = await self._get_entries()
            entry = next((e for e in entries if e["id"] == target_id), None)

            if not entry:
                await self._reply(platform, group_id, f"未找到 ID {target_id} 的倒数日")
                return

            entries.remove(entry)
            await self._save_entries(entries)
            await self._reply(platform, group_id, f"管理员已删除倒数日「{entry['name']}」(用户: {entry['user_id']})")

        else:
            await self._reply(platform, group_id, "格式: /cd admin add <用户ID> <名称> <日期> 或 /cd admin remove <id>")

    async def _handle_setprefix(self, platform, user_id, group_id, parts):
        if not await self._is_admin(platform, user_id):
            await self._reply(platform, group_id, "仅管理员可使用此命令")
            return

        prefix = parts[2] if len(parts) >= 3 else ""
        config = await self._get_config()
        config["prefix"] = prefix
        await self._save_config(config)
        await self._reply(platform, group_id, f"群名前缀已设为「{prefix}」")

    async def _handle_setsuffix(self, platform, user_id, group_id, parts):
        if not await self._is_admin(platform, user_id):
            await self._reply(platform, group_id, "仅管理员可使用此命令")
            return

        suffix = parts[2] if len(parts) >= 3 else ""
        config = await self._get_config()
        config["suffix"] = suffix
        await self._save_config(config)
        await self._reply(platform, group_id, f"群名后缀已设为「{suffix}」")

    async def _handle_help(self, platform, user_id, group_id, parts=None):
        await self._reply(platform, group_id, self._get_detailed_help())

    async def _handle_setnotevent(self, platform, user_id, group_id, parts):
        if not await self._is_admin(platform, user_id):
            await self._reply(platform, group_id, "仅管理员可使用此命令")
            return

        text = parts[2] if len(parts) >= 3 else "暂无倒数日"
        config = await self._get_config()
        config["no_event_text"] = text
        await self._save_config(config)
        await self._reply(platform, group_id, f"无倒数日文案已设为「{text}」")

    async def _handle_status(self, platform, user_id, group_id, parts=None):
        entries = await self._get_entries()
        config = await self._get_config()
        today = date.today()

        future = [e for e in entries if datetime.strptime(e["target_date"], "%Y-%m-%d").date() > today]

        lines = [
            f"[{self.name} 状态]",
            f"倒数日数量: {len(future)}",
            f"群名前缀: 「{config.get('prefix', '')}」",
            f"群名后缀: 「{config.get('suffix', '')}」",
            f"无倒数日文案: 「{config.get('no_event_text', '暂无倒数日')}」",
        ]

        if future:
            nearest = min(future, key=lambda e: e["target_date"])
            remaining = (datetime.strptime(nearest["target_date"], "%Y-%m-%d").date() - today).days
            lines.append(f"最近倒数日: {nearest['name']} ({remaining}天)")

        await self._reply(platform, group_id, "\n".join(lines))

    async def _daily_scheduler(self):
        while True:
            try:
                now = datetime.now()
                today_str = date.today().isoformat()
                config = await self._get_config()
                entries = await self._get_entries()

                if now.hour == 6 and now.minute == 0 and config.get("last_push_date") != today_str:
                    await self._daily_push(entries)
                    config["last_push_date"] = today_str
                    await self._save_config(config)

                if now.hour == 6 and now.minute == 5 and config.get("last_group_name_date") != today_str:
                    await self._update_group_name(entries)
                    config["last_group_name_date"] = today_str
                    await self._save_config(config)
            except Exception as e:
                logger.error(f"[{self.name}] 定时任务异常: {e}")
            await asyncio.sleep(60)

    async def _daily_push(self, entries):
        today = date.today()

        if not entries:
            msg = "📅 当前暂无倒数日记录"
        else:
            lines = ["📅 倒数日日报:"]
            for entry in sorted(entries, key=lambda e: e["target_date"]):
                remaining = (datetime.strptime(entry["target_date"], "%Y-%m-%d").date() - today).days
                if remaining <= 0:
                    continue
                tag = "🔴 " if remaining <= 7 else "🟡 " if remaining <= 30 else "🟢 "
                lines.append(f"{tag}{entry['name']}: {remaining}天 ({entry['target_date']})")
            if len(lines) == 1:
                lines.append("暂无有效的未来倒数日")
            msg = "\n".join(lines)

        try:
            await self.ctx.tg_bot.send_message(chat_id=self.ctx.tg_group_id, text=msg)
        except Exception as e:
            logger.error(f"[{self.name}] TG推送失败: {e}")
        try:
            await self.ctx.qq_client.send_group_msg(self.ctx.qq_group_id, msg)
        except Exception as e:
            logger.error(f"[{self.name}] QQ推送失败: {e}")

    async def _update_group_name(self, entries):
        today = date.today()
        config = await self._get_config()
        prefix = config.get("prefix", "") or ""
        suffix = config.get("suffix", "") or ""

        future = [e for e in entries if datetime.strptime(e["target_date"], "%Y-%m-%d").date() > today]

        no_text = config.get("no_event_text", "暂无倒数日")
        if not future:
            name = f"{prefix}{no_text}{suffix}"
        else:
            nearest = min(future, key=lambda e: e["target_date"])
            remaining = (datetime.strptime(nearest["target_date"], "%Y-%m-%d").date() - today).days
            name = f"{prefix}{nearest['name']}: {remaining}天{suffix}"

        await self._set_group_titles(name)

    async def _set_group_titles(self, name):
        if len(name) > 128:
            name = name[:128]

        try:
            await self.ctx.tg_bot.set_chat_title(chat_id=self.ctx.tg_group_id, title=name)
        except Exception as e:
            logger.error(f"[{self.name}] TG设置群名失败: {e}")

        try:
            url = f"{self.ctx.qq_client.base_url}/set_group_name"
            payload = {"group_id": self.ctx.qq_group_id, "group_name": name}
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, headers=self.ctx.qq_client.headers) as resp:
                    result = await resp.json()
                    if result.get('retcode') != 0:
                        logger.warning(f"[{self.name}] QQ设置群名失败: {result}")
        except Exception as e:
            logger.error(f"[{self.name}] QQ设置群名异常: {e}")

    async def _is_admin(self, platform, user_id):
        if platform == 'qq':
            return await self._is_qq_admin(user_id)
        elif platform == 'tg':
            return await self._is_tg_admin(user_id)
        return False

    async def _is_qq_admin(self, user_id):
        try:
            url = f"{self.ctx.qq_client.base_url}/get_group_member_info"
            payload = {"group_id": str(self.ctx.qq_group_id), "user_id": str(user_id)}
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, headers=self.ctx.qq_client.headers) as resp:
                    result = await resp.json()
                    if result.get('retcode') == 0:
                        return result.get('data', {}).get('role', 'member') in ('owner', 'admin')
        except Exception as e:
            logger.error(f"[{self.name}] QQ管理员检查失败: {e}")
        return False

    async def _is_tg_admin(self, user_id):
        try:
            member = await self.ctx.tg_bot.get_chat_member(
                chat_id=self.ctx.tg_group_id, user_id=user_id
            )
            return member.status in ('creator', 'administrator')
        except Exception as e:
            logger.error(f"[{self.name}] TG管理员检查失败: {e}")
        return False

    async def _get_entries(self):
        raw = await self.ctx.db.get_plugin_data(self.name, "entries") or "[]"
        return json.loads(raw)

    async def _save_entries(self, entries):
        await self.ctx.db.set_plugin_data(self.name, "entries", json.dumps(entries))

    async def _get_config(self):
        raw = await self.ctx.db.get_plugin_data(self.name, "config")
        return json.loads(raw) if raw else {"prefix": "", "suffix": "", "no_event_text": "暂无倒数日", "last_push_date": "", "last_group_name_date": ""}

    async def _save_config(self, config):
        await self.ctx.db.set_plugin_data(self.name, "config", json.dumps(config))

    def _get_help(self):
        return "📅 使用 /cd help 查看详细指令说明"

    def _get_detailed_help(self):
        return (
            "📅 倒数日插件使用说明\n"
            "──────────────\n"
            "【通用指令】\n"
            "/cd add <名称> <日期>\n"
            "  添加倒数日  例: /cd add 中考 2026-06-28\n"
            "/cd remove <id>\n"
            "  删除自己的倒数日  ID 用 /cd list 查看\n"
            "/cd list\n"
            "  查看所有倒数日及剩余天数\n"
            "/cd status\n"
            "  查看插件当前状态和配置\n"
            "──────────────\n"
            "【管理员指令】\n"
            "/cd admin add <用户ID> <名称> <日期>\n"
            "  为指定用户添加倒数日\n"
            "/cd admin remove <id>\n"
            "  删除任意用户的倒数日\n"
            "/cd setprefix <前缀>\n"
            "  设置群名前缀  例: /cd setprefix DP |\n"
            "/cd setsuffix <后缀>\n"
            "  设置群名后缀  例: /cd setsuffix 🎯\n"
            "/cd gcupdate\n"
            "  立即更新群名为最近倒数日\n"
            "/cd setnotevent <文案>\n"
            "  设置无倒数日时的群名文案\n"
            "  默认为「暂无倒数日」\n"
            "──────────────\n"
            "【定时任务】每天 06:00 推送倒数日日报\n"
            "并自动将最临近的倒数日设为群名\n"
            "群名格式: <前缀><名称>: X天<后缀>"
        )

    async def _reply(self, platform, group_id, text):
        if platform == 'tg':
            try:
                await self.ctx.tg_bot.send_message(chat_id=group_id, text=text)
            except Exception as e:
                logger.error(f"[{self.name}] TG回复失败: {e}")
        elif platform == 'qq':
            try:
                await self.ctx.qq_client.send_group_msg(group_id, text)
            except Exception as e:
                logger.error(f"[{self.name}] QQ回复失败: {e}")
