"""统一文件传输模块
基于 NapCat API 实现智能文件解析、流式下载、跨平台转发。
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

import aiofiles
import aiohttp
from PIL import Image

from config.config_loader import config_loader
from handlers.qq_handler import onebot_client
from utils.logger import logger

# ---------------------------------------------------------------------------
# 魔数签名表 — 仅保留最常用格式
# ---------------------------------------------------------------------------
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b'\x89\x50\x4E\x47', '.png'),
    (b'\xFF\xD8\xFF', '.jpg'),
    (b'\x47\x49\x46\x38', '.gif'),
    (b'\x25\x50\x44\x46', '.pdf'),
    (b'\x50\x4B\x03\x04', '.zip'),
    (b'\xD0\xCF\x11\xE0', '.doc'),
    (b'\x52\x61\x72\x21', '.rar'),
    (b'\x1A\x45\xDF\xA3', '.webm'),
    (b'\x00\x00\x00\x18\x66\x74\x79\x70', '.mp4'),
    (b'\x66\x74\x79\x70\x69\x73\x6F\x6D', '.mp4'),
    (b'\x49\x44\x33', '.mp3'),
    (b'\x7B\x5C\x72\x74\x66', '.rtf'),
    (b'\x1F\x8B', '.gz'),
    (b'\x4D\x5A', '.exe'),
]

# 大文件阈值 (50 MB)，超过此大小使用流式下载
_STREAMING_THRESHOLD = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _format_size(size_bytes: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024.0:
            return f'{size_bytes:.2f} {unit}'
        size_bytes /= 1024.0
    return f'{size_bytes:.2f} TB'


def _resolve_temp_dir() -> str:
    d = os.path.join(os.getcwd(), 'temp')
    os.makedirs(d, exist_ok=True)
    return d


def _unique_temp_path(prefix: str = 'file', ext: str = '.tmp') -> str:
    return os.path.join(_resolve_temp_dir(), f'{prefix}_{uuid.uuid4().hex}_{int(time.time() * 1000)}{ext}')


# ---------------------------------------------------------------------------
# MediaType
# ---------------------------------------------------------------------------
class MediaType(Enum):
    IMAGE = auto()
    VIDEO = auto()
    AUDIO = auto()
    DOCUMENT = auto()
    ANIMATION = auto()
    STICKER = auto()


# ---------------------------------------------------------------------------
# FileSource — 统一的文件来源表示
# ---------------------------------------------------------------------------
@dataclass
class FileSource:
    """文件来源，封装所有可能的文件定位方式。

    解析优先级:
    1. local_path  (文件已在本地)
    2. http_url     (直接 HTTP 下载)
    3. napcat_file  (通过 NapCat /get_file API 解析)
    4. data         (原始字节，直接使用)
    """

    local_path: Optional[str] = None
    http_url: Optional[str] = None
    napcat_file: Optional[str] = None          # file_id 或 file:// 路径(供 /get_file)
    napcat_file_id: Optional[str] = None       # 明确的 file_id
    data: Optional[bytes] = None
    file_name: str = 'unknown_file'
    file_size: int = 0
    media_type: Optional[MediaType] = None

    @classmethod
    def from_qq_webhook(cls, file_url: str, file_name: str = '',
                        raw_file: str = '', raw_url: str = '') -> FileSource:
        """从 QQ webhook 数据构造 FileSource。"""
        fs = cls(file_name=file_name or 'unknown_file')

        if not file_url:
            return fs

        # QQ 内部 CDN URL 不可直接 HTTP 访问，必须通过 NapCat API
        _qq_cdn_domains = ('gchat.qpic.cn', 'multimedia.nt.qq.com.cn',
                           'c2c.p.afjackimg.com', 'groupprocover.gtimg.cn')

        if file_url.startswith('http') and any(d in file_url for d in _qq_cdn_domains):
            fs.napcat_file = raw_file or file_url
            fs.http_url = None  # 禁止直接 HTTP 下载
        elif file_url.startswith('http'):
            fs.http_url = file_url
        elif file_url.startswith('file:///'):
            fs.local_path = file_url.replace('file://', '')
            fs.napcat_file = raw_file or file_url
        elif os.path.isabs(file_url):
            fs.local_path = file_url
        else:
            fs.napcat_file = file_url

        return fs

    @classmethod
    def from_telegram(cls, file_id: str, file_name: str = '', file_size: int = 0,
                      token: str = '') -> FileSource:
        """从 Telegram file_id 构造 FileSource。"""
        fs = cls(file_name=file_name or f'file_{uuid.uuid4().hex[:8]}', file_size=file_size)
        if token:
            fs.http_url = f'https://api.telegram.org/file/bot{token}/{file_id}'
        else:
            fs.http_url = file_id  # 将由调用者构造完整 URL
        return fs

    @property
    def size_str(self) -> str:
        return _format_size(self.file_size) if self.file_size else '未知'

    def __bool__(self) -> bool:
        return bool(self.local_path or self.http_url or self.napcat_file or self.data)


# ---------------------------------------------------------------------------
# NapCat File API 封装
# ---------------------------------------------------------------------------
class NapCatFileAPI:
    """封装 NapCat 文件相关 API (get_file / get_image / download_file 等)。"""

    @staticmethod
    async def get_file(file: str = None, file_id: str = None,
                       file_name: str = '') -> Optional[dict]:
        """调用 /get_image 或 /get_file 获取文件信息及下载路径。

        根据文件名/扩展名自动选择正确的 API 端点:
        - 图片格式 → /get_image
        - 其他 → /get_file
        """
        if not file and not file_id:
            return None

        # 根据扩展名判断是否为图片
        _image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.ico')
        is_image = any(file_name.lower().endswith(e) for e in _image_exts) if file_name else False

        payload = {}
        if file_id:
            payload['file_id'] = file_id
        if file:
            payload['file'] = file

        endpoints = [('/get_image', '图片'), ('/get_file', '文件')] if is_image else [
            ('/get_file', '文件'), ('/get_image', '图片')
        ]

        for endpoint, label in endpoints:
            try:
                result = await onebot_client._post_json(endpoint, payload, max_retries=2, base_delay=1.0)
                if result.get('retcode') == 0 and result.get('data'):
                    logger.debug(f'NapCat {label} API 解析成功')
                    return result['data']
            except Exception as e:
                logger.debug(f'NapCat {label} API 失败: {e}')

        return None

    @staticmethod
    async def download_file(file_url: str, thread_count: int = 3,
                            headers: list = None) -> Optional[str]:
        """调用 NapCat /download_file 下载到其缓存目录，返回本地路径。"""
        payload = {'url': file_url, 'thread_count': thread_count}
        if headers:
            payload['headers'] = headers
        try:
            result = await onebot_client._post_json('/download_file', payload, max_retries=2, base_delay=1.0)
            if result.get('retcode') == 0 and result.get('data'):
                return result['data'].get('file')
        except Exception as e:
            logger.debug(f'NapCat /download_file 失败: {e}')
        return None


# ---------------------------------------------------------------------------
# 文件解析 & 下载
# ---------------------------------------------------------------------------
class FileTransfer:
    """文件传输核心 — 解析 -> 下载 -> 跨平台发送。"""

    # 注入的外部依赖（由 sync_engine 初始化时设置）
    tg_bot = None
    tg_group_id: int = 0
    qq_group_id: int = 0

    # ---- 魔数检测 ----------------------------------------------------------
    @staticmethod
    def detect_extension(file_path: str) -> Optional[str]:
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)
            for magic, ext in _MAGIC_SIGNATURES:
                if header.startswith(magic):
                    return ext
        except Exception:
            pass
        return None

    @staticmethod
    def classify_media(file_path: str, fallback_name: str = '') -> MediaType:
        """根据扩展名 / 魔数判断媒体类型。"""
        name = file_path if file_path else fallback_name
        ext = os.path.splitext(name)[1].lower()

        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.ico'):
            return MediaType.IMAGE
        if ext in ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm'):
            return MediaType.VIDEO
        if ext in ('.mp3', '.ogg', '.wav', '.amr', '.aac', '.flac', '.m4a', '.opus'):
            return MediaType.AUDIO
        if ext in ('.gif',):
            return MediaType.ANIMATION
        if ext in ('.tgs',):
            return MediaType.STICKER

        # 魔数回退检测
        if file_path and os.path.exists(file_path):
            det = FileTransfer.detect_extension(file_path)
            if det == '.gif':
                return MediaType.ANIMATION
            if det in ('.webm', '.mp4'):
                return MediaType.VIDEO
            if det in ('.png', '.jpg'):
                return MediaType.IMAGE

        return MediaType.DOCUMENT

    # ---- 智能文件解析 (核心) ------------------------------------------------
    @staticmethod
    async def resolve(source: FileSource) -> FileSource:
        """将 FileSource 解析为可用的本地文件路径。

        解析链路 (QQ 媒体优先走 NapCat API):
        1. local_path 已存在 → 直接使用
        2. data (字节) → 写入临时文件
        3. napcat_file → 调用 NapCat API 获取本地路径/base64
        4. http_url → HTTP 下载 (非 QQ CDN)
        """
        # 1. 本地路径
        if source.local_path and os.path.exists(source.local_path):
            source.file_size = os.path.getsize(source.local_path)
            logger.debug(f'使用本地文件: {source.local_path} ({source.size_str})')
            return source

        # 2. 内存数据
        if source.data:
            dest = _unique_temp_path('data', os.path.splitext(source.file_name)[1] or '.tmp')
            async with aiofiles.open(dest, 'wb') as f:
                await f.write(source.data)
            source.local_path = dest
            source.file_size = len(source.data)
            logger.debug(f'内存数据写入: {dest} ({source.size_str})')
            return source

        # 3. NapCat API 解析 (QQ 媒体优先)
        if source.napcat_file or source.napcat_file_id:
            data = await NapCatFileAPI.get_file(
                file=source.napcat_file,
                file_id=source.napcat_file_id,
                file_name=source.file_name
            )
            if data:
                if data.get('file') and os.path.exists(data['file']):
                    source.local_path = data['file']
                    source.file_size = int(data.get('file_size', 0)) or os.path.getsize(source.local_path)
                    source.file_name = data.get('file_name') or source.file_name
                    return source
                if data.get('url'):
                    try:
                        path = await FileTransfer._http_download(
                            data['url'],
                            data.get('file_name') or source.file_name
                        )
                        source.local_path = path
                        source.file_size = os.path.getsize(path)
                        source.file_name = data.get('file_name') or source.file_name
                        return source
                    except Exception as e:
                        logger.warning(f'NapCat URL 下载失败: {e}')
                if data.get('base64'):
                    try:
                        import base64
                        raw = base64.b64decode(data['base64'])
                        ext = os.path.splitext(data.get('file_name', source.file_name))[1] or '.tmp'
                        dest = _unique_temp_path('napcat', ext)
                        async with aiofiles.open(dest, 'wb') as f:
                            await f.write(raw)
                        source.local_path = dest
                        source.file_size = len(raw)
                        source.file_name = data.get('file_name') or source.file_name
                        return source
                    except Exception as e:
                        logger.warning(f'NapCat base64 解码失败: {e}')

        # 4. HTTP 下载 (非 QQ CDN 的普通 HTTP URL)
        if source.http_url:
            try:
                path = await FileTransfer._http_download(source.http_url, source.file_name)
                source.local_path = path
                source.file_size = os.path.getsize(path)
                logger.debug(f'HTTP 下载完成: {path} ({source.size_str})')
                return source
            except Exception as e:
                logger.warning(f'HTTP 下载失败: {e}')

        # 5. 兜底检查
        if source.local_path and os.path.exists(source.local_path):
            source.file_size = os.path.getsize(source.local_path)
            return source

        raise FileNotFoundError(f'无法解析文件: name={source.file_name} '
                                f'http={source.http_url[:60] if source.http_url else None} '
                                f'local={source.local_path} napcat={source.napcat_file}')

    @staticmethod
    async def _http_download(url: str, file_name: str) -> str:
        """HTTP 下载文件到 temp 目录，支持流式进度日志。"""
        temp_dir = _resolve_temp_dir()
        ext = os.path.splitext(url.split('?')[0])[1] or os.path.splitext(file_name)[1] or '.tmp'

        temp_path = _unique_temp_path('dl', '.tmp')
        final_path = os.path.join(temp_dir, f'dl_{uuid.uuid4().hex[:8]}_{int(time.time())}{ext}')

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=600, connect=30)

        start_time = time.time()
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception(f'HTTP {resp.status}')
                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded = 0
                    last_log = start_time

                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            if now - last_log >= 2.0 and total_size > 0:
                                pct = downloaded / total_size * 100
                                speed = downloaded / (now - start_time) if now > start_time else 0
                                logger.debug(f'下载: {pct:.1f}% ({_format_size(speed)}/s)')
                                last_log = now

            shutil.move(temp_path, final_path)
            elapsed = time.time() - start_time
            size = os.path.getsize(final_path)
            logger.info(f'下载完成: {os.path.basename(final_path)} ({_format_size(size)}) {elapsed:.1f}s')
            return final_path

        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise

    # ---- 文件内容规范化 (扩展名修正) ----------------------------------------
    @staticmethod
    def normalize_extension(file_path: str, file_name: str) -> tuple[str, str]:
        """检测魔数并修正文件扩展名，返回 (new_path, new_name)。"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ('.dat', '.tmp', ''):
            return file_path, file_name

        detected = FileTransfer.detect_extension(file_path)
        if detected and detected != ext:
            new_path = os.path.splitext(file_path)[0] + detected
            os.rename(file_path, new_path)
            new_name = os.path.splitext(file_name)[0] + detected
            logger.info(f'魔数检测: {ext or "无扩展名"} → {detected}')
            return new_path, new_name
        return file_path, file_name

    # ---- 发送至 Telegram ---------------------------------------------------
    @staticmethod
    async def send_to_telegram(source: FileSource, *,
                               caption: str = '',
                               reply_to: int = None) -> Optional[int]:
        """将已解析的文件发送到 Telegram，返回 message_id 或 None。"""
        if not source.local_path or not os.path.exists(source.local_path):
            raise FileNotFoundError(f'文件不存在: {source.local_path}')

        file_path, file_name = FileTransfer.normalize_extension(
            source.local_path, source.file_name
        )
        media_type = source.media_type or FileTransfer.classify_media(file_path, file_name)

        async with aiofiles.open(file_path, 'rb') as f:
            content = await f.read()

        bot = FileTransfer.tg_bot
        chat_id = FileTransfer.tg_group_id
        kwargs = {'chat_id': chat_id}
        if caption:
            kwargs['caption'] = caption
        if reply_to:
            kwargs['reply_to_message_id'] = reply_to

        async def _do_send():
            if media_type == MediaType.IMAGE:
                try:
                    img = Image.open(io.BytesIO(content))
                    w, h = img.size
                    if w < 10 and h < 10 and w + h < 20:
                        raise ValueError('图片过小')
                    return await bot.send_photo(**kwargs, photo=content, filename=file_name)
                except Exception:
                    logger.debug(f'图片发送失败, 改为文档: {file_name}')

            elif media_type == MediaType.VIDEO:
                return await bot.send_video(**kwargs, video=content, filename=file_name)

            elif media_type == MediaType.ANIMATION:
                try:
                    return await bot.send_animation(**kwargs, animation=content, filename=file_name)
                except Exception:
                    logger.debug(f'动画发送失败, 改为文档: {file_name}')

            elif media_type == MediaType.AUDIO:
                return await bot.send_audio(**kwargs, audio=content, filename=file_name)

            else:
                return await bot.send_document(**kwargs, document=content, filename=file_name)

        result = await _retry_async(_do_send, max_retries=3, base_delay=2.0)
        logger.info(f'已发送至 Telegram: {os.path.basename(file_path)}')
        return result.message_id if result else None

    # ---- 发送至 QQ ---------------------------------------------------------
    @staticmethod
    async def send_to_qq(source: FileSource, *,
                         prefix: str = '',
                         reply_segment: list = None) -> Optional[dict]:
        """将已解析的文件发送到 QQ 群，返回 OneBot 响应 dict。"""
        if not source.local_path or not os.path.exists(source.local_path):
            raise FileNotFoundError(f'文件不存在: {source.local_path}')

        file_path, file_name = FileTransfer.normalize_extension(
            source.local_path, source.file_name
        )
        media_type = source.media_type or FileTransfer.classify_media(file_path, file_name)

        # 构造消息段
        msg = list(reply_segment) if reply_segment else []
        if prefix:
            msg.append({'type': 'text', 'data': {'text': prefix}})

        # 根据类型选择 OneBot 消息段
        onebot_type_map = {
            MediaType.IMAGE: 'image',
            MediaType.VIDEO: 'video',
            MediaType.AUDIO: 'record',
            MediaType.DOCUMENT: 'file',
            MediaType.ANIMATION: 'image',  # QQ 不支持 GIF 动画，作为图片发送
            MediaType.STICKER: 'image',
        }

        ob_type = onebot_type_map.get(media_type, 'file')
        msg.append({'type': ob_type, 'data': {'file': file_path}})

        result = await onebot_client.send_group_msg(FileTransfer.qq_group_id, msg)
        logger.info(f'已发送至 QQ: {os.path.basename(file_path)}')
        return result

    # ---- 完整流程: 解析 + 发送 ---------------------------------------------
    @staticmethod
    async def transfer_qq_to_tg(source: FileSource, *,
                                qq_user_id: int, display_name: str,
                                caption: str = '', reply_to: int = None,
                                qq_message_id: int = None) -> Optional[int]:
        """QQ → TG: 解析文件 + 发送 + 保存映射。"""
        try:
            source = await FileTransfer.resolve(source)
            prefix = f'[QQ] {display_name}'
            full_caption = f'{prefix}\n{caption}' if caption else prefix

            tg_msg_id = await FileTransfer.send_to_telegram(
                source, caption=full_caption, reply_to=reply_to
            )
            if tg_msg_id and qq_message_id:
                from db.database import db
                await db.save_message_mapping(
                    tg_message_id=tg_msg_id,
                    qq_message_id=qq_message_id,
                    sender_qq_id=qq_user_id
                )
            return tg_msg_id

        except Exception as e:
            logger.error(f'QQ→TG 文件传输失败: {e}', exc_info=True)
            try:
                await onebot_client.send_group_msg(
                    FileTransfer.qq_group_id,
                    f'⚠️ 文件同步至 Telegram 失败: {str(e)[:100]}'
                )
            except Exception:
                pass
            return None
        finally:
            FileTransfer._cleanup(source)

    @staticmethod
    async def transfer_tg_to_qq(source: FileSource, *,
                                tg_user_id: int, display_name: str,
                                reply_segment: list = None,
                                tg_message_id: int = None) -> Optional[dict]:
        """TG → QQ: 解析文件 + 发送 + 保存映射。"""
        from db.database import db
        try:
            source = await FileTransfer.resolve(source)
            prefix = f'[TG] {display_name}\n'
            if source.media_type == MediaType.DOCUMENT:
                prefix = f'[TG] {display_name} 发送了一个文件: {source.file_name}\n'
            elif source.media_type == MediaType.VIDEO:
                prefix = f'[TG] {display_name} 发送了一个视频\n'
            elif source.media_type == MediaType.AUDIO:
                prefix = f'[TG] {display_name} 发送了一条语音\n'

            result = await FileTransfer.send_to_qq(
                source, prefix=prefix, reply_segment=reply_segment
            )
            if result and tg_message_id:
                qq_msg_id = _extract_qq_msg_id(result)
                if qq_msg_id:
                    await db.save_message_mapping(
                        tg_message_id=tg_message_id,
                        qq_message_id=qq_msg_id,
                        sender_tg_id=tg_user_id
                    )
            return result

        except Exception as e:
            logger.error(f'TG→QQ 文件传输失败: {e}', exc_info=True)
            try:
                if FileTransfer.tg_bot:
                    await FileTransfer.tg_bot.send_message(
                        chat_id=FileTransfer.tg_group_id,
                        text=f'⚠️ 文件同步至 QQ 失败: {str(e)[:100]}'
                    )
            except Exception:
                pass
            return None
        finally:
            FileTransfer._cleanup(source)

    @staticmethod
    def _cleanup(source: FileSource):
        """清理临时文件（保留非 temp 目录的文件）。"""
        if source.local_path and _resolve_temp_dir() in source.local_path:
            try:
                if os.path.exists(source.local_path):
                    os.remove(source.local_path)
                    logger.debug(f'已清理临时文件: {source.local_path}')
            except Exception as e:
                logger.warning(f'清理失败: {e}')


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _extract_qq_msg_id(result) -> Optional[int]:
    if result and isinstance(result, dict):
        data = result.get('data', {})
        if isinstance(data, dict):
            return data.get('message_id')
        return result.get('message_id')
    return None


async def _retry_async(func, *args, max_retries: int = 3, base_delay: float = 1.0, **kwargs):
    last_error = None
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(f'重试 ({attempt + 1}/{max_retries}): {e}, {delay:.1f}s 后重试')
                await asyncio.sleep(delay)
    raise last_error
