"""管理白名单校验（Telegram / QQ 共用）

统一处理 ``server.admin_user_ids``，解决两类历史问题：

1. 配置里混入字符串（如 ``"10001"``）导致 ``int in list`` 永远不成立，
   管理员全部失效；
2. 白名单为空时 ``if admin_ids and ...`` 短路成「允许」，等于清空配置就
   对所有人开放管理命令（fail-open）。
"""

from config.config_loader import config_loader
from utils.logger import logger


def get_admin_ids() -> set:
    """读取并规范化管理员 ID 集合（统一转 int，忽略非法项）。"""
    raw = config_loader.get('server.admin_user_ids', []) or []
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]

    ids = set()
    for item in raw:
        try:
            ids.add(int(str(item).strip()))
        except (TypeError, ValueError):
            logger.warning(f"忽略非法的管理员 ID 配置项: {item!r}")
    return ids


def is_admin(user_id) -> bool:
    """判断用户是否在管理白名单内。

    fail-closed：白名单为空时一律返回 False，避免配置被清空或写错后
    所有人获得管理权限。
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False

    admins = get_admin_ids()
    if not admins:
        return False
    return uid in admins
