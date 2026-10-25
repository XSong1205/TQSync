"""机器人提示消息的统一格式。

风格以 /help、/status 两条手写消息为基准：

- 多行消息：``| TQSync <Title>`` 标题行 + 26 个短横线分隔 + ``- 标签: 值`` 正文 + 结尾分隔线。
- 单行结果：直接一句中文结论（如「已添加屏蔽词：xxx」），不加前缀、不加 emoji。
- 标签与值之间统一用半角冒号 + 空格（``: ``），正文用中文标点（，。：！？）。
- 命令说明统一写成 ``/cmd - 说明``。
- 提示消息不使用 emoji；消息内容本身的 emoji（如用户表情回应）原样保留。

用法::

    from utils.message_style import block, bullet, command_line

    text = block("Status", [bullet("版本信息", "v1.4.0"), bullet("运行时长", "3 分 1 秒")])
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

# 与 /status 消息中使用的分隔线完全一致（26 个半角短横线）
SEP = "-" * 26


def header(title: str) -> str:
    """``| TQSync <Title>`` 标题行。"""
    return f"| TQSync {title}"


def bullet(label: str, value) -> str:
    """``- 标签: 值`` 正文行。"""
    return f"- {label}: {value}"


def command_line(command: str, description: str) -> str:
    """``/cmd - 说明`` 命令说明行。"""
    return f"{command} - {description}"


def block(
    title: str,
    body: Union[Sequence[str], str] = (),
    footer: Optional[Union[Sequence[str], str]] = None,
) -> str:
    """构造多行提示消息。

    Args:
        title: 标题（如 ``Status`` / ``Bind`` / ``Health``）。
        body: 正文行（字符串列表，或单个字符串）。
        footer: 可选，结尾分隔线之前的补充说明。

    Returns:
        形如::

            | TQSync Status
            --------------------------
            - 版本信息: v1.4.0
            --------------------------
    """
    lines = list(body) if not isinstance(body, str) else [body]
    parts = [header(title), SEP, *lines]
    if footer:
        parts.append("")
        parts.extend(list(footer) if not isinstance(footer, str) else [footer])
    parts.append(SEP)
    return "\n".join(parts)


def duration(seconds: float) -> str:
    """秒数 → 中文时长（运行时长、重启耗时等）。"""
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days} 天 {hours} 小时"
    if hours:
        return f"{hours} 小时 {minutes} 分"
    if minutes:
        return f"{minutes} 分 {secs} 秒"
    return f"{secs} 秒"


__all__ = ["SEP", "header", "bullet", "command_line", "block", "duration"]
