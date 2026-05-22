from telegram import Bot
import os
import sys
import uuid
import json
import base64
import re
import io
import gzip
import time
import asyncio
import ffmpeg
import subprocess
from datetime import datetime
from utils.version_utils import get_full_version_string
from config.config_loader import config_loader
from handlers.qq_handler import onebot_client
from db.database import db
from utils.logger import logger
from utils.ffmpeg_manager import ffmpeg_manager
from core.file_transfer import FileTransfer, FileSource, MediaType


async def retry_async(func, *args, max_retries=3, base_delay=1.0, retry_on=None, **kwargs):
    """带指数退避的异步重试

    Args:
        func: 异步函数
        max_retries: 最大重试次数 (含首次调用)
        base_delay: 首次重试等待秒数
        retry_on: 可重试的异常类型元组，None 表示所有异常都重试
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            last_error = e
            if retry_on and not isinstance(e, retry_on):
                raise

            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                func_name = getattr(func, '__name__', str(func))
                logger.warning(f"重试 {func_name} (第 {attempt + 1}/{max_retries} 次失败): {e}，{delay:.1f}s 后重试...")
                await asyncio.sleep(delay)

    raise last_error


class SyncEngine:
    _instance = None

    def __init__(self, bot: Bot):
        if SyncEngine._instance is not None:
            return
        self.bot = bot
        self.tg_group_id = config_loader.get('telegram.group_id')
        self.qq_group_id = config_loader.get('qq.group_id')
        
        # 初始化统一文件传输模块
        FileTransfer.tg_bot = bot
        FileTransfer.tg_group_id = self.tg_group_id
        FileTransfer.qq_group_id = self.qq_group_id
        
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
        """后台同步工作者：从队列中获取任务并执行，失败自动重试"""
        logger.info(f"同步工作者 #{worker_id} 已启动")
        while True:
            try:
                task_func, args, kwargs = await self.sync_queue.get()
                logger.debug(f"工作者 #{worker_id} 开始处理任务: {task_func.__name__}")
                try:
                    await retry_async(task_func, *args, max_retries=3, base_delay=2.0, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"工作者 #{worker_id} 执行任务失败 (已重试3次): {e}", exc_info=True)
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

    # ---- 统一媒体转发 (QQ → TG) ------------------------------------------

    @staticmethod
    def _extract_qq_message_id(result) -> int:
        if result and isinstance(result, dict):
            data = result.get('data', {})
            if isinstance(data, dict):
                return data.get('message_id')
            return result.get('message_id')
        return None

    async def forward_media_to_tg(self, qq_user_id: int, qq_nickname: str,
                                  source: FileSource, *, caption: str = '',
                                  reply_to_message_id: int = None,
                                  qq_message_id: int = None):
        """统一 QQ → TG 媒体文件转发入口。"""
        display_name = await self.get_display_name(
            qq_user_id=qq_user_id, fallback_name=qq_nickname
        )
        await FileTransfer.transfer_qq_to_tg(
            source,
            qq_user_id=qq_user_id,
            display_name=display_name,
            caption=caption,
            reply_to=reply_to_message_id,
            qq_message_id=qq_message_id
        )

    # ---- 统一媒体转发 (TG → QQ) ------------------------------------------

    async def forward_media_to_qq(self, tg_user_id: int, tg_username: str,
                                  file_id: str, *, file_name: str = '',
                                  file_size: int = 0,
                                  reply_segment: list = None,
                                  tg_message_id: int = None):
        """统一 TG → QQ 媒体文件转发入口。"""
        display_name = await self.get_display_name(
            tg_user_id=tg_user_id, fallback_name=tg_username
        )
        # 先通过 Telegram API 获取实际文件 URL
        file = await self.bot.get_file(file_id)
        actual_path = file.file_path
        if not actual_path.startswith('http'):
            actual_path = f'https://api.telegram.org/file/bot{self.bot.token}/{actual_path}'
        source = FileSource(file_name=file_name or 'unknown_file',
                            file_size=file_size, http_url=actual_path)
        await FileTransfer.transfer_tg_to_qq(
            source,
            tg_user_id=tg_user_id,
            display_name=display_name,
            reply_segment=reply_segment,
            tg_message_id=tg_message_id
        )

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

    async def _tgs_to_gif_lottie(self, tgs_path: str, gif_path: str, fps: int = 30, width: int = 512, height: int = 512):
        """使用 lottie 库将 TGS 贴纸转换为 GIF（备用方案）
        
        Args:
            tgs_path: TGS 文件路径
            gif_path: 输出 GIF 路径
            fps: 帧率
            width: 宽度
            height: 高度
        """
        logger.info(f"正在转换 Lottie 贴纸 (备用): {tgs_path} -> {gif_path}")
        loop = asyncio.get_event_loop()
        
        def _render():
            from rlottie_python import LottieAnimation
            
            animation = LottieAnimation.from_tgs(tgs_path)
            
            total_frames = animation.lottie_animation_get_totalframe()
            duration = animation.lottie_animation_get_duration()
            
            logger.debug(f"TGS 动画信息: 总帧数={total_frames}, 时长={duration}s")
            
            if total_frames <= 0 or duration <= 0:
                raise ValueError(f"TGS 动画数据无效 (帧数={total_frames}, 时长={duration})")
            
            animation.save_animation(gif_path, fps=fps, width=width, height=height, loop=0)
            logger.info(f"Lottie 贴纸转换成功")
        
        await loop.run_in_executor(None, _render)

    async def convert_webm_to_gif(self, input_path: str, output_path: str):
        """使用 FFmpeg 将 WebM 贴纸转换为 GIF"""
        logger.info(f"正在转换贴纸格式: {input_path} -> {output_path}")
        try:
            # 获取 FFmpeg 路径
            ffmpeg_path = ffmpeg_manager.get_executable_path() or 'ffmpeg'
            logger.debug(f"使用 FFmpeg 路径: {ffmpeg_path}")
            
            # 异步运行 FFmpeg 进程
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                ffmpeg
                .input(input_path)
                .filter('scale', 320, -1, flags='lanczos')
                .filter('fps', fps=15, round='up')
                .output(output_path, **{'loop': 0})
                .overwrite_output()
                .run(cmd=ffmpeg_path, capture_stdout=True, capture_stderr=True)
            ))
            logger.info("贴纸格式转换成功")
        except ffmpeg.Error as e:
            stderr_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else 'N/A'
            stdout_msg = e.stdout.decode('utf-8', errors='ignore') if e.stdout else 'N/A'
            logger.error(f"FFmpeg 转换失败:")
            logger.error(f"  Stderr: {stderr_msg}")
            logger.error(f"  Stdout: {stdout_msg}")
            logger.error(f"  Input file: {input_path}")
            logger.error(f"  Input file size: {os.path.getsize(input_path) if os.path.exists(input_path) else 'N/A'} bytes")
            raise
        except FileNotFoundError:
            error_msg = "FFmpeg 未安装，无法转换动态贴纸"
            logger.error(error_msg + "。请安装 FFmpeg 并添加到系统 PATH")
            
            # 尝试向 Telegram 发送提示
            try:
                if hasattr(self, 'bot') and self.bot:
                    await self.bot.send_message(
                        chat_id=self.tg_group_id,
                        text="⚠️ 动态贴纸转换失败：系统未安装 FFmpeg\n\n"
                             "如需启用动态贴纸同步，请安装 FFmpeg：\n"
                             "- Windows: winget install Gyan.FFmpeg\n"
                             "- Linux: sudo apt install ffmpeg\n"
                             "- macOS: brew install ffmpeg"
                    )
            except Exception as e:
                logger.debug(f"发送 TG 提示失败: {e}")
            
            raise Exception(error_msg)

    async def _tgs_to_gif_rlottie(self, tgs_path: str, gif_path: str, width: int = 512, height: int = 512, fps: int = 30):
        """使用 rlottie 库将 TGS 贴纸转换为 GIF
        
        Args:
            tgs_path: TGS 文件路径
            gif_path: 输出 GIF 路径
            width: 宽度
            height: 高度
            fps: 帧率
        """
        logger.info(f"正在转换 TGS 贴纸 (rlottie): {tgs_path} -> {gif_path}")
        loop = asyncio.get_event_loop()
        
        def _convert():
            import gzip
            import json
            from rlottie_python import LottieAnimation
            
            with open(tgs_path, 'rb') as f:
                raw_data = f.read()
            
            logger.debug(f"TGS 文件原始大小: {len(raw_data)} bytes")
            logger.debug(f"TGS 文件头: {raw_data[:4].hex()}")
            
            is_gzip = raw_data[:2] == b'\x1f\x8b'
            logger.debug(f"是否为 gzip 压缩: {is_gzip}")
            
            if is_gzip:
                tgs_data = gzip.decompress(raw_data)
                json_str = tgs_data.decode('utf-8')
                logger.debug(f"TGS 解压后大小: {len(json_str)} bytes")
                
                try:
                    json.loads(json_str)
                    logger.debug("JSON 格式验证: 有效")
                except:
                    logger.warning("JSON 格式验证: 无效")
                
                animation = LottieAnimation.from_data(json_str)
            else:
                json_str = raw_data.decode('utf-8')
                animation = LottieAnimation.from_file(tgs_path)
            
            total_frames = animation.lottie_animation_get_totalframe()
            duration = animation.lottie_animation_get_duration()
            framerate = animation.lottie_animation_get_framerate()
            
            logger.debug(f"TGS 动画信息: 总帧数={total_frames}, 时长={duration}s, 帧率={framerate}")
            
            if total_frames <= 0 or duration <= 0:
                raise ValueError(f"TGS 动画数据无效 (帧数={total_frames}, 时长={duration})")
            
            animation.save_animation(
                gif_path,
                fps=fps,
                width=width,
                height=height,
                loop=0
            )
            logger.info(f"TGS 转换成功: {gif_path}")
        
        await loop.run_in_executor(None, _convert)

    async def convert_tgs_to_gif(self, tgs_path: str, gif_path: str, width: int = 512, height: int = 512, fps: int = 30):
        """将 TGS 贴纸转换为 GIF（自动选择最佳渲染方案）
        
        依次尝试 rlottie -> lottie 库渲染
        
        Args:
            tgs_path: TGS 文件路径
            gif_path: 输出 GIF 路径
            width: 宽度
            height: 高度
            fps: 帧率
        """
        errors = []
        
        try:
            await self._tgs_to_gif_rlottie(tgs_path, gif_path, width, height, fps)
            return
        except Exception as e:
            errors.append(f"rlottie: {e}")
            logger.warning(f"rlottie 渲染失败，尝试备用方案 lottie: {e}")
        
        try:
            await self._tgs_to_gif_lottie(tgs_path, gif_path, fps, width, height)
            return
        except Exception as e:
            errors.append(f"lottie: {e}")
            logger.warning(f"lottie 渲染也失败了: {e}")
        
        raise Exception(f"TGS 转换失败，已尝试: {', '.join(errors)}")

    async def forward_voice_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, reply_segment: list = None, tg_message_id: int = None):
        """转发 Telegram 语音消息到 QQ (带 FFmpeg 转码)"""
        display_name = await self.get_display_name(tg_user_id, tg_username)
        temp_path = None
        try:
            file_url = await self.bot.get_file(file_id)
            if isinstance(file_url, dict):
                file_url = file_url.get('file_path', '')
            if not file_url.startswith('http'):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            original_name = getattr(file_url, 'name', None) or f"voice_{tg_user_id}.ogg"
            temp_filename = f"voice_{uuid.uuid4().hex}_{original_name}"
            temp_path = await FileTransfer._http_download(file_url, temp_filename)
            
            # 使用 FFmpeg 转换为 AMR (QQ 兼容格式)
            amr_filename = f"voice_{uuid.uuid4().hex}.amr"
            amr_path = os.path.join(os.getcwd(), 'temp', amr_filename)
            
            ffmpeg_path = ffmpeg_manager.get_executable_path() or 'ffmpeg'
            logger.debug(f"使用 FFmpeg 路径: {ffmpeg_path}")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                ffmpeg.input(temp_path)
                .output(amr_path, acodec='libopencore_amrnb', ar=8000, ab=12.2)
                .overwrite_output()
                .run(cmd=ffmpeg_path, quiet=True)
            ))
            
            if reply_segment:
                message_array = list(reply_segment)
                message_array.append({"type": "text", "data": {"text": f"[TG] {display_name} 发送了一条语音\n"}})
            else:
                message_array = [
                    {"type": "text", "data": {"text": f"[TG] {display_name} 发送了一条语音\n"}},
                ]
            message_array.append({"type": "record", "data": {"file": amr_path}})
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            if result and tg_message_id:
                qq_msg_id = self._extract_qq_message_id(result)
                if qq_msg_id:
                    await db.save_message_mapping(
                        tg_message_id=tg_message_id,
                        qq_message_id=qq_msg_id,
                        sender_tg_id=tg_user_id
                    )
            logger.info(f"语音已转发至 QQ 群 {self.qq_group_id}")
            return result
        except FileNotFoundError:
            error_msg = "FFmpeg 未安装，无法转换语音消息"
            logger.error(error_msg + "。请安装 FFmpeg 并添加到系统 PATH")
            
            # 尝试向 Telegram 发送提示
            try:
                if hasattr(self, 'bot') and self.bot:
                    await self.bot.send_message(
                        chat_id=self.tg_group_id,
                        text="⚠️ 语音消息转换失败：系统未安装 FFmpeg\n\n"
                             "如需启用语音同步，请安装 FFmpeg：\n"
                             "- Windows: winget install Gyan.FFmpeg\n"
                             "- Linux: sudo apt install ffmpeg\n"
                             "- macOS: brew install ffmpeg"
                    )
            except Exception as e:
                logger.debug(f"发送 TG 提示失败: {e}")
            
            return None
        except Exception as e:
            logger.error(f"转发语音至 QQ 失败: {e}")
            return None
        finally:
            if 'temp_path' in locals() and temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            if 'amr_path' in locals() and amr_path and os.path.exists(amr_path):
                try: os.remove(amr_path)
                except: pass

    def _detect_sticker_format(self, file_path: str) -> str:
        """通过文件头检测贴纸格式
        
        Args:
            file_path: 文件路径
            
        Returns:
            'tgs', 'webm' 或 'unknown'
        """
        if not os.path.exists(file_path):
            return 'unknown'
        
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                if header[:2] == b'\x1f\x8b':
                    logger.info("检测到 TGS 格式（gzip 压缩的 Lottie JSON）")
                    return 'tgs'
                elif header == b'\x1a\x45\xdf\xa3':
                    logger.info("检测到 WebM 格式")
                    return 'webm'
                else:
                    logger.warning(f"未知文件格式 (header: {header.hex()})")
                    return 'unknown'
        except Exception as e:
            logger.warning(f"文件头检查失败: {e}")
            return 'unknown'

    def _get_sticker_error_text(self, error: Exception) -> str:
        """根据错误类型返回用户友好的错误消息"""
        error_str = str(error).lower()
        if "FFmpeg" in str(error) or isinstance(error, FileNotFoundError):
            return "⚠️ 动态贴纸同步失败：系统未安装 FFmpeg\n请安装 FFmpeg 以启用动态贴纸功能"
        elif "rlottie" in error_str or "lottie" in error_str or "ImportError" in str(type(error).__name__):
            return "⚠️ 贴纸转换失败：Lottie 库异常\n请检查相关依赖"
        else:
            return "贴纸转换失败，请查看日志"

    async def forward_sticker_to_qq(self, tg_user_id: int, tg_username: str, file_id: str, is_animated: bool = False, reply_segment: list = None, tg_message_id: int = None):
        """将 Telegram 贴纸转发到 QQ (支持静态和动态)
        
        Args:
            tg_user_id: Telegram 用户 ID
            tg_username: Telegram 用户名
            file_id: 贴纸文件 ID
            is_animated: 是否为动态贴纸
        """
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        temp_path = None
        gif_path = None
        
        try:
            file = await self.bot.get_file(file_id)
            file_url = file.file_path
            if not file_url.startswith("http"):
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file_url}"
            
            ext = os.path.splitext(file_url)[1] if '.' in file_url else ''
            temp_filename = f"sticker_{uuid.uuid4().hex}{ext}"
            temp_path = await FileTransfer._http_download(file_url, temp_filename)
            
            actual_format = self._detect_sticker_format(temp_path)
            
            if reply_segment:
                message_array = list(reply_segment)
                message_array.append({"type": "text", "data": {"text": f"[TG] {display_name} 发送了一个贴纸\n"}})
            else:
                message_array = [
                    {"type": "text", "data": {"text": f"[TG] {display_name} 发送了一个贴纸\n"}},
                ]
            
            final_send_path = temp_path
            
            if is_animated or actual_format in ['tgs', 'webm']:
                gif_filename = f"sticker_{uuid.uuid4().hex}.gif"
                gif_path = os.path.join(os.getcwd(), 'temp', gif_filename)
                
                try:
                    if actual_format == 'tgs':
                        logger.info("检测到 TGS 格式，使用 Lottie/rlottie 渲染")
                        await self.convert_tgs_to_gif(temp_path, gif_path, width=512, height=512)
                    elif actual_format == 'webm':
                        logger.info("检测到 WebM 格式，使用 FFmpeg 转换")
                        await self.convert_webm_to_gif(temp_path, gif_path)
                    else:
                        logger.warning(f"未知格式 ({actual_format})，尝试使用 FFmpeg 转换")
                        await self.convert_webm_to_gif(temp_path, gif_path)
                    
                    final_send_path = gif_path
                except Exception as e:
                    logger.error(f"贴纸转换失败: {e}")
                    error_text = self._get_sticker_error_text(e)
                    message_array.append({"type": "text", "data": {"text": f"({error_text})"}})
                    result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
                    return result
                
                message_array.append({"type": "image", "data": {"file": final_send_path}})
            else:
                message_array.append({"type": "image", "data": {"file": final_send_path}})
            
            result = await onebot_client.send_group_msg(self.qq_group_id, message_array)
            if result and tg_message_id:
                qq_msg_id = self._extract_qq_message_id(result)
                if qq_msg_id:
                    await db.save_message_mapping(
                        tg_message_id=tg_message_id,
                        qq_message_id=qq_msg_id,
                        sender_tg_id=tg_user_id
                    )
            logger.info(f"贴纸已成功发送至 QQ。结果: {result}")
            return result

        except Exception as e:
            logger.error(f"转发贴纸至 QQ 失败: {e}", exc_info=True)
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            if gif_path and os.path.exists(gif_path):
                try: os.remove(gif_path)
                except: pass

    async def forward_voice_to_tg(self, qq_user_id: int, qq_nickname: str, file_url: str, reply_to_message_id: int = None, qq_message_id: int = None):
        """转发 QQ 语音消息到 Telegram (带 FFmpeg 转码)"""
        display_name = await self.get_display_name(qq_user_id=qq_user_id, fallback_name=qq_nickname)
        
        try:
            # 提取原始文件名或生成默认名
            original_name = os.path.basename(file_url).split('?')[0] or f"voice_{qq_user_id}.amr"
            temp_filename = f"voice_{uuid.uuid4().hex}_{original_name}"
            temp_path = await FileTransfer._http_download(file_url, temp_filename)
            
            # 使用 FFmpeg 转换为 OGG Opus (Telegram 兼容格式)
            ogg_filename = f"voice_{uuid.uuid4().hex}.ogg"
            ogg_path = os.path.join(os.getcwd(), 'temp', ogg_filename)
            
            ffmpeg_path = ffmpeg_manager.get_executable_path() or 'ffmpeg'
            logger.debug(f"使用 FFmpeg 路径: {ffmpeg_path}")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: (
                ffmpeg.input(temp_path)
                .output(ogg_path, acodec='libopus', ar=48000, ab='64k')
                .overwrite_output()
                .run(cmd=ffmpeg_path, quiet=True)
            ))
            
            caption = f"[QQ] {display_name} 发送了一条语音"
            with open(ogg_path, 'rb') as audio_file:
                result = await self.bot.send_voice(
                    chat_id=self.tg_group_id,
                    voice=audio_file,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
            
            if result and qq_message_id:
                await db.save_message_mapping(
                    tg_message_id=result.message_id,
                    qq_message_id=qq_message_id,
                    sender_qq_id=qq_user_id
                )
            
            logger.info(f"语音已转发至 TG 群 {self.tg_group_id}")
            return result
        except Exception as e:
            logger.error(f"转发语音至 Telegram 失败: {e}")
            return None
        finally:
            if 'temp_path' in locals() and temp_path and os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            if 'ogg_path' in locals() and ogg_path and os.path.exists(ogg_path):
                try: os.remove(ogg_path)
                except: pass

    async def forward_to_qq(self, tg_user_id: int, tg_username: str, text: str, reply_segment: list = None, tg_message_id: int = None):
        display_name = await self.get_display_name(tg_user_id=tg_user_id, fallback_name=tg_username)
        if reply_segment:
            message = reply_segment + [{"type": "text", "data": {"text": f"[TG] {display_name}: {text}"}}]
        else:
            message = f"[TG] {display_name}: {text}"
        result = await onebot_client.send_group_msg(self.qq_group_id, message)
        if result and tg_message_id:
            qq_msg_id = self._extract_qq_message_id(result)
            if qq_msg_id:
                await db.save_message_mapping(
                    tg_message_id=tg_message_id,
                    qq_message_id=qq_msg_id,
                    sender_tg_id=tg_user_id
                )
        return result

    async def forward_merged_to_tg(self, qq_user_id: int, qq_nickname: str, content_data, qq_message_id: int = None):
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
        markdown_parts = [f"📋 合并转发消息 \\(来自 {safe_display_name}\\):\n"]
        
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
            if result and qq_message_id:
                await db.save_message_mapping(
                    tg_message_id=result.message_id,
                    qq_message_id=qq_message_id,
                    sender_qq_id=qq_user_id
                )
            logger.info(f"已同步合并转发消息至 TG，共 {len(msg_list)} 条子消息")
            return result

        except Exception as e:
            logger.error(f"解析或发送合并转发消息失败: {e}")
            return None

    async def forward_to_tg(self, qq_user_id: int, qq_nickname: str, text: str, reply_to_message_id: int = None, qq_message_id: int = None):
        display_name = await self.get_display_name(qq_user_id=qq_user_id, fallback_name=qq_nickname)
        message = f"[QQ] {display_name}: {text}"
        try:
            result = await retry_async(
                self.bot.send_message,
                chat_id=self.tg_group_id,
                text=message,
                reply_to_message_id=reply_to_message_id,
                max_retries=3,
                base_delay=1.0
            )
            if result and qq_message_id:
                await db.save_message_mapping(
                    tg_message_id=result.message_id,
                    qq_message_id=qq_message_id,
                    sender_qq_id=qq_user_id
                )
            return result
        except Exception as e:
            logger.error(f"转发文本至 Telegram 失败 (已重试3次): {e}")
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
            f"| TQSync NEXT {version_str} \n"
            f"--------------------------\n"
            f"- 最后更新: {last_update}\n"
            f"- 目标 QQ 群: {qq_gid}\n"
            f"- 目标 TG 群: {tg_gid}\n"
            f"--------------------------"
        )
        
        # 4. 发送通知
        # 发送到 Telegram
        try:
            await self.bot.send_message(chat_id=self.tg_group_id, text=message)
            logger.info("向 TG 发送启动通知")
        except Exception as e:
            logger.error(f"Failed to send startup notification to Telegram: {e}")
            
        # 发送到 QQ
        try:
            await onebot_client.send_group_msg(self.qq_group_id, message)
            logger.info("向 QQ 发送启动通知")
        except Exception as e:
            logger.error(f"Failed to send startup notification to QQ: {e}")

sync_engine = None  # Will be initialized in main.py with the bot instance
