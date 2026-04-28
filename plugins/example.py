from core.plugin_base import PluginBase


class ThumbsUp(PluginBase):
    name = "example"
    version = "1.0"
    description = "test"
    author = "XSong"

    def get_matchers(self):
        return [
            {"type": "exact", "pattern": "/plugintest", "description": "测试plugin是否正常工作"},
        ]

    async def on_message(self, platform, user_id, group_id, message):
        if platform == 'tg':
            await self.ctx.tg_bot.send_message(
                chat_id=group_id,
                text="Example Plugin is working."
            )
        elif platform == 'qq':
            await self.ctx.qq_client.send_group_msg(group_id, "Example Plugin is working.")

        return None
