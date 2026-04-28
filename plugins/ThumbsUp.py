from core.plugin_base import PluginBase


class ThumbsUp(PluginBase):
    name = "ThumbsUp"
    version = "1.0"
    description = "自动检测'赞我'消息并回复大拇指表情"
    author = "TQSync"

    def get_matchers(self):
        return [
            {"type": "exact", "pattern": "赞我", "description": "收到'赞我'后回复👍"},
        ]

    async def on_message(self, platform, user_id, group_id, message):
        if platform == 'tg':
            await self.ctx.tg_bot.send_message(
                chat_id=group_id,
                text="👍👍👍"
            )
        elif platform == 'qq':
            await self.ctx.qq_client.send_group_msg(group_id, "👍👍👍")

        return None
