import os
import sys
import platform
import zipfile
import tarfile
import aiohttp
import shutil
import asyncio
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

    async def download_and_install(self, progress_callback=None) -> bool:
        """根据系统自动下载并安装 FFmpeg"""
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

        logger.info(f"正在下载 FFmpeg ({system}/{machine})...")
        os.makedirs(self.bin_dir, exist_ok=True)
        
        zip_path = os.path.join(self.bin_dir, filename)
        
        try:
            # 1. 下载文件
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=300) # 5分钟超时
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Download failed with status {resp.status}")
                    
                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(zip_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                await progress_callback(percent)

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
                return False

        except Exception as e:
            logger.error(f"FFmpeg 下载或安装失败: {e}", exc_info=True)
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return False

ffmpeg_manager = FFmpegManager()
