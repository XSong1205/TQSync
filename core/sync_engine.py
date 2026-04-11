from telegram import Bot
import os
import uuid
import json
import base64
import re
import aiohttp
import asyncio
import subprocess
from datetime import datetime
from utils.version_utils import get_full_version_string
from config.config_loader import config_loader
from handlers.qq_handler import onebot_client
from db.database import db
from utils.logger import logger

class SyncEngine:
    _instance = None

    def __init__(self, bot: Bot):
        if SyncEngine._instance is not None:
            return
        self.bot = bot
        self.tg_group_id = config_loader.get('telegram.group_id')
        self.qq_group_id = config_loader.get('qq.group_id')
        
        # 异步同步队列：限制并发数为 3，防止大文件耗尽资源
        self.sync_queue = asyncio.Queue(maxsize=50)
        self.max_concurrent_syncs = 3
        self._worker_tasks = []
        
        # 启动后台工作者
        for i in range(self.max_concurrent_syncs):
            task = asyncio.create_task(self._sync_worker(i))
            self._worker_tasks.append(task)
            
        SyncEngine._instance = self

    async def _sync_worker(self, worker_id: int):
        """后台同步工作者：从队列中获取任务并执行"""
        logger.info(f"同步工作者 #{worker_id} 已启动")
        while True:
            try:
                task_func, args, kwargs = await self.sync_queue.get()
                logger.debug(f"工作者 #{worker_id} 开始处理任务: {task_func.__name__}")
                try:
                    await task_func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"工作者 #{worker_id} 执行任务失败: {e}", exc_info=True)
                finally:
                    self.sync_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"工作者 #{worker_id} 异常退出: {e}")

    def enqueue_sync_task(self, task_func, *args, **kwargs):
        """将同步任务加入队列"""
        try:
            self.sync_queue.put_nowait((task_func, args, kwargs))
            logger.debug(f"任务已加入同步队列: {task_func.__name__}, 当前队列大小: {self.sync_queue.qsize()}")
        except asyncio.QueueFull:
            logger.warning("同步队列已满，丢弃新任务")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("SyncEngine has not been initialized. Call SyncEngine(bot) first.")
        return cls._instance

    async def _download_to_temp(self, file_url: str, filename: str) -> str:
        """下载文件到 temp 目录并返回本地绝对路径"""
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 确保文件名唯一，防止冲突
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = os.path.join(temp_dir, unique_filename)
        logger.info(f"正在下载文件至本地中转: {file_url[:50]}... (保存为: {filename})")
        
        # 全局禁用 SSL 验证以适配国内代理环境
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=60, connect=15)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            try:
                async with session.get(file_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Download failed with status {resp.status}")
                    with open(file_path, 'wb') as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
            except asyncio.TimeoutError:
                raise Exception("Download timed out")
            except Exception as e:
                if os.path.exists(file_path): os.remove(file_path)
                raise e
        return os.path.abspath(file_path)

    def _cleanup_temp(self, file_path: str):
        """清理临时文件"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"已清理临时文件: {file_path}")
        except Exception as e:
            logger.warning(f"清理临时文件失败 {file_path}: {e}")

    async def get_display_name(self, tg_user_id: int = None, qq_user_id: int = None, fallback_name: str = "Unknown"):
        """根据绑定关系获取统一显示名称，优先使用自定义前缀"""
        uid = None
        binding = None
        
        if tg_user_id:
            binding = await db.get_binding_by_tg(tg_user_id)
        elif qq_user_id:
            binding = await db.get_binding_by_qq(qq_user_id)
        
        if binding:
            uid = binding[4] # uid 是第 5 列 (0-based index 4)
            custom_prefix = await db.get_custom_prefix_by_uid(uid)
            if custom_prefix:
                return custom_prefix
            # 回退到绑定的昵称或用户名
            return binding[3] or binding[2] or fallback_name
        
        return f"{fallback_name} [未绑定]"

    async def forward_image_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, caption: str = ""):
        """将 Telegram 图片转发到 QQ (本地文件中转方案，支持 Caption 图文混排)"""
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        temp_path = None
        
        try:
            # 1. 获取 Telegram 文件链接
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            # 2. 下载到本地 temp
            ext = os.path.splitext(file_url)[1] or '.jpg'
            temp_filename = f"img_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            # 3. 构造消息段 (实现图文混排：文字在上，图片在下)
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {display_name}\n"}},
            ]
            
            # 如果有 Caption，则添加在图片上方
            if caption:
                message_array.append({"type": "text", "data": {"text": f"{caption}\n"}})
            
            message_array.append({"type": "image", "data": {"file": temp_path}})
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"图片已成功发送至 QQ。结果: {result}")
            return result

        except Exception as e:
            logger.error(f"转发图片至 QQ 失败: {e}", exc_info=True)
            return None
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_video_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """将 Telegram 视频转发到 QQ"""
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        temp_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(file_url)[1] or '.mp4'
            temp_filename = f"vid_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {display_name} 发送了一个视频\n"}},
                {"type": "video", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"视频已成功发送至 QQ。结果: {result}")
            return result

        except Exception as e:
            logger.error(f"转发视频至 QQ 失败: {e}", exc_info=True)
            return None
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_file_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, filename: str):
        """将 Telegram 通用文件转发到 QQ (卡片形式)"""
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        temp_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(filename)[1]
            temp_filename = f"file_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {display_name} 发送了一个文件: {filename}\n"}},
                {"type": "file", "data": {"file": temp_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"文件已成功发送至 QQ。结果: {result}")
            return result

        except Exception as e:
            logger.error(f"转发文件至 QQ 失败: {e}", exc_info=True)
            return None
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

    async def forward_image_to_tg(self, qq_user_id: int, qq_nickname: str, image_url: str, caption: str = "", reply_to_message_id: int = None):
        """将 QQ 图片转发到 Telegram (支持本地文件中转)"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        full_caption = f"{prefix}\n{caption}" if caption else prefix
        await self._send_file_to_tg(qq_user_id, qq_nickname, image_url, self.bot.send_photo, "photo", caption=full_caption, reply_to_message_id=reply_to_message_id)

    async def forward_video_to_tg(self, qq_user_id: int, qq_nickname: str, video_url: str, caption: str = "", reply_to_message_id: int = None):
        """将 QQ 视频转发到 Telegram (支持本地文件中转)"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        full_caption = f"{prefix}\n{caption}" if caption else prefix
        await self._send_file_to_tg(qq_user_id, qq_nickname, video_url, self.bot.send_video, "video", caption=full_caption, reply_to_message_id=reply_to_message_id)

    async def forward_file_to_tg(self, qq_user_id: int, qq_nickname: str, file_url: str, file_name: str = "file", reply_to_message_id: int = None):
        """将 QQ 文件转发到 Telegram (支持本地文件中转)"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        
        # 确保文件名有扩展名
        if not os.path.splitext(file_name)[1]:
            ext = os.path.splitext(file_url.split('?')[0])[1] or '.dat'
            file_name += ext

        await self._send_file_to_tg(qq_user_id, qq_nickname, file_url, self.bot.send_document, "document", filename=file_name, caption=prefix, reply_to_message_id=reply_to_message_id)

    async def _send_file_to_tg(self, qq_user_id: int, qq_nickname: str, file_url: str, send_func, file_key: str, **kwargs):
        """通用文件转发到 Telegram 方法，支持本地路径中转"""
        binding = await db.get_binding_by_qq(qq_user_id)
        prefix = f"[QQ] {binding[2] or qq_nickname}" if binding else f"[QQ] {qq_nickname}"
        temp_path = None
        
        try:
            # 判断是否为本地路径或内网地址
            if file_url.startswith(("file:///", "/", "C:\\", "D:\\")) or "127.0.0.1" in file_url or "localhost" in file_url:
                local_path = file_url.replace("file://", "")
                if os.path.exists(local_path):
                    temp_path = local_path
                else:
                    raise FileNotFoundError(f"Local file not found: {local_path}")
            else:
                temp_path = file_url

            # 准备发送参数
            send_kwargs = {"chat_id": self.tg_group_id}
            
            # 处理回复 ID
            if "reply_to_message_id" in kwargs:
                send_kwargs["reply_to_message_id"] = kwargs.pop("reply_to_message_id")
            
            # 处理 Caption
            if "caption" in kwargs:
                send_kwargs["caption"] = kwargs.pop("caption")
            elif file_key == "document":
                send_kwargs["caption"] = prefix

            # 关键修复：即使是 http URL，如果 Telegram 无法访问（如内网或需代理），也应下载到本地再上传
            # 我们统一采用“下载到本地 -> 上传给 TG”的策略以确保稳定性
            temp_path = file_url
            if not os.path.exists(temp_path) or temp_path.startswith("http"):
                # 如果是 URL，先下载到临时文件
                if temp_path.startswith("http"):
                    ext = os.path.splitext(temp_path.split('?')[0])[1]
                    original_filename = kwargs.get('filename', 'unknown_file')
                    if not ext and original_filename != 'unknown_file':
                        ext = os.path.splitext(original_filename)[1]
                    ext = ext or '.tmp'
                    temp_filename = f"forward_{uuid.uuid4().hex[:8]}{ext}"
                    downloaded_path = await self._download_to_temp(temp_path, temp_filename)
                    temp_path = downloaded_path

            # 以二进制流形式发送给 Telegram
            if os.path.exists(temp_path):
                with open(temp_path, 'rb') as f:
                    # 对于文档类型，需要传递 filename 参数以便 TG 显示正确的文件名
                    if file_key == "document":
                        send_kwargs[file_key] = (kwargs.get('filename', os.path.basename(temp_path)), f)
                    else:
                        send_kwargs[file_key] = f
                    await send_func(**send_kwargs)
            else:
                raise FileNotFoundError(f"File not found for forwarding: {temp_path}")
                
        except Exception as e:
            logger.error(f"转发消息至 Telegram 失败: {e}", exc_info=True)

    async def forward_to_qq(self, tg_user_id: int, tg_username: str, text: str):
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        message = f"[TG] {display_name}: {text}"
        result = await onebot_client.send_group_msg(self.qq_group_id, message)
        return result

    async def forward_merged_to_tg(self, qq_user_id: int, qq_nickname: str, content_data):
        """
        解析并转发 QQ 合并转发消息到 Telegram (单层支持)
        :param content_data: OneBot forward 消息段中的 data 内容
        """
        # MarkdownV2 转义函数：Telegram 对特殊字符有严格要求
        def escape_md_v2(text):
            if not text:
                return ""
            # Telegram MarkdownV2 需要转义的字符: _ * [ ] ( ) ~ ` > # + - = | { } . !
            escape_chars = r'_*[]()~`>#+-=|{}.!'
            result = ""
            for char in str(text):
                if char in escape_chars:
                    result += "\\" + char
                else:
                    result += char
            return result

        display_name = await self.get_display_name(qq_user_id=qq_user_id, fallback_name=qq_nickname)
        safe_display_name = escape_md_v2(display_name)
        markdown_parts = [f"📋 \*\*合并转发消息\*\* \(来自 {safe_display_name}\):\n"]
        
        try:
            # 尝试解析 content，它可能是 JSON 字符串或 Base64 编码的 JSON
            raw_content = content_data.get('content', '')
            if not raw_content:
                logger.warning("合并转发消息内容为空")
                return

            # 简单的解码逻辑：如果是 Base64 则解码，否则直接尝试解析
            try:
                decoded_str = base64.b64decode(raw_content).decode('utf-8')
                msg_list = json.loads(decoded_str)
            except:
                msg_list = json.loads(raw_content) if isinstance(raw_content, str) else raw_content

            if not isinstance(msg_list, list):
                msg_list = [msg_list]

            for index, msg_node in enumerate(msg_list):
                sender = msg_node.get('sender', {})
                nickname = sender.get('nickname', '未知用户')
                message_array = msg_node.get('message', [])
                
                # 提取文本和图片
                text_content = ""
                has_image = False
                for part in message_array:
                    p_type = part.get('type')
                    if p_type == 'text':
                        text_content += part.get('data', {}).get('text', '')
                    elif p_type == 'image':
                        has_image = True
                
                safe_nickname = escape_md_v2(nickname)
                safe_text = escape_md_v2(text_content)
                
                # 格式化单条消息
                formatted_msg = f"{index + 1}\. \*\*{safe_nickname}\*\*: {safe_text}"
                if has_image:
                    formatted_msg += " \[图片\]"
                
                markdown_parts.append(formatted_msg)

            final_md = "\n".join(markdown_parts)
            result = await self.bot.send_message(
                chat_id=self.tg_group_id, 
                text=final_md, 
                parse_mode='MarkdownV2'
            )
            logger.info(f"已同步合并转发消息至 TG，共 {len(msg_list)} 条子消息")
            return result

        except Exception as e:
            logger.error(f"解析或发送合并转发消息失败: {e}")
            return None

    async def forward_to_tg(self, qq_user_id: int, qq_nickname: str, text: str, reply_to_message_id: int = None):
        display_name = await self.get_display_name(qq_user_id=qq_user_id, fallback_name=qq_nickname)
        message = f"[QQ] {display_name}: {text}"
        try:
            result = await self.bot.send_message(chat_id=self.tg_group_id, text=message, reply_to_message_id=reply_to_message_id)
            return result
        except Exception as e:
            print(f"Error sending to TG: {e}")
            return None

    async def send_startup_notification(self):
        """向两个平台发送启动成功通知"""
        
        # 1. 获取最后更新时间
        last_update = "Unknown"
        try:
            result = subprocess.run(['git', 'log', '-1', '--format=%ci'], 
                                    capture_output=True, text=True, check=True)
            git_time_str = result.stdout.strip()
            last_update = git_time_str.split('+')[0].strip()
        except Exception:
            try:
                mtime = os.path.getmtime('main.py')
                last_update = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass

        # 2. 获取配置信息
        qq_gid = config_loader.get('qq.group_id')
        tg_gid = config_loader.get('telegram.group_id')

        # 3. 构造消息
        version_str = get_full_version_string()
        message = (
            f"🚀 TQSync {version_str} 已成功启动并正在运行！\n"
            f"--------------------------\n"
            f"🕒 最后更新: {last_update}\n"
            f"💬 目标 QQ 群: {qq_gid}\n"
            f"✈️ 目标 TG 群: {tg_gid}\n"
            f"--------------------------"
        )
        
        # 4. 发送通知
        # 发送到 Telegram
        try:
            await self.bot.send_message(chat_id=self.tg_group_id, text=message)
            logger.info("Startup notification sent to Telegram.")
        except Exception as e:
            logger.error(f"Failed to send startup notification to Telegram: {e}")
            
        # 发送到 QQ
        try:
            await onebot_client.send_group_msg(self.qq_group_id, message)
            logger.info("Startup notification sent to QQ.")
        except Exception as e:
            logger.error(f"Failed to send startup notification to QQ: {e}")

sync_engine = None  # Will be initialized in main.py with the bot instance
