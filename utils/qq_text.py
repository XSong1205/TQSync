"""QQ 消息段 / 表情相关的文本格式化助手。

集中在两个场景：
1. QQ -> TG：把 QQ 的 `face`（小黄脸表情）消息段转成可读文本；
2. TG -> QQ：把 Telegram 的表情回应（emoji）转成 NapCat `set_msg_emoji_like` 需要的 emoji_id。
"""

from __future__ import annotations

# QQ 表情 id -> 中文名。NapCat 4.x 的 face 段自带 raw.faceText（如 "/微笑"），
# 优先用它；这张表是旧版本 NapCat 或字段缺失时的兜底。
QQ_FACE_NAMES = {
    0: '惊讶', 1: '撇嘴', 2: '色', 3: '发呆', 4: '得意', 5: '流泪', 6: '害羞', 7: '闭嘴',
    8: '睡', 9: '大哭', 10: '尴尬', 11: '发怒', 12: '调皮', 13: '呲牙', 14: '微笑',
    15: '难过', 16: '酷', 17: '非礼', 18: '偷笑', 19: '可爱', 20: '白眼', 21: '傲慢',
    22: '饥饿', 23: '困', 24: '惊恐', 25: '流汗', 26: '憨笑', 27: '悠闲', 28: '奋斗',
    29: '咒骂', 30: '疑问', 31: '嘘', 32: '晕', 33: '折磨', 34: '衰', 35: '骷髅',
    36: '敲打', 37: '再见', 38: '擦汗', 39: '抠鼻', 40: '鼓掌', 41: '糗大了', 42: '坏笑',
    43: '左哼哼', 44: '右哼哼', 45: '哈欠', 46: '鄙视', 47: '委屈', 48: '快哭了',
    49: '阴险', 50: '亲亲', 51: '吓', 52: '可怜', 53: '菜刀', 54: '西瓜', 55: '啤酒',
    56: '篮球', 57: '乒乓', 58: '咖啡', 59: '饭', 60: '猪头', 61: '玫瑰', 62: '凋谢',
    63: '嘴唇', 64: '爱心', 65: '心碎', 66: '蛋糕', 67: '闪电', 68: '炸弹', 69: '刀',
    70: '足球', 71: '瓢虫', 72: '便便', 73: '月亮', 74: '太阳', 75: '礼物', 76: '拥抱',
    77: '强', 78: '弱', 79: '握手', 80: '胜利', 81: '抱拳', 82: '勾引', 83: '拳头',
    84: '差劲', 85: '爱你', 86: 'NO', 87: 'OK', 88: '爱情', 89: '飞吻', 90: '跳跳',
    91: '发抖', 92: '怄火', 93: '转圈', 94: '磕头', 95: '回头', 96: '跳绳', 97: '挥手',
    98: '激动', 99: '街舞', 100: '献吻', 101: '左太极', 102: '右太极',
}


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def qq_face_name(data: dict) -> str:
    """返回 QQ 表情的可读名称（不含方括号），无法识别时返回空串。"""
    if not isinstance(data, dict):
        return ''
    raw = data.get('raw') or {}
    text = str(raw.get('faceText') or '').strip()
    if text:
        # NapCat 给的是 "/微笑" 这种带前缀的写法
        return text.lstrip('/').strip()
    face_id = _to_int(data.get('id'))
    if face_id is None:
        return ''
    return QQ_FACE_NAMES.get(face_id, '')


def format_qq_face(data: dict) -> str:
    """把一个 QQ `face` 消息段格式化为文本，例如 `[微笑]`。"""
    name = qq_face_name(data)
    return f'[{name}]' if name else '[表情]'


def tg_emoji_to_qq_emoji_id(emoji: str) -> str:
    """Telegram 的 emoji 字符 -> NapCat set_msg_emoji_like 的 emoji_id。

    NapCat 接受十进制 Unicode 码点字符串（实测 "128077" 即 👍 可用），
    因此取第一个字符的码点即可；多码点 emoji（如 ❤️ = U+2764 U+FE0F）取其基础字符。
    """
    if not emoji:
        return ''
    return str(ord(emoji[0]))


def qq_emoji_id_to_emoji(emoji_id) -> str:
    """QQ 的 emoji_id -> Unicode emoji 字符；无法反查（如 QQ 内置表情 id）时返回空串。"""
    raw = str(emoji_id if emoji_id is not None else '').strip()
    if not raw:
        return ''
    if not raw.isdigit():
        # 直接就是 emoji 字符
        return raw
    code = int(raw)
    # QQ 内置表情 id 都小于 1000（如 14=微笑），不能按码点解释
    if code < 1000:
        return ''
    try:
        return chr(code)
    except (ValueError, OverflowError):
        return ''


def tg_emoji_from_qq(item) -> str:
    """从 NapCat 的表情点赞条目里尽力取出 Unicode emoji。

    不同版本字段名不一致（emoji / reaction / emoji_id / id），这里逐个尝试。
    """
    if isinstance(item, str):
        return qq_emoji_id_to_emoji(item) or item
    if not isinstance(item, dict):
        return ''
    for key in ('emoji', 'reaction', 'emoji_id', 'id'):
        value = item.get(key)
        if value is None or value == '':
            continue
        emoji = qq_emoji_id_to_emoji(value)
        if emoji:
            return emoji
    return ''
