import aiohttp
from config.config_loader import config_loader

class OneBotClient:
    def __init__(self):
        self.base_url = config_loader.get('qq.napcat_api_url')
        self.access_token = config_loader.get('qq.access_token')
        self.headers = {}
        if self.access_token:
            self.headers['Authorization'] = f'Bearer {self.access_token}'

    async def send_group_msg(self, group_id: int, message: str):
        url = f"{self.base_url}/send_group_msg"
        payload = {
            "group_id": group_id,
            "message": message
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as resp:
                return await resp.json()

# 全局实例
onebot_client = OneBotClient()
