import os
import sys
import platform
from utils.version_utils import get_full_version_string

BANNER_ART = r"""
  ______ ____   _____                 
 /_  __/ __ \ / ___/__  ______  _____ 
  / / / / / / \__ \/ / / / __ \/ ___/ 
 / / / /_/ / ___/ / /_/ / / / / /__   
/_/  \___\_\/____/\__, /_/ /_/\___/   
                 /____/               """


def print_banner(config_loader=None):
    """在控制台打印 TQSync 启动字符画和系统配置信息。"""
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    use_color = sys.stdout.isatty() and 'NO_COLOR' not in os.environ
    if sys.platform == 'win32':
        try:
            os.system('')
        except Exception:
            pass

    CYAN = '\033[96m' if use_color else ''
    BLUE = '\033[94m' if use_color else ''
    GREEN = '\033[92m' if use_color else ''
    YELLOW = '\033[93m' if use_color else ''
    BOLD = '\033[1m' if use_color else ''
    DIM = '\033[2m' if use_color else ''
    RESET = '\033[0m' if use_color else ''

    # 获取系统与配置信息
    version_str = get_full_version_string()
    py_ver = f"Python {platform.python_version()} ({platform.system()})"
    is_container = os.environ.get('TQSYNC_CONTAINER', '0') == '1'
    env_mode = "容器环境" if is_container else "本地环境"

    webui_host = "0.0.0.0"
    admin_port = 8081
    webhook_port = 8080
    webhook_path = "/webhook/qq"
    tg_group = "未配置"
    qq_group = "未配置"

    if config_loader:
        try:
            webui_host = config_loader.get('server.host', webui_host)
            admin_port = config_loader.get('server.admin_api_port', admin_port)
            webhook_port = config_loader.get('server.qq_webhook_port', webhook_port)
            webhook_path = config_loader.get('server.webhook_path', webhook_path)
            tg_group = str(config_loader.get('telegram.group_id', tg_group))
            qq_group = str(config_loader.get('qq.group_id', qq_group))
        except Exception:
            pass

    sep = '=' * 58

    lines = [
        f"{CYAN}{BOLD}{BANNER_ART}{RESET}",
        f"  {DIM}{sep}{RESET}",
        f"   * 版本标识 (Version) : {GREEN}{version_str}{RESET}",
        f"   * 运行环境 (Runtime) : {YELLOW}{py_ver} [{env_mode}]{RESET}",
        f"   * WebUI 管理面板     : {BLUE}http://{webui_host}:{admin_port}{RESET}",
        f"   * QQ Webhook 服务    : 端口 {webhook_port} ({webhook_path})",
        f"   * 目标 Telegram 群组 : {tg_group}",
        f"   * 目标 QQ 群组       : {qq_group}",
        f"  {DIM}{sep}{RESET}\n",
    ]

    try:
        sys.stdout.write('\n'.join(lines) + '\n')
        sys.stdout.flush()
    except Exception:
        for line in lines:
            try:
                print(line)
            except Exception:
                pass


__all__ = ["print_banner", "BANNER_ART"]
