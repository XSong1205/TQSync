import aiohttp
import asyncio
from config.config_loader import config_loader
from utils.logger import logger

class OneBotClient:
    def __init__(self):
        self.base_url = config_loader.get('qq.napcat_api_url')
        self.access_token = config_loader.get('qq.access_token')
        self.headers = {}
        if self.access_token:
            self.headers['Authorization'] = f'Bearer {self.access_token}'
        self._bot_id = None

    async def _post_json(self, endpoint: str, payload: dict, max_retries: int = 3, base_delay: float = 1.5):
        """带指数退避重试的 JSON POST 请求"""
        url = f"{self.base_url}{endpoint}"
        last_error = None
        connector = aiohttp.TCPConnector(ssl=False)
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.post(url, json=payload, headers=self.headers) as resp:
                        result = await resp.json()
                        if result.get('retcode') != 0:
                            logger.warning(f"OneBot API 返回非零状态: {endpoint} -> {result}")
                        return result
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"OneBot API {endpoint} 调用失败 (第 {attempt + 1}/{max_retries} 次): {e}，{delay:.1f}s 后重试...")
                    await asyncio.sleep(delay)
        logger.error(f"OneBot API {endpoint} 调用失败 (已重试{max_retries}次): {last_error}")
        raise last_error

    async def _get_json(self, endpoint: str, max_retries: int = 3, base_delay: float = 1.0):
        """带指数退避重试的 JSON GET 请求"""
        url = f"{self.base_url}{endpoint}"
        last_error = None
        connector = aiohttp.TCPConnector(ssl=False)
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(url, headers=self.headers) as resp:
                        return await resp.json()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"OneBot API {endpoint} GET 失败 (第 {attempt + 1}/{max_retries} 次): {e}，{delay:.1f}s 后重试...")
                    await asyncio.sleep(delay)
        logger.error(f"OneBot API {endpoint} GET 失败 (已重试{max_retries}次): {last_error}")
        raise last_error

    async def get_bot_id(self) -> int:
        """获取当前登录的 Bot QQ 号"""
        if self._bot_id is None:
            try:
                res = await self._get_json("/get_login_info")
                if res.get('retcode') == 0:
                    self._bot_id = res['data']['user_id']
            except Exception as e:
                logger.warning(f"获取 Bot QQ ID 失败: {e}")
        return self._bot_id

    async def send_group_msg(self, group_id: int, message):
        """发送群消息。支持字符串（CQ码）或列表（消息段数组）。"""
        payload = {
            "group_id": group_id,
            "message": message,
            "auto_escape": False
        }
        return await self._post_json("/send_group_msg", payload)

    async def send_private_msg(self, user_id: int, message):
        """发送私聊消息。支持字符串（CQ码）或列表（消息段数组）。"""
        payload = {
            "user_id": user_id,
            "message": message,
            "auto_escape": False
        }
        return await self._post_json("/send_private_msg", payload)

    async def delete_msg(self, message_id: int):
        """撤回消息"""
        payload = {"message_id": message_id}
        return await self._post_json("/delete_msg", payload)

# 全局实例
onebot_client = OneBotClient()
