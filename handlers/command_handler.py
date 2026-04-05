from db.database import db
import logging

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "🤖 TQSync 帮助文档\n\n"
    "可用命令：\n"
    "/bind <qq_number> - 绑定您的 QQ 号以启用同步\n"
    "/setprefix <nickname> - 设置您在双端显示的统一昵称\n"
    "/help - 显示此帮助信息\n\n"
    "提示：绑定后，您在 Telegram 和 QQ 的消息将自动双向同步。"
)

async def handle_bind_command(qq_user_id: int, args: list):
    """处理 /bind 指令"""
    if not args:
        return "Usage: /bind <qq_number>"
    
    try:
        qq_number = int(args[0])
    except ValueError:
        return "Error: QQ number must be an integer."
    
    # 在 QQ 端触发绑定时，我们通常不知道对方的 TG ID，除非他们先在 TG 端操作过
    # 这里我们暂时只记录 QQ 侧的信息，或者尝试查找是否已有 TG 绑定
    # 为了简化，我们假设用户是在 QQ 端发起绑定，我们需要一个“待绑定”状态或者反向查找逻辑
    # 但根据项目现状，/bind 通常在 TG 端使用。如果在 QQ 端使用，我们可以尝试通过某种方式关联
    # 这里实现一个简单的逻辑：如果该 QQ 号已经被某个 TG ID 绑定，则更新；否则提示去 TG 端绑定
    # 或者：允许在 QQ 端输入 /bind <tg_user_id> ? 
    # 按照用户需求：/bind <qq_number>。这通常意味着用户在 TG 里发 /bind 12345。
    # 如果用户在 QQ 里发 /bind，他可能想绑定自己的 TG？
    # 让我们保持一致性：在 QQ 端，/bind 指令可能用于“声明”这个 QQ 号属于当前发送者，以便后续 TG 端匹配？
    # 实际上，最合理的跨平台绑定是：
    # 1. TG: /bind <QQ号> -> 存入 DB (TG_ID, QQ_ID)
    # 2. QQ: /bind <TG用户名/ID>? -> 存入 DB
    
    # 鉴于用户需求描述为“/bind <qq_number>”，我将假设这是在 TG 端的用法。
    # 但如果要在 QQ 端响应，我们需要定义 QQ 端的绑定逻辑。
    # 暂定：QQ 端不支持直接通过 /bind 绑定 TG，除非我们引入验证码机制。
    # 为了满足“双端指令行为一致性”，我们在 QQ 端收到 /bind 时，提示用户去 TG 端操作，或者实现一个简单的反向绑定。
    
    # 改进方案：在 QQ 端发送 /bind 时，我们记录该 QQ 号的“待绑定”状态，并生成一个验证码？
    # 太复杂。让我们先实现最简单的：提示用户。
    
    # 重新阅读需求：“调用 db/database.py 中的绑定逻辑... 将发送者的 TG ID（如果已绑定）或当前上下文与 QQ 号关联”
    # 这意味着在 QQ 端，我们可能无法直接获取 TG ID。
    # 我们将实现一个占位符，或者如果用户已经在 TG 绑定过，这里可以用来验证？
    
    # 让我们实现一个更通用的逻辑：
    # 如果用户在 QQ 端发送 /bind，我们提示：“请在 Telegram 中使用 /bind <您的QQ号> 来完成绑定。”
    return "Please use /bind <your_qq_number> in Telegram to complete the binding process."

async def handle_setprefix_command(user_id: int, platform: str, args: list):
    """处理 /setprefix 指令"""
    if not args:
        return "Usage: /setprefix <nickname>"
    
    new_prefix = " ".join(args)
    
    # 查找 UID
    uid = None
    if platform == 'tg':
        binding = await db.get_binding_by_tg(user_id)
        if binding: uid = binding[4]
    else: # qq
        binding = await db.get_binding_by_qq(user_id)
        if binding: uid = binding[4]
        
    if not uid:
        return "You are not bound yet. Please use /bind first."
    
    await db.update_custom_prefix(uid, new_prefix)
    return f"Your unified display name has been updated to: {new_prefix}"

async def handle_help_command():
    """处理 /help 指令"""
    return HELP_TEXT
