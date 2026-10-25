import secrets
import string
from config.config_loader import config_loader
from utils.logger import logger


def generate_random_password(length: int = 16) -> str:
    """生成指定长度的高强度易读随机密码（包含大小写字母与数字）"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def init_admin_security() -> dict:
    """检查 WebUI 鉴权 Token 配置。

    初次启动或检测到 token 为空时，生成随机安全密码并打印到日志，同时标记为初始密码。
    """
    admin_key = config_loader.get('server.admin_api_key')
    
    # 检测是否为空、全空白字符或模板默认占位符
    is_empty_or_placeholder = (
        admin_key is None
        or not str(admin_key).strip()
        or str(admin_key).strip() == 'your_secure_admin_key_here'
    )

    if is_empty_or_placeholder:
        new_token = generate_random_password(16)
        config_loader.update_config('server.admin_api_key', new_token)
        config_loader.update_config('server.is_initial_token', True)
        
        masked_token = f"{new_token[:4]}****" if len(new_token) >= 4 else "****"
        logger.warning("=" * 64)
        logger.warning("【安全提示】检测到 WebUI Token 为空或未设置，已自动生成初始管理密码：")
        logger.warning(f"🔑 WebUI 初始密码: {masked_token}")
        logger.warning("完整密钥见 config.yaml → server.admin_api_key")
        logger.warning("首次使用该密码登录 WebUI 时系统将提示修改密码，请妥善保管！")
        logger.warning("=" * 64)
        return {"is_new": True, "password": new_token, "is_initial": True}

    is_initial = bool(config_loader.get('server.is_initial_token', False))
    if is_initial:
        admin_key_str = str(admin_key)
        masked_key = f"{admin_key_str[:4]}****" if len(admin_key_str) >= 4 else "****"
        logger.warning("=" * 64)
        logger.warning("【安全提示】当前 WebUI 仍在使用系统生成的初始密码，建议尽快登录 WebUI 进行修改！")
        logger.warning(f"🔑 当前初始密码: {masked_key}")
        logger.warning("完整密钥见 config.yaml → server.admin_api_key")
        logger.warning("=" * 64)
        return {"is_new": False, "password": str(admin_key), "is_initial": True}

    return {"is_new": False, "password": str(admin_key), "is_initial": False}

