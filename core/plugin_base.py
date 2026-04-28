"""插件基类 - 所有 TQSync 插件必须继承此类"""

from typing import Optional


class PluginContext:
    """插件上下文，提供对主程序资源的访问"""

    def __init__(self, tg_bot, qq_client, config, db, tg_group_id, qq_group_id):
        self.tg_bot = tg_bot
        self.qq_client = qq_client
        self.config = config
        self.db = db
        self.tg_group_id = tg_group_id
        self.qq_group_id = qq_group_id


class PluginBase:
    """插件基类，所有插件必须继承此类并提供必要的方法"""

    name: str = "base"
    version: str = "0.1"
    description: str = "Base plugin"
    author: str = ""

    def __init__(self, ctx: Optional[PluginContext] = None):
        self.ctx = ctx

    async def on_load(self) -> None:
        """插件加载时调用"""
        pass

    async def on_unload(self) -> None:
        """插件卸载时调用"""
        pass

    def get_matchers(self) -> list:
        """返回消息匹配器列表
        
        每个匹配器是一个 dict，包含:
        - type: 'exact' (精确匹配), 'prefix' (前缀匹配), 'regex' (正则匹配)
        - pattern: 匹配模式
        - description: 功能描述
        """
        return []

    async def on_message(self, platform: str, user_id: int, group_id: int, message: str) -> None:
        """处理匹配到的文本消息
        
        Args:
            platform: 'tg' 或 'qq'
            user_id: 发送者 ID
            group_id: 群组 ID
            message: 消息文本
        """
        pass
