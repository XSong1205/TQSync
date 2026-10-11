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
        self._session: aiohttp.ClientSession = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False, limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def _post_json(self, endpoint: str, payload: dict, max_retries: int = 3, base_delay: float = 1.5):
        """带指数退避重试的 JSON POST 请求"""
        url = f"{self.base_url}{endpoint}"
        last_error = None
        await self._ensure_session()
        for attempt in range(max_retries):
            try:
                async with self._session.post(url, json=payload, headers=self.headers) as resp:
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
        await self._ensure_session()
        for attempt in range(max_retries):
            try:
                async with self._session.get(url, headers=self.headers) as resp:
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

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

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

    async def send_group_forward_msg(self, group_id: int, nodes: list):
        """发送群合并转发消息。nodes 为 node 类型消息段列表。"""
        payload = {
            "group_id": group_id,
            "messages": nodes
        }
        return await self._post_json("/send_group_forward_msg", payload)

    async def send_private_forward_msg(self, user_id: int, nodes: list):
        """发送私聊合并转发消息。nodes 为 node 类型消息段列表。"""
        payload = {
            "user_id": user_id,
            "messages": nodes
        }
        return await self._post_json("/send_private_forward_msg", payload)

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

    async def send_group_notice(self, group_id: int, content: str, image: str = "", pinned: int = 1) -> dict:
        """发送群公告 (需 Bot 拥有群主或管理员权限)"""
        payload = {
            "group_id": str(group_id),
            "content": content,
            "pinned": pinned,
            "type": 1,
            "confirm_required": 1,
            "is_show_edit_card": 0,
            "tip_window_type": 0
        }
        if image:
            payload["image"] = image
        try:
            return await self._post_json("/_send_group_notice", payload)
        except Exception as e:
            logger.debug(f"/_send_group_notice 失败，尝试降级到 /send_group_notice: {e}")
            return await self._post_json("/send_group_notice", payload)

    async def get_group_notice(self, group_id: int) -> dict:
        """获取群公告列表"""
        payload = {"group_id": str(group_id)}
        try:
            return await self._post_json("/_get_group_notice", payload)
        except Exception as e:
            logger.debug(f"/_get_group_notice 失败，尝试降级到 /get_group_notice: {e}")
            return await self._post_json("/get_group_notice", payload)

    async def del_group_notice(self, group_id: int, notice_id: str) -> dict:
        """删除群公告"""
        payload = {
            "group_id": str(group_id),
            "notice_id": str(notice_id)
        }
        try:
            return await self._post_json("/_del_group_notice", payload)
        except Exception as e:
            logger.debug(f"/_del_group_notice 失败，尝试降级到 /del_group_notice: {e}")
            return await self._post_json("/del_group_notice", payload)

# 全局实例
onebot_client = OneBotClient()

