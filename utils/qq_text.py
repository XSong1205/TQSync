"""表情回应（消息表情点赞）相关的 ID/emoji 转换助手。

NapCat 的 `/set_msg_emoji_like` 用 `emoji_id` 表示表情：
- 十进制 Unicode 码点字符串（如 "128077" 表示 👍），实测可用；
- 或 QQ 内置表情 id（如 "14"）。

Telegram 侧的表情回应给的是 emoji 字符，因此这里负责双向转换。
"""

from __future__ import annotations


def tg_emoji_to_qq_emoji_id(emoji: str) -> str:
    """Telegram 的 emoji 字符 -> NapCat set_msg_emoji_like 的 emoji_id。

    取第一个字符的十进制码点；多码点 emoji（如 ❤️ = U+2764 U+FE0F）取其基础字符。
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
        return qq_emoji_id_to_emoji(item)
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
