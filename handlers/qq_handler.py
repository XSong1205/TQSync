import aiohttp
import logging
from config.config_loader import config_loader

logger = logging.getLogger(__name__)

class OneBotClient:
    def __init__(self):
        self.base_url = config_loader.get('qq.napcat_api_url')
        self.access_token = config_loader.get('qq.access_token')
        self.headers = {}
        if self.access_token:
            self.headers['Authorization'] = f'Bearer {self.access_token}'

    async def send_group_msg(self, group_id: int, message):
        """
        发送群消息。支持字符串（CQ码）或列表（消息段数组）。
        """
        url = f"{self.base_url}/send_group_msg"
        payload = {
            "group_id": group_id,
            "message": message,
            "auto_escape": False
        }
        # 禁用 SSL 验证以适配国内代理环境
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, json=payload, headers=self.headers) as resp:
                result = await resp.json()
                if result.get('retcode') != 0:
                    logger.error(f"OneBot API Error: {result}")
                return result

# 全局实例
onebot_client = OneBotClient()
