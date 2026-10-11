import socket
import re
import aiohttp
from typing import Optional
from config.config_loader import config_loader
from utils.logger import logger

IP_REGEX = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')

def is_valid_ipv4(ip: str) -> bool:
    """验证是否为合法的 IPv4 地址"""
    if not ip or not IP_REGEX.match(ip):
        return False
    parts = ip.split('.')
    return all(0 <= int(p) <= 255 for p in parts)

def get_local_ip() -> str:
    """获取本机局域网内网 IP，失败返回 127.0.0.1"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        if is_valid_ipv4(ip):
            return ip
    except Exception:
        pass
    return '127.0.0.1'

async def get_public_ip(timeout_sec: float = 3.0) -> str:
    """通过多个第三方接口获取服务器公网 IP，失败返回空字符串"""
    urls = (
        'https://api.ipify.org',
        'https://ipv4.icanhazip.com',
        'https://api.ip.sb/ip',
        'https://ifconfig.me/ip',
        'https://myip.ipip.net/s',
    )
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in urls:
                try:
                    headers = {'User-Agent': 'curl/7.68.0'}
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            content = (await resp.text()).strip()
                            if is_valid_ipv4(content):
                                return content
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"获取公网 IP 异常: {e}")
    return ''

async def get_webui_url() -> str:
    """获取 WebUI 访问地址

    优先级:
    1. server.webui_url 配置
    2. 通过外部接口获取的公网 IP:端口
    3. 本机局域网内网 IP:端口 (当 host 为 0.0.0.0 时)
    4. server.host:端口
    """
    configured = config_loader.get('server.webui_url')
    if configured:
        return str(configured).rstrip('/')

    port = config_loader.get('server.admin_api_port', 8081)
    
    # 尝试通过接口获取公网 IP
    public_ip = await get_public_ip()
    if public_ip:
        return f"http://{public_ip}:{port}"

    # 尝试获取内网 IP 或 host
    host = config_loader.get('server.host', '127.0.0.1')
    if host in ('0.0.0.0', '', '::', '0:0:0:0:0:0:0:0'):
        local_ip = get_local_ip()
        return f"http://{local_ip}:{port}"

    return f"http://{host}:{port}"

