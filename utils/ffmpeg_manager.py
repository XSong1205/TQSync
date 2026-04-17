import os
import sys
import platform
import zipfile
import tarfile
import aiohttp
import shutil
import asyncio
import time
from utils.logger import logger

class FFmpegManager:
    def __init__(self):
        self.bin_dir = os.path.join(os.getcwd(), 'bin', 'ffmpeg')
        self.executable_name = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'
        self.local_path = os.path.join(self.bin_dir, self.executable_name)

    def get_executable_path(self) -> str:
        """获取 FFmpeg 可执行文件的绝对路径"""
        if os.path.exists(self.local_path):
            return self.local_path
        return None

    async def download_and_install(self, progress_callback=None, max_retries: int = 3) -> bool:
        """根据系统自动下载并安装 FFmpeg
        
        Args:
            progress_callback: 进度回调函数
            max_retries: 最大重试次数
        """
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        url = None
        filename = "ffmpeg.zip"
        is_tar = False

        # 确定下载地址 (使用 gyan.dev 的 release builds，比较稳定)
        if system == 'windows':
            url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            if machine in ['arm64', 'aarch64']:
                url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-winarm64-gpl.zip"
        elif system == 'darwin': # macOS
            url = "https://evermeet.cx/ffmpeg/getrelease/zip"
        elif system == 'linux':
            # Linux 架构较多，这里提供一个通用的 x86_64 静态编译版本
            url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
            filename = "ffmpeg.tar.xz"
            is_tar = True
            if machine in ['aarch64', 'arm64']:
                url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
        else:
            logger.error(f"不支持的操作系统: {system}")
            return False

        if not url:
            logger.error("无法找到适合当前系统的 FFmpeg 下载链接")
            return False

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"正在下载 FFmpeg ({system}/{machine})... (尝试 {attempt}/{max_retries})")
                logger.info(f"下载地址: {url}")
                os.makedirs(self.bin_dir, exist_ok=True)
                
                zip_path = os.path.join(self.bin_dir, filename)
                
                # 如果之前下载失败，清理残留文件
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                
                # 1. 下载文件
                connector = aiohttp.TCPConnector(ssl=False)
                timeout = aiohttp.ClientTimeout(total=600) # 10分钟超时，FFmpeg 包较大
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise Exception(f"Download failed with status {resp.status}")
                        
                        total_size = int(resp.headers.get('content-length', 0))
                        downloaded = 0
                        start_time = time.time()
                        last_update_time = start_time
                        last_downloaded = 0
                        
                        # 格式化文件大小
                        def format_size(size_bytes):
                            for unit in ['B', 'KB', 'MB', 'GB']:
                                if size_bytes < 1024.0:
                                    return f"{size_bytes:.2f} {unit}"
                                size_bytes /= 1024.0
                            return f"{size_bytes:.2f} TB"
                        
                        if total_size > 0:
                            logger.info(f"文件大小: {format_size(total_size)}")
                        
                        with open(zip_path, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                current_time = time.time()
                                time_diff = current_time - last_update_time
                                
                                # 每 1 秒更新一次进度
                                if time_diff >= 1.0 or downloaded == total_size:
                                    elapsed_time = current_time - start_time
                                    speed = (downloaded - last_downloaded) / time_diff if time_diff > 0 else 0
                                    
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        remaining_bytes = total_size - downloaded
                                        eta_seconds = remaining_bytes / speed if speed > 0 else 0
                                        
                                        # 格式化 ETA
                                        if eta_seconds < 60:
                                            eta_str = f"{int(eta_seconds)}秒"
                                        elif eta_seconds < 3600:
                                            eta_str = f"{int(eta_seconds / 60)}分{int(eta_seconds % 60)}秒"
                                        else:
                                            eta_str = f"{int(eta_seconds / 3600)}小时{int((eta_seconds % 3600) / 60)}分"
                                        
                                        progress_msg = (
                                            f"下载进度: {percent:.1f}% | "
                                            f"速度: {format_size(speed)}/s | "
                                            f"已下载: {format_size(downloaded)}/{format_size(total_size)} | "
                                            f"预计剩余: {eta_str}"
                                        )
                                        logger.info(progress_msg)
                                        
                                        # 调用回调函数（用于 TG 端显示）
                                        if progress_callback:
                                            await progress_callback(int(percent))
                                    else:
                                        logger.info(f"已下载: {format_size(downloaded)} | 速度: {format_size(speed)}/s")
                                    
                                    last_update_time = current_time
                                    last_downloaded = downloaded
                
                logger.info("下载完成，正在解压...")
                
                # 2. 解压文件
                if is_tar:
                    with tarfile.open(zip_path, 'r:xz') as tar:
                        # 寻找 bin/ffmpeg 文件
                        for member in tar.getmembers():
                            if member.name.endswith('/ffmpeg'):
                                member.name = os.path.basename(member.name)
                                tar.extract(member, self.bin_dir)
                                break
                else:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        # 寻找 ffmpeg.exe
                        for name in zip_ref.namelist():
                            if name.endswith(self.executable_name):
                                # 尝试从压缩包子目录中提取
                                zip_ref.extract(name, self.bin_dir)
                                # 移动到根目录并重命名
                                src = os.path.join(self.bin_dir, name)
                                dst = self.local_path
                                if os.path.exists(src):
                                    shutil.move(src, dst)
                                break
                
                # 3. 清理安装包
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    
                # 4. 赋予执行权限 (Linux/macOS)
                if system != 'windows' and os.path.exists(self.local_path):
                    os.chmod(self.local_path, 0o755)

                if os.path.exists(self.local_path):
                    logger.info(f"FFmpeg 已成功安装至: {self.local_path}")
                    return True
                else:
                    logger.error("解压后未找到 FFmpeg 可执行文件")
                    if attempt < max_retries:
                        logger.info(f"将在 3 秒后重试...")
                        await asyncio.sleep(3)
                    continue

            except Exception as e:
                logger.error(f"FFmpeg 下载或安装失败 (尝试 {attempt}/{max_retries}): {e}")
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                
                if attempt < max_retries:
                    wait_time = 3 * attempt  # 递增等待时间
                    logger.info(f"将在 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("已达到最大重试次数，下载失败")
                    return False
        
        return False

ffmpeg_manager = FFmpegManager()
