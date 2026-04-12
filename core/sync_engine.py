from telegram import Bot
import os
import uuid
import json
import base64
import re
import io
import gzip
import json
import aiofiles
import ffmpeg
from lottie import objects, exporters
from PIL import Image
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
                    async with aiofiles.open(file_path, 'wb') as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            await f.write(chunk)
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

    async def tgs_to_gif(self, tgs_path: str, gif_path: str, fps: int = 30, width: int = 512, height: int = 512):
        """使用 lottie + Pillow 将 TGS 贴纸转换为 GIF"""
        logger.info(f"正在转换 Lottie 贴纸: {tgs_path} -> {gif_path}")
        loop = asyncio.get_event_loop()
        
        def _render():
            try:
                # 1. 解压并加载 Lottie JSON
                with gzip.open(tgs_path, "rb") as f:
                    data = json.loads(f.read().decode("utf-8"))
                animation = objects.Animation.from_dict(data)
                
                # 2. 渲染帧
                frames = exporters.render_frames(animation, width=width, height=height, fps=fps)
                
                # 3. 转成 Pillow Image 并保存
                pil_frames = [Image.fromarray(frame) for frame in frames]
                if pil_frames:
                    pil_frames[0].save(
                        gif_path,
                        save_all=True,
                        append_images=pil_frames[1:],
                        duration=int(1000 / fps),
                        loop=0,
                        transparency=0,
                        disposal=2
                    )
            except Exception as e:
                logger.error(f"Lottie 渲染失败: {e}")
                raise

        await loop.run_in_executor(None, _render)
        logger.info("Lottie 贴纸转换成功")

    async def convert_webm_to_gif(self, input_path: str, output_path: str):
        """使用 FFmpeg 将 WebM 贴纸转换为 GIF"""
        logger.info(f"正在转换贴纸格式: {input_path} -> {output_path}")
        try:
            # 异步运行 FFmpeg 进程
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                ffmpeg
                .input(input_path)
                .filter('scale', 320, -1, flags='lanczos')
                .filter('fps', fps=15, round='up')
                .output(output_path, **{'loop': 0})
                .overwrite_output()
                .run(quiet=True)
            ))
            logger.info("贴纸格式转换成功")
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg 转换失败 (stderr: {e.stderr.decode() if e.stderr else 'N/A'})")
            raise
        except FileNotFoundError:
            logger.error("未找到 FFmpeg 可执行文件。请确保已安装 FFmpeg 并将其添加到系统环境变量 PATH 中。")
            raise

    async def forward_voice_to_qq(self, tg_user_id: int, tg_username: str, file_id: str):
        """转发 Telegram 语音消息到 QQ (带 FFmpeg 转码)"""
        display_name = await self.get_display_name(tg_user_id, tg_username)
        onebot_client = OneBotClient(self.config['napcat']['host'], self.config['napcat']['port'])

        try:
            file_url = await self.bot.get_file(file_id)
            if isinstance(file_url, dict):
                file_url = file_url.get('file_path', '')
            if not file_url.startswith('http'):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            # 提取原始文件名或生成默认名
            original_name = getattr(file_url, 'name', None) or f"voice_{tg_user_id}.ogg"
            temp_filename = f"voice_{uuid.uuid4().hex}_{original_name}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            # 使用 FFmpeg 转换为 AMR (QQ 兼容格式)
            amr_filename = f"voice_{uuid.uuid4().hex}.amr"
            amr_path = os.path.join(os.getcwd(), 'temp', amr_filename)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                ffmpeg.input(temp_path)
                .output(amr_path, acodec='libopencore_amrnb', ar=8000, ab=12.2)
                .overwrite_output()
                .run(quiet=True)
            ))
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {display_name} 发送了一条语音\n"}},
                {"type": "record", "data": {"file": amr_path}}
            ]
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"语音已转发至 QQ 群 {self.qq_group_id}")
            return result
        except Exception as e:
            logger.error(f"转发语音至 QQ 失败: {e}")
            return None
        finally:
            if 'temp_path' in locals() and temp_path:
                self._cleanup_temp(temp_path)
            if 'amr_path' in locals() and amr_path:
                self._cleanup_temp(amr_path)

    async def forward_sticker_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, is_animated: bool = False):
        """将 Telegram 贴纸转发到 QQ (支持静态和动态)"""
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        temp_path = None
        gif_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            # 动态贴纸通常是 .webm，静态是 .png 或 .webp
            # 注意：.tgs 是 Lottie 格式，现在支持转换
            ext = os.path.splitext(file_url)[1] or ('.webm' if is_animated else '.png')

            temp_filename = f"sticker_{uuid.uuid4().hex}{ext}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            message_array = [
                {"type": "text", "data": {"text": f"[TG] {display_name} 发送了一个贴纸\n"}},
            ]
            
            final_send_path = temp_path
            
            # 根据类型选择消息段：动态贴纸转换为 GIF 后作为图片发送
            if is_animated or ext in ['.webm', '.tgs']:
                gif_filename = f"sticker_{uuid.uuid4().hex}.gif"
                gif_path = os.path.join(os.getcwd(), 'temp', gif_filename)
                
                try:
                    if ext == '.tgs':
                        await self.tgs_to_gif(temp_path, gif_path)
                    else:
                        await self.convert_webm_to_gif(temp_path, gif_path)
                    final_send_path = gif_path
                except Exception as e:
                    logger.error(f"贴纸转换失败: {e}")
                    # 转换失败时尝试发送原始文件（如果 QQ 支持）或发送提示文本
                    message_array.append({"type": "text", "data": {"text": "(贴纸转换失败，请查看日志)"}})
                    result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
                    return result
                
                message_array.append({"type": "image", "data": {"file": final_send_path}})
            else:
                message_array.append({"type": "image", "data": {"file": final_send_path}})
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            logger.info(f"贴纸已成功发送至 QQ。结果: {result}")
            return result

        except Exception as e:
            logger.error(f"转发贴纸至 QQ 失败: {e}", exc_info=True)
            return None
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)
            if gif_path:
                self._cleanup_temp(gif_path)

    async def forward_voice_to_tg(self, qq_user_id: int, qq_nickname: str, file_url: str, reply_to_message_id: int = None):
        """转发 QQ 语音消息到 Telegram (带 FFmpeg 转码)"""
        display_name = await self.get_display_name(qq_user_id=qq_user_id, fallback_name=qq_nickname)
        
        try:
            # 提取原始文件名或生成默认名
            original_name = os.path.basename(file_url).split('?')[0] or f"voice_{qq_user_id}.amr"
            temp_filename = f"voice_{uuid.uuid4().hex}_{original_name}"
            temp_path = await self._download_to_temp(file_url, temp_filename)
            
            # 使用 FFmpeg 转换为 OGG Opus (Telegram 兼容格式)
            ogg_filename = f"voice_{uuid.uuid4().hex}.ogg"
            ogg_path = os.path.join(os.getcwd(), 'temp', ogg_filename)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                ffmpeg.input(temp_path)
                .output(ogg_path, acodec='libopus', ar=48000, ab='64k')
                .overwrite_output()
                .run(quiet=True)
            ))
            
            caption = f"[QQ] {display_name} 发送了一条语音"
            with open(ogg_path, 'rb') as audio_file:
                result = await self.bot.send_voice(
                    chat_id=self.tg_group_id,
                    voice=audio_file,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
            
            logger.info(f"语音已转发至 TG 群 {self.tg_group_id}")
            return result
        except Exception as e:
            logger.error(f"转发语音至 Telegram 失败: {e}")
            return None
        finally:
            if 'temp_path' in locals() and temp_path:
                self._cleanup_temp(temp_path)
            if 'ogg_path' in locals() and ogg_path:
                self._cleanup_temp(ogg_path)

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
                async with aiofiles.open(temp_path, 'rb') as f:
                    file_content = await f.read()
                    # 对于文档类型，需要传递 filename 参数以便 TG 显示正确的文件名
                    if file_key == "document":
                        send_kwargs[file_key] = (kwargs.get('filename', os.path.basename(temp_path)), io.BytesIO(file_content))
                    else:
                        send_kwargs[file_key] = io.BytesIO(file_content)
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
        # 移除加粗格式以避免 MarkdownV2 转义冲突（如 **{safe}** 中 safe 含 * 时会导致解析失败）
        # 确保括号被正确转义
        markdown_parts = [f"📋 合并转发消息 \(来自 {safe_display_name}\):\n"]
        
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
                
                # 移除加粗格式以确保 MarkdownV2 解析稳定
                formatted_msg = f"{index + 1}\\. {safe_nickname}: {safe_text}"
                if has_image:
                    formatted_msg += r" \[图片\]"
                
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
